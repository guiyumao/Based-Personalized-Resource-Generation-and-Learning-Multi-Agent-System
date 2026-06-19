"""Unit tests for learner profile dashboard helpers."""

from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


def test_profile_snapshot_contains_radar_and_heatmap(db_session, test_user) -> None:
    """Profile snapshot should expose dashboard-ready radar and heatmap data."""

    service = ReportService(db_session)
    service.evaluate_practice(
        PracticeSubmission(
            user_id=test_user.id,
            exercise_id=110000 + test_user.id,
            knowledge_point="Python 循环",
            question_type="choice",
            user_answer="B",
            correct_answer="B",
            analysis="循环用于按照规则重复执行任务。",
            time_spent=15,
        )
    )

    snapshot = service.generate_profile_snapshot(test_user.id)

    assert snapshot["mastery_overview"] >= 0
    assert snapshot["radar_metrics"]
    assert snapshot["heatmap"]
