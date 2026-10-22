"""Business logic for platform check-ins, teacher tasks and classroom attendance.

Design rules enforced here:

* the platform daily check-in is the student's own habit record and has no
  classroom/course reference; streak, calendar and totals come only from it;
* teacher task completion and classroom attendance never share its denominator;
* teacher task periods are derived deterministically from the persisted
  schedule, so a replayed request cannot invent an extra occurrence;
* notifications are emitted inside the same transaction as the business write.
"""

from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from common.db.session import SessionLocal
from common.models.checkin import (
    AttendanceRecord,
    AttendanceSession,
    CheckinAuditLog,
    CheckinSubmissionRevision,
    CheckinTask,
    CheckinTaskSubmission,
    PlatformDailyCheckin,
)
from common.models.learning import ClassEnrollment, Classroom, User
from common.notifications import emit
from services.teacher_service.app.schemas.checkin import (
    AdminCheckinOverview,
    AttendanceLive,
    AttendanceSessionCreate,
    AttendanceSessionItem,
    AttendanceStudentRow,
    AttendanceUpdatePayload,
    CheckinHome,
    CheckinPeriodItem,
    CheckinReviewPayload,
    CheckinSubmissionItem,
    CheckinSubmitPayload,
    CheckinTaskCompletion,
    CheckinTaskCreate,
    CheckinTaskDetail,
    CheckinTaskItem,
    CheckinTaskUpdate,
    CheckinTrendPoint,
    ClassCheckinStat,
    DailyCheckinItem,
    DailyCheckinPayload,
    PlatformCalendarDay,
    PlatformCheckinCalendar,
    PlatformCheckinStatus,
    StudentTaskSummary,
    TeacherCheckinOverview,
)

TZ = ZoneInfo("Asia/Shanghai")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_PERIOD_DAYS = 730
MAX_TASK_ITEMS = 200


def local_today() -> date:
    """Return the current date in the configured school timezone."""

    return datetime.now(TZ).date()


def _local_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(TZ).date()


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _period_due(day: date, due_time: str) -> datetime:
    hour, minute = (int(part) for part in due_time.split(":"))
    local = datetime.combine(day, datetime.min.time()).replace(
        hour=hour, minute=minute, tzinfo=TZ
    )
    return local.astimezone(UTC).replace(tzinfo=None)


def _task_periods(task: CheckinTask, until: date | None = None) -> list[tuple[str, datetime]]:
    """Derive the concrete occurrences of one task from its stored schedule."""

    start = _local_date(task.start_at)
    end = _local_date(task.end_at)
    if until is not None:
        end = min(end, until)
    if end < start:
        return []
    if task.frequency == "once":
        return [(start.isoformat(), task.end_at)]
    weekdays = set(task.weekly_days or [])
    periods: list[tuple[str, datetime]] = []
    cursor = start
    while cursor <= end and len(periods) < MAX_PERIOD_DAYS:
        if task.frequency == "daily" or cursor.isoweekday() in weekdays:
            periods.append((cursor.isoformat(), _period_due(cursor, task.due_time)))
        cursor += timedelta(days=1)
    return periods


