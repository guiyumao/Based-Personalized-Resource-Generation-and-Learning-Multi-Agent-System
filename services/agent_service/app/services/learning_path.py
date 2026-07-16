"""Learning path planning service for the student workspace."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from common.config import get_settings
from common.models.learning import LearningPath
from common.schemas.agent import LearningPathAdjustRequest, LearningPathRequest
from services.agent_service.app.services.llm_factory import LLMFactory


logger = logging.getLogger(__name__)


class LearningPathService:
    """Build a lightweight but actionable personalized learning path."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def generate_path(self, request: LearningPathRequest) -> dict[str, object]:
        """Create a staged learning path around one knowledge point."""

        teacher_scope = self._extract_teacher_scope(request.learner_profile)
        payload = self._build_rule_based_path(request, teacher_scope)
        llm_payload = self._generate_path_with_llm(request, payload, teacher_scope)
        if llm_payload is not None:
            payload = llm_payload
            payload.setdefault("generation_source", "llm")
        else:
            payload.setdefault("generation_source", "rule_fallback")

        return self._persist_generated_path(request.user_id, payload) if self.db is not None else payload

    def _build_rule_based_path(
        self,
        request: LearningPathRequest,
        teacher_scope: dict[str, object] | None,
    ) -> dict[str, object]:
        """Build the deterministic path used as an LLM schema/template fallback."""

        daily_minutes = request.daily_minutes
        estimated_days = 3 if daily_minutes >= 45 else 4
        style = str(request.learner_profile.get("learning_style", "visual"))

        # Only inject profile summary if the topic matches known weak areas
        kp = request.knowledge_point.lower()
        weak_areas = request.learner_profile.get("weak_question_types", [])
        topic_matches_profile = any(
            area.lower() in kp or kp in area.lower() for area in (weak_areas if isinstance(weak_areas, list) else [])
        )

        overview = (
            f"围绕 {request.knowledge_point} 设计的 {estimated_days} 天学习路径，"
            f"先理解概念，再完成练习与复盘。"
        )
        if topic_matches_profile:
            overview += f" 优先采用 {style} 风格资源。{self._build_profile_summary(request.learner_profile)}"
        else:
            overview += f" 学生正在探索全新领域，请从基础入门角度规划路径。"

        payload = {
            "user_id": request.user_id,
            "subject": request.subject,
            "knowledge_point": request.knowledge_point,
            "overview": overview,
            "estimated_days": estimated_days,
            "stages": [
                {
                    "stage_id": "stage-1",
                    "title": "阶段一：概念建构",
                    "description": "先掌握知识点定义、适用场景和常见误区。",
                    "tasks": [
                        {
                            "task_id": "task-1",
                            "title": f"学习 {request.knowledge_point} 核心概念",
                            "task_type": "courseware",
                            "knowledge_point": request.knowledge_point,
                            "objective": "理解基本定义、语法结构与使用场景。",
                            "estimated_minutes": max(15, daily_minutes // 2),
                            "difficulty": "foundation",
                            "completed": False,
                            "status": "pending",
                        },
                        {
                            "task_id": "task-2",
                            "title": "查看前置知识依赖",
                            "task_type": "graph",
                            "knowledge_point": request.knowledge_point,
                            "objective": "确认当前知识点所依赖的前置能力。",
                            "estimated_minutes": 10,
                            "difficulty": "foundation",
                            "completed": False,
                            "status": "pending",
                        },
                    ],
                },
                {
                    "stage_id": "stage-2",
                    "title": "阶段二：练习强化",
                    "description": "通过基础题和进阶题完成理解检验。",
                    "tasks": [
                        {
                            "task_id": "task-3",
                            "title": "完成基础与进阶习题",
                            "task_type": "exercise",
                            "knowledge_point": request.knowledge_point,
                            "objective": "完成 5 道结构化练习题并查看解析。",
                            "estimated_minutes": max(20, daily_minutes // 2),
                            "difficulty": "intermediate",
                            "completed": False,
                            "status": "pending",
                        },
                    ],
                },
                {
                    "stage_id": "stage-3",
                    "title": "阶段三：复盘提升",
                    "description": "针对薄弱点进行总结与错题复练。",
                    "tasks": [
                        {
                            "task_id": "task-4",
                            "title": "错题复盘与再次练习",
                            "task_type": "review",
                            "knowledge_point": request.knowledge_point,
                            "objective": "整理薄弱点并进行一次定向复练。",
                            "estimated_minutes": 20,
                            "difficulty": "advanced",
                            "completed": False,
                            "status": "pending",
                        },
                    ],
                },
            ],
        }
        payload = self._apply_teacher_scope_to_path(payload, teacher_scope)
        return payload

    def _generate_path_with_llm(
        self,
        request: LearningPathRequest,
        fallback_payload: dict[str, object],
        teacher_scope: dict[str, object] | None,
    ) -> dict[str, object] | None:
        """Ask the configured LLM to personalize the path while preserving API shape."""

        try:
            settings = get_settings()
            llm = LLMFactory(settings).build_chat_model(temperature=0.25)
            prompt = self._build_llm_prompt(request, fallback_payload, teacher_scope)
            result = llm.invoke(prompt)
            content = self._coerce_llm_text(getattr(result, "content", result))
            payload = self._parse_llm_json(content)
            return self._normalize_llm_path(request, payload, fallback_payload, teacher_scope)
        except Exception as exc:
            logger.warning("LLM learning path generation failed, using fallback: %s", exc)
            return None

    def _build_llm_prompt(
        self,
        request: LearningPathRequest,
        fallback_payload: dict[str, object],
        teacher_scope: dict[str, object] | None,
    ) -> list[tuple[str, str]]:
        profile = {
            "daily_minutes": request.daily_minutes,
            "learner_profile": request.learner_profile,
            "teacher_scope": teacher_scope,
        }
        system = (
            "你是个性化学习路径规划智能体。请严格输出 JSON，不要输出 Markdown。"
            "JSON 必须包含 user_id, subject, knowledge_point, overview, estimated_days, stages。"
            "stages 为 3 个阶段左右；每个阶段包含 stage_id, title, description, tasks。"
            "每个 task 包含 task_id, title, task_type, knowledge_point, objective, "
            "estimated_minutes, difficulty, completed, status。"
            "task_type 只能是 courseware/exercise/review/graph，difficulty 只能是 "
            "foundation/intermediate/advanced，status 使用 pending。"
        )
        user = (
            "请基于学习者画像、教师范围和参考结构生成更自然的个性化学习路径。\n"
            f"学习主题：{request.knowledge_point}\n"
            f"学科：{request.subject}\n"
            f"画像与约束：{json.dumps(profile, ensure_ascii=False, default=str)}\n"
            f"参考结构：{json.dumps(fallback_payload, ensure_ascii=False, default=str)}"
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
        fallback_payload: dict[str, object],
        teacher_scope: dict[str, object] | None,
    ) -> dict[str, object]:
        normalized: dict[str, object] = {
            "user_id": request.user_id,
            "subject": str(payload.get("subject") or fallback_payload.get("subject") or request.subject),
            "knowledge_point": str(
                payload.get("knowledge_point")
                or fallback_payload.get("knowledge_point")
                or request.knowledge_point
            ),
            "overview": str(payload.get("overview") or fallback_payload.get("overview") or ""),
            "estimated_days": self._safe_int(payload.get("estimated_days"), fallback_payload.get("estimated_days"), 3),
            "stages": [],
        }
        if teacher_scope:
            normalized["teacher_scope"] = teacher_scope
        elif "teacher_scope" in fallback_payload:
            normalized["teacher_scope"] = fallback_payload.get("teacher_scope")

        fallback_stages = fallback_payload.get("stages", [])
        stages = payload.get("stages")
        if not isinstance(stages, list) or not stages:
            stages = fallback_stages

        normalized_stages: list[dict[str, object]] = []
        for stage_index, stage in enumerate(stages[:4], start=1):
            if not isinstance(stage, dict):
                continue
            fallback_stage = (
                fallback_stages[stage_index - 1]
                if isinstance(fallback_stages, list) and len(fallback_stages) >= stage_index
                else {}
            )
            if not isinstance(fallback_stage, dict):
                fallback_stage = {}
            tasks = stage.get("tasks")
            fallback_tasks = fallback_stage.get("tasks", [])
            normalized_tasks = self._normalize_llm_tasks(
                tasks if isinstance(tasks, list) else fallback_tasks,
                fallback_tasks if isinstance(fallback_tasks, list) else [],
                normalized["knowledge_point"],
            )
            if not normalized_tasks:
                continue
            normalized_stages.append(
                {
                    "stage_id": str(stage.get("stage_id") or fallback_stage.get("stage_id") or f"stage-{stage_index}"),
                    "title": str(stage.get("title") or fallback_stage.get("title") or f"阶段{stage_index}"),
                    "description": str(stage.get("description") or fallback_stage.get("description") or ""),
                    "tasks": normalized_tasks,
                }
            )

        if not normalized_stages:
            return fallback_payload
        normalized["stages"] = normalized_stages
        return self._normalize_payload(normalized)

    def _normalize_llm_tasks(
        self,
        tasks: Any,
        fallback_tasks: list[Any],
        knowledge_point: object,
    ) -> list[dict[str, object]]:
        allowed_types = {"courseware", "exercise", "review", "graph"}
        allowed_difficulties = {"foundation", "intermediate", "advanced"}
        normalized: list[dict[str, object]] = []
        if not isinstance(tasks, list):
            tasks = fallback_tasks
        for task_index, task in enumerate(tasks[:5], start=1):
            if not isinstance(task, dict):
                continue
            fallback_task = fallback_tasks[task_index - 1] if len(fallback_tasks) >= task_index else {}
            if not isinstance(fallback_task, dict):
                fallback_task = {}
            task_type = str(task.get("task_type") or fallback_task.get("task_type") or "courseware")
            difficulty = str(task.get("difficulty") or fallback_task.get("difficulty") or "foundation")
            normalized.append(
                {
                    "task_id": str(task.get("task_id") or fallback_task.get("task_id") or f"task-{task_index}"),
                    "title": str(task.get("title") or fallback_task.get("title") or "学习任务"),
                    "task_type": task_type if task_type in allowed_types else "courseware",
                    "knowledge_point": str(task.get("knowledge_point") or fallback_task.get("knowledge_point") or knowledge_point),
                    "objective": str(task.get("objective") or fallback_task.get("objective") or ""),
                    "estimated_minutes": self._safe_int(
                        task.get("estimated_minutes"),
                        fallback_task.get("estimated_minutes"),
                        20,
                    ),
                    "difficulty": difficulty if difficulty in allowed_difficulties else "foundation",
                    "completed": False,
                    "status": "pending",
                }
            )
        return normalized

    def _safe_int(self, value: Any, fallback: Any, default: int) -> int:
        for candidate in (value, fallback, default):
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return default

    def _coerce_llm_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
        return str(content)

    def _build_profile_summary(self, learner_profile: dict[str, object]) -> str:
        summaries = learner_profile.get("profile_analysis_summaries")
        if not isinstance(summaries, dict):
            return ""

        summary_parts: list[str] = []
        for key in ("knowledgeBase", "learningSpeed", "goalOrientation"):
            summary = str(summaries.get(key) or "").strip()
            if summary:
                summary_parts.append(summary)
        if not summary_parts:
            return ""
        return " 深度画像建议：" + "；".join(summary_parts[:3])

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

    def _apply_teacher_scope_to_path(
        self,
        payload: dict[str, object],
        teacher_scope: dict[str, object] | None,
    ) -> dict[str, object]:
        if not teacher_scope:
            payload.setdefault("teacher_scope", None)
            return payload

        knowledge_points = teacher_scope.get("knowledge_points", [])
        if not isinstance(knowledge_points, list) or not knowledge_points:
            knowledge_points = [payload["knowledge_point"]]
        knowledge_points_text = " / ".join(str(item) for item in knowledge_points[:5])
        direction = str(teacher_scope.get("learning_direction") or "")
        goal = str(teacher_scope.get("teaching_goal") or "")
        courseware_title = str(teacher_scope.get("courseware_title") or "")

        payload["teacher_scope"] = teacher_scope
        payload["overview"] = (
            f"教师已划定学习范围：{knowledge_points_text}。"
            f"{direction or '请先完成教师发布的课件，再完成配套练习与复盘。'}"
        )

        stages = payload.get("stages", [])
        if not isinstance(stages, list) or not stages:
            return payload

        first_stage = stages[0]
        if isinstance(first_stage, dict):
            first_stage["title"] = "教师范围学习启动"
            first_stage["description"] = direction or first_stage.get("description", "")
            tasks = first_stage.get("tasks", [])
            if isinstance(tasks, list) and tasks:
                first_task = tasks[0]
                if isinstance(first_task, dict):
                    first_task["title"] = f"学习教师发布课件：{courseware_title or payload['knowledge_point']}"
                    first_task["objective"] = goal or first_task.get("objective", "")
                    first_task["teacher_scope_id"] = teacher_scope.get("id")
                    first_task["teacher_courseware_content"] = teacher_scope.get("courseware_content", "")
                if len(tasks) > 1 and isinstance(tasks[1], dict):
                    tasks[1]["objective"] = f"确认教师划定范围内的知识关联：{knowledge_points_text}"

        return payload
