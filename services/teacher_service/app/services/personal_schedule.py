"""Merge authoritative classroom occurrences with private student schedules."""

from datetime import date, timedelta

from common.db.session import SessionLocal
from common.models.checkin import ClassScheduleException, ClassSession, PersonalSchedule
from common.models.learning import ClassEnrollment, Classroom, User
from services.teacher_service.app.schemas.schedule import (
    ImportedClassroom,
    PersonalScheduleItem,
    StudentSchedule,
    StudentScheduleEntry,
)


def _rooms(db, user_id):
    return db.query(Classroom).join(ClassEnrollment, ClassEnrollment.class_id == Classroom.id).filter(
        ClassEnrollment.student_user_id == user_id, Classroom.status == "active",
    ).all()


def save_personal(manager, user_id, payload, entry_id=None):
    with SessionLocal() as db:
        manager._lock_write(db)
        entry = db.get(PersonalSchedule, entry_id) if entry_id else None
        if entry_id and (entry is None or entry.user_id != user_id):
            raise PermissionError("无权修改该个人安排")
        rooms = {r.id for r in _rooms(db, user_id)}
        if payload.class_id is not None and payload.class_id not in rooms:
            raise PermissionError("只能安排已加入课堂的课程")
        values = payload.model_dump()
        if payload.source_session_id:
            source = db.get(ClassSession, payload.source_session_id)
            if source is None or source.class_id not in rooms or source.status != "active":
                raise PermissionError("无权调整该课堂安排")
            # Only an actual occurrence can be privately adjusted. Its identity
            # stays the original date even after the teacher reschedules it.
            original = date.fromisoformat(payload.source_date)
            if not (source.week_start <= payload.source_date <= source.week_end) or original.isoweekday() != source.weekday:
                raise ValueError("原课程日期无效")
            values["class_id"] = source.class_id
            duplicate = db.query(PersonalSchedule).filter_by(
                user_id=user_id, source_session_id=source.id, source_date=payload.source_date,
            ).first()
            if duplicate and (entry is None or duplicate.id != entry.id):
                raise RuntimeError("该课程已有个人调整，请编辑或恢复原安排")
        if entry is None:
            entry = PersonalSchedule(user_id=user_id, **values)
            db.add(entry)
        else:
            for key, value in values.items():
                setattr(entry, key, value)
        db.commit()
        db.refresh(entry)
        return PersonalScheduleItem.model_validate(entry)


def delete_personal(manager, user_id, entry_id):
    with SessionLocal() as db:
        manager._lock_write(db)
        entry = db.get(PersonalSchedule, entry_id)
        if entry is None or entry.user_id != user_id:
            raise PermissionError("无权删除该个人安排")
        db.delete(entry)
        db.commit()
        return {"deleted": True, "id": entry_id}


def build_student_schedule(manager, user_id, week_start=None):
    from services.teacher_service.app.services.classroom_schedule import _local_today, _monday_of

    today = _local_today()
    start = _monday_of(date.fromisoformat(week_start) if week_start else today)
    end = start + timedelta(days=6)
    with SessionLocal() as db:
        rooms = {r.id: r for r in _rooms(db, user_id)}
        teachers = {u.id: u.username for u in db.query(User).filter(
            User.id.in_({r.teacher_user_id for r in rooms.values()} or [-1]))}
        sessions = db.query(ClassSession).filter(
            ClassSession.class_id.in_(list(rooms) or [-1]), ClassSession.status == "active",
        ).all()
        session_map = {s.id: s for s in sessions}
        exceptions = db.query(ClassScheduleException).filter(
            ClassScheduleException.session_id.in_(list(session_map) or [-1]),
        ).all()
        personal = [p for p in db.query(PersonalSchedule).filter_by(user_id=user_id).all()
                    if (p.class_id is None or p.class_id in rooms)
                    and (p.source_session_id is None or p.source_session_id in session_map)]
        overrides = {(p.source_session_id, p.source_date): p for p in personal if p.source_session_id}
        entries = []
        for session in sessions:
            room = rooms[session.class_id]
            for day, begin, finish, status, original, location in manager._occurrences(session, exceptions, start, end):
                if (session.id, original) in overrides:
                    continue
                entries.append(StudentScheduleEntry(
                    date=day.isoformat(), weekday=day.isoweekday(), start_time=begin, end_time=finish,
                    topic=session.topic, location=location, mode=session.mode, class_id=room.id,
                    class_name=room.name, teacher_name=teachers.get(room.teacher_user_id, ""),
                    status=status, session_id=session.id, source_date=original,
                ))
        for item in personal:
            if item.hidden:
                continue
            source = session_map.get(item.source_session_id)
            if source:
                change = next((e for e in exceptions if e.session_id == source.id and e.date == item.source_date), None)
                if change and change.kind == "cancel":
                    continue
            cursor = max(start, date.fromisoformat(item.week_start))
            last = min(end, date.fromisoformat(item.week_end))
            cursor += timedelta(days=(item.weekday - cursor.isoweekday()) % 7)
            room = rooms.get(item.class_id)
            while cursor <= last:
                entries.append(StudentScheduleEntry(
                    date=cursor.isoformat(), weekday=cursor.isoweekday(),
                    start_time=item.start_time, end_time=item.end_time, topic=item.topic,
                    location=item.location, mode=item.mode, class_id=item.class_id or 0,
                    class_name=room.name if room else "个人课程", teacher_name="",
                    status="personal", session_id=item.source_session_id or -item.id,
                    personal_id=item.id, source="personal", source_date=item.source_date,
                ))
                cursor += timedelta(days=7)
        return StudentSchedule(
            week_start=start.isoformat(), week_end=end.isoformat(), today=today.isoformat(),
            entries=sorted(entries, key=lambda e: (e.date, e.start_time, e.topic)),
            classrooms=[ImportedClassroom(
                class_id=r.id, class_name=r.name, teacher_name=teachers.get(r.teacher_user_id, ""),
                scheduled=any(s.class_id == r.id for s in sessions) or any(p.class_id == r.id and not p.hidden for p in personal),
            ) for r in rooms.values()],
            personal=[PersonalScheduleItem.model_validate(p) for p in personal],
        )