def _eligible_students(db, class_id: int) -> list[User]:
    return (
        db.query(User)
        .join(ClassEnrollment, ClassEnrollment.student_user_id == User.id)
        .filter(ClassEnrollment.class_id == class_id, User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )


def _class_name(db, class_id: int) -> str:
    room = db.get(Classroom, class_id)
    return room.name if room else ""


def _submission_snapshot(row: CheckinTaskSubmission) -> dict:
    return {
        "content": row.content,
        "attachment_ids": list(row.attachment_ids or []),
        "status": row.status,
        "score": row.score,
        "review_comment": row.review_comment,
        "version": row.version,
        "period_key": row.period_key,
    }


def _submission_item(
    db,
    row: CheckinTaskSubmission,
    task: CheckinTask | None = None,
    student_name: str | None = None,
    with_history: bool = False,
) -> CheckinSubmissionItem:
    task = task or db.get(CheckinTask, row.task_id)
    owner = db.get(User, row.student_user_id)
    history = []
    if with_history:
        revisions = (
            db.query(CheckinSubmissionRevision)
            .filter_by(submission_id=row.id)
            .order_by(CheckinSubmissionRevision.id)
            .all()
        )
        history = [
            {"action": item.action, "recorded_at": item.created_at, **item.snapshot}
            for item in revisions
        ]
    return CheckinSubmissionItem(
        id=row.id,
        task_id=row.task_id,
        task_title=task.title if task else "",
        class_name=_class_name(db, task.class_id) if task else "",
        student_user_id=row.student_user_id,
        student_name=student_name or (owner.username if owner else ""),
        period_key=row.period_key,
        period_due_at=row.period_due_at,
        content=row.content,
        attachment_ids=list(row.attachment_ids or []),
        status=row.status,
        submitted_at=row.submitted_at,
        reviewed_at=row.reviewed_at,
        review_comment=row.review_comment,
        score=row.score,
        version=row.version,
        late=row.submitted_at > row.period_due_at,
        history=history,
    )


def _daily_item(row: PlatformDailyCheckin) -> DailyCheckinItem:
    return DailyCheckinItem(
        id=row.id,
        checkin_date=row.checkin_date,
        checkin_at=row.checkin_at,
        goal=row.goal,
        reflection=row.reflection,
    )


def _period_state(
    task: CheckinTask,
    due_at: datetime,
    submission: CheckinTaskSubmission | None,
    now: datetime,
) -> str:
    if task.status == "closed":
        return "closed"
    if task.status != "published":
        return "draft"
    if submission is not None:
        return {
            "approved": "approved",
            "returned": "returned",
            "submitted": "pending_review",
        }.get(submission.status, "pending_review")
    if now < task.start_at:
        return "not_started"
    if now > due_at:
        return "overdue"
    return "pending"


def _can_submit(task: CheckinTask, due_at: datetime, submission, now: datetime) -> bool:
    if task.status != "published":
        return False
    if now < task.start_at:
        return False
    if submission is not None and submission.status == "approved":
        return False
    return now <= due_at or bool(task.allow_late)


class CheckinManager:
    """Transactional manager shared by the student, teacher and admin routes."""

    def _lock_write(self, db) -> None:
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))

    # ---------------------------------------------------------------- helpers
    def _teacher_task(self, db, task_id: int, teacher_id: int, role: str) -> CheckinTask:
        task = db.get(CheckinTask, task_id)
        if task is None:
            raise ValueError("打卡任务不存在")
        if role != "admin" and task.teacher_user_id != teacher_id:
            raise PermissionError("无权管理该打卡任务")
        return task

    def _teacher_session(self, db, session_id: int, teacher_id: int) -> AttendanceSession:
        session = db.get(AttendanceSession, session_id)
        if session is None:
            raise ValueError("签到活动不存在")
        if session.teacher_user_id != teacher_id:
            raise PermissionError("无权管理该签到活动")
        return session

    def _teacher_class(self, db, class_id: int, teacher_id: int) -> Classroom:
        room = db.get(Classroom, class_id)
        if room is None:
            raise ValueError("班级不存在")
        if room.teacher_user_id != teacher_id:
            raise PermissionError("无权管理该班级")
        return room

    def _enrolled(self, db, class_id: int, student_id: int) -> bool:
        return (
            db.query(ClassEnrollment.id)
            .filter_by(class_id=class_id, student_user_id=student_id)
            .first()
            is not None
        )

    def _audit(
        self,
        db,
        actor_id: int | None,
        action: str,
        target_type: str,
        target_id: int | None,
        reason: str = "",
        before: dict | None = None,
        after: dict | None = None,
    ) -> None:
        db.add(
            CheckinAuditLog(
                actor_user_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                reason=reason[:500],
                before_json=before or {},
                after_json=after or {},
            )
        )

    def _task_stats(self, db, task: CheckinTask, now: datetime) -> dict:
        students = _eligible_students(db, task.class_id)
        periods = _task_periods(task, until=local_today())
        expected_periods = [period for period in periods if period[1] <= now]
        expected_keys = {key for key, _ in expected_periods}
        submissions = db.query(CheckinTaskSubmission).filter_by(task_id=task.id).all()
        approved = [row for row in submissions if row.status == "approved"]
        expected = len(expected_periods) * len(students)
        approved_expected = sum(1 for row in approved if row.period_key in expected_keys)
        return {
            "student_count": len(students),
            "submitted_count": len(submissions),
            "approved_count": len(approved),
            "pending_review_count": sum(1 for row in submissions if row.status == "submitted"),
            "expected_count": expected,
            "completion_rate": round(approved_expected / expected * 100, 1) if expected else None,
        }

    # -------------------------------------------------- platform daily check-in
    def daily_status(self, user_id: int) -> PlatformCheckinStatus:
        today = local_today()
        with SessionLocal() as db:
            row = (
                db.query(PlatformDailyCheckin)
                .filter_by(user_id=user_id, checkin_date=today.isoformat())
                .first()
            )
            streak, total = self._streak_and_total(db, user_id)
            week_start = today - timedelta(days=today.weekday())
            week_days = (
                db.query(PlatformDailyCheckin)
                .filter(
                    PlatformDailyCheckin.user_id == user_id,
                    PlatformDailyCheckin.checkin_date >= week_start.isoformat(),
                    PlatformDailyCheckin.checkin_date <= today.isoformat(),
                )
                .count()
            )
            month_days = (
                db.query(PlatformDailyCheckin)
                .filter(
                    PlatformDailyCheckin.user_id == user_id,
                    PlatformDailyCheckin.checkin_date.like(f"{today.strftime('%Y-%m')}-%"),
                )
                .count()
            )
            return PlatformCheckinStatus(
                today=today.isoformat(),
                checked_in=row is not None,
                today_checkin=_daily_item(row) if row else None,
                current_streak=streak,
                total_days=total,
                week_days=week_days,
                week_goal=7,
                month_days=month_days,
            )

    def daily_checkin(self, user_id: int, payload: DailyCheckinPayload) -> PlatformCheckinStatus:
        today = local_today().isoformat()
        with SessionLocal() as db:
            self._lock_write(db)
            row = (
                db.query(PlatformDailyCheckin)
                .filter_by(user_id=user_id, checkin_date=today)
                .first()
            )
            if row is None:
                row = PlatformDailyCheckin(
                    user_id=user_id,
                    checkin_date=today,
                    goal=payload.goal,
                    reflection=payload.reflection,
                    timezone="Asia/Shanghai",
                )
                db.add(row)
                try:
                    with db.begin_nested():
                        db.flush()
                except IntegrityError:
                    db.rollback()
                    row = (
                        db.query(PlatformDailyCheckin)
                        .filter_by(user_id=user_id, checkin_date=today)
                        .first()
                    )
                else:
                    db.commit()
            else:
                if payload.goal or payload.reflection:
                    row.goal = payload.goal or row.goal
                    row.reflection = payload.reflection or row.reflection
                    db.commit()
        return self.daily_status(user_id)

    def daily_history(self, user_id: int, limit: int = 120) -> list[DailyCheckinItem]:
        with SessionLocal() as db:
            rows = (
                db.query(PlatformDailyCheckin)
                .filter_by(user_id=user_id)
                .order_by(PlatformDailyCheckin.checkin_date.desc())
                .limit(min(limit, 400))
                .all()
            )
            return [_daily_item(row) for row in rows]

    def daily_calendar(self, user_id: int, month: str) -> PlatformCheckinCalendar:
        try:
            year, month_no = (int(part) for part in month.split("-"))
            first = date(year, month_no, 1)
        except (ValueError, TypeError):
            raise ValueError("月份格式必须为 YYYY-MM") from None
        next_month = date(first.year + (first.month == 12), (first.month % 12) + 1, 1)
        last = next_month - timedelta(days=1)
        with SessionLocal() as db:
            rows = (
                db.query(PlatformDailyCheckin)
                .filter(
                    PlatformDailyCheckin.user_id == user_id,
                    PlatformDailyCheckin.checkin_date >= first.isoformat(),
                    PlatformDailyCheckin.checkin_date <= last.isoformat(),
                )
                .order_by(PlatformDailyCheckin.checkin_date)
                .all()
            )
            streak, total = self._streak_and_total(db, user_id)
            return PlatformCheckinCalendar(
                month=month,
                days=[
                    PlatformCalendarDay(
                        date=row.checkin_date,
                        checked_in=True,
                        goal=row.goal,
                        reflection=row.reflection,
                    )
                    for row in rows
                ],
                streak=streak,
                total_days=total,
            )

    # ---------------------------------------------------------- student tasks
    def _student_task_item(
        self, db, task: CheckinTask, student_id: int, now: datetime
    ) -> CheckinTaskItem:
        periods = _task_periods(task)
        today_key = local_today().isoformat()
        period = next((item for item in periods if item[0] == today_key), None)
        submission = None
        if period:
            submission = (
                db.query(CheckinTaskSubmission)
                .filter_by(task_id=task.id, student_user_id=student_id, period_key=period[0])
                .first()
            )
        stats = self._task_stats(db, task, now)
        state = _period_state(task, period[1], submission, now) if period else None
        return CheckinTaskItem(
            id=task.id,
            class_id=task.class_id,
            class_name=_class_name(db, task.class_id),
            course_id=task.course_id,
            title=task.title,
            goal=task.goal,
            description=task.description,
            frequency=task.frequency,
            weekly_days=list(task.weekly_days or []),
            start_at=task.start_at,
            end_at=task.end_at,
            due_time=task.due_time,
            allow_late=task.allow_late,
            review_mode=task.review_mode,
            require_attachment=task.require_attachment,
            knowledge_points=list(task.knowledge_points or []),
            status=task.status,
            created_at=task.created_at,
            published_at=task.published_at,
            closed_at=task.closed_at,
            today_period=period[0] if period else None,
            my_state=state,
            can_submit=bool(period) and _can_submit(task, period[1], submission, now),
            my_submission=_submission_item(db, submission, task) if submission else None,
            **stats,
        )

    def list_student_tasks(
        self, student_id: int, include_closed: bool = False, limit: int = 100
    ) -> list[CheckinTaskItem]:
        now = _utcnow()
        with SessionLocal() as db:
            class_ids = [
                row.class_id
                for row in db.query(ClassEnrollment).filter_by(student_user_id=student_id).all()
            ]
            if not class_ids:
                return []
            query = db.query(CheckinTask).filter(CheckinTask.class_id.in_(class_ids))
            if not include_closed:
                query = query.filter(CheckinTask.status == "published")
            tasks = query.order_by(CheckinTask.id.desc()).limit(min(limit, MAX_TASK_ITEMS)).all()
            return [self._student_task_item(db, task, student_id, now) for task in tasks]

    def student_task_detail(self, task_id: int, student_id: int) -> CheckinTaskDetail:
        now = _utcnow()
        with SessionLocal() as db:
            task = db.get(CheckinTask, task_id)
            if task is None or task.status == "draft":
                raise ValueError("打卡任务不存在")
            if not self._enrolled(db, task.class_id, student_id):
                raise PermissionError("你不在该任务的发布班级中")
            base = self._student_task_item(db, task, student_id, now)
            periods = []
            for key, due in _task_periods(task, until=local_today()):
                submission = (
                    db.query(CheckinTaskSubmission)
                    .filter_by(task_id=task.id, student_user_id=student_id, period_key=key)
                    .first()
                )
                periods.append(
                    CheckinPeriodItem(
                        period_key=key,
                        due_at=due,
                        state=_period_state(task, due, submission, now),
                    )
                )
            teacher = db.get(User, task.teacher_user_id)
            return CheckinTaskDetail(
                **base.model_dump(),
                teacher_name=teacher.username if teacher else "",
                periods=periods[-90:],
            )

    def submit_task(
        self, task_id: int, student_id: int, payload: CheckinSubmitPayload
    ) -> CheckinSubmissionItem:
        now = _utcnow()
        today = local_today()
        with SessionLocal() as db:
            self._lock_write(db)
            task = db.get(CheckinTask, task_id)
            if task is None or task.status != "published":
                raise ValueError("打卡任务不存在或已结束")
            if not self._enrolled(db, task.class_id, student_id):
                raise PermissionError("你不在该任务的发布班级中")
            periods = dict(_task_periods(task, until=today))
            period_key = payload.period_key or next(
                (key for key in periods if key == today.isoformat()), None
            )
            if period_key is None:
                period_key = today.isoformat()
            if period_key not in periods:
                raise ValueError("所选日期不在该任务的打卡周期内")
            due_at = periods[period_key]
            if now < task.start_at:
                raise RuntimeError("任务尚未开始")
            if now > due_at and not task.allow_late:
                raise RuntimeError("已超过截止时间，且该任务不允许逾期提交")
            if task.require_attachment and not payload.attachment_ids:
                raise ValueError("该任务要求上传学习成果附件")
            existing = (
                db.query(CheckinTaskSubmission)
                .filter_by(task_id=task.id, student_user_id=student_id, period_key=period_key)
                .first()
            )
            if existing is not None:
                unchanged = existing.content == payload.content and list(
                    existing.attachment_ids or []
                ) == list(payload.attachment_ids)
                if unchanged and existing.status in ("submitted", "approved"):
                    return _submission_item(db, existing, task, with_history=True)
                if existing.status == "approved":
                    raise RuntimeError("该周期已通过审核，不能覆盖提交")
            status = "approved" if task.review_mode == "auto" else "submitted"
            review_comment = "系统自动验收通过" if task.review_mode == "auto" else ""
            if existing is None:
                row = CheckinTaskSubmission(
                    task_id=task.id,
                    student_user_id=student_id,
                    period_key=period_key,
                    period_due_at=due_at,
                    content=payload.content,
                    attachment_ids=list(payload.attachment_ids),
                    status=status,
                    submitted_at=now,
                    reviewed_at=now if status == "approved" else None,
                    review_comment=review_comment,
                )
                db.add(row)
                try:
                    with db.begin_nested():
                        db.flush()
                except IntegrityError:
                    raise RuntimeError("该周期已提交，请刷新后重试") from None
            else:
                db.add(
                    CheckinSubmissionRevision(
                        submission_id=existing.id,
                        actor_user_id=student_id,
                        action="resubmit",
                        snapshot=_submission_snapshot(existing),
                    )
                )
                row = existing
                row.content = payload.content
                row.attachment_ids = list(payload.attachment_ids)
                row.period_due_at = due_at
                row.status = status
                row.submitted_at = now
                row.reviewed_at = now if status == "approved" else None
                row.reviewer_user_id = None
                row.review_comment = review_comment
                row.score = None
                row.version += 1
            emit(
                db,
                user_id=task.teacher_user_id,
                sender_id=student_id,
                event_key=f"checkin-submitted:{row.id}:{row.version}",
                title="学生提交打卡任务",
                content=f"{db.get(User, student_id).username} 提交了《{task.title}》（{period_key}）",
                type="checkin",
                related_type="checkin_task",
                related_id=task.id,
            )
            db.commit()
            db.refresh(row)
            return _submission_item(db, row, task, with_history=True)

    def list_my_submissions(self, student_id: int, limit: int = 100) -> list[CheckinSubmissionItem]:
        with SessionLocal() as db:
            rows = (
                db.query(CheckinTaskSubmission)
                .filter_by(student_user_id=student_id)
                .order_by(CheckinTaskSubmission.submitted_at.desc())
                .limit(min(limit, 300))
                .all()
            )
            return [_submission_item(db, row) for row in rows]

    # ------------------------------------------------------------ streak stats
    def _streak_dates(self, db, student_id: int) -> set[str]:
        return {
            row[0]
            for row in db.query(PlatformDailyCheckin.checkin_date)
            .filter(PlatformDailyCheckin.user_id == student_id)
            .all()
            if row[0]
        }

    def _streak_and_total(self, db, student_id: int) -> tuple[int, int]:
        dates = self._streak_dates(db, student_id)
        if not dates:
            return 0, 0
        today = local_today()
        cursor = today if today.isoformat() in dates else today - timedelta(days=1)
        if cursor.isoformat() not in dates:
            return 0, len(dates)
        streak = 0
        while cursor.isoformat() in dates and streak < 3660:
            streak += 1
            cursor -= timedelta(days=1)
        return streak, len(dates)

    # ------------------------------------------------------------------ home
    def home(self, student_id: int) -> CheckinHome:
        now = _utcnow()
        today = local_today()
        today_key = today.isoformat()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        with SessionLocal() as db:
            class_ids = [
                row.class_id
                for row in db.query(ClassEnrollment).filter_by(student_user_id=student_id).all()
            ]
            tasks = (
                db.query(CheckinTask)
                .filter(
                    CheckinTask.class_id.in_(class_ids or [-1]),
                    CheckinTask.status == "published",
                )
                .order_by(CheckinTask.id.desc())
                .limit(MAX_TASK_ITEMS)
                .all()
            )
            due_today = completed_today = 0
            pending: list[StudentTaskSummary] = []
            upcoming: list[StudentTaskSummary] = []
            week_expected = week_approved = 0
            for task in tasks:
                periods = _task_periods(task)
                period_map = dict(periods)
                today_due = period_map.get(today_key)
                submissions = {
                    item.period_key: item
                    for item in db.query(CheckinTaskSubmission)
                    .filter_by(task_id=task.id, student_user_id=student_id)
                    .all()
                }
                if today_due is not None and now >= task.start_at:
                    submission = submissions.get(today_key)
                    state = _period_state(task, today_due, submission, now)
                    if state == "approved":
                        completed_today += 1
                    elif state in ("pending", "overdue", "returned", "not_started"):
                        due_today += 1
                        pending.append(
                            StudentTaskSummary(
                                task_id=task.id,
                                title=task.title,
                                class_name=_class_name(db, task.class_id),
                                task_type="teacher",
                                period_key=today_key,
                                due_at=today_due,
                                state=state,
                                can_submit=_can_submit(task, today_due, submission, now),
                            )
                        )
                for key, due in periods:
                    if key <= today_key or due <= now:
                        continue
                    if due - now > timedelta(days=3):
                        continue
                    submission = submissions.get(key)
                    if submission is not None and submission.status == "approved":
                        continue
                    upcoming.append(
                        StudentTaskSummary(
                            task_id=task.id,
                            title=task.title,
                            class_name=_class_name(db, task.class_id),
                            task_type="teacher",
                            period_key=key,
                            due_at=due,
                            state="pending",
                            can_submit=True,
                        )
                    )
                    if len(upcoming) >= 10:
                        break
                for key, due in periods:
                    if key < week_start.isoformat() or key > week_end.isoformat():
                        continue
                    if due > now:
                        continue
                    week_expected += len(_eligible_students(db, task.class_id))
                    submission = submissions.get(key)
                    if submission is not None and submission.status == "approved":
                        week_approved += 1
            streak, total = self._streak_and_total(db, student_id)
            available = self._available_attendance(db, student_id, now)
            feedback_rows = (
                db.query(CheckinTaskSubmission)
                .filter(
                    CheckinTaskSubmission.student_user_id == student_id,
                    CheckinTaskSubmission.reviewed_at.isnot(None),
                )
                .order_by(CheckinTaskSubmission.reviewed_at.desc())
                .limit(5)
                .all()
            )
            recent_checkins = (
                db.query(PlatformDailyCheckin)
                .filter_by(user_id=student_id)
                .order_by(PlatformDailyCheckin.checkin_date.desc())
                .limit(5)
                .all()
            )
            today_row = (
                db.query(PlatformDailyCheckin)
                .filter_by(user_id=student_id, checkin_date=today_key)
                .first()
            )
            return CheckinHome(
                today=today_key,
                due_today=due_today,
                completed_today=completed_today,
                current_streak=streak,
                total_days=total,
                week_completion_rate=(
                    round(week_approved / week_expected * 100, 1) if week_expected else None
                ),
                week_expected=week_expected,
                week_approved=week_approved,
                pending_tasks=pending[:10],
                upcoming_tasks=upcoming[:10],
                available_attendance=available,
                latest_feedback=[_submission_item(db, row) for row in feedback_rows],
                recent_checkins=[_daily_item(row) for row in recent_checkins],
                today_checked_in=today_row is not None,
            )

    # ------------------------------------------------------------- attendance
    def _session_item(
        self,
        db,
        session: AttendanceSession,
        student_id: int | None = None,
        with_code: bool = False,
    ) -> AttendanceSessionItem:
        records = db.query(AttendanceRecord).filter_by(session_id=session.id).all()
        students = _eligible_students(db, session.class_id)
        counts: dict[str, int] = defaultdict(int)
        for row in records:
            counts[row.status] += 1
        mine = next((row for row in records if row.student_user_id == student_id), None)
        return AttendanceSessionItem(
            id=session.id,
            class_id=session.class_id,
            class_name=_class_name(db, session.class_id),
            title=session.title,
            start_at=session.start_at,
            end_at=session.end_at,
            late_after_at=session.late_after_at,
            status=session.status,
            code=session.code if with_code else None,
            token=session.token if with_code else None,
            my_record=(
                {
                    "id": mine.id,
                    "status": mine.status,
                    "checked_in_at": mine.checked_in_at,
                    "source": mine.source,
                    "note": mine.note,
                }
                if mine
                else None
            ),
            checked_in_count=counts["present"],
            late_count=counts["late"],
            leave_count=counts["leave"],
            absent_count=counts["absent"],
            missing_count=max(0, len(students) - len(records)),
            student_count=len(students),
        )

    def _available_attendance(
        self, db, student_id: int, now: datetime
    ) -> list[AttendanceSessionItem]:
        class_ids = [
            row.class_id
            for row in db.query(ClassEnrollment).filter_by(student_user_id=student_id).all()
        ]
        if not class_ids:
            return []
        sessions = (
            db.query(AttendanceSession)
            .filter(
                AttendanceSession.class_id.in_(class_ids),
                AttendanceSession.status == "open",
                AttendanceSession.start_at <= now,
                AttendanceSession.end_at >= now,
            )
            .order_by(AttendanceSession.id.desc())
            .all()
        )
        return [self._session_item(db, session, student_id) for session in sessions]

    def list_student_attendance(self, student_id: int) -> list[AttendanceSessionItem]:
        now = _utcnow()
        with SessionLocal() as db:
            available = self._available_attendance(db, student_id, now)
            seen = {item.id for item in available}
            class_ids = [
                row.class_id
                for row in db.query(ClassEnrollment).filter_by(student_user_id=student_id).all()
            ]
            history = (
                db.query(AttendanceSession)
                .filter(
                    AttendanceSession.class_id.in_(class_ids or [-1]),
                    AttendanceSession.id.notin_(list(seen) or [-1]),
                )
                .order_by(AttendanceSession.id.desc())
                .limit(50)
                .all()
            )
            return available + [self._session_item(db, row, student_id) for row in history]

    def checkin_attendance(
        self, student_id: int, code: str | None, token: str | None
    ) -> AttendanceSessionItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            session = None
            if token:
                session = db.query(AttendanceSession).filter_by(token=token.strip()).first()
            elif code:
                session = (
                    db.query(AttendanceSession)
                    .filter_by(code=code.strip().upper())
                    .order_by(AttendanceSession.id.desc())
                    .first()
                )
            if session is None:
                raise ValueError("签到码或二维码无效")
            if session.status != "open":
                raise RuntimeError("签到活动已结束，签到码已失效")
            if now < session.start_at:
                raise RuntimeError("签到尚未开始")
            if now > session.end_at:
                raise RuntimeError("签到已截止")
            if not self._enrolled(db, session.class_id, student_id):
                raise PermissionError("你不属于该签到活动的班级")
            status = "late" if session.late_after_at and now > session.late_after_at else "present"
            existing = (
                db.query(AttendanceRecord)
                .filter_by(session_id=session.id, student_user_id=student_id)
                .first()
            )
            if existing is None:
                db.add(
                    AttendanceRecord(
                        session_id=session.id,
                        student_user_id=student_id,
                        status=status,
                        checked_in_at=now,
                        source="token" if token else "code",
                    )
                )
                try:
                    with db.begin_nested():
                        db.flush()
                except IntegrityError:
                    pass
            elif existing.source == "manual":
                raise RuntimeError("教师已人工登记出勤，如有异议请联系教师")
            db.commit()
            return self._session_item(db, session, student_id)

    # ------------------------------------------------------------ teacher tasks
    def create_task(self, teacher_id: int, payload: CheckinTaskCreate) -> CheckinTaskItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            room = self._teacher_class(db, payload.class_id, teacher_id)
            if room.status != "active":
                raise ValueError("班级已停用，无法发布打卡任务")
            task = CheckinTask(
                class_id=room.id,
                course_id=room.course_id,
                teacher_user_id=teacher_id,
                title=payload.title,
                goal=payload.goal,
                description=payload.description,
                frequency=payload.frequency,
                weekly_days=payload.weekly_days,
                start_at=payload.start_at,
                end_at=payload.end_at,
                due_time=payload.due_time,
                allow_late=payload.allow_late,
                review_mode=payload.review_mode,
                require_attachment=payload.require_attachment,
                knowledge_points=payload.knowledge_points,
                status="draft",
            )
            db.add(task)
            db.flush()
            self._audit(db, teacher_id, "task.create", "checkin_task", task.id, "创建打卡任务")
            db.commit()
            db.refresh(task)
            return self._student_task_item(db, task, teacher_id, now)

    def update_task(
        self, task_id: int, teacher_id: int, role: str, payload: CheckinTaskUpdate
    ) -> CheckinTaskItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            task = self._teacher_task(db, task_id, teacher_id, role)
            if task.status in ("closed", "cancelled"):
                raise ValueError("已结束的任务不能修改")
            if task.status == "published" and (
                db.query(CheckinTaskSubmission).filter_by(task_id=task.id).count() > 0
            ):
                raise RuntimeError("任务已有学生提交，不能修改规则")
            room = self._teacher_class(db, payload.class_id, task.teacher_user_id)
            before = {"title": task.title, "frequency": task.frequency, "class_id": task.class_id}
            task.class_id, task.course_id = room.id, room.course_id
            task.title = payload.title
            task.goal = payload.goal
            task.description = payload.description
            task.frequency = payload.frequency
            task.weekly_days = payload.weekly_days
            task.start_at = payload.start_at
            task.end_at = payload.end_at
            task.due_time = payload.due_time
            task.allow_late = payload.allow_late
            task.review_mode = payload.review_mode
            task.require_attachment = payload.require_attachment
            task.knowledge_points = payload.knowledge_points
            self._audit(
                db, teacher_id, "task.update", "checkin_task", task.id, "修改打卡任务", before
            )
            db.commit()
            db.refresh(task)
            return self._student_task_item(db, task, teacher_id, now)

    def _set_task_status(
        self, task_id: int, teacher_id: int, role: str, status: str
    ) -> CheckinTaskItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            task = self._teacher_task(db, task_id, teacher_id, role)
            if task.status == status:
                return self._student_task_item(db, task, teacher_id, now)
            if status == "published":
                if task.status not in ("draft", "closed", "cancelled"):
                    raise ValueError("当前状态不能发布")
                if task.end_at <= now:
                    raise ValueError("任务结束时间已过，请先修改时间")
                task.status = "published"
                task.published_at = now
                task.closed_at = None
                for student in _eligible_students(db, task.class_id):
                    emit(
                        db,
                        user_id=student.id,
                        sender_id=teacher_id,
                        event_key=f"checkin-task-published:{task.id}",
                        title=f"新打卡任务：{task.title}",
                        content=f"{_class_name(db, task.class_id)} 发布了打卡任务，请在截止时间前完成。",
                        type="checkin",
                        related_type="checkin_task",
                        related_id=task.id,
                    )
            else:
                task.status = status
                task.closed_at = now
                if status == "cancelled":
                    for student in _eligible_students(db, task.class_id):
                        emit(
                            db,
                            user_id=student.id,
                            sender_id=teacher_id,
                            event_key=f"checkin-task-cancelled:{task.id}",
                            title=f"打卡任务已取消：{task.title}",
                            content="教师取消了该打卡任务，已提交的历史记录仍可查看。",
                            type="checkin",
                            related_type="checkin_task",
                            related_id=task.id,
                        )
            self._audit(db, teacher_id, f"task.{status}", "checkin_task", task.id, "状态变更")
            db.commit()
            db.refresh(task)
            return self._student_task_item(db, task, teacher_id, now)

    def publish_task(self, task_id: int, teacher_id: int, role: str) -> CheckinTaskItem:
        return self._set_task_status(task_id, teacher_id, role, "published")

    def close_task(self, task_id: int, teacher_id: int, role: str) -> CheckinTaskItem:
        return self._set_task_status(task_id, teacher_id, role, "closed")

    def cancel_task(self, task_id: int, teacher_id: int, role: str) -> CheckinTaskItem:
        return self._set_task_status(task_id, teacher_id, role, "cancelled")

    def list_teacher_tasks(
        self, teacher_id: int, role: str, class_id: int | None = None
    ) -> list[CheckinTaskItem]:
        now = _utcnow()
        with SessionLocal() as db:
            query = db.query(CheckinTask)
            if role != "admin":
                query = query.filter(CheckinTask.teacher_user_id == teacher_id)
            if class_id:
                query = query.filter(CheckinTask.class_id == class_id)
            tasks = query.order_by(CheckinTask.id.desc()).limit(MAX_TASK_ITEMS).all()
            return [self._teacher_task_item(db, task, now) for task in tasks]

    def _teacher_task_item(self, db, task: CheckinTask, now: datetime) -> CheckinTaskItem:
        periods = _task_periods(task, until=local_today())
        today_key = local_today().isoformat()
        today_period = next((due for key, due in periods if key == today_key), None)
        return CheckinTaskItem(
            id=task.id,
            class_id=task.class_id,
            class_name=_class_name(db, task.class_id),
            course_id=task.course_id,
            title=task.title,
            goal=task.goal,
            description=task.description,
            frequency=task.frequency,
            weekly_days=list(task.weekly_days or []),
            start_at=task.start_at,
            end_at=task.end_at,
            due_time=task.due_time,
            allow_late=task.allow_late,
            review_mode=task.review_mode,
            require_attachment=task.require_attachment,
            knowledge_points=list(task.knowledge_points or []),
            status=task.status,
            created_at=task.created_at,
            published_at=task.published_at,
            closed_at=task.closed_at,
            today_period=today_key if today_period else None,
            **self._task_stats(db, task, now),
        )

    def task_completion(
        self, task_id: int, teacher_id: int, role: str, period_key: str | None = None
    ) -> CheckinTaskCompletion:
        now = _utcnow()
        with SessionLocal() as db:
            task = self._teacher_task(db, task_id, teacher_id, role)
            periods = _task_periods(task, until=local_today())
            if not periods:
                raise ValueError("任务尚未生成有效周期")
            due_periods = [item for item in periods if item[1] <= now] or periods
            period_map = dict(periods)
            if period_key is None:
                period_key = due_periods[-1][0]
            if period_key not in period_map:
                raise ValueError("所选周期不在任务时间范围内")
            submissions = {
                row.student_user_id: row
                for row in db.query(CheckinTaskSubmission)
                .filter_by(task_id=task.id, period_key=period_key)
                .all()
            }
            rows = []
            for student in _eligible_students(db, task.class_id):
                submission = submissions.get(student.id)
                state = _period_state(task, period_map[period_key], submission, now)
                rows.append(
                    {
                        "student_user_id": student.id,
                        "student_name": student.username,
                        "state": state,
                        "submitted_at": submission.submitted_at if submission else None,
                        "review_comment": submission.review_comment if submission else "",
                        "score": submission.score if submission else None,
                        "submission_id": submission.id if submission else None,
                        "content": submission.content if submission else "",
                        "attachment_ids": (
                            list(submission.attachment_ids or []) if submission else []
                        ),
                        "version": submission.version if submission else 0,
                    }
                )
            return CheckinTaskCompletion(
                task=self._teacher_task_item(db, task, now),
                period_key=period_key,
                periods=[
                    CheckinPeriodItem(period_key=key, due_at=due) for key, due in periods[-90:]
                ],
                rows=rows,
            )

    def review_submission(
        self, submission_id: int, teacher_id: int, role: str, payload: CheckinReviewPayload
    ) -> CheckinSubmissionItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            row = db.get(CheckinTaskSubmission, submission_id)
            if row is None:
                raise ValueError("提交记录不存在")
            task = self._teacher_task(db, row.task_id, teacher_id, role)
            if row.status == "approved" and payload.verdict == "approve":
                raise RuntimeError("该提交已通过审核")
            db.add(
                CheckinSubmissionRevision(
                    submission_id=row.id,
                    actor_user_id=teacher_id,
                    action="review",
                    snapshot=_submission_snapshot(row),
                )
            )
            row.status = "approved" if payload.verdict == "approve" else "returned"
            row.review_comment = payload.comment
            row.score = payload.score
            row.reviewed_at = now
            row.reviewer_user_id = teacher_id
            title = "打卡任务已通过" if payload.verdict == "approve" else "打卡任务被退回"
            emit(
                db,
                user_id=row.student_user_id,
                sender_id=teacher_id,
                event_key=f"checkin-review:{row.id}:{row.version}:{row.status}",
                title=f"{title}：{task.title}",
                content=(
                    payload.comment
                    or ("教师已通过你的学习成果。" if payload.verdict == "approve" else "请补交后重新提交。")
                ),
                type="checkin",
                related_type="checkin_task",
                related_id=task.id,
            )
            self._audit(
                db,
                teacher_id,
                f"submission.{row.status}",
                "checkin_submission",
                row.id,
                payload.comment,
            )
            db.commit()
            db.refresh(row)
            return _submission_item(db, row, task, with_history=True)

    def batch_review(
        self, submission_ids: list[int], teacher_id: int, role: str, payload: CheckinReviewPayload
    ) -> dict:
        results, skipped = [], []
        for submission_id in submission_ids:
            try:
                results.append(
                    self.review_submission(
                        submission_id, teacher_id, role, payload
                    ).model_dump()
                )
            except (ValueError, PermissionError, RuntimeError) as exc:
                skipped.append({"id": submission_id, "reason": str(exc)})
        return {"reviewed": results, "skipped": skipped}

    def list_task_submissions(
        self, task_id: int, teacher_id: int, role: str, status: str | None = None
    ) -> list[CheckinSubmissionItem]:
        with SessionLocal() as db:
            task = self._teacher_task(db, task_id, teacher_id, role)
            query = db.query(CheckinTaskSubmission).filter_by(task_id=task.id)
            if status:
                query = query.filter(CheckinTaskSubmission.status == status)
            rows = query.order_by(CheckinTaskSubmission.submitted_at.desc()).limit(1000).all()
            names = {row.id: row.username for row in _eligible_students(db, task.class_id)}
            return [
                _submission_item(
                    db,
                    row,
                    task,
                    names.get(row.student_user_id),
                    with_history=True,
                )
                for row in rows
            ]

    def remind_task(
        self, task_id: int, teacher_id: int, role: str, period_key: str | None
    ) -> dict:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            task = self._teacher_task(db, task_id, teacher_id, role)
            periods = dict(_task_periods(task, until=local_today()))
            key = period_key or local_today().isoformat()
            if key not in periods:
                due = [item for item in periods.items() if item[1] <= now]
                if not due:
                    raise ValueError("没有可提醒的有效周期")
                key = due[-1][0]
            submitted = {
                row.student_user_id
                for row in db.query(CheckinTaskSubmission)
                .filter_by(task_id=task.id, period_key=key, status="approved")
                .all()
            }
            count = 0
            for student in _eligible_students(db, task.class_id):
                if student.id in submitted:
                    continue
                emit(
                    db,
                    user_id=student.id,
                    sender_id=teacher_id,
                    event_key=f"checkin-remind:{task.id}:{key}:{student.id}",
                    title=f"打卡提醒：{task.title}",
                    content=f"你在 {key} 的打卡任务尚未完成，请及时提交。",
                    type="checkin",
                    related_type="checkin_task",
                    related_id=task.id,
                )
                count += 1
            db.commit()
            return {"period_key": key, "reminded": count}

    # ------------------------------------------------------- teacher attendance
    def create_attendance(
        self, teacher_id: int, payload: AttendanceSessionCreate
    ) -> AttendanceSessionItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            room = self._teacher_class(db, payload.class_id, teacher_id)
            if room.status != "active":
                raise ValueError("班级已停用，无法发起签到")
            if payload.end_at <= now:
                raise ValueError("签到结束时间已过")
            late_after = payload.late_after_at
            if late_after is None:
                late_after = payload.start_at + (payload.end_at - payload.start_at) / 2
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            session = AttendanceSession(
                class_id=room.id,
                course_id=room.course_id,
                teacher_user_id=teacher_id,
                title=payload.title,
                start_at=payload.start_at,
                end_at=payload.end_at,
                late_after_at=late_after,
                code=code,
                token=secrets.token_urlsafe(24),
                status="open",
            )
            db.add(session)
            db.flush()
            for student in _eligible_students(db, room.id):
                emit(
                    db,
                    user_id=student.id,
                    sender_id=teacher_id,
                    event_key=f"attendance-opened:{session.id}",
                    title=f"课堂签到已开启：{session.title}",
                    content=f"{room.name} 正在签到，请在截止时间前完成签到。",
                    type="attendance",
                    related_type="attendance",
                    related_id=session.id,
                )
            self._audit(
                db, teacher_id, "attendance.create", "attendance_session", session.id, session.title
            )
            db.commit()
            db.refresh(session)
            return self._session_item(db, session, with_code=True)

    def list_teacher_attendance(
        self, teacher_id: int, role: str, class_id: int | None = None
    ) -> list[AttendanceSessionItem]:
        with SessionLocal() as db:
            query = db.query(AttendanceSession)
            if role != "admin":
                query = query.filter(AttendanceSession.teacher_user_id == teacher_id)
            if class_id:
                query = query.filter(AttendanceSession.class_id == class_id)
            sessions = query.order_by(AttendanceSession.id.desc()).limit(100).all()
            return [self._session_item(db, row, with_code=True) for row in sessions]

    def attendance_live(self, session_id: int, teacher_id: int, role: str) -> AttendanceLive:
        with SessionLocal() as db:
            session = db.get(AttendanceSession, session_id)
            if session is None:
                raise ValueError("签到活动不存在")
            if role != "admin" and session.teacher_user_id != teacher_id:
                raise PermissionError("无权查看该签到活动")
            records = {
                row.student_user_id: row
                for row in db.query(AttendanceRecord).filter_by(session_id=session.id).all()
            }
            rows = []
            for student in _eligible_students(db, session.class_id):
                record = records.get(student.id)
                rows.append(
                    AttendanceStudentRow(
                        student_user_id=student.id,
                        student_name=student.username,
                        status=record.status if record else "missing",
                        checked_in_at=record.checked_in_at if record else None,
                        source=record.source if record else "",
                        note=record.note if record else "",
                        record_id=record.id if record else None,
                    )
                )
            return AttendanceLive(
                session=self._session_item(db, session, with_code=True), rows=rows
            )

    def close_attendance(self, session_id: int, teacher_id: int, role: str) -> AttendanceSessionItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            session = self._teacher_session(db, session_id, teacher_id)
            if session.status == "closed":
                return self._session_item(db, session, with_code=True)
            session.status = "closed"
            session.closed_at = now
            existing = {
                row.student_user_id
                for row in db.query(AttendanceRecord).filter_by(session_id=session.id).all()
            }
            for student in _eligible_students(db, session.class_id):
                if student.id in existing:
                    continue
                db.add(
                    AttendanceRecord(
                        session_id=session.id,
                        student_user_id=student.id,
                        status="absent",
                        checked_in_at=None,
                        source="system",
                        note="签到结束未签到",
                        recorded_by=teacher_id,
                    )
                )
            self._audit(db, teacher_id, "attendance.close", "attendance_session", session.id)
            db.commit()
            db.refresh(session)
            return self._session_item(db, session, with_code=True)

    def update_attendance_record(
        self, session_id: int, student_id: int, teacher_id: int, payload: AttendanceUpdatePayload
    ) -> AttendanceSessionItem:
        now = _utcnow()
        with SessionLocal() as db:
            self._lock_write(db)
            session = self._teacher_session(db, session_id, teacher_id)
            if not self._enrolled(db, session.class_id, student_id):
                raise ValueError("该学生不在签到班级中")
            record = (
                db.query(AttendanceRecord)
                .filter_by(session_id=session.id, student_user_id=student_id)
                .first()
            )
            before = (
                {"status": record.status, "source": record.source, "note": record.note}
                if record
                else {}
            )
            if record is None:
                record = AttendanceRecord(
                    session_id=session.id,
                    student_user_id=student_id,
                    status=payload.status,
                    checked_in_at=now if payload.status in ("present", "late") else None,
                    source="manual",
                    note=payload.note or payload.reason,
                    recorded_by=teacher_id,
                )
                db.add(record)
            else:
                if record.source != "manual":
                    record.checked_in_at = (
                        record.checked_in_at
                        if payload.status in ("present", "late") and record.checked_in_at
                        else (now if payload.status in ("present", "late") else None)
                    )
                record.status = payload.status
                record.source = "manual"
                record.note = payload.note or payload.reason
                record.recorded_by = teacher_id
            self._audit(
                db,
                teacher_id,
                "attendance.manual_update",
                "attendance_record",
                record.id,
                payload.reason,
                before,
                {"status": payload.status, "source": "manual"},
            )
            db.commit()
            db.refresh(session)
            return self._session_item(db, session, with_code=True)

    # ------------------------------------------------------------ teacher stats
    def teacher_overview(self, teacher_id: int, role: str) -> TeacherCheckinOverview:
        now = _utcnow()
        today = local_today()
        with SessionLocal() as db:
            class_query = db.query(Classroom)
            if role != "admin":
                class_query = class_query.filter(Classroom.teacher_user_id == teacher_id)
            rooms = class_query.order_by(Classroom.id.desc()).all()
            room_ids = [room.id for room in rooms]
            tasks = (
                db.query(CheckinTask)
                .filter(CheckinTask.class_id.in_(room_ids or [-1]))
                .order_by(CheckinTask.id.desc())
                .limit(MAX_TASK_ITEMS)
                .all()
            )
            sessions = (
                db.query(AttendanceSession)
                .filter(AttendanceSession.class_id.in_(room_ids or [-1]))
                .order_by(AttendanceSession.id.desc())
                .limit(200)
                .all()
            )
            pending_review = (
                db.query(CheckinTaskSubmission)
                .join(CheckinTask, CheckinTask.id == CheckinTaskSubmission.task_id)
                .filter(
                    CheckinTask.class_id.in_(room_ids or [-1]),
                    CheckinTaskSubmission.status == "submitted",
                )
                .count()
            )
            class_stats: list[ClassCheckinStat] = []
            for room in rooms:
                room_tasks = [task for task in tasks if task.class_id == room.id]
                students = _eligible_students(db, room.id)
                approved = expected = 0
                for task in room_tasks:
                    periods = [due for _, due in _task_periods(task, until=today) if due <= now]
                    expected += len(periods) * len(students)
                    approved += (
                        db.query(CheckinTaskSubmission)
                        .filter(
                            CheckinTaskSubmission.task_id == task.id,
                            CheckinTaskSubmission.status == "approved",
                        )
                        .count()
                    )
                records = (
                    db.query(AttendanceRecord)
                    .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
                    .filter(AttendanceSession.class_id == room.id)
                    .all()
                )
                attended = sum(
                    1 for row in records if row.status in ("present", "late", "leave")
                )
                room_pending = (
                    db.query(CheckinTaskSubmission)
                    .join(CheckinTask, CheckinTask.id == CheckinTaskSubmission.task_id)
                    .filter(
                        CheckinTask.class_id == room.id,
                        CheckinTaskSubmission.status == "submitted",
                    )
                    .count()
                )
                low = 0
                if room_tasks:
                    for student in students:
                        student_approved = (
                            db.query(CheckinTaskSubmission)
                            .join(CheckinTask, CheckinTask.id == CheckinTaskSubmission.task_id)
                            .filter(
                                CheckinTaskSubmission.student_user_id == student.id,
                                CheckinTask.class_id == room.id,
                                CheckinTaskSubmission.status == "approved",
                            )
                            .count()
                        )
                        if student_approved == 0:
                            low += 1
                class_stats.append(
                    ClassCheckinStat(
                        class_id=room.id,
                        class_name=room.name,
                        student_count=len(students),
                        task_completion_rate=(
                            round(approved / expected * 100, 1) if expected else None
                        ),
                        attendance_rate=(
                            round(attended / len(records) * 100, 1) if records else None
                        ),
                        pending_review=room_pending,
                        low_participation=low,
                    )
                )
            trend: list[CheckinTrendPoint] = []
            for offset in range(6, -1, -1):
                day = today - timedelta(days=offset)
                key = day.isoformat()
                approved = (
                    db.query(CheckinTaskSubmission)
                    .join(CheckinTask, CheckinTask.id == CheckinTaskSubmission.task_id)
                    .filter(
                        CheckinTask.class_id.in_(room_ids or [-1]),
                        CheckinTaskSubmission.period_key == key,
                        CheckinTaskSubmission.status == "approved",
                    )
                    .count()
                )
                submitted = (
                    db.query(CheckinTaskSubmission)
                    .join(CheckinTask, CheckinTask.id == CheckinTaskSubmission.task_id)
                    .filter(
                        CheckinTask.class_id.in_(room_ids or [-1]),
                        CheckinTaskSubmission.period_key == key,
                        CheckinTaskSubmission.status == "submitted",
                    )
                    .count()
                )
                attendance = 0
                for session in sessions:
                    if _local_date(session.start_at) != day:
                        continue
                    attendance += (
                        db.query(AttendanceRecord)
                        .filter(
                            AttendanceRecord.session_id == session.id,
                            AttendanceRecord.status.in_(["present", "late", "leave"]),
                        )
                        .count()
                    )
                trend.append(
                    CheckinTrendPoint(
                        date=key, approved=approved, submitted=submitted, attendance=attendance
                    )
                )
            today_sessions = [row for row in sessions if _local_date(row.start_at) == today]
            overdue_students = set()
            for task in tasks:
                if task.status != "published":
                    continue
                for key, due in _task_periods(task, until=today):
                    if due >= now:
                        continue
                    approved_ids = {
                        row.student_user_id
                        for row in db.query(CheckinTaskSubmission)
                        .filter_by(task_id=task.id, period_key=key, status="approved")
                        .all()
                    }
                    for student in _eligible_students(db, task.class_id):
                        if student.id not in approved_ids:
                            overdue_students.add((task.id, key, student.id))
            return TeacherCheckinOverview(
                class_count=len(rooms),
                active_task_count=sum(1 for task in tasks if task.status == "published"),
                pending_review_count=pending_review,
                today_attendance_count=len(today_sessions),
                overdue_student_count=len(overdue_students),
                classes=class_stats,
                trend=trend,
                recent_tasks=[self._teacher_task_item(db, task, now) for task in tasks[:6]],
            )

    def admin_overview(self) -> AdminCheckinOverview:
        with SessionLocal() as db:
            audits = (
                db.query(CheckinAuditLog).order_by(CheckinAuditLog.id.desc()).limit(30).all()
            )
            return AdminCheckinOverview(
                task_count=db.query(CheckinTask).count(),
                published_task_count=db.query(CheckinTask)
                .filter(CheckinTask.status == "published")
                .count(),
                submission_count=db.query(CheckinTaskSubmission).count(),
                pending_review_count=db.query(CheckinTaskSubmission)
                .filter(CheckinTaskSubmission.status == "submitted")
                .count(),
                attendance_session_count=db.query(AttendanceSession).count(),
                attendance_record_count=db.query(AttendanceRecord).count(),
                self_checkin_count=db.query(PlatformDailyCheckin).count(),
                recent_audits=[
                    {
                        "id": row.id,
                        "action": row.action,
                        "target_type": row.target_type,
                        "target_id": row.target_id,
                        "reason": row.reason,
                        "actor_user_id": row.actor_user_id,
                        "created_at": row.created_at,
                    }
                    for row in audits
                ],
            )

    def list_audits(self, limit: int = 200) -> list[dict]:
        with SessionLocal() as db:
            rows = (
                db.query(CheckinAuditLog)
                .order_by(CheckinAuditLog.id.desc())
                .limit(min(limit, 500))
                .all()
            )
            return [
                {
                    "id": row.id,
                    "action": row.action,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "reason": row.reason,
                    "before": row.before_json,
                    "after": row.after_json,
                    "actor_user_id": row.actor_user_id,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
