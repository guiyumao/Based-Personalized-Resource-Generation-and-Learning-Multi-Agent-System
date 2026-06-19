"""Unit tests for learner profile dashboard helpers."""

import asyncio

from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


class FakePublisher:
    """No-op publisher for tests that should not touch external queues."""

    def publish(self, queue_name: str, message: dict[str, object]) -> None:
        return None


def test_profile_snapshot_contains_radar_and_heatmap(db_session, test_user) -> None:
    """Profile snapshot should expose dashboard-ready radar and heatmap data."""

    async def run() -> None:
        service = ReportService(publisher=FakePublisher())
        await service.evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=110000 + test_user.id,
                knowledge_point="Python loops",
                question_type="choice",
                user_answer="B",
                correct_answer="B",
                analysis="Loops repeat a task according to a condition.",
                time_spent=15,
            )
        )

        snapshot = await service.generate_profile_snapshot(test_user.id)

        assert snapshot["mastery_overview"] >= 0
        assert snapshot["radar_metrics"]
        assert snapshot["heatmap"]

    asyncio.run(run())
