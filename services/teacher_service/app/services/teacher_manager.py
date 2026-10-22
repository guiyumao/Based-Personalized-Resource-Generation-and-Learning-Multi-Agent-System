"""Teacher service manager with lightweight aggregation over evaluation-service."""

from __future__ import annotations

import logging
import secrets
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from statistics import mean

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from common.assignment_access import student_assignment_clause
from common.config import get_settings
from common.db.session import SessionLocal
from common.learning_evidence import load_evidence, resolve_point, summarize
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
    HomeworkAttachment,
    KnowledgePoint,
    LearningPath,
    Notification,
    SubmissionRevision,
    TeachingScope,
    User,
    UserProfile,
)
from common.notifications import emit, visible
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

from .classroom_membership import ClassroomMembership
from .homework_files import MAX_TOTAL_BYTES, current_files, descriptor

logger = logging.getLogger(__name__)


class TeacherManager(ClassroomMembership):
    """Store teacher-created classes and aggregate learner details from evaluation-service."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _lock_write(self, db):
        # SQLite has no row locks. Serialize the short write transaction before reads.
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))

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
            self._lock_write(db)
            course = Course(
                title=payload.name,
                subject=payload.subject,
                description=payload.description or f"{payload.name}课程",
                teacher_user_id=teacher_user_id,
            )
            db.add(course)
            db.flush()
            record = Classroom(
                name=payload.name,
                subject=payload.subject,
                teacher_name=payload.teacher_name or db.get(User, teacher_user_id).username,
                invite_code=secrets.token_hex(8).upper(),
                teacher_user_id=teacher_user_id,
                join_mode=payload.join_mode,
                description=payload.description,
                objective=payload.objective,
                syllabus=payload.syllabus,
                semester=payload.semester,
                is_public=payload.is_public,
                capacity=payload.capacity,
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
            self._lock_write(db)
            classroom = self._teacher_class(db, class_id, teacher_user_id)
            if classroom.status != "active":
                raise ValueError("班级已停用")
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
                emit(
                    db,
                    user_id=student_user_id,
                    sender_id=teacher_user_id,
                    event_key=f"enrollment:{class_id}:{student_user_id}",
                    title="你已加入新班级",
                    content=f"已加入 {classroom.name}，后续作业和讨论将在班级空间展示。",
                    type="class",
                    related_type="class",
                    related_id=class_id,
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
            self._lock_write(db)
            classroom = self._teacher_class(db, payload.class_id, teacher_user_id)
            if classroom.status != "active":
                raise ValueError("班级已停用")
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
                emit(
                    db,
                    event_key=f"assignment:{record.id}",
                    sender_id=teacher_user_id,
                    user_id=enrollment.student_user_id,
                    title=f"新作业：{record.title}",
                    content=record.description,
                    type="assignment",
                    related_type="assignment",
                    related_id=record.id,
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
                .filter(Assignment.class_id.in_(class_ids), student_assignment_clause(student_user_id))
                .order_by(Assignment.id.desc())
                .all()
            )
            return [self._assignment_to_item(db, item, student_user_id) for item in records]

    def submit_assignment(
        self,
        assignment_id: int,
        payload: SubmissionCreate,
        student_user_id: int,
    ) -> SubmissionItem:
        """Create or update one student's submission while preserving cutoff checks."""

        with SessionLocal() as db:
            self._lock_write(db)
            assignment = db.query(Assignment).filter_by(id=assignment_id).with_for_update().first()
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
            from common.assignment_access import can_access_assignment
            if not can_access_assignment(db, assignment_id, student_user_id):
                raise PermissionError("该补强作业仅面向指定学生")
            if db.get(Classroom, assignment.class_id).status != "active":
                raise RuntimeError("班级已停用，无法提交")
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
            from common.models.teacher_support import ReinforcementAttempt, ReinforcementDraft
            reinforcement = db.query(ReinforcementDraft).filter_by(assignment_id=assignment_id).first()
            if reinforcement:
                existing_attempt = db.query(ReinforcementAttempt).filter_by(draft_id=reinforcement.id).first()
                if existing_attempt:
                    if existing_attempt.answers != payload.answers:
                        raise RuntimeError("已提交并展示参考答案，不能覆盖首次作答")
                    return self._submission_to_item(db, record)
                if payload.answers is None or len(payload.answers) != len(reinforcement.questions) or any(not a.strip() for a in payload.answers):
                    raise RuntimeError("请逐题完成全部补强练习后提交")
            previous_ids = [f["id"] for f in current_files(db, record.id)] if record else []
            selected_ids = (
                payload.attachment_ids if payload.attachment_ids is not None else previous_ids
            )
            if len(selected_ids) != len(set(selected_ids)):
                raise RuntimeError("附件不能重复选择")
            selected_files = (
                db.query(HomeworkAttachment).filter(HomeworkAttachment.id.in_(selected_ids)).all()
                if selected_ids
                else []
            )
            if len(selected_files) != len(selected_ids) or any(
                f.student_user_id != student_user_id
                or f.assignment_id != assignment_id
                or (
                    f.submission_id is not None and (record is None or f.submission_id != record.id)
                )
                for f in selected_files
            ):
                raise PermissionError("附件不存在或不属于本人的本次作业")
            if sum(f.size_bytes for f in selected_files) > MAX_TOTAL_BYTES:
                raise RuntimeError("本次附件总大小不能超过100MB")
            if not payload.content.strip() and not selected_files and not (reinforcement and payload.answers):
                raise RuntimeError("请填写作业内容或选择至少一个附件")
            if record is None:
                record = AssignmentSubmission(
                    assignment_id=assignment_id,
                    student_user_id=student_user_id,
                    content=payload.content.strip(),
                    attachment_url=payload.attachment_url,
                )
                db.add(record)
            else:
                if (
                    record.content == payload.content.strip()
                    and record.attachment_url == payload.attachment_url
                    and sorted(previous_ids) == sorted(selected_ids)
                ):
                    return self._submission_to_item(db, record)
                if record.status == "reviewed":
                    raise RuntimeError("作业已批改，不能覆盖成绩或重新提交")
                self._snapshot_submission(db, record, student_user_id)
                record.content = payload.content.strip()
                record.attachment_url = payload.attachment_url
                record.status = "submitted"
                record.submitted_at = datetime.utcnow()
                record.score = None
                record.teacher_comment = ""
                record.reviewed_at = None
            db.flush()
            if reinforcement:
                from services.teacher_service.app.services.reinforcement_feedback import (
                    create_attempt,
                )
                create_attempt(db, reinforcement, record, payload.answers, payload.time_spent)
            db.query(HomeworkAttachment).filter_by(submission_id=record.id).update(
                {"is_current": False}
            )
            for file in selected_files:
                file.submission_id = record.id
                file.is_current = True
            db.flush()
            emit(
                db,
                user_id=assignment.teacher_user_id,
                sender_id=student_user_id,
                event_key=f"submission:{record.id}",
                title=f"学生提交作业：{assignment.title}",
                content="学生已提交作业，请进入作业批改查看。",
                type="submission",
                related_type="assignment",
                related_id=assignment.id,
            )
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
            self._lock_write(db)
            record = (
                db.query(AssignmentSubmission).filter_by(id=submission_id).with_for_update().first()
            )
            assignment = db.get(Assignment, record.assignment_id) if record else None
            if (
                record is None
                or assignment is None
                or assignment.teacher_user_id != teacher_user_id
            ):
                raise ValueError("Submission not found.")
            if (
                record.status == "reviewed"
                and record.score == payload.score
                and record.teacher_comment == payload.comment.strip()
            ):
                return self._submission_to_item(db, record)
            self._snapshot_submission(db, record, teacher_user_id)
            record.score = payload.score
            record.teacher_comment = payload.comment.strip()
            record.status = "reviewed"
            record.reviewed_at = datetime.utcnow()
            emit(
                db,
                user_id=record.student_user_id,
                sender_id=teacher_user_id,
                event_key=f"review:{record.id}:"
                + sha256(
                    f"{record.submitted_at}:{payload.score}:{payload.comment.strip()}".encode()
                ).hexdigest(),
                title=f"作业已批改：{assignment.title}",
                content=f"得分 {payload.score:g}。{payload.comment.strip()}",
                type="review",
                related_type="assignment",
                related_id=assignment.id,
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
            db.flush()
            if role == "student" and payload.class_id is not None:
                classroom = db.get(Classroom, payload.class_id)
                emit(
                    db,
                    user_id=classroom.teacher_user_id,
                    sender_id=user_id,
                    event_key=f"discussion:{record.id}",
                    title=f"学生课程提问：{record.title}",
                    content=record.content,
                    type="discussion",
                    related_type="discussion",
                    related_id=record.id,
                )
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
                        sender_id=user_id,
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
                visible(db, db.get(User, user_id)).order_by(Notification.id.desc()).limit(100).all()
            )
            return [self._notification_to_item(item) for item in records]

    def mark_notification_read(self, notification_id: int, user_id: int) -> NotificationItem:
        with SessionLocal() as db:
            record = visible(db, db.get(User, user_id)).filter_by(id=notification_id).first()
            if record is None:
                raise ValueError("Notification not found.")
            record.is_read = True
            record.read_at = record.read_at or datetime.utcnow()
            db.commit()
            db.refresh(record)
            return self._notification_to_item(record)

    def list_student_insights(self, class_id: int) -> list[StudentInsight]:
        """Return teacher-facing learner insight cards."""

        _ = class_id
        with SessionLocal() as db:
            students = self._list_students(db, class_id)
            return [self._build_student_insight(db, student, class_id) for student in students]

    def create_teaching_scope(self, payload: TeachingScopeCreate) -> TeachingScopeItem:
        """Persist one teacher-defined learning scope in the shared database."""

        with SessionLocal() as db:
            self._lock_write(db)
            classroom = db.get(Classroom, payload.class_id)
            if classroom is None or classroom.status != "active":
                raise ValueError("班级不存在或已停用")
            if (
                payload.student_user_id
                and not db.query(ClassEnrollment)
                .filter_by(class_id=payload.class_id, student_user_id=payload.student_user_id)
                .first()
            ):
                raise ValueError("投放学生不是本班成员")
            record = TeachingScope(**self._to_dict(payload))
            db.add(record)
            db.flush()
            self._publish_scope_to_students(db, record)
            db.refresh(record)
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
            visibility = (TeachingScope.student_user_id == user_id) & TeachingScope.class_id.in_(
                class_ids
            )
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

    def _class_answers(self, db, class_id, student_ids):
        classroom = db.get(Classroom, class_id)
        if not classroom or not student_ids:
            return []
        from common.models.teacher_support import CourseResourceDelivery
        names = {
            point
            for scope in db.query(TeachingScope).filter(
                TeachingScope.class_id == class_id,
                TeachingScope.student_user_id.is_(None) | TeachingScope.student_user_id.in_(student_ids),
            ).all()
            for point in (scope.knowledge_points or [])
        }
        names.update(point for delivery in db.query(CourseResourceDelivery).filter(
            CourseResourceDelivery.class_id == class_id,
            CourseResourceDelivery.student_user_id.is_(None) | CourseResourceDelivery.student_user_id.in_(student_ids),
        ).all() for point in (delivery.knowledge_points or []))
        points = [
            point
            for name in names
            if (point := resolve_point(db, name, subject=classroom.subject)) is not None
        ]
        evidence_ids = set()
        for student_id in student_ids:
            for point in points:
                evidence_ids.update(
                    summarize(load_evidence(db, student_id, point=point))["evidence_ids"]
                )
        if not evidence_ids:
            return []
        return (
            db.query(AnswerRecord)
            .join(Exercise, Exercise.id == AnswerRecord.exercise_id)
            .filter(
                AnswerRecord.id.in_(evidence_ids),
                Exercise.knowledge_point_id.in_([p.id for p in points]),
            )
            .order_by(AnswerRecord.created_at.desc(), AnswerRecord.id.desc())
            .all()
        )

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

            homework = (
                db.query(AssignmentSubmission)
                .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
                .filter(
                    Assignment.class_id == class_id,
                    AssignmentSubmission.student_user_id.in_(student_ids),
                )
                .all()
            )
            scores = [r.score for r in homework if r.status == "reviewed" and r.score is not None]
            records = self._class_answers(db, class_id, student_ids)
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
                homework_submissions=len(homework),
                homework_reviewed=len(scores),
                homework_average_score=round(mean(scores), 2) if scores else None,
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

        with SessionLocal() as db:
            records = self._class_answers(db, class_id, [user_id])
            mistakes = []
            for record in records:
                if record.is_correct is not False:
                    continue
                exercise = db.get(Exercise, record.exercise_id)
                point = db.get(KnowledgePoint, exercise.knowledge_point_id)
                mistakes.append(
                    MistakeNotebookItem(
                        exercise_id=exercise.id,
                        knowledge_point=point.name,
                        question_type=exercise.type,
                        user_answer=record.user_answer or "",
                        correct_answer=exercise.answer,
                        analysis=exercise.analysis or "",
                        suggested_action="复习本班教学范围中的相关知识点",
                    )
                )
            report = TeacherReportDetail(
                report_type="class",
                user_id=user_id,
                title="本班学习证据",
                summary=insight.report_summary,
                strengths=[],
                weaknesses=[m.knowledge_point for m in mistakes],
                next_actions=[
                    "本页仅展示本班已配置教学范围内的练习，不读取学生其他课程的私人报告。"
                ],
            )
            return StudentLearningDetail(
                **self._to_dict(insight),
                mistake_notebook=mistakes,
                stage_report=report,
                comprehensive_report=report,
            )

    def _find_student_insight(self, class_id: int, user_id: int) -> StudentInsight | None:
        """Return one student insight by class and user id."""

        return next(
            (item for item in self.list_student_insights(class_id) if item.user_id == user_id), None
        )

    def _list_students(self, db: Session, class_id: int | None = None) -> list[User]:
        """Return enrolled students, or all active students for legacy unscoped publishing."""

        query = db.query(User).filter(User.role == "student", User.is_active.is_(True))
        if class_id is not None:
            query = query.join(ClassEnrollment, ClassEnrollment.student_user_id == User.id).filter(
                ClassEnrollment.class_id == class_id
            )
        return query.order_by(User.id.asc()).all()

    def _build_student_insight(
        self, db: Session, student: User, class_id: int | None = None
    ) -> StudentInsight:
        """Build one student card from real profile and answer records."""

        records = (
            db.query(AnswerRecord)
            .filter(AnswerRecord.user_id == student.id)
            .order_by(AnswerRecord.created_at.desc(), AnswerRecord.id.desc())
            .all()
        )
        if class_id is not None:
            records = self._class_answers(db, class_id, [student.id])
        total = len(records)
        correct = sum(1 for record in records if record.is_correct is True)
        wrong_records = [record for record in records if record.is_correct is False]
        mastery = (
            round(sum(r.is_correct is True for r in records) / len(records) * 100)
            if records
            else None
        )
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
            assignment_count=db.query(Assignment).filter_by(class_id=record.id).count(),
            invite_code=record.invite_code,
            status=record.status,
            join_mode=record.join_mode,
            description=record.description,
            objective=record.objective,
            syllabus=record.syllabus,
            semester=record.semester,
            is_public=record.is_public,
            capacity=record.capacity,
        )

    def _assignment_to_item(
        self, db: Session, record: Assignment, student_id: int | None = None
    ) -> AssignmentItem:
        members = db.query(ClassEnrollment).filter_by(class_id=record.class_id).count()
        from common.models.teacher_support import ReinforcementDraft
        reinforcement = db.query(ReinforcementDraft).filter_by(assignment_id=record.id).first()
        if reinforcement:
            members = int(db.query(ClassEnrollment).filter_by(class_id=record.class_id, student_user_id=reinforcement.student_user_id).first() is not None)
        submissions = db.query(AssignmentSubmission).filter_by(assignment_id=record.id).all()
        own = next((r for r in submissions if r.student_user_id == student_id), None)
        classroom = db.get(Classroom, record.class_id)
        return AssignmentItem(
            target_student_id=reinforcement.student_user_id if reinforcement else None,
            practice_questions=[
                dict(q) if student_id is None or own else
                {key: value for key, value in q.items() if key not in ("answer", "analysis", "evidence_ids")}
                for q in (reinforcement.questions if reinforcement else [])
            ],
            pending_attachments=[
                descriptor(f)
                for f in db.query(HomeworkAttachment)
                .filter_by(assignment_id=record.id, student_user_id=student_id, submission_id=None)
                .all()
            ]
            if student_id
            else [],
            class_name=classroom.name if classroom else "",
            student_count=members,
            pending_count=max(
                0,
                members
                - sum(
                    1
                    for r in submissions
                    if db.query(ClassEnrollment)
                    .filter_by(class_id=record.class_id, student_user_id=r.student_user_id)
                    .first()
                ),
            ),
            reviewed_count=sum(r.status == "reviewed" for r in submissions),
            my_submission=self._submission_to_item(db, own) if own else None,
            id=record.id,
            class_id=record.class_id,
            title=record.title,
            description=record.description,
            due_at=record.due_at,
            status=(
                "inactive"
                if classroom and classroom.status != "active"
                else "expired"
                if record.due_at and datetime.utcnow() > record.due_at
                else record.status
            ),
            created_at=record.created_at,
            submission_count=db.query(AssignmentSubmission)
            .filter_by(assignment_id=record.id)
            .count(),
        )

    def _snapshot_submission(self, db, record, actor_id):
        db.add(
            SubmissionRevision(
                submission_id=record.id,
                actor_user_id=actor_id,
                snapshot={
                    "content": record.content,
                    "attachments": current_files(db, record.id),
                    "status": record.status,
                    "score": record.score,
                    "teacher_comment": record.teacher_comment or "",
                    "submitted_at": record.submitted_at.isoformat(),
                },
            )
        )

    def _submission_to_item(self, db: Session, record: AssignmentSubmission) -> SubmissionItem:
        student = db.get(User, record.student_user_id)
        from common.models.teacher_support import ReinforcementAttempt
        from services.teacher_service.app.services.reinforcement_feedback import attempt_item
        return SubmissionItem(
            practice_result=attempt_item(db.query(ReinforcementAttempt).filter_by(submission_id=record.id).first()),
            attachments=current_files(db, record.id),
            history=[
                dict(r.snapshot, recorded_at=r.created_at.isoformat())
                for r in db.query(SubmissionRevision)
                .filter_by(submission_id=record.id)
                .order_by(SubmissionRevision.id)
                .all()
            ],
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

    def _publish_scope_to_students(
        self, db: Session, scope: TeachingScope, only_student: User | None = None
    ) -> None:
        """Turn a teacher scope into active student learning paths."""

        if only_student is not None:
            students = [only_student]
        elif scope.student_user_id is not None:
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
                # Only retire the previous scope of the *same* class. A learner who
                # takes several teaching classes must keep one active path per class
                # instead of losing the earlier course when a new scope is published.
                previous = (item.path_data_json or {}).get("teacher_scope") or {}
                if previous.get("class_id") == scope.class_id:
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
