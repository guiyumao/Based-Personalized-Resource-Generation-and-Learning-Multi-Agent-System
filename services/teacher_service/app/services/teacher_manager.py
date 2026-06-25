"""Teacher service manager with lightweight aggregation over evaluation-service."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, defaultdict
from statistics import mean

import httpx
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import AnswerRecord, Exercise, KnowledgePoint, LearningPath, TeachingScope, User, UserProfile
from services.teacher_service.app.schemas.teacher import (
    ClassCreate,
    ClassItem,
    KnowledgePointMistakeStat,
    MistakeNotebookItem,
    StudentInsight,
    StudentLearningDetail,
    TeacherTeachingAnalytics,
    TeacherReportDetail,
    TeachingScopeCreate,
    TeachingScopeItem,
)

logger = logging.getLogger(__name__)


class TeacherManager:
    """Store teacher-created classes and aggregate learner details from evaluation-service."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._classes: list[ClassItem] = []

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
        """Return progress snapshot derived from real answer records."""

        analytics = self.get_teaching_analytics(class_id)
        return {
            "class_id": class_id,
            "student_count": analytics.student_count,
            "completed_tasks": analytics.total_answers,
            "average_mastery": analytics.correct_rate,
        }

    def list_student_insights(self, class_id: int) -> list[StudentInsight]:
        """Return teacher-facing learner insight cards."""

        _ = class_id
        with SessionLocal() as db:
            students = self._list_students(db)
            return [self._build_student_insight(db, student) for student in students]

    def create_teaching_scope(self, payload: TeachingScopeCreate) -> TeachingScopeItem:
        """Persist one teacher-defined learning scope in the shared database."""

        with SessionLocal() as db:
            record = TeachingScope(**self._to_dict(payload))
            db.add(record)
            db.commit()
            db.refresh(record)
            self._publish_scope_to_students(db, record)
            return self._scope_to_item(record)

    def list_teaching_scopes(self, class_id: int) -> list[TeachingScopeItem]:
        """Return scopes defined for one class."""

        with SessionLocal() as db:
            records = (
                db.query(TeachingScope)
                .filter(TeachingScope.class_id == class_id)
                .order_by(TeachingScope.id.desc())
                .all()
            )
            return [self._scope_to_item(record) for record in records]

    def list_student_teaching_scopes(self, user_id: int) -> list[TeachingScopeItem]:
        """Return scopes visible to one student, including class-wide scopes."""

        with SessionLocal() as db:
            records = (
                db.query(TeachingScope)
                .filter((TeachingScope.student_user_id.is_(None)) | (TeachingScope.student_user_id == user_id))
                .order_by(TeachingScope.id.desc())
                .all()
            )
            return [self._scope_to_item(record) for record in records]

    def get_teaching_analytics(self, class_id: int) -> TeacherTeachingAnalytics:
        """Aggregate real mistakes and answer statistics for teacher decisions."""

        _ = class_id
        with SessionLocal() as db:
            students = self._list_students(db)
            student_ids = [student.id for student in students]
            if not student_ids:
                return TeacherTeachingAnalytics(
                    class_id=class_id,
                    student_count=0,
                    answered_students=0,
                    total_answers=0,
                    correct_rate=None,
                    total_mistakes=0,
                    weak_knowledge_points=[],
                    teaching_suggestions=["当前还没有学生学习数据，建议先组织一次诊断练习再划定教学方向。"],
                )

            records = db.query(AnswerRecord).filter(AnswerRecord.user_id.in_(student_ids)).all()
            total_answers = len(records)
            answered_students = len({record.user_id for record in records})
            correct_records = [record for record in records if record.is_correct is True]
            wrong_records = [record for record in records if record.is_correct is False]
            correct_rate = round((len(correct_records) / total_answers) * 100) if total_answers else None
            weak_points = self._build_weak_point_stats(db, wrong_records)
            suggestions = self._build_teaching_suggestions(correct_rate, weak_points, answered_students, len(students))

            return TeacherTeachingAnalytics(
                class_id=class_id,
                student_count=len(students),
                answered_students=answered_students,
                total_answers=total_answers,
                correct_rate=correct_rate,
                total_mistakes=len(wrong_records),
                weak_knowledge_points=weak_points,
                teaching_suggestions=suggestions,
            )

    async def get_student_learning_detail(self, class_id: int, user_id: int) -> StudentLearningDetail:
        """Aggregate one learner's mistake notebook and reports for teachers."""

        insight = self._find_student_insight(class_id, user_id)
        if insight is None:
            raise ValueError(f"Student {user_id} not found in class {class_id}.")

        endpoints = {
            "stage": f"{self._settings.evaluation_service_url}/evaluation/reports/stage/{user_id}/detail",
            "comprehensive": (
                f"{self._settings.evaluation_service_url}/evaluation/reports/comprehensive/{user_id}/detail"
            ),
            "mistakes": f"{self._settings.evaluation_service_url}/evaluation/mistakes/{user_id}/teacher-detail",
        }

        async with httpx.AsyncClient(timeout=6.0) as client:
            stage_response, comprehensive_response, mistakes_response = await asyncio.gather(
                client.get(endpoints["stage"]),
                client.get(endpoints["comprehensive"]),
                client.get(endpoints["mistakes"]),
            )

        stage_report = self._parse_report_response(stage_response)
        comprehensive_report = self._parse_report_response(comprehensive_response)
        mistake_notebook = self._parse_mistake_response(mistakes_response)

        return StudentLearningDetail(
            **self._to_dict(insight),
            mistake_notebook=mistake_notebook,
            stage_report=stage_report,
            comprehensive_report=comprehensive_report,
        )

    def _find_student_insight(self, class_id: int, user_id: int) -> StudentInsight | None:
        """Return one student insight by class and user id."""

        return next((item for item in self.list_student_insights(class_id) if item.user_id == user_id), None)

    def _list_students(self, db: Session) -> list[User]:
        """Return active student users from the shared user table."""

        return (
            db.query(User)
            .filter(User.role == "student")
            .filter(User.is_active.is_(True))
            .order_by(User.id.asc())
            .all()
        )

    def _build_student_insight(self, db: Session, student: User) -> StudentInsight:
        """Build one student card from real profile and answer records."""

        records = (
            db.query(AnswerRecord)
            .filter(AnswerRecord.user_id == student.id)
            .order_by(AnswerRecord.created_at.desc(), AnswerRecord.id.desc())
            .all()
        )
        total = len(records)
        correct = sum(1 for record in records if record.is_correct is True)
        wrong_records = [record for record in records if record.is_correct is False]
        mastery = self._estimate_student_mastery(db, student.id, records)
        recent_focus = self._resolve_recent_focus(db, records)
        report_summary = self._build_student_report_summary(total, correct, len(wrong_records), recent_focus)

        return StudentInsight(
            user_id=student.id,
            student_name=student.username,
            mastery=mastery,
            recent_focus=recent_focus,
            mistake_count=len(wrong_records),
            report_summary=report_summary,
        )

    def _estimate_student_mastery(self, db: Session, user_id: int, records: list[AnswerRecord]) -> int:
        """Estimate mastery from profile first, then real answer correctness."""

        profile = db.get(UserProfile, user_id)
        mastery_json = profile.mastery_json if profile and isinstance(profile.mastery_json, dict) else {}
        scores = [
            float(value.get("score"))
            for value in mastery_json.values()
            if isinstance(value, dict) and isinstance(value.get("score"), (int, float))
        ]
        if scores:
            return max(0, min(100, round(mean(scores))))
        scored_records = [record for record in records if record.is_correct is not None]
        if not scored_records:
            return 0
        correct_count = sum(1 for record in scored_records if record.is_correct is True)
        return round((correct_count / len(scored_records)) * 100)

    def _resolve_recent_focus(self, db: Session, records: list[AnswerRecord]) -> str:
        """Resolve the most recent answered knowledge point."""

        for record in records:
            exercise = db.get(Exercise, record.exercise_id)
            if exercise is None:
                continue
            knowledge_point = db.get(KnowledgePoint, exercise.knowledge_point_id)
            if knowledge_point is not None:
                return knowledge_point.name
        return "暂无真实学习记录"

    def _build_student_report_summary(self, total: int, correct: int, mistakes: int, recent_focus: str) -> str:
        """Create a concise teacher-facing summary without fabricated data."""

        if total == 0:
            return "暂无真实作答记录，建议先安排诊断练习。"
        correct_rate = round((correct / total) * 100)
        if mistakes == 0:
            return f"已完成 {total} 次作答，正确率 {correct_rate}%，可围绕 {recent_focus} 提升迁移应用。"
        return f"已完成 {total} 次作答，正确率 {correct_rate}%，建议优先复盘 {recent_focus} 相关错题。"

    def _build_weak_point_stats(
        self,
        db: Session,
        wrong_records: list[AnswerRecord],
    ) -> list[KnowledgePointMistakeStat]:
        """Aggregate wrong answers by knowledge point."""

        mistake_counts: Counter[str] = Counter()
        affected_students: dict[str, set[int]] = defaultdict(set)
        for record in wrong_records:
            exercise = db.get(Exercise, record.exercise_id)
            if exercise is None:
                continue
            knowledge_point = db.get(KnowledgePoint, exercise.knowledge_point_id)
            name = knowledge_point.name if knowledge_point is not None else "未标注知识点"
            mistake_counts[name] += 1
            affected_students[name].add(record.user_id)

        return [
            KnowledgePointMistakeStat(
                knowledge_point=name,
                mistake_count=count,
                affected_students=len(affected_students[name]),
                suggested_direction=self._suggest_direction_for_weak_point(name, count, len(affected_students[name])),
            )
            for name, count in mistake_counts.most_common(5)
        ]

    def _suggest_direction_for_weak_point(self, knowledge_point: str, mistake_count: int, affected_count: int) -> str:
        """Build a teacher action suggestion for one weak knowledge point."""

        if affected_count >= 3 or mistake_count >= 5:
            return f"建议将 {knowledge_point} 设为班级共性复讲方向，并配套分层练习。"
        return f"建议对 {knowledge_point} 进行小组补练或个别化课件推送。"

    def _build_teaching_suggestions(
        self,
        correct_rate: int | None,
        weak_points: list[KnowledgePointMistakeStat],
        answered_students: int,
        student_count: int,
    ) -> list[str]:
        """Create class-level suggestions from actual statistics."""

        suggestions: list[str] = []
        if student_count and answered_students < student_count:
            suggestions.append("部分学生还没有真实作答记录，建议先补齐诊断数据再做全班判断。")
        if correct_rate is None:
            suggestions.append("当前暂无作答统计，建议先布置一组覆盖核心知识点的诊断任务。")
        elif correct_rate < 60:
            suggestions.append("班级整体正确率偏低，建议先收窄学习范围，进行基础概念复讲。")
        elif correct_rate < 80:
            suggestions.append("班级正确率处于巩固区间，建议围绕高频错题做变式训练。")
        else:
            suggestions.append("班级整体表现较稳，可增加综合应用与迁移任务。")
        if weak_points:
            top_point = weak_points[0]
            suggestions.append(
                f"当前最高频薄弱点是 {top_point.knowledge_point}，涉及 {top_point.affected_students} 名学生。"
            )
        return suggestions

    def _to_dict(self, model: object) -> dict[str, object]:
        """Serialize a pydantic model across v1 and v2 runtimes."""

        if hasattr(model, "model_dump"):
            return getattr(model, "model_dump")()
        if hasattr(model, "dict"):
            return getattr(model, "dict")()
        raise TypeError(f"Unsupported model type: {type(model)!r}")

    def _scope_to_item(self, record: TeachingScope) -> TeachingScopeItem:
        """Serialize a persisted teaching scope."""

        return TeachingScopeItem(
            id=record.id,
            class_id=record.class_id,
            student_user_id=record.student_user_id,
            knowledge_points=list(record.knowledge_points or []),
            learning_direction=record.learning_direction,
            courseware_title=record.courseware_title,
            courseware_content=record.courseware_content,
            teaching_goal=record.teaching_goal or "",
        )

    def _publish_scope_to_students(self, db: Session, scope: TeachingScope) -> None:
        """Turn a teacher scope into active student learning paths."""

        if scope.student_user_id is not None:
            students = [db.get(User, scope.student_user_id)]
        else:
            students = self._list_students(db)

        for student in [item for item in students if item is not None and item.role == "student"]:
            payload = self._build_scope_learning_path(scope, student.id)
            existing_records = (
                db.query(LearningPath)
                .filter(LearningPath.user_id == student.id, LearningPath.status == "active")
                .all()
            )
            for item in existing_records:
                item.status = "archived"
            db.add(LearningPath(user_id=student.id, path_data_json=payload, status="active"))
        db.commit()

    def _build_scope_learning_path(self, scope: TeachingScope, user_id: int) -> dict[str, object]:
        knowledge_points = list(scope.knowledge_points or [])
        primary_point = knowledge_points[0] if knowledge_points else scope.courseware_title
        scope_payload = self._to_dict(self._scope_to_item(scope))
        return {
            "user_id": user_id,
            "subject": scope.courseware_title,
            "knowledge_point": primary_point,
            "overview": (
                f"教师已划定学习范围：{' / '.join(knowledge_points) or primary_point}。"
                f"{scope.learning_direction}"
            ),
            "estimated_days": 3,
            "teacher_scope": scope_payload,
            "stages": [
                {
                    "stage_id": f"teacher-scope-{scope.id}-stage-1",
                    "title": "教师范围学习启动",
                    "description": scope.learning_direction,
                    "tasks": [
                        {
                            "task_id": f"teacher-scope-{scope.id}-courseware",
                            "title": f"学习教师发布课件：{scope.courseware_title}",
                            "task_type": "courseware",
                            "knowledge_point": primary_point,
                            "objective": scope.teaching_goal or scope.learning_direction,
                            "estimated_minutes": 30,
                            "difficulty": "foundation",
                            "completed": False,
                            "status": "pending",
                            "teacher_scope_id": scope.id,
                            "teacher_courseware_content": scope.courseware_content,
                        },
                        {
                            "task_id": f"teacher-scope-{scope.id}-graph",
                            "title": "查看教师范围知识关联",
                            "task_type": "graph",
                            "knowledge_point": primary_point,
                            "objective": f"确认范围内知识点：{' / '.join(knowledge_points) or primary_point}",
                            "estimated_minutes": 10,
                            "difficulty": "foundation",
                            "completed": False,
                            "status": "pending",
                        },
                    ],
                },
                {
                    "stage_id": f"teacher-scope-{scope.id}-stage-2",
                    "title": "配套练习与反馈",
                    "description": "围绕教师划定范围完成练习，提交后进入错题与反馈闭环。",
                    "tasks": [
                        {
                            "task_id": f"teacher-scope-{scope.id}-exercise",
                            "title": "完成教师范围配套练习",
                            "task_type": "exercise",
                            "knowledge_point": primary_point,
                            "objective": "用练习验证教师划定范围的掌握情况。",
                            "estimated_minutes": 25,
                            "difficulty": "intermediate",
                            "completed": False,
                            "status": "pending",
                        },
                    ],
                },
                {
                    "stage_id": f"teacher-scope-{scope.id}-stage-3",
                    "title": "复盘与提升",
                    "description": "结合答题结果和教师目标进行复盘。",
                    "tasks": [
                        {
                            "task_id": f"teacher-scope-{scope.id}-review",
                            "title": "复盘教师范围学习结果",
                            "task_type": "review",
                            "knowledge_point": primary_point,
                            "objective": scope.teaching_goal or "整理薄弱点并准备下一轮学习。",
                            "estimated_minutes": 20,
                            "difficulty": "advanced",
                            "completed": False,
                            "status": "pending",
                        },
                    ],
                },
            ],
        }

    def _parse_report_response(
        self,
        response: httpx.Response,
    ) -> TeacherReportDetail:
        """Normalize a report-service response."""

        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        return TeacherReportDetail(**data)

    def _parse_mistake_response(
        self,
        response: httpx.Response,
    ) -> list[MistakeNotebookItem]:
        """Normalize a mistake notebook response."""

        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        items = data.get("items", [])
        return [MistakeNotebookItem(**item) for item in items]
