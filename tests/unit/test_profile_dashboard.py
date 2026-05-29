"""Unit tests for learner profile dashboard helpers."""

from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


def test_profile_snapshot_contains_radar_and_heatmap() -> None:
    """Profile snapshot should expose dashboard-ready radar and heatmap data."""

    service = ReportService()
    service.evaluate_practice(
        PracticeSubmission(
            user_id=1,
            exercise_id=10,
            knowledge_point="Python 循环",
            question_type="choice",
            user_answer="B",
            correct_answer="B",
            analysis="循环用于重复执行。",
            time_spent=15,
        )
    )

    snapshot = service.generate_profile_snapshot(1)

    assert snapshot["mastery_overview"] >= 0
    assert snapshot["radar_metrics"]
    assert snapshot["heatmap"]
