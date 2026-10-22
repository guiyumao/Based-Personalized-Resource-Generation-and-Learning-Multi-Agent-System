"""Regression tests for multi-course teaching scopes.

Publishing a teaching scope used to archive *every* active learning path of the
student. A learner enrolled in two teaching classes therefore lost the earlier
course path as soon as the second teacher published a scope.
"""

from __future__ import annotations

from common.models.learning import ClassEnrollment, Classroom, LearningPath, TeachingScope
from services.teacher_service.app.services.teacher_manager import TeacherManager


def _classroom(db, teacher, name: str) -> Classroom:
    room = Classroom(
        name=name,
        subject="数据结构",
        teacher_name=teacher.username,
        teacher_user_id=teacher.id,
        join_mode="invite",
        status="active",
        is_public=True,
        capacity=0,
        semester="2026-2027-1",
    )
    db.add(room)
    db.flush()
    return room


def _scope(db, room: Classroom, title: str) -> TeachingScope:
    scope = TeachingScope(
        class_id=room.id,
        student_user_id=None,
        knowledge_points=["链表"],
        learning_direction="按章节顺序推进",
        courseware_title=title,
        courseware_content="# 讲义\n演示内容",
        teaching_goal="掌握核心概念",
    )
    db.add(scope)
    db.flush()
    return scope


def _active_scope_classes(db, user_id: int) -> set[int | None]:
    rows = (
        db.query(LearningPath)
        .filter(LearningPath.user_id == user_id, LearningPath.status == "active")
        .all()
    )
    return {(row.path_data_json or {}).get("teacher_scope", {}).get("class_id") for row in rows}


def _cleanup(db, rooms: list[Classroom], user_id: int) -> None:
    db.query(LearningPath).filter(LearningPath.user_id == user_id).delete(synchronize_session=False)
    for room in rooms:
        db.query(TeachingScope).filter(TeachingScope.class_id == room.id).delete(
            synchronize_session=False
        )
        db.query(ClassEnrollment).filter(ClassEnrollment.class_id == room.id).delete(
            synchronize_session=False
        )
        db.query(Classroom).filter(Classroom.id == room.id).delete(synchronize_session=False)
    db.commit()


def test_second_class_scope_keeps_first_course_path(db_session, teacher_user, test_user):
    manager = TeacherManager()
    rooms: list[Classroom] = []
    try:
        first = _classroom(db_session, teacher_user, "多课程回归-数据结构")
        second = _classroom(db_session, teacher_user, "多课程回归-算法设计")
        rooms = [first, second]
        db_session.add_all(
            [
                ClassEnrollment(class_id=first.id, student_user_id=test_user.id),
                ClassEnrollment(class_id=second.id, student_user_id=test_user.id),
            ]
        )
        db_session.commit()

        manager._publish_scope_to_students(db_session, _scope(db_session, first, "第一门课讲义"))
        db_session.commit()
        assert _active_scope_classes(db_session, test_user.id) == {first.id}

        manager._publish_scope_to_students(db_session, _scope(db_session, second, "第二门课讲义"))
        db_session.commit()

        # Both courses stay active instead of the second one retiring the first.
        assert _active_scope_classes(db_session, test_user.id) == {first.id, second.id}
    finally:
        _cleanup(db_session, rooms, test_user.id)


def test_republishing_same_class_archives_only_previous_version(db_session, teacher_user, test_user):
    manager = TeacherManager()
    rooms: list[Classroom] = []
    try:
        room = _classroom(db_session, teacher_user, "多课程回归-同班重发")
        other = _classroom(db_session, teacher_user, "多课程回归-其他课程")
        rooms = [room, other]
        db_session.add_all(
            [
                ClassEnrollment(class_id=room.id, student_user_id=test_user.id),
                ClassEnrollment(class_id=other.id, student_user_id=test_user.id),
            ]
        )
        db_session.commit()

        manager._publish_scope_to_students(db_session, _scope(db_session, room, "旧讲义"))
        manager._publish_scope_to_students(db_session, _scope(db_session, other, "其他课程讲义"))
        db_session.commit()

        manager._publish_scope_to_students(db_session, _scope(db_session, room, "新讲义"))
        db_session.commit()

        active = _active_scope_classes(db_session, test_user.id)
        assert active == {room.id, other.id}
        same_class = (
            db_session.query(LearningPath)
            .filter(LearningPath.user_id == test_user.id, LearningPath.status == "active")
            .all()
        )
        versions = [
            (row.path_data_json or {}).get("teacher_scope", {}).get("courseware_title")
            for row in same_class
            if (row.path_data_json or {}).get("teacher_scope", {}).get("class_id") == room.id
        ]
        assert versions == ["新讲义"]
    finally:
        _cleanup(db_session, rooms, test_user.id)
