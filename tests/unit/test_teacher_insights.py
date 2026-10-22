"""Unit tests for teacher insight capabilities."""

import asyncio
from unittest.mock import patch

import pytest

from common.db.session import SessionLocal
from common.models.learning import LearningPath, TeachingScope
from services.teacher_service.app.schemas.teacher import TeachingScopeCreate
from services.teacher_service.app.services.teacher_manager import TeacherManager


@pytest.fixture
def enrolled_class(test_user):
    """Use a real class membership rather than nonexistent class 1 and global users."""
    from uuid import uuid4

    from common.models.learning import User
    from services.teacher_service.app.schemas.teacher import ClassCreate

    with SessionLocal() as db:
        teacher = User(
            id=-int(uuid4().hex[:7], 16),
            username="insight-teacher-" + uuid4().hex[:8],
            password_hash="disabled",
            role="teacher",
            is_active=True,
        )
        db.add(teacher)
        db.commit()
        teacher_id = teacher.id
    manager = TeacherManager()
    classroom = manager.create_class(ClassCreate(name="学情证据班", subject="Python"), teacher_id)
    manager.enroll_student(classroom.id, test_user.id, teacher_id)
    yield classroom
    from common.models.learning import ClassEnrollment, Classroom, Course, Notification

    with SessionLocal() as db:
        db.query(ClassEnrollment).filter_by(class_id=classroom.id).delete()
        db.query(Classroom).filter_by(id=classroom.id).delete()
        db.query(Course).filter_by(id=classroom.course_id).delete()
        db.query(Notification).filter_by(sender_id=teacher_id).delete()
        db.query(User).filter_by(id=teacher_id).delete()
        db.commit()


def test_teacher_manager_returns_student_insights(test_user, enrolled_class) -> None:
    manager = TeacherManager()
    insights = manager.list_student_insights(enrolled_class.id)
    assert len(insights) == 1 and insights[0].user_id == test_user.id
    assert insights[0].student_name
    assert isinstance(insights[0].mistake_count, int)
    assert manager.list_student_insights(987654321) == []


def test_teacher_manager_returns_student_learning_detail_fallback(
    test_user, enrolled_class
) -> None:
    """Class details no longer need external student-global reports."""
    manager = TeacherManager()
    with patch(
        "services.teacher_service.app.services.teacher_manager.httpx.AsyncClient",
        side_effect=RuntimeError("must not read global reports"),
    ):
        detail = asyncio.run(manager.get_student_learning_detail(enrolled_class.id, test_user.id))
    assert detail.user_id == test_user.id
    assert detail.mistake_notebook == []
    assert detail.stage_report.report_type == "class"


def test_teacher_manager_uses_teacher_mistake_detail_endpoint(test_user, enrolled_class) -> None:
    """Regression: a teacher must not receive another course's global mistake notebook."""
    manager = TeacherManager()
    with patch("services.teacher_service.app.services.teacher_manager.httpx.AsyncClient") as remote:
        detail = asyncio.run(manager.get_student_learning_detail(enrolled_class.id, test_user.id))
    remote.assert_not_called()
    assert isinstance(detail.mistake_notebook, list)
    assert detail.stage_report.title == "本班学习证据"


def test_teacher_manager_forwards_caller_token_to_evaluation(test_user, enrolled_class) -> None:
    """No token is sent to a global report endpoint after scoping details to class evidence."""
    manager = TeacherManager()
    with patch("services.teacher_service.app.services.teacher_manager.httpx.AsyncClient") as remote:
        detail = asyncio.run(
            manager.get_student_learning_detail(
                enrolled_class.id, test_user.id, auth_header="Bearer teacher-token"
            )
        )
    remote.assert_not_called()
    assert detail.user_id == test_user.id
    with pytest.raises(ValueError):
        asyncio.run(manager.get_student_learning_detail(enrolled_class.id, 987654321))


def test_teacher_scope_is_visible_to_target_student(test_user, enrolled_class) -> None:
    """Teacher-created scopes should be persisted and readable by students."""

    manager = TeacherManager()
    created = manager.create_teaching_scope(
        TeachingScopeCreate(
            class_id=enrolled_class.id,
            student_user_id=test_user.id,
            knowledge_points=["Python loops"],
            learning_direction="Practice loop boundaries",
            courseware_title="Loop boundary courseware",
            courseware_content="Focus on while-loop stop conditions.",
            teaching_goal="Avoid infinite loops.",
        )
    )

    scopes = manager.list_student_teaching_scopes(test_user.id)

    assert created.id
    assert any(item.id == created.id for item in scopes)
    assert scopes[0].knowledge_points == ["Python loops"]

    with SessionLocal() as db:
        db.query(LearningPath).filter(LearningPath.user_id == test_user.id).delete()
        db.query(TeachingScope).filter(TeachingScope.id == created.id).delete()
        db.commit()


def test_teacher_scope_publishes_active_student_path(test_user, enrolled_class) -> None:
    """Creating a teaching scope should directly update the student's active path."""

    manager = TeacherManager()
    created = manager.create_teaching_scope(
        TeachingScopeCreate(
            class_id=enrolled_class.id,
            student_user_id=test_user.id,
            knowledge_points=["Functions"],
            learning_direction="Follow the teacher scope before practicing.",
            courseware_title="Function scope courseware",
            courseware_content="Function concepts and examples.",
            teaching_goal="Understand function definition and calls.",
        )
    )

    with SessionLocal() as db:
        path = (
            db.query(LearningPath)
            .filter(LearningPath.user_id == test_user.id, LearningPath.status == "active")
            .order_by(LearningPath.id.desc())
            .first()
        )
        assert path is not None
        assert path.path_data_json["teacher_scope"]["id"] == created.id
        assert path.path_data_json["stages"][0]["tasks"][0]["teacher_scope_id"] == created.id

        db.query(LearningPath).filter(LearningPath.user_id == test_user.id).delete()
        db.query(TeachingScope).filter(TeachingScope.id == created.id).delete()
        db.commit()
