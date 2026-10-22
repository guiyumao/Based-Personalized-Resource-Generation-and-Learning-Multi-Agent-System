"""Classroom schedule: recurring weekly sessions and one-off changes.

All conflict checks are deterministic and run on the server. Students only see
schedules of classrooms they currently belong to; leaving a classroom removes
future occurrences from their timetable while keeping historical learning data.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from common.db.session import SessionLocal
from common.models.checkin import (
    CheckinAuditLog,
    ClassScheduleException,
    ClassSession,
    PersonalSchedule,
)
from common.models.learning import ClassEnrollment, Classroom, User
from common.notifications import emit
from services.teacher_service.app.schemas.schedule import (
    ClassSessionItem,
    ClassSessionPayload,
    ScheduleExceptionItem,
    ScheduleExceptionPayload,
    StudentSchedule,
    TeacherSchedule,
)

WEEKDAY_NAMES = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


def _local_today() -> date:
    from services.teacher_service.app.services.checkin_manager import local_today

    return local_today()


def _monday_of(value: date) -> date:
    return value - timedelta(days=value.weekday())


class ClassScheduleManager:
    def _lock_write(self, db) -> None:
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))

    def _teacher_class(self, db, class_id: int, teacher_id: int) -> Classroom:
        room = db.get(Classroom, class_id)
        if room is None:
            raise ValueError("课堂不存在")
        if room.teacher_user_id != teacher_id:
            raise PermissionError("无权管理该课堂")
        return room

    def _session(self, db, session_id: int, teacher_id: int) -> ClassSession:
        session = db.get(ClassSession, session_id)
        if session is None:
            raise ValueError("课程安排不存在")
        if session.teacher_user_id != teacher_id:
            raise PermissionError("无权管理该课程安排")
        return session

    def _conflict(
        self,
        db,
        teacher_id: int,
        class_id: int,
        weekday: int,
        start: str,
        end: str,
        week_start: str,
        week_end: str,
        exclude_session_id: int | None = None,
        exclude_date: str | None = None,
    ) -> ClassSession | None:
        sessions = (
            db.query(ClassSession)
            .filter(
                ClassSession.status == "active",
                (ClassSession.teacher_user_id == teacher_id)
                | (ClassSession.class_id == class_id),
            )
            .all()
        )
        exceptions = db.query(ClassScheduleException).all()
        start_date, end_date = date.fromisoformat(week_start), date.fromisoformat(week_end)
        for item in sessions:
            if exclude_session_id and item.id == exclude_session_id and exclude_date is None:
                continue
            for day, begin, finish, _, original, _ in self._occurrences(item, exceptions, start_date, end_date):
                if item.id == exclude_session_id and original == exclude_date:
                    continue
                if day.isoweekday() == weekday and begin < end and start < finish:
                    return item
        return None

    @staticmethod
    def _occurrences(session, exceptions, start, end):
        changes = {e.date: e for e in exceptions if e.session_id == session.id}
        cursor = max(start, date.fromisoformat(session.week_start))
        last = min(end, date.fromisoformat(session.week_end))
        cursor += timedelta(days=(session.weekday - cursor.isoweekday()) % 7)
        while cursor <= last:
            change = changes.get(cursor.isoformat())
            if change is None:
                yield cursor, session.start_time, session.end_time, "normal", cursor.isoformat(), session.location
            cursor += timedelta(days=7)
        for change in changes.values():
            if change.kind not in ("reschedule", "makeup"):
                continue
            target = date.fromisoformat(change.new_date or change.date)
            if start <= target <= end:
                yield (target, change.new_start_time or session.start_time,
                       change.new_end_time or session.end_time,
                       "rescheduled" if change.kind == "reschedule" else "makeup",
                       change.date, change.location or session.location)

    def _audit(
        self,
        db,
        teacher_id: int,
        action: str,
        target_id: int,
        reason: str,
        before: dict | None = None,
        after: dict | None = None,
    ) -> None:
        db.add(
            CheckinAuditLog(
                actor_user_id=teacher_id,
                action=action,
                target_type="class_session",
                target_id=target_id,
                reason=reason[:500],
                before_json=before or {},
                after_json=after or {},
            )
        )

    def _notify(
        self,
        db,
        room: Classroom,
        teacher_id: int,
        event: str,
        title: str,
        content: str,
    ) -> None:
        for student in (
            db.query(User)
            .join(ClassEnrollment, ClassEnrollment.student_user_id == User.id)
            .filter(ClassEnrollment.class_id == room.id, User.is_active.is_(True))
            .all()
        ):
            emit(
                db,
                user_id=student.id,
                sender_id=teacher_id,
                event_key=f"schedule:{event}:{room.id}:{student.id}",
                title=title,
                content=content,
                type="class",
                related_type="class",
                related_id=room.id,
            )

    def _session_item(self, db, session: ClassSession) -> ClassSessionItem:
        room = db.get(Classroom, session.class_id)
        teacher = db.get(User, session.teacher_user_id)
        return ClassSessionItem(
            id=session.id,
            class_id=session.class_id,
            class_name=room.name if room else "",
            teacher_name=teacher.username if teacher else "",
            topic=session.topic,
            weekday=session.weekday,
            start_time=session.start_time,
            end_time=session.end_time,
            week_start=session.week_start,
            week_end=session.week_end,
            location=session.location,
            mode=session.mode,
            status=session.status,
            created_at=session.created_at,
        )

    def _exception_item(self, db, item: ClassScheduleException) -> ScheduleExceptionItem:
        room = db.get(Classroom, item.class_id)
        return ScheduleExceptionItem(
            id=item.id,
            session_id=item.session_id,
            class_id=item.class_id,
            class_name=room.name if room else "",
            date=item.date,
            kind=item.kind,
            new_date=item.new_date,
            new_start_time=item.new_start_time,
            new_end_time=item.new_end_time,
            location=item.location,
            reason=item.reason,
            created_at=item.created_at,
        )

    def teacher_schedule(
        self, class_id: int, teacher_id: int, role: str
    ) -> TeacherSchedule:
        with SessionLocal() as db:
            room = db.get(Classroom, class_id)
            if room is None:
                raise ValueError("课堂不存在")
            if role != "admin" and room.teacher_user_id != teacher_id:
                raise PermissionError("无权查看该课堂")
            sessions = (
                db.query(ClassSession)
                .filter_by(class_id=class_id)
                .order_by(ClassSession.weekday, ClassSession.start_time)
                .all()
            )
            exceptions = (
                db.query(ClassScheduleException)
                .filter_by(class_id=class_id)
                .order_by(ClassScheduleException.date.desc())
                .all()
            )
            return TeacherSchedule(
                class_id=class_id,
                class_name=room.name,
                sessions=[self._session_item(db, item) for item in sessions],
                exceptions=[self._exception_item(db, item) for item in exceptions],
            )

    def create_session(
        self, class_id: int, teacher_id: int, payload: ClassSessionPayload
    ) -> ClassSessionItem:
        with SessionLocal() as db:
            self._lock_write(db)
            room = self._teacher_class(db, class_id, teacher_id)
            conflict = self._conflict(
                db,
                teacher_id,
                room.id,
                payload.weekday,
                payload.start_time,
                payload.end_time,
                payload.week_start,
                payload.week_end,
            )
            if conflict is not None:
                other = db.get(Classroom, conflict.class_id)
                name = other.name if other else f"课堂 #{conflict.class_id}"
                raise RuntimeError(
                    f"时间冲突：{name} 在{payload.weekday}已有 "
                    f"{conflict.start_time}-{conflict.end_time} 的课程"
                )
            session = ClassSession(
                class_id=room.id,
                teacher_user_id=teacher_id,
                topic=payload.topic,
                weekday=payload.weekday,
                start_time=payload.start_time,
                end_time=payload.end_time,
                week_start=payload.week_start,
                week_end=payload.week_end,
                location=payload.location,
                mode=payload.mode,
            )
            db.add(session)
            db.flush()
            self._audit(db, teacher_id, "schedule.create", session.id, payload.topic)
            self._notify(
                db,
                room,
                teacher_id,
                f"session-created-{session.id}",
                f"课程安排更新：{room.name}",
                f"{WEEKDAY_NAMES[payload.weekday]} {payload.start_time}-{payload.end_time} {payload.topic}",
            )
            db.commit()
            db.refresh(session)
            return self._session_item(db, session)

    def update_session(
        self, session_id: int, teacher_id: int, payload: ClassSessionPayload
    ) -> ClassSessionItem:
        with SessionLocal() as db:
            self._lock_write(db)
            session = self._session(db, session_id, teacher_id)
            room = db.get(Classroom, session.class_id)
            conflict = self._conflict(
                db,
                teacher_id,
                session.class_id,
                payload.weekday,
                payload.start_time,
                payload.end_time,
                payload.week_start,
                payload.week_end,
                exclude_session_id=session.id,
            )
            if conflict is not None:
                raise RuntimeError("调整后的时间与已有课程冲突")
            before = {
                "topic": session.topic,
                "weekday": session.weekday,
                "start_time": session.start_time,
                "end_time": session.end_time,
            }
            session.topic = payload.topic
            session.weekday = payload.weekday
            session.start_time = payload.start_time
            session.end_time = payload.end_time
            session.week_start = payload.week_start
            session.week_end = payload.week_end
            session.location = payload.location
            session.mode = payload.mode
            self._audit(
                db, teacher_id, "schedule.update", session.id, "修改课程安排", before
            )
            if room:
                self._notify(
                    db,
                    room,
                    teacher_id,
                    f"session-updated-{session.id}-{payload.weekday}-{payload.start_time}",
                    f"课程安排调整：{room.name}",
                    f"最新安排：{WEEKDAY_NAMES[payload.weekday]} {payload.start_time}-{payload.end_time} {payload.topic}",
                )
            db.commit()
            db.refresh(session)
            return self._session_item(db, session)

    def delete_session(self, session_id: int, teacher_id: int) -> dict:
        with SessionLocal() as db:
            self._lock_write(db)
            session = self._session(db, session_id, teacher_id)
            room = db.get(Classroom, session.class_id)
            db.query(ClassScheduleException).filter_by(session_id=session.id).delete(
                synchronize_session=False
            )
            db.query(PersonalSchedule).filter_by(source_session_id=session.id).delete(synchronize_session=False)
            self._audit(db, teacher_id, "schedule.delete", session.id, session.topic)
            db.delete(session)
            if room:
                self._notify(
                    db,
                    room,
                    teacher_id,
                    f"session-deleted-{session_id}",
                    f"课程安排取消：{room.name}",
                    f"原安排 {WEEKDAY_NAMES[session.weekday]} {session.start_time}-{session.end_time} {session.topic} 已删除",
                )
            db.commit()
            return {"deleted": True, "id": session_id}

    def add_exception(
        self, session_id: int, teacher_id: int, payload: ScheduleExceptionPayload
    ) -> ScheduleExceptionItem:
        with SessionLocal() as db:
            self._lock_write(db)
            session = self._session(db, session_id, teacher_id)
            room = db.get(Classroom, session.class_id)
            original_weekday = session.weekday
            if payload.kind in ("cancel", "reschedule"):
                if not (session.week_start <= payload.date <= session.week_end):
                    raise ValueError("所选日期不在该课程的教学周范围内")
                if date.fromisoformat(payload.date).isoweekday() != original_weekday:
                    raise ValueError("所选日期与课程星期不一致")
            existing = (
                db.query(ClassScheduleException)
                .filter_by(session_id=session.id, date=payload.date)
                .first()
            )
            if existing is not None:
                raise RuntimeError("该日期的课程已有调整记录，请先删除后重试")
            new_start = payload.new_start_time or session.start_time
            new_end = payload.new_end_time or session.end_time
            target_date = payload.new_date or payload.date
            if payload.kind in ("reschedule", "makeup"):
                if new_start >= new_end:
                    raise RuntimeError("调整后开始时间必须早于结束时间")
                conflict = self._conflict(
                    db,
                    teacher_id,
                    session.class_id,
                    date.fromisoformat(target_date).isoweekday(),
                    new_start,
                    new_end,
                    target_date,
                    target_date,
                    exclude_session_id=session.id,
                    exclude_date=payload.date,
                )
                if conflict is not None:
                    raise RuntimeError("调整后的时间与已有课程冲突")
            exception = ClassScheduleException(
                session_id=session.id,
                class_id=session.class_id,
                teacher_user_id=teacher_id,
                date=payload.date,
                kind=payload.kind,
                new_date=payload.new_date,
                new_start_time=payload.new_start_time,
                new_end_time=payload.new_end_time,
                location=payload.location,
                reason=payload.reason,
            )
            db.add(exception)
            db.flush()
            self._audit(
                db, teacher_id, f"schedule.{payload.kind}", session.id, payload.reason
            )
            if room:
                self._notify(
                    db,
                    room,
                    teacher_id,
                    f"exception-{exception.id}",
                    f"{'停课' if payload.kind == 'cancel' else '调课' if payload.kind == 'reschedule' else '补课'}通知：{room.name}",
                    payload.reason,
                )
            db.commit()
            db.refresh(exception)
            return self._exception_item(db, exception)

    def delete_exception(self, exception_id: int, teacher_id: int) -> dict:
        with SessionLocal() as db:
            self._lock_write(db)
            exception = db.get(ClassScheduleException, exception_id)
            if exception is None:
                raise ValueError("调整记录不存在")
            if exception.teacher_user_id != teacher_id:
                raise PermissionError("无权管理该调整记录")
            self._audit(db, teacher_id, "schedule.exception_delete", exception.session_id, "撤销调整")
            db.delete(exception)
            db.commit()
            return {"deleted": True, "id": exception_id}

    def student_schedule(self, student_id: int, week_start: str | None = None) -> StudentSchedule:
        from services.teacher_service.app.services.personal_schedule import build_student_schedule

        return build_student_schedule(self, student_id, week_start)
