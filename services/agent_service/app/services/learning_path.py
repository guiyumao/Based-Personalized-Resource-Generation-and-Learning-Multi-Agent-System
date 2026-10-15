"""Learning path planning service for the student workspace."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from common.ai_errors import AIServiceError
from common.config import get_settings
from common.models.learning import LearningPath
from common.performance import traced_invoke
from common.schemas.agent import LearningPathAdjustRequest, LearningPathRequest
from services.agent_service.app.services.llm_factory import LLMFactory

logger = logging.getLogger(__name__)


class LearningPathService:
    """Build an actionable personalized learning path through the configured LLM."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def generate_path(self, request: LearningPathRequest) -> dict[str, object]:
        """Create a staged learning path around one knowledge point."""

        teacher_scope = self._extract_teacher_scope(request.learner_profile)
        payload = self._generate_path_with_llm(request, teacher_scope)
        payload["generation_source"] = "llm"
        return self._persist_generated_path(request.user_id, payload) if self.db is not None else payload

    def _generate_path_with_llm(
        self,
        request: LearningPathRequest,
        teacher_scope: dict[str, object] | None,
    ) -> dict[str, object]:
        """Ask the configured LLM to personalize the path while preserving API shape."""

        try:
            settings = get_settings()
            llm = LLMFactory(settings).build_chat_model(temperature=0.25)
            prompt = self._build_llm_prompt(request, teacher_scope)
            result = traced_invoke(llm, prompt, stage="generation")
            content = self._coerce_llm_text(getattr(result, "content", result))
            payload = self._parse_llm_json(content)
            return self._normalize_llm_path(request, payload, teacher_scope)
        except AIServiceError:
            raise
        except Exception as exc:
            logger.warning("LLM learning path generation failed: %s", exc)
            raise RuntimeError("LLM learning path generation failed") from exc

    def _build_llm_prompt(
        self,
        request: LearningPathRequest,
        teacher_scope: dict[str, object] | None,
    ) -> list[tuple[str, str]]:
        profile = {
            "daily_minutes": request.daily_minutes,
            "learner_profile": request.learner_profile,
            "teacher_scope": teacher_scope,
        }
        system = (
            "You are a personalized learning-path planning agent. "
            "Return strict JSON only, with no Markdown fences. "
            "The JSON object must include user_id, subject, knowledge_point, overview, "
            "estimated_days, and stages. "
            "Each stage must include stage_id, title, description, and tasks. "
            "Each task must include task_id, title, task_type, knowledge_point, objective, "
            "estimated_minutes, difficulty, completed, and status. "
            "Allowed task_type values: courseware, exercise, review, graph. "
            "Allowed difficulty values: foundation, intermediate, advanced. "
            "Use status=pending for new tasks."
        )
        user = (
            "Create a natural, personalized learning path from the learner profile and teacher scope.\n"
            f"Knowledge point: {request.knowledge_point}\n"
            f"Subject: {request.subject}\n"
            f"Profile and constraints: {json.dumps(profile, ensure_ascii=False, default=str)}"
        )
        return [("system", system), ("user", user)]

    def _parse_llm_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM did not return a JSON object")
        parsed = json.loads(text[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("LLM JSON payload must be an object")
        return parsed

    def _normalize_llm_path(
        self,
        request: LearningPathRequest,
        payload: dict[str, Any],
        teacher_scope: dict[str, object] | None,
    ) -> dict[str, object]:
        normalized: dict[str, object] = {
            "user_id": request.user_id,
            "subject": str(payload.get("subject") or request.subject),
            "knowledge_point": str(payload.get("knowledge_point") or request.knowledge_point),
            "overview": self._required_text(payload, "overview"),
            "estimated_days": self._required_int(payload, "estimated_days"),
            "stages": [],
            "teacher_scope": teacher_scope,
        }

        stages = payload.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValueError("LLM learning path must include at least one stage")

        normalized_stages: list[dict[str, object]] = []
        for stage_index, stage in enumerate(stages[:4], start=1):
            if not isinstance(stage, dict):
                raise ValueError("Each learning stage must be an object")
            normalized_tasks = self._normalize_llm_tasks(stage.get("tasks"), normalized["knowledge_point"])
            if not normalized_tasks:
                raise ValueError("Each learning stage must include at least one task")
            normalized_stages.append(
                {
                    "stage_id": str(stage.get("stage_id") or f"stage-{stage_index}"),
                    "title": self._required_text(stage, "title"),
                    "description": str(stage.get("description") or ""),
                    "tasks": normalized_tasks,
                }
            )

        normalized["stages"] = normalized_stages
        return self._normalize_payload(normalized)

    def _normalize_llm_tasks(self, tasks: Any, knowledge_point: object) -> list[dict[str, object]]:
        allowed_types = {"courseware", "exercise", "review", "graph"}
        allowed_difficulties = {"foundation", "intermediate", "advanced"}
        normalized: list[dict[str, object]] = []
        if not isinstance(tasks, list):
            raise ValueError("Learning stage tasks must be a list")

        for task_index, task in enumerate(tasks[:5], start=1):
            if not isinstance(task, dict):
                raise ValueError("Each learning task must be an object")
            task_type = str(task.get("task_type") or "")
            difficulty = str(task.get("difficulty") or "")
            if task_type not in allowed_types:
                raise ValueError(f"Invalid learning task type: {task_type}")
            if difficulty not in allowed_difficulties:
                raise ValueError(f"Invalid learning task difficulty: {difficulty}")

            raw_status = task.get("status")
            normalized.append(
                {
                    "task_id": str(task.get("task_id") or f"task-{task_index}"),
                    "title": self._required_text(task, "title"),
                    "task_type": task_type,
                    "knowledge_point": str(task.get("knowledge_point") or knowledge_point),
                    "objective": self._required_text(task, "objective"),
                    "estimated_minutes": self._required_int(task, "estimated_minutes"),
                    "difficulty": difficulty,
                    "completed": bool(task.get("completed", False)),
                    "status": str(raw_status) if raw_status in {"completed", "skipped"} else "pending",
                }
            )
        return normalized

    def _required_text(self, payload: dict[str, Any], key: str) -> str:
        value = str(payload.get(key) or "").strip()
        if not value:
            raise ValueError(f"LLM learning path missing required text field: {key}")
        return value

    def _required_int(self, payload: dict[str, Any], key: str) -> int:
        try:
            value = int(payload.get(key))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"LLM learning path missing required integer field: {key}") from exc
        if value <= 0:
            raise ValueError(f"LLM learning path integer field must be positive: {key}")
        return value

    def _coerce_llm_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
        return str(content)

    def get_latest_path(self, user_id: int) -> dict[str, object] | None:
        """Return the latest active path for a learner if one exists."""

        if self.db is None:
            return None
        record = self._get_active_path_record(user_id)
        if record is None:
            return None
        return self._normalize_payload(record.path_data_json or {})

    def adjust_path(self, request: LearningPathAdjustRequest) -> dict[str, object] | None:
        """Adjust one task state inside the latest active path."""

        if self.db is None:
            return None

        record = self._get_active_path_record(request.user_id)
        if record is None:
            return None

        payload = self._normalize_payload(record.path_data_json or {})
        found = False
        stages = payload.get("stages", [])
        if not isinstance(stages, list):
            return None

        for stage in stages:
            tasks = stage.get("tasks", [])
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if task.get("task_id") != request.task_id:
                    continue
                found = True
                if request.action == "complete":
                    task["completed"] = True
                    task["status"] = "completed"
                elif request.action == "reset":
                    task["completed"] = False
                    task["status"] = "pending"
                else:
                    task["completed"] = False
                    task["status"] = "skipped"
                break

        if not found:
            return None

        record.path_data_json = payload
        self.db.commit()
        self.db.refresh(record)
        return self._normalize_payload(record.path_data_json or {})

    def _persist_generated_path(self, user_id: int, payload: dict[str, object]) -> dict[str, object]:
        existing_records = (
            self.db.query(LearningPath)
            .filter(LearningPath.user_id == user_id, LearningPath.status == "active")
            .all()
        )
        for item in existing_records:
            item.status = "archived"

        record = LearningPath(
            user_id=user_id,
            path_data_json=deepcopy(payload),
            status="active",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._normalize_payload(record.path_data_json or {})

    def _get_active_path_record(self, user_id: int) -> LearningPath | None:
        return (
            self.db.query(LearningPath)
            .filter(LearningPath.user_id == user_id, LearningPath.status == "active")
            .order_by(LearningPath.id.desc())
            .first()
        )

    def _normalize_payload(self, payload: dict[str, object]) -> dict[str, object]:
        data = deepcopy(payload)
        stages = data.get("stages", [])
        if not isinstance(stages, list):
            return data
        for stage in stages:
            tasks = stage.get("tasks", [])
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                task.setdefault("completed", False)
                task.setdefault("status", "completed" if task.get("completed") else "pending")
        return data

    def _extract_teacher_scope(self, learner_profile: dict[str, object]) -> dict[str, object] | None:
        raw_scope = learner_profile.get("teacher_scope")
        if isinstance(raw_scope, dict):
            return deepcopy(raw_scope)
        if not learner_profile.get("teacher_scope_id"):
            return None
        return {
            "id": learner_profile.get("teacher_scope_id"),
            "knowledge_points": learner_profile.get("teacher_knowledge_points", []),
            "learning_direction": learner_profile.get("teacher_learning_direction", ""),
            "teaching_goal": learner_profile.get("teacher_teaching_goal", ""),
            "courseware_title": learner_profile.get("teacher_courseware_title", ""),
            "courseware_content": learner_profile.get("teacher_courseware_content", ""),
        }
