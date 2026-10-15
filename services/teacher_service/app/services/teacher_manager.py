"""Teacher service manager with lightweight aggregation over evaluation-service."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean

import httpx
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import (
    AnswerRecord,
    Assignment,
    AssignmentSubmission,
    ClassEnrollment,
    Classroom,
    Course,
    DiscussionReply,
    DiscussionThread,
    Exercise,
    KnowledgePoint,
    LearningPath,
    Notification,
    TeachingScope,
    User,
    UserProfile,
)
from services.teacher_service.app.schemas.teacher import (
    AssignmentItem,
    ClassCreate,
    ClassItem,
    DiscussionCreate,
    DiscussionItem,
    DiscussionReplyCreate,
    DiscussionReplyItem,
    HomeworkAssign,
    KnowledgePointMistakeStat,
    MistakeNotebookItem,
    NotificationItem,
    ReviewPayload,
    StudentInsight,
    StudentLearningDetail,
    SubmissionCreate,
    SubmissionItem,
    TeacherReportDetail,
    TeacherTeachingAnalytics,
    TeachingScopeCreate,
    TeachingScopeItem,
)

logger = logging.getLogger(__name__)


class TeacherManager:
    """Store teacher-created classes and aggregate learner details from evaluation-service."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def list_classes(self, user_id: int, role: str) -> list[ClassItem]:
        """Return persisted classes owned by the teacher, or all for an admin."""

        with SessionLocal() as db:
            query = db.query(Classroom)
            if role != "admin":
                query = query.filter(Classroom.teacher_user_id == user_id)
            records = query.order_by(Classroom.id.desc()).all()
            return [self._class_to_item(db, record) for record in records]

    def create_class(self, payload: ClassCreate, teacher_user_id: int) -> ClassItem:
        """Create a persisted course and class owned by the current teacher."""

        with SessionLocal() as db:
            course = Course(
                title=payload.name,
                subject=payload.subject,
                description=f"{payload.name}课程",
                teacher_user_id=teacher_user_id,
            )
            db.add(course)
            db.flush()
            record = Classroom(
                name=payload.name,
                subject=payload.subject,
                teacher_name=payload.teacher_name,
                teacher_user_id=teacher_user_id,
                course_id=course.id,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return self._class_to_item(db, record)

    def enroll_student(
        self, class_id: int, student_user_id: int, teacher_user_id: int
    ) -> ClassItem:
        """Enroll an existing active student in a teacher-owned class."""

        with SessionLocal() as db:
            classroom = self._teacher_class(db, class_id, teacher_user_id)
            student = db.get(User, student_user_id)
            if student is None or student.role != "student" or not student.is_active:
                raise ValueError("Student account not found or inactive.")
            existing = (
                db.query(ClassEnrollment)
                .filter_by(class_id=class_id, student_user_id=student_user_id)
                .first()
            )
            if existing is None:
                db.add(ClassEnrollment(class_id=class_id, student_user_id=student_user_id))
                db.add(
                    Notification(
                        user_id=student_user_id,
                        title="你已加入新班级",
                        content=f"已加入 {classroom.name}，后续作业和讨论将在班级空间展示。",
                        type="class",
                        related_type="class",
                        related_id=class_id,
                    )
                )
                db.commit()
            return self._class_to_item(db, classroom)

    def get_student_progress(self, class_id: int) -> dict[str, object]:
        """Return progress snapshot derived from real answer records."""

        analytics = self.get_teaching_analytics(class_id)
        return {
            "class_id": class_id,
            "student_count": analytics.student_count,
            "completed_tasks": analytics.total_answers,
            "average_mastery": analytics.correct_rate,
        }

    def create_assignment(self, payload: HomeworkAssign, teacher_user_id: int) -> AssignmentItem:
        """Publish homework and notify every enrolled learner."""

        with SessionLocal() as db:
            classroom = self._teacher_class(db, payload.class_id, teacher_user_id)
            record = Assignment(
                class_id=payload.class_id,
                course_id=classroom.course_id,
                teacher_user_id=teacher_user_id,
                title=payload.title.strip(),
                description=payload.description.strip(),
                due_at=payload.due_at,
            )
            db.add(record)
            db.flush()
            enrollments = db.query(ClassEnrollment).filter_by(class_id=payload.class_id).all()
            for enrollment in enrollments:
                db.add(
                    Notification(
                        user_id=enrollment.student_user_id,
                        title=f"新作业：{record.title}",
                        content=record.description,
                        type="assignment",
                        related_type="assignment",
                        related_id=record.id,
                    )
                )
            db.commit()
            db.refresh(record)
            return self._assignment_to_item(db, record)

    def list_teacher_assignments(self, teacher_user_id: int, role: str) -> list[AssignmentItem]:
        with SessionLocal() as db:
            query = db.query(Assignment)
            if role != "admin":
                query = query.filter(Assignment.teacher_user_id == teacher_user_id)
            return [
                self._assignment_to_item(db, item)
                for item in query.order_by(Assignment.id.desc()).all()
            ]

    def list_student_assignments(self, student_user_id: int) -> list[AssignmentItem]:
        with SessionLocal() as db:
            class_ids = [
                row.class_id
                for row in db.query(ClassEnrollment)
                .filter_by(student_user_id=student_user_id)
                .all()
            ]
            if not class_ids:
                return []
            records = (
                db.query(Assignment)
                .filter(Assignment.class_id.in_(class_ids))
                .order_by(Assignment.id.desc())
                .all()
            )
            return [self._assignment_to_item(db, item) for item in records]

    def submit_assignment(
        self,
        assignment_id: int,
        payload: SubmissionCreate,
        student_user_id: int,
    ) -> SubmissionItem:
        """Create or update one student's submission while preserving cutoff checks."""

        with SessionLocal() as db:
            assignment = db.get(Assignment, assignment_id)
            if assignment is None or assignment.status != "published":
                raise ValueError("Assignment not found or closed.")
            enrolled = (
                db.query(ClassEnrollment)
                .filter_by(
                    class_id=assignment.class_id,
                    student_user_id=student_user_id,
                )
                .first()
            )
            if enrolled is None:
                raise PermissionError("You are not enrolled in this class.")
            if assignment.due_at and datetime.utcnow() > assignment.due_at:
                raise RuntimeError("Assignment deadline has passed.")
            record = (
                db.query(AssignmentSubmission)
                .filter_by(
                    assignment_id=assignment_id,
                    student_user_id=student_user_id,
                )
                .first()
            )
            if record is None:
                record = AssignmentSubmission(
                    assignment_id=assignment_id,
                    student_user_id=student_user_id,
                    content=payload.content.strip(),
                    attachment_url=payload.attachment_url,
                )
                db.add(record)
            else:
                record.content = payload.content.strip()
                record.attachment_url = payload.attachment_url
                record.status = "submitted"
                record.submitted_at = datetime.utcnow()
                record.score = None
                record.teacher_comment = ""
                record.reviewed_at = None
            db.commit()
            db.refresh(record)
            return self._submission_to_item(db, record)

    def list_submissions(
        self, assignment_id: int, teacher_user_id: int, role: str
    ) -> list[SubmissionItem]:
        with SessionLocal() as db:
            assignment = db.get(Assignment, assignment_id)
            if assignment is None or (
                role != "admin" and assignment.teacher_user_id != teacher_user_id
            ):
                raise ValueError("Assignment not found.")
            records = (
                db.query(AssignmentSubmission)
                .filter_by(assignment_id=assignment_id)
                .order_by(AssignmentSubmission.submitted_at.desc())
                .all()
            )
            return [self._submission_to_item(db, item) for item in records]

    def review_submission(
        self, submission_id: int, payload: ReviewPayload, teacher_user_id: int
    ) -> SubmissionItem:
        with SessionLocal() as db:
            record = db.get(AssignmentSubmission, submission_id)
            assignment = db.get(Assignment, record.assignment_id) if record else None
            if (
                record is None
                or assignment is None
                or assignment.teacher_user_id != teacher_user_id
            ):
                raise ValueError("Submission not found.")
            record.score = payload.score
            record.teacher_comment = payload.comment.strip()
            record.status = "reviewed"
            record.reviewed_at = datetime.utcnow()
            db.add(
                Notification(
                    user_id=record.student_user_id,
                    title=f"作业已批改：{assignment.title}",
                    content=f"得分 {payload.score:g}。{payload.comment.strip()}",
                    type="review",
                    related_type="assignment",
                    related_id=assignment.id,
                )
            )
            db.commit()
            db.refresh(record)
            return self._submission_to_item(db, record)

    def list_discussions(self, user_id: int, role: str) -> list[DiscussionItem]:
        with SessionLocal() as db:
            query = db.query(DiscussionThread)
            if role == "student":
                class_ids = [
                    row.class_id
                    for row in db.query(ClassEnrollment).filter_by(student_user_id=user_id).all()
                ]
                query = (
                    query.filter(DiscussionThread.class_id.in_(class_ids))
                    if class_ids
                    else query.filter(False)
                )
            elif role == "teacher":
                class_ids = [
                    row.id for row in db.query(Classroom).filter_by(teacher_user_id=user_id).all()
                ]
                query = (
                    query.filter(DiscussionThread.class_id.in_(class_ids))
                    if class_ids
                    else query.filter(False)
                )
            return [
                self._discussion_to_item(db, item)
                for item in query.order_by(DiscussionThread.updated_at.desc()).all()
            ]

    def create_discussion(
        self, payload: DiscussionCreate, user_id: int, role: str
    ) -> DiscussionItem:
        with SessionLocal() as db:
            if payload.class_id is not None:
                self._ensure_class_access(db, payload.class_id, user_id, role)
            record = DiscussionThread(
                class_id=payload.class_id,
                author_user_id=user_id,
                title=payload.title.strip(),
                content=payload.content.strip(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return self._discussion_to_item(db, record)

    def reply_discussion(
        self, thread_id: int, payload: DiscussionReplyCreate, user_id: int, role: str
    ) -> DiscussionItem:
        with SessionLocal() as db:
            thread = db.get(DiscussionThread, thread_id)
            if thread is None:
                raise ValueError("Discussion not found.")
            if thread.class_id is not None:
                self._ensure_class_access(db, thread.class_id, user_id, role)
            db.add(
                DiscussionReply(
                    thread_id=thread_id, author_user_id=user_id, content=payload.content.strip()
                )
            )
            thread.updated_at = datetime.utcnow()
            if thread.author_user_id != user_id:
                db.add(
                    Notification(
                        user_id=thread.author_user_id,
                        title=f"讨论有新回复：{thread.title}",
                        content=payload.content.strip(),
                        type="discussion",
                        related_type="discussion",
                        related_id=thread.id,
                    )
                )
            db.commit()
            db.refresh(thread)
            return self._discussion_to_item(db, thread)

    def list_notifications(self, user_id: int) -> list[NotificationItem]:
        with SessionLocal() as db:
            records = (
                db.query(Notification)
                .filter_by(user_id=user_id)
                .order_by(Notification.id.desc())
                .limit(100)
                .all()
            )
            return [self._notification_to_item(item) for item in records]

    def mark_notification_read(self, notification_id: int, user_id: int) -> NotificationItem:
        with SessionLocal() as db:
            record = db.query(Notification).filter_by(id=notification_id, user_id=user_id).first()
            if record is None:
                raise ValueError("Notification not found.")
            record.is_read = True
            db.commit()
            db.refresh(record)
            return self._notification_to_item(record)

    def list_student_insights(self, class_id: int) -> list[StudentInsight]:
        """Return teacher-facing learner insight cards."""

        _ = class_id
        with SessionLocal() as db:
            students = self._list_students(db, class_id)
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
        """Return targeted scopes plus class-wide scopes for enrolled classes only."""

        with SessionLocal() as db:
            class_ids = [
                row.class_id
                for row in db.query(ClassEnrollment).filter_by(student_user_id=user_id).all()
            ]
            visibility = TeachingScope.student_user_id == user_id
            if class_ids:
                visibility = visibility | (
                    TeachingScope.student_user_id.is_(None) & TeachingScope.class_id.in_(class_ids)
                )
            records = (
                db.query(TeachingScope).filter(visibility).order_by(TeachingScope.id.desc()).all()
            )
            return [self._scope_to_item(record) for record in records]

    def ensure_teacher_class_access(self, class_id: int, user_id: int, role: str) -> None:
        """Enforce class ownership for teachers while allowing administrators."""

        if role == "admin":
            return
        with SessionLocal() as db:
            if db.query(Classroom).filter_by(id=class_id, teacher_user_id=user_id).first() is None:
                raise PermissionError("You do not have access to this class.")

    def get_teaching_analytics(self, class_id: int) -> TeacherTeachingAnalytics:
        """Aggregate real mistakes and answer statistics for teacher decisions."""

        _ = class_id
        with SessionLocal() as db:
            students = self._list_students(db, class_id)
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
                    teaching_suggestions=[
                        "当前还没有学生学习数据，建议先组织一次诊断练习再划定教学方向。"
                    ],
                )

            records = db.query(AnswerRecord).filter(AnswerRecord.user_id.in_(student_ids)).all()
            total_answers = len(records)
            answered_students = len({record.user_id for record in records})
            correct_records = [record for record in records if record.is_correct is True]
            wrong_records = [record for record in records if record.is_correct is False]
            correct_rate = (
                round((len(correct_records) / total_answers) * 100) if total_answers else None
            )
            weak_points = self._build_weak_point_stats(db, wrong_records)
            suggestions = self._build_teaching_suggestions(
                correct_rate, weak_points, answered_students, len(students)
            )

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

    async def get_student_learning_detail(
        self, class_id: int, user_id: int, auth_header: str | None = None
    ) -> StudentLearningDetail:
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
        # The evaluation service enforces its own authorization, so the teacher's
        # bearer token must be propagated on these internal calls.
        forward_headers = {"Authorization": auth_header} if auth_header else {}

        async with httpx.AsyncClient(timeout=6.0) as client:
            stage_response, comprehensive_response, mistakes_response = await asyncio.gather(
                client.get(endpoints["stage"], headers=forward_headers),
                client.get(endpoints["comprehensive"], headers=forward_headers),
                client.get(endpoints["mistakes"], headers=forward_headers),
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

        return next(
            (item for item in self.list_student_insights(class_id) if item.user_id == user_id), None
        )

    def _list_students(self, db: Session, class_id: int | None = None) -> list[User]:
        """Return enrolled students, or all active students for legacy unscoped publishing."""

        query = db.query(User).filter(User.role == "student", User.is_active.is_(True))
        if class_id is not None and db.get(Classroom, class_id) is not None:
            query = query.join(ClassEnrollment, ClassEnrollment.student_user_id == User.id).filter(
                ClassEnrollment.class_id == class_id
            )
        return query.order_by(User.id.asc()).all()

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
        report_summary = self._build_student_report_summary(
            total, correct, len(wrong_records), recent_focus
        )

        return StudentInsight(
            user_id=student.id,
            student_name=student.username,
            mastery=mastery,
            recent_focus=recent_focus,
            mistake_count=len(wrong_records),
            report_summary=report_summary,
        )

    def _estimate_student_mastery(
        self, db: Session, user_id: int, records: list[AnswerRecord]
    ) -> int:
        """Estimate mastery from profile first, then real answer correctness."""

        profile = db.get(UserProfile, user_id)
        mastery_json = (
            profile.mastery_json if profile and isinstance(profile.mastery_json, dict) else {}
        )
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
        return ""

    def _build_student_report_summary(
        self, total: int, correct: int, mistakes: int, recent_focus: str
    ) -> str:
        """Create a concise teacher-facing summary without fabricated data."""

        if total == 0:
            return ""
        correct_rate = round((correct / total) * 100)
        if mistakes == 0:
            return f"已完成 {total} 次作答，正确率 {correct_rate}%，可围绕 {recent_focus} 提升迁移应用。"
        return (
            f"已完成 {total} 次作答，正确率 {correct_rate}%，建议优先复盘 {recent_focus} 相关错题。"
        )

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
            name = knowledge_point.name if knowledge_point is not None else ""
            if not name:
                continue
            mistake_counts[name] += 1
            affected_students[name].add(record.user_id)

        return [
            KnowledgePointMistakeStat(
                knowledge_point=name,
                mistake_count=count,
                affected_students=len(affected_students[name]),
                suggested_direction=self._suggest_direction_for_weak_point(
                    name, count, len(affected_students[name])
                ),
            )
            for name, count in mistake_counts.most_common(5)
        ]

    def _suggest_direction_for_weak_point(
        self, knowledge_point: str, mistake_count: int, affected_count: int
    ) -> str:
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
            return model.model_dump()
        if hasattr(model, "dict"):
            return model.dict()
        raise TypeError(f"Unsupported model type: {type(model)!r}")

    def _teacher_class(self, db: Session, class_id: int, teacher_user_id: int) -> Classroom:
        record = db.query(Classroom).filter_by(id=class_id, teacher_user_id=teacher_user_id).first()
        if record is None:
            raise ValueError("Class not found or not owned by the current teacher.")
        return record

    def _ensure_class_access(self, db: Session, class_id: int, user_id: int, role: str) -> None:
        if role == "admin":
            return
        if (
            role == "teacher"
            and db.query(Classroom).filter_by(id=class_id, teacher_user_id=user_id).first()
        ):
            return
        if (
            role == "student"
            and db.query(ClassEnrollment)
            .filter_by(class_id=class_id, student_user_id=user_id)
            .first()
        ):
            return
        raise PermissionError("You do not have access to this class.")

    def _class_to_item(self, db: Session, record: Classroom) -> ClassItem:
        return ClassItem(
            id=record.id,
            name=record.name,
            subject=record.subject,
            teacher_name=record.teacher_name,
            course_id=record.course_id,
            student_count=db.query(ClassEnrollment).filter_by(class_id=record.id).count(),
        )

    def _assignment_to_item(self, db: Session, record: Assignment) -> AssignmentItem:
        return AssignmentItem(
            id=record.id,
            class_id=record.class_id,
            title=record.title,
            description=record.description,
            due_at=record.due_at,
            status=record.status,
            created_at=record.created_at,
            submission_count=db.query(AssignmentSubmission)
            .filter_by(assignment_id=record.id)
            .count(),
        )

    def _submission_to_item(self, db: Session, record: AssignmentSubmission) -> SubmissionItem:
        student = db.get(User, record.student_user_id)
        return SubmissionItem(
            id=record.id,
            assignment_id=record.assignment_id,
            student_user_id=record.student_user_id,
            student_name=student.username if student else f"用户 {record.student_user_id}",
            content=record.content,
            attachment_url=record.attachment_url,
            status=record.status,
            submitted_at=record.submitted_at,
            score=record.score,
            teacher_comment=record.teacher_comment or "",
            reviewed_at=record.reviewed_at,
        )

    def _discussion_to_item(self, db: Session, record: DiscussionThread) -> DiscussionItem:
        author = db.get(User, record.author_user_id)
        replies = (
            db.query(DiscussionReply)
            .filter_by(thread_id=record.id)
            .order_by(DiscussionReply.id.asc())
            .all()
        )
        return DiscussionItem(
            id=record.id,
            class_id=record.class_id,
            author_user_id=record.author_user_id,
            author_name=author.username if author else f"用户 {record.author_user_id}",
            title=record.title,
            content=record.content,
            status=record.status,
            created_at=record.created_at,
            replies=[
                DiscussionReplyItem(
                    id=item.id,
                    author_user_id=item.author_user_id,
                    author_name=(
                        db.get(User, item.author_user_id).username
                        if db.get(User, item.author_user_id)
                        else f"用户 {item.author_user_id}"
                    ),
                    content=item.content,
                    created_at=item.created_at,
                )
                for item in replies
            ],
        )

    def _notification_to_item(self, record: Notification) -> NotificationItem:
        return NotificationItem(
            id=record.id,
            title=record.title,
            content=record.content,
            type=record.type,
            related_type=record.related_type,
            related_id=record.related_id,
            is_read=record.is_read,
            created_at=record.created_at,
        )

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
            students = self._list_students(db, scope.class_id)

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
