"""Unit tests for teacher insight capabilities."""

import asyncio

from services.teacher_service.app.services.teacher_manager import TeacherManager


def test_teacher_manager_returns_student_insights() -> None:
    """Teacher manager should expose student insight cards."""

    manager = TeacherManager()
    insights = manager.list_student_insights(1)

    assert insights
    assert insights[0].student_name
    assert isinstance(insights[0].mistake_count, int)


def test_teacher_manager_returns_student_learning_detail_fallback() -> None:
    """Teacher manager should aggregate a student detail payload even without remote services."""

    manager = TeacherManager()
    detail = asyncio.run(manager.get_student_learning_detail(1, 1))

    assert detail.student_name
    assert detail.stage_report.title
    assert detail.comprehensive_report.title
    assert isinstance(detail.mistake_notebook, list)
