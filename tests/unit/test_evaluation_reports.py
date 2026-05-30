"""Unit tests for detailed evaluation report endpoints."""

from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


def test_mistake_notebook_collects_wrong_answers(db_session, test_user) -> None:
    """Wrong answers should appear in the mistake notebook."""

    service = ReportService(db_session)
    service.evaluate_practice(
        PracticeSubmission(
            user_id=test_user.id,
            exercise_id=120000 + test_user.id,
            knowledge_point="Python 循环",
            question_type="blank",
            user_answer="if",
            correct_answer="for / while",
            analysis="循环语句需要关注重复执行与停止条件。",
            time_spent=8,
        )
    )

    notebook = service.get_mistake_notebook(test_user.id)

    assert notebook.mistake_count == 1
    assert notebook.items[0].exercise_id == 120000 + test_user.id


def test_report_detail_contains_action_items(db_session, test_user) -> None:
    """Detailed reports should contain strengths and next actions."""

    service = ReportService(db_session)
    report = service.generate_stage_report_detail(test_user.id)

    assert report.strengths
    assert report.next_actions
