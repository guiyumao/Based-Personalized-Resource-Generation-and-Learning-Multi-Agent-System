"""Natural-language feedback on a learning-path draft, persisted as a proposal.

This is the "计划制定反馈" half of the interactive planning loop.  It mirrors the
evidence-driven ``PathAdaptationService`` contract — preview produces a persisted
proposal with a diff, confirm applies it under the same JSON revision / CAS /
idempotency rules — but the trigger is arbitrary learner language ("太难了",
"先学链表", "压缩到四周", "改成中文") instead of answer-accuracy evidence.

The revised plan is produced by the configured LLM.  With no credentials the
service raises a clear ``blocked``-style error rather than pretending to adjust
the plan, so a "已收到反馈" no-op is never presented as a real revision.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from common.models.learning import LearningPath
from services.agent_service.app.services.learning_path import LearningPathService

logger = logging.getLogger(__name__)

_ALLOWED_TASK_TYPES = {"courseware", "exercise", "review", "graph"}
_ALLOWED_DIFFICULTIES = {"foundation", "intermediate", "advanced"}


def _ordered_tasks(payload: dict) -> list[dict]:
    """Flatten a payload into an ordered task list, each tagged with its stage title."""
    ordered: list[dict] = []
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        for task in stage.get("tasks", []) or []:
            if isinstance(task, dict):
                item = deepcopy(task)
                item["_stage"] = str(stage.get("title") or "")
                ordered.append(item)
    return ordered


def _index_tasks(payload: dict) -> dict[str, dict]:
    return {str(task.get("task_id")): task for task in _ordered_tasks(payload) if task.get("task_id")}


def compute_plan_diff(before: dict, after: dict) -> dict:
    """Diff two normalized path payloads into a reviewable change summary.

    Pure function with no side effects, so the proposal diff is testable without
    any LLM call and the browser can render it before confirmation.
    """

    before_tasks = _index_tasks(before)
    after_tasks = _index_tasks(after)
    before_ids = set(before_tasks)
    after_ids = set(after_tasks)

    added = [
        {"task_id": tid, "title": t.get("title", ""), "stage": t.get("_stage", "")}
        for tid, t in after_tasks.items() if tid not in before_ids
    ]
    removed = [
        {"task_id": tid, "title": t.get("title", ""), "stage": t.get("_stage", "")}
        for tid, t in before_tasks.items() if tid not in after_ids
    ]
    kept = sorted(before_ids & after_ids)

    duration_changes = [
        {"task_id": tid, "title": after_tasks[tid].get("title", ""),
         "before": before_tasks[tid].get("estimated_minutes"),
         "after": after_tasks[tid].get("estimated_minutes")}
        for tid in kept
        if before_tasks[tid].get("estimated_minutes") != after_tasks[tid].get("estimated_minutes")
    ]
    difficulty_changes = [
        {"task_id": tid, "title": after_tasks[tid].get("title", ""),
         "before": before_tasks[tid].get("difficulty"),
         "after": after_tasks[tid].get("difficulty")}
        for tid in kept
        if before_tasks[tid].get("difficulty") != after_tasks[tid].get("difficulty")
    ]
    status_changes = [
        {"task_id": tid, "title": after_tasks[tid].get("title", ""),
         "before": {"completed": before_tasks[tid].get("completed"), "status": before_tasks[tid].get("status")},
         "after": {"completed": after_tasks[tid].get("completed"), "status": after_tasks[tid].get("status")}}
        for tid in kept
        if before_tasks[tid].get("completed") != after_tasks[tid].get("completed")
        or before_tasks[tid].get("status") != after_tasks[tid].get("status")
    ]

    before_order = [str(t.get("task_id")) for t in _ordered_tasks(before) if t.get("task_id")]
    after_order = [str(t.get("task_id")) for t in _ordered_tasks(after) if t.get("task_id")]
    reordered = [tid for tid in kept if before_order.index(tid) != after_order.index(tid)]

    stage_changes = _diff_stages(before, after)

    return {
        "added_tasks": added,
        "removed_tasks": removed,
        "kept_task_ids": kept,
        "reordered_task_ids": reordered,
        "duration_changes": duration_changes,
        "difficulty_changes": difficulty_changes,
        "status_changes": status_changes,
        "stage_changes": stage_changes,
        "overview_changed": (before.get("overview") or "") != (after.get("overview") or ""),
        "impact": {
            "total_tasks_before": len(before_ids),
            "total_tasks_after": len(after_ids),
            "estimated_days_before": before.get("estimated_days"),
            "estimated_days_after": after.get("estimated_days"),
            "daily_minutes_before": before.get("daily_minutes"),
            "daily_minutes_after": after.get("daily_minutes"),
        },
    }


def _diff_stages(before: dict, after: dict) -> list[dict]:
    before_stages = [str(s.get("stage_id")) for s in before.get("stages", []) if isinstance(s, dict)]
    after_stages = [str(s.get("stage_id")) for s in after.get("stages", []) if isinstance(s, dict)]
    changes: list[dict] = []
    for stage_id in before_stages:
        if stage_id not in after_stages:
            changes.append({"stage_id": stage_id, "change": "removed"})
    for stage_id in after_stages:
        if stage_id not in before_stages:
            changes.append({"stage_id": stage_id, "change": "added"})
    if before_stages != after_stages:
        changes.append({"change": "reordered", "before": before_stages, "after": after_stages})
    return changes


class PlanFeedbackService:
    """Persist and apply learner feedback revisions to an active learning path."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.paths = LearningPathService(db)

    def _record(self, user_id: int) -> LearningPath:
        record = self.paths._get_active_path_record(user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="当前没有可反馈的学习计划，请先生成计划。")
        return record

    def preview(self, user_id: int, feedback_text: str) -> dict:
        """Produce a persisted revision proposal and its diff; nothing is applied yet."""
        feedback_text = (feedback_text or "").strip()
        if not feedback_text:
            raise HTTPException(status_code=422, detail="反馈意见不能为空。")
        record = self._record(user_id)
        current = deepcopy(record.path_data_json or {})
        current.pop("feedback_proposal", None)
        revised = self._revise_with_llm(current, feedback_text)
        return self._persist_proposal(record, current, feedback_text, revised)

    def _persist_proposal(self, record: LearningPath, current: dict, feedback_text: str, revised: dict) -> dict:
        """Shared preview tail: normalize, diff, and persist a proposal without applying it."""
        revised = self.paths._normalize_payload(deepcopy(revised))
        revised.pop("feedback_proposal", None)

        diff = compute_plan_diff(current, revised)
        if not any([diff["added_tasks"], diff["removed_tasks"], diff["reordered_task_ids"],
                    diff["duration_changes"], diff["difficulty_changes"], diff["status_changes"],
                    diff["stage_changes"], diff["overview_changed"],
                    diff["impact"]["daily_minutes_before"] != diff["impact"]["daily_minutes_after"],
                    diff["impact"]["estimated_days_before"] != diff["impact"]["estimated_days_after"]]):
            return {"status": "no_change", "message": "根据反馈重新生成后计划内容未变化，请换一种表述再试。", "diff": diff}

        proposal = {
            "proposal_id": str(uuid4()),
            "path_id": record.id,
            "base_revision": int(current.get("path_revision", 0)) + 1,
            "created_at": datetime.now(UTC).isoformat(),
            "feedback_text": feedback_text,
            "after_payload": revised,
            "diff": diff,
            "message": "已生成修改方案，仅在你确认后生效；已完成任务与成绩会保留。",
        }
        payload = deepcopy(current)
        payload["feedback_proposal"] = proposal
        self.paths.commit_path_update(record, payload)
        return {"status": "proposed", **proposal}

    def confirm(self, user_id: int, proposal_id: str) -> dict:
        """Apply a previewed revision under revision CAS and idempotency rules."""
        record = self._record(user_id)
        payload = deepcopy(record.path_data_json or {})
        history = payload.get("applied_feedback", [])
        if proposal_id in history:
            return {"status": "already_applied", "path": self.paths._normalize_payload(payload)}
        proposal = payload.get("feedback_proposal")
        if not isinstance(proposal, dict) or proposal.get("proposal_id") != proposal_id:
            raise HTTPException(status_code=404, detail="反馈提案不存在或已被替换。")
        if int(payload.get("path_revision", 0)) != proposal["base_revision"]:
            raise HTTPException(status_code=409, detail="计划已变化，请重新预览修改。")
        after_payload = deepcopy(proposal.get("after_payload") or {})
        if not after_payload:
            raise HTTPException(status_code=409, detail="反馈提案缺少可应用的修改内容。")
        # Never let a revision erase a completed task's tracking.
        after_payload = self._preserve_completed(current=payload, revised=after_payload)
        after_payload["applied_feedback"] = [*history[-19:], proposal_id]
        after_payload.pop("feedback_proposal", None)
        self.paths.commit_path_update(record, after_payload)
        return {"status": "applied", "path": self.paths._normalize_payload(record.path_data_json or {})}

    @staticmethod
    def _preserve_completed(current: dict, revised: dict) -> dict:
        """Carry completed/status flags for surviving tasks and record removed ones."""
        before_tasks = _index_tasks(current)
        after = deepcopy(revised)
        removed_completed: list[dict] = []
        kept_completed_ids: list[str] = []
        after_ids: set[str] = set()
        for stage in after.get("stages", []) or []:
            for task in stage.get("tasks", []) or []:
                tid = str(task.get("task_id") or "")
                if not tid:
                    continue
                after_ids.add(tid)
                if before_tasks.get(tid, {}).get("completed"):
                    task["completed"] = True
                    task["status"] = "completed"
                    kept_completed_ids.append(tid)
        for tid, task in before_tasks.items():
            if task.get("completed") and tid not in after_ids:
                removed_completed.append({"task_id": tid, "title": task.get("title", "")})
        if removed_completed:
            previous = after.get("removed_completed_history") or []
            after["removed_completed_history"] = [*previous, {
                "at": datetime.now(UTC).isoformat(),
                "tasks": removed_completed,
            }]
        return after

    def _revise_with_llm(self, current: dict, feedback_text: str) -> dict:
        """Ask the configured LLM to revise the plan; raises when unavailable."""
        from common.config import get_settings
        from common.performance import traced_invoke
        from services.agent_service.app.services.llm_factory import LLMFactory

        settings = get_settings()
        try:
            llm = LLMFactory(settings).build_chat_model(temperature=0.25)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail="尚未配置模型凭据，无法处理计划反馈。") from exc
        prompt = self._build_revision_prompt(current, feedback_text)
        result = traced_invoke(llm, prompt, stage="plan_feedback_revision")
        content = getattr(result, "content", result)
        if isinstance(content, list):
            content = "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
        revised = self._parse_json(str(content))
        return self._normalize_revised(current, revised)

    def _build_revision_prompt(self, current: dict, feedback_text: str) -> list[tuple[str, str]]:
        current_summary = json.dumps({
            "subject": current.get("subject"),
            "knowledge_point": current.get("knowledge_point"),
            "daily_minutes": current.get("daily_minutes"),
            "estimated_days": current.get("estimated_days"),
            "overview": current.get("overview"),
            "stages": current.get("stages"),
        }, ensure_ascii=False)
        system = (
            "You are a personalized learning-path planning agent. Given the current plan and "
            "the learner's feedback, return a revised plan as strict JSON only (no Markdown). "
            "Keep the same top-level shape: user_id, subject, knowledge_point, overview, "
            "estimated_days, daily_minutes, and stages. Each stage has stage_id, title, "
            "description, tasks; each task has task_id, title, task_type, knowledge_point, "
            "objective, estimated_minutes, difficulty, completed, status, depends_on. "
            f"Allowed task_type: {sorted(_ALLOWED_TASK_TYPES)}. "
            f"Allowed difficulty: {sorted(_ALLOWED_DIFFICULTIES)}. "
            "Preserve task_id for tasks you keep so completion history is not lost. "
            "Answer in the same language as the learner's feedback. "
            "Only change what the feedback asks for; do not invent unrelated changes."
        )
        user = (
            "Current plan (JSON):\n"
            f"{current_summary}\n\n"
            f"Learner feedback: {feedback_text}"
        )
        return [("system", system), ("user", user)]

    @staticmethod
    def _parse_json(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HTTPException(status_code=503, detail="模型未返回可解析的计划修改。")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=503, detail="模型未返回可解析的计划修改。")
        return parsed

    @staticmethod
    def _normalize_revised(current: dict, revised: dict) -> dict:
        """Coerce the LLM revision into the canonical path payload shape."""
        result: dict = {
            "user_id": current.get("user_id"),
            "daily_minutes": int(revised.get("daily_minutes") or current.get("daily_minutes") or 45),
            "subject": str(revised.get("subject") or current.get("subject") or ""),
            "knowledge_point": str(revised.get("knowledge_point") or current.get("knowledge_point") or ""),
            "overview": str(revised.get("overview") or current.get("overview") or ""),
            "estimated_days": int(revised.get("estimated_days") or current.get("estimated_days") or 1),
            "stages": [],
            "generation_source": current.get("generation_source", "llm"),
        }
        # Preserve metadata the LLM must not be allowed to drop.
        for key in ("subject_id", "knowledge_versions", "source_transcript_analysis_id",
                    "assistant_task_id", "teacher_scope", "applied_adjustments",
                    "removed_completed_history", "applied_feedback"):
            if key in current:
                result[key] = deepcopy(current[key])
        stages = revised.get("stages")
        if not isinstance(stages, list) or not stages:
            raise HTTPException(status_code=503, detail="模型返回的修改缺少学习阶段。")
        for stage_index, stage in enumerate(stages[:6], start=1):
            if not isinstance(stage, dict):
                continue
            tasks = stage.get("tasks")
            if not isinstance(tasks, list):
                continue
            normalized_tasks: list[dict] = []
            for task_index, task in enumerate(tasks[:8], start=1):
                if not isinstance(task, dict):
                    continue
                task_type = str(task.get("task_type") or "courseware")
                difficulty = str(task.get("difficulty") or "foundation")
                if task_type not in _ALLOWED_TASK_TYPES:
                    task_type = "courseware"
                if difficulty not in _ALLOWED_DIFFICULTIES:
                    difficulty = "foundation"
                raw_status = task.get("status")
                status = str(raw_status) if raw_status in {"completed", "skipped"} else "pending"
                normalized_tasks.append({
                    "task_id": str(task.get("task_id") or f"task-{task_index}"),
                    "title": str(task.get("title") or f"学习任务 {task_index}"),
                    "task_type": task_type,
                    "knowledge_point": str(task.get("knowledge_point") or result["knowledge_point"]),
                    "objective": str(task.get("objective") or ""),
                    "estimated_minutes": int(task.get("estimated_minutes") or 30),
                    "difficulty": difficulty,
                    "completed": bool(task.get("completed", False)),
                    "status": status,
                    "depends_on": list(task.get("depends_on") or []),
                })
            if normalized_tasks:
                result["stages"].append({
                    "stage_id": str(stage.get("stage_id") or f"stage-{stage_index}"),
                    "title": str(stage.get("title") or f"阶段 {stage_index}"),
                    "description": str(stage.get("description") or ""),
                    "tasks": normalized_tasks,
                })
        if not result["stages"]:
            raise HTTPException(status_code=503, detail="模型返回的修改不包含可用的学习任务。")
        return result
