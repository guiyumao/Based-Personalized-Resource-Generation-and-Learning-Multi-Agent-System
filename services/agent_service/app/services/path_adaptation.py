"""Evidence-based plan changes, persisted as proposals before learner confirmation."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from common.learning_evidence import EVIDENCE_VERSION, load_evidence, resolve_point, summarize
from services.agent_service.app.services.learning_path import LearningPathService


class PathAdaptationService:
    def __init__(self, db: Session):
        self.db = db
        self.paths = LearningPathService(db)

    def _record(self, user_id: int):
        record = self.paths._get_active_path_record(user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="当前没有可调整的学习计划。")
        return record

    def preview(self, user_id: int, daily_minutes: int | None = None) -> dict:
        record = self._record(user_id)
        payload = deepcopy(record.path_data_json or {})
        tasks = self.paths._ordered_tasks(payload)
        topics = {str(task.get("knowledge_point", "")).strip() for task in tasks}
        topics.discard("")
        now = datetime.now(UTC).replace(tzinfo=None)
        cutoff = now - timedelta(days=30)
        # Use the same confirmed memberships and unique-question policy as the
        # visible profile, including the selected plan's subject boundary.
        pending_remedial = {task.get("knowledge_point") for task in tasks
                            if task.get("adaptation_source") and not task.get("completed")}
        weak = []
        for topic in topics:
            point = resolve_point(self.db, topic, subject=str(payload.get("subject") or ""))
            if point is None or topic in pending_remedial:
                continue
            evidence = [row for row in load_evidence(self.db, user_id, point=point)
                        if cutoff <= datetime.fromisoformat(row["submitted_at"]).replace(tzinfo=None) <= now]
            stats = summarize(evidence)
            if stats["mastery_score"] is not None and stats["mastery_score"] < 60:
                weak.append({"name": topic, "knowledge_point_id": point.id, "subject_id": point.subject_id,
                    "graded_answers": stats["sample_size"], "accuracy_percent": stats["correct_rate"],
                    "evidence_ids": stats["evidence_ids"], "evidence_version": EVIDENCE_VERSION})
        weak.sort(key=lambda row: (row["accuracy_percent"], -row["graded_answers"], row["name"]))
        weak = weak[:3]
        old_minutes = payload.get("daily_minutes")
        time_changed = daily_minutes is not None and daily_minutes != old_minutes
        if not weak and not time_changed:
            return {"status": "no_change", "message": "当前没有足够的薄弱项证据或新的时间约束，保留原计划。", "evidence": []}
        proposal_id = str(uuid4())
        new_tasks = [{"task_id": f"adapt-{proposal_id[:8]}-{index}", "title": f"补强练习：{item['name']}",
                      "task_type": "exercise", "knowledge_point": item["name"],
                      "objective": f"复习后重新作答；近30天{item['graded_answers']}次判分正确率{item['accuracy_percent']}%。",
                      "estimated_minutes": min(daily_minutes or 20, 20), "difficulty": "foundation", "completed": False,
                      "status": "pending", "depends_on": [], "adaptation_source": proposal_id} for index, item in enumerate(weak)]
        remaining = sum(max(0, int(task.get("estimated_minutes") or 0)) for task in tasks if not task.get("completed"))
        remaining += sum(task["estimated_minutes"] for task in new_tasks)
        proposal = {"evidence_version": EVIDENCE_VERSION, "proposal_id": proposal_id, "path_id": record.id,
                    "base_revision": int(payload.get("path_revision", 0)) + 1,
                    "created_at": datetime.now(UTC).isoformat(), "evidence": weak, "added_tasks": new_tasks,
                    "before": {"daily_minutes": old_minutes, "estimated_days": payload.get("estimated_days"), "task_count": len(tasks)},
                    "after": {"daily_minutes": daily_minutes if daily_minutes is not None else old_minutes,
                              "estimated_days": max(1, ceil(remaining / daily_minutes)) if daily_minutes else payload.get("estimated_days"),
                              "task_count": len(tasks) + len(new_tasks)},
                    "message": "补强任务追加到后续目录；已有任务和完成记录保留。仅确认后生效。"}
        payload["adjustment_proposal"] = proposal
        self.paths.commit_path_update(record, payload)
        return {"status": "proposed", **proposal}

    def confirm(self, user_id: int, proposal_id: str) -> dict:
        record = self._record(user_id)
        payload = deepcopy(record.path_data_json or {})
        history = payload.get("applied_adjustments", [])
        if proposal_id in history:
            return {"status": "already_applied", "path": self.paths._normalize_payload(payload)}
        proposal = payload.get("adjustment_proposal")
        if not isinstance(proposal, dict) or proposal.get("proposal_id") != proposal_id:
            raise HTTPException(status_code=404, detail="调整提案不存在或已被替换。")
        if proposal.get("evidence_version") != EVIDENCE_VERSION:
            raise HTTPException(status_code=409, detail="学情证据规则已更新，请重新预览调整。")
        if int(payload.get("path_revision", 0)) != proposal["base_revision"]:
            raise HTTPException(status_code=409, detail="计划已变化，请重新预览调整。")
        if proposal["added_tasks"]:
            payload.setdefault("stages", []).append({"stage_id": f"adaptation-{proposal_id}", "title": "学情补强",
                                                     "description": "依据近30天作答证据，经本人确认新增。", "tasks": proposal["added_tasks"]})
        payload.update({key: value for key, value in proposal["after"].items() if key in {"daily_minutes", "estimated_days"} and value is not None})
        payload["applied_adjustments"] = [*history[-19:], proposal_id]
        payload.pop("adjustment_proposal", None)
        self.paths.commit_path_update(record, payload)
        return {"status": "applied", "path": self.paths._normalize_payload(record.path_data_json or {})}
