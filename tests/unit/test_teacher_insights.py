"""Unit tests for teacher insight capabilities."""

import asyncio
from unittest.mock import patch

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


def test_teacher_manager_uses_teacher_mistake_detail_endpoint() -> None:
    """Teacher detail should request the teacher-side mistake notebook endpoint."""

    manager = TeacherManager()

    requested_urls: list[str] = []

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str):
            requested_urls.append(url)
            if url.endswith("/teacher-detail"):
                return DummyResponse({"data": {"user_id": 1, "mistake_count": 0, "items": []}})
            return DummyResponse(
                {
                    "data": {
                        "report_type": "stage" if "/stage/" in url else "comprehensive",
                        "user_id": 1,
                        "title": "ok",
                        "summary": "ok",
                        "strengths": [],
                        "weaknesses": [],
                        "next_actions": [],
                    }
                }
            )

    with patch("services.teacher_service.app.services.teacher_manager.httpx.AsyncClient", return_value=DummyClient()):
        detail = asyncio.run(manager.get_student_learning_detail(1, 1))

    assert isinstance(detail.mistake_notebook, list)
    assert any(url.endswith("/evaluation/mistakes/1/teacher-detail") for url in requested_urls)
