"""Learning path planning service for the student workspace."""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy.orm import Session

from common.models.learning import LearningPath
from common.schemas.agent import LearningPathAdjustRequest, LearningPathRequest


class LearningPathService:
    """Build a lightweight but actionable personalized learning path."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def generate_path(self, request: LearningPathRequest) -> dict[str, object]:
        """Create a staged learning path around one knowledge point."""

        daily_minutes = request.daily_minutes
        estimated_days = 3 if daily_minutes >= 45 else 4
        style = str(request.learner_profile.get("learning_style", "visual"))
        teacher_scope = self._extract_teacher_scope(request.learner_profile)

        payload = {
            "user_id": request.user_id,
            "subject": request.subject,
            "knowledge_point": request.knowledge_point,
            "overview": (
                f"围绕 {request.knowledge_point} 设计的 {estimated_days} 天学习路径，"
                f"优先采用 {style} 风格资源，先理解概念，再完成练习与复盘。"
            ),
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
        return self._persist_generated_path(request.user_id, payload) if self.db is not None else payload

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
