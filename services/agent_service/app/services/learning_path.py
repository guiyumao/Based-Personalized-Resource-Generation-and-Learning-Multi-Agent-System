"""Learning path planning service for the student workspace."""

from __future__ import annotations

from common.schemas.agent import LearningPathRequest


class LearningPathService:
    """Build a lightweight but actionable personalized learning path."""

    def generate_path(self, request: LearningPathRequest) -> dict[str, object]:
        """Create a staged learning path around one knowledge point."""

        daily_minutes = request.daily_minutes
        estimated_days = 3 if daily_minutes >= 45 else 4
        style = str(request.learner_profile.get("learning_style", "visual"))

        return {
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
                    "title": "阶段一：概念建立",
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
                        },
                    ],
                },
            ],
        }
