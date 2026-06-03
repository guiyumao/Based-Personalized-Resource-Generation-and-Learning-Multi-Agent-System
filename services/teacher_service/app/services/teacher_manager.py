"""Teacher service manager with lightweight aggregation over evaluation-service."""

from __future__ import annotations

import asyncio
import logging

import httpx

from common.config import get_settings
from services.teacher_service.app.schemas.teacher import (
    ClassCreate,
    ClassItem,
    MistakeNotebookItem,
    StudentInsight,
    StudentLearningDetail,
    TeacherReportDetail,
)

logger = logging.getLogger(__name__)


class TeacherManager:
    """Store teacher demo data and aggregate learner details from evaluation-service."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._classes = [
            ClassItem(id=1, name="Python 基础班", subject="Python", teacher_name="李老师"),
        ]

    def list_classes(self) -> list[ClassItem]:
        """Return all classes."""

        return self._classes

    def create_class(self, payload: ClassCreate) -> ClassItem:
        """Create a class entry."""

        next_id = max((item.id for item in self._classes), default=0) + 1
        item = ClassItem(id=next_id, **self._to_dict(payload))
        self._classes.append(item)
        return item

    def get_student_progress(self, class_id: int) -> dict[str, object]:
        """Return a demo progress snapshot for a class."""

        return {
            "class_id": class_id,
            "student_count": 32,
            "completed_tasks": 187,
            "average_mastery": 74,
        }

    def list_student_insights(self, class_id: int) -> list[StudentInsight]:
        """Return teacher-facing learner insight cards."""

        _ = class_id
        return [
            StudentInsight(
                user_id=1,
                student_name="示例学生A",
                mastery=78,
                recent_focus="Python 循环",
                mistake_count=2,
                report_summary="基础掌握较稳，建议重点复练边界条件相关错题。",
            ),
            StudentInsight(
                user_id=2,
                student_name="示例学生B",
                mastery=66,
                recent_focus="条件判断",
                mistake_count=4,
                report_summary="当前正确率波动较大，建议先补前置知识再推进新任务。",
            ),
        ]

    async def get_student_learning_detail(self, class_id: int, user_id: int) -> StudentLearningDetail:
        """Aggregate one learner's mistake notebook and reports for teachers."""

        insight = self._find_student_insight(class_id, user_id)
        if insight is None:
            raise ValueError(f"Student {user_id} not found in class {class_id}.")

        stage_fallback = self._build_stage_fallback(insight)
        comprehensive_fallback = self._build_comprehensive_fallback(insight)
        mistakes_fallback = self._build_mistake_fallback(insight)

        endpoints = {
            "stage": f"{self._settings.evaluation_service_url}/evaluation/reports/stage/{user_id}/detail",
            "comprehensive": (
                f"{self._settings.evaluation_service_url}/evaluation/reports/comprehensive/{user_id}/detail"
            ),
            "mistakes": f"{self._settings.evaluation_service_url}/evaluation/mistakes/{user_id}/detail",
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                stage_response, comprehensive_response, mistakes_response = await asyncio.gather(
                    client.get(endpoints["stage"]),
                    client.get(endpoints["comprehensive"]),
                    client.get(endpoints["mistakes"]),
                )
        except httpx.HTTPError as exc:
            logger.warning("teacher detail aggregation fallback triggered: %s", exc)
            return StudentLearningDetail(
                **self._to_dict(insight),
                mistake_notebook=mistakes_fallback,
                stage_report=stage_fallback,
                comprehensive_report=comprehensive_fallback,
            )
        except Exception as exc:
            logger.warning("teacher detail aggregation unexpected fallback triggered: %s", exc)
            return StudentLearningDetail(
                **self._to_dict(insight),
                mistake_notebook=mistakes_fallback,
                stage_report=stage_fallback,
                comprehensive_report=comprehensive_fallback,
            )

        stage_report = self._parse_report_response(stage_response, stage_fallback)
        comprehensive_report = self._parse_report_response(comprehensive_response, comprehensive_fallback)
        mistake_notebook = self._parse_mistake_response(mistakes_response, mistakes_fallback)

        return StudentLearningDetail(
            **self._to_dict(insight),
            mistake_notebook=mistake_notebook,
            stage_report=stage_report,
            comprehensive_report=comprehensive_report,
        )

    def _find_student_insight(self, class_id: int, user_id: int) -> StudentInsight | None:
        """Return one student insight by class and user id."""

        return next((item for item in self.list_student_insights(class_id) if item.user_id == user_id), None)

    def _to_dict(self, model: object) -> dict[str, object]:
        """Serialize a pydantic model across v1 and v2 runtimes."""

        if hasattr(model, "model_dump"):
            return getattr(model, "model_dump")()
        if hasattr(model, "dict"):
            return getattr(model, "dict")()
        raise TypeError(f"Unsupported model type: {type(model)!r}")

    def _parse_report_response(
        self,
        response: httpx.Response,
        fallback: TeacherReportDetail,
    ) -> TeacherReportDetail:
        """Safely normalize a report-service response."""

        try:
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", {})
            return TeacherReportDetail(**data)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("teacher report parse fallback triggered: %s", exc)
            return fallback

    def _parse_mistake_response(
        self,
        response: httpx.Response,
        fallback: list[MistakeNotebookItem],
    ) -> list[MistakeNotebookItem]:
        """Safely normalize a mistake notebook response."""

        try:
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", {})
            items = data.get("items", [])
            return [MistakeNotebookItem(**item) for item in items]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("teacher mistake parse fallback triggered: %s", exc)
            return fallback

    def _build_stage_fallback(self, insight: StudentInsight) -> TeacherReportDetail:
        """Create a useful local stage report when evaluation-service is unavailable."""

        return TeacherReportDetail(
            report_type="stage",
            user_id=insight.user_id,
            title=f"{insight.student_name} 阶段报告",
            summary=f"当前掌握度约 {insight.mastery}，最近重点在 {insight.recent_focus}。",
            strengths=[
                "能够持续推进当前学习任务。",
                "基础题完成质量相对稳定。",
            ],
            weaknesses=[
                "对边界条件和步骤完整性仍需加强。",
                "错题复盘的节奏还可以更密集。",
            ],
            next_actions=[
                "先完成最近知识点的 1 轮错题重练。",
                "教师可安排一次针对薄弱点的小测。",
            ],
        )

    def _build_comprehensive_fallback(self, insight: StudentInsight) -> TeacherReportDetail:
        """Create a local comprehensive report fallback."""

        return TeacherReportDetail(
            report_type="comprehensive",
            user_id=insight.user_id,
            title=f"{insight.student_name} 综合报告",
            summary=insight.report_summary,
            strengths=[
                "学习节奏基本稳定。",
                "当前重点知识点已有持续投入。",
            ],
            weaknesses=[
                f"累计错题 {insight.mistake_count} 道，仍需持续清理。",
                "高阶迁移题目的表达与拆解能力需要提升。",
            ],
            next_actions=[
                "把错题本按知识点重新分类复盘。",
                "下阶段增加 1 组综合应用题训练。",
            ],
        )

    def _build_mistake_fallback(self, insight: StudentInsight) -> list[MistakeNotebookItem]:
        """Return local mistake notebook examples for the teacher workspace."""

        return [
            MistakeNotebookItem(
                exercise_id=1000 + insight.user_id,
                knowledge_point=insight.recent_focus,
                question_type="choice",
                user_answer="A",
                correct_answer="B",
                analysis="这道题主要暴露出对循环边界和终止条件理解不够稳定。",
                suggested_action="先复盘题干条件，再完成 2 道同类型变式题。",
            )
        ]
