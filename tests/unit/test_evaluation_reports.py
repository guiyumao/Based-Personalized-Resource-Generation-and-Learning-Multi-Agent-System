"""Unit tests for detailed evaluation report endpoints."""

from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


def test_mistake_notebook_collects_wrong_answers() -> None:
    """Wrong answers should appear in the mistake notebook."""

    service = ReportService()
    service.evaluate_practice(
        PracticeSubmission(
            user_id=1,
            exercise_id=2,
            knowledge_point="Python 循环",
            question_type="blank",
            user_answer="if",
            correct_answer="for / while",
            analysis="循环语句需要关注重复执行。",
            time_spent=8,
        )
    )

    notebook = service.get_mistake_notebook(1)

    assert notebook.mistake_count == 1
    assert notebook.items[0].exercise_id == 2


def test_report_detail_contains_action_items() -> None:
    """Detailed reports should contain strengths and next actions."""

    service = ReportService()
    report = service.generate_stage_report_detail(1)

    assert report.strengths
    assert report.next_actions
