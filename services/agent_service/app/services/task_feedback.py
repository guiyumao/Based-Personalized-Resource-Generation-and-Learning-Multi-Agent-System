"""Task-level execution feedback, unified with the same proposal/confirm model.

This is the "计划执行反馈" half: the learner reacts to one task ("太难",
"太简单", "时间不足", "已经掌握", "希望更多练习" …) and the service produces a
deterministic, evidence-free-but-explicit revision proposal that reuses the exact
``PlanFeedbackService`` proposal/CAS/idempotency machinery.  No LLM is required,
so the flow is fully testable in the no-cost environment.

Deliberately kept deterministic: the feedback vocabulary is bounded, and the
service never infers mastery from a click.  "已经掌握" only proposes to mark the
task complete in the plan (with confirmation), it does not touch proficiency.
"""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.agent_service.app.services.plan_feedback import PlanFeedbackService

_FEEDBACK_TYPES = {
    "too_hard", "too_easy", "not_understood", "not_enough_time",
    "already_mastered", "more_practice", "more_video", "more_illustration",
}
_LABELS = {
    "too_hard": "太难", "too_easy": "太简单", "not_understood": "内容不理解",
    "not_enough_time": "时间不足", "already_mastered": "已经掌握",
    "more_practice": "希望更多练习", "more_video": "希望补充视频",
    "more_illustration": "希望补充图文",
}
_DIFFICULTY_DOWN = {"advanced": "intermediate", "intermediate": "foundation", "foundation": "foundation"}
_DIFFICULTY_UP = {"foundation": "intermediate", "intermediate": "advanced", "advanced": "advanced"}


def _find_task(payload: dict, task_id: str) -> tuple[int, int, dict, list] | None:
    """Return (stage_index, task_index, task, tasks_list) or None."""
    for stage_index, stage in enumerate(payload.get("stages", []) or []):
        tasks = stage.get("tasks") if isinstance(stage, dict) else None
        if not isinstance(tasks, list):
            continue
        for task_index, task in enumerate(tasks):
            if isinstance(task, dict) and str(task.get("task_id")) == task_id:
                return stage_index, task_index, task, tasks
    return None


def _new_task(task_type: str, title: str, knowledge_point: str, difficulty: str, minutes: int,
              objective: str, depends_on: list[str]) -> dict:
    return {"task_id": f"fb-{uuid4().hex[:8]}", "title": title, "task_type": task_type,
            "knowledge_point": knowledge_point, "objective": objective,
            "estimated_minutes": minutes, "difficulty": difficulty,
            "completed": False, "status": "pending", "depends_on": list(depends_on)}


class TaskFeedbackService:
    """Produce deterministic task-level revision proposals through the shared model."""

    def __init__(self, db: Session) -> None:
        self.feedback = PlanFeedbackService(db)

    def preview(self, user_id: int, task_id: str, feedback_type: str, note: str | None = None) -> dict:
        if feedback_type not in _FEEDBACK_TYPES:
            raise HTTPException(status_code=422, detail=f"不支持的反馈类型：{feedback_type}")
        record = self.feedback._record(user_id)
        current = deepcopy(record.path_data_json or {})
        revised = self._revise_deterministic(current, task_id, feedback_type, (note or "").strip())
        label = _LABELS[feedback_type] + (f"（{note}）" if note and note.strip() else "")
        return self.feedback._persist_proposal(record, current, label, revised)

    def confirm(self, user_id: int, proposal_id: str) -> dict:
        return self.feedback.confirm(user_id, proposal_id)

    def _revise_deterministic(self, current: dict, task_id: str, feedback_type: str, note: str) -> dict:
        located = _find_task(current, task_id)
        if located is None:
            raise HTTPException(status_code=404, detail="任务不存在或不属于当前计划。")
        stage_index, task_index, task, tasks = located
        revised = deepcopy(current)
        _, _, target, target_tasks = _find_task(revised, task_id)  # same indices on the copy
        knowledge_point = str(target.get("knowledge_point") or revised.get("knowledge_point") or "")

        if feedback_type == "too_hard":
            old_difficulty = target.get("difficulty")
            new_difficulty = _DIFFICULTY_DOWN.get(old_difficulty, "foundation")
            if new_difficulty != old_difficulty:
                target["difficulty"] = new_difficulty
            else:
                # Already at the easiest level: add foundational support instead.
                pre = _new_task("review", f"基础预备：{knowledge_point}", knowledge_point, "foundation",
                                20, f"为「{target.get('title')}」补充前置基础。", [])
                target_tasks.insert(task_index, pre)
                target["depends_on"] = list(dict.fromkeys([pre["task_id"], *target.get("depends_on", [])]))
        elif feedback_type == "too_easy":
            target["difficulty"] = _DIFFICULTY_UP.get(target.get("difficulty"), "advanced")
        elif feedback_type == "not_understood":
            explain = _new_task("courseware", f"基础讲解：{knowledge_point}", knowledge_point, "foundation",
                                25, f"用更浅显的方式解释「{target.get('title')}」。", [])
            target_tasks.insert(task_index, explain)
            target["depends_on"] = list(dict.fromkeys([explain["task_id"], *target.get("depends_on", [])]))
        elif feedback_type == "not_enough_time":
            target["estimated_minutes"] = max(10, int(target.get("estimated_minutes", 30) or 30) // 2)
            revised["estimated_days"] = int(revised.get("estimated_days", 1) or 1) + 1
        elif feedback_type == "already_mastered":
            target["completed"] = True
            target["status"] = "completed"
        elif feedback_type == "more_practice":
            practice = _new_task("exercise", f"巩固练习：{knowledge_point}", knowledge_point,
                                 target.get("difficulty", "foundation"), 30,
                                 f"针对「{target.get('title')}」的补充练习。", [task_id])
            target_tasks.insert(task_index + 1, practice)
        elif feedback_type == "more_video":
            video = _new_task("courseware", f"视频讲解：{knowledge_point}", knowledge_point,
                              target.get("difficulty", "foundation"), 25,
                              f"为「{target.get('title')}」补充视频讲解资源。", [task_id])
            target_tasks.insert(task_index + 1, video)
        elif feedback_type == "more_illustration":
            illustration = _new_task("graph", f"图文讲解：{knowledge_point}", knowledge_point,
                                     target.get("difficulty", "foundation"), 20,
                                     f"为「{target.get('title')}」补充图文/图解说明。", [task_id])
            target_tasks.insert(task_index + 1, illustration)
        return revised
