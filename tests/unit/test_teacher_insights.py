"""Unit tests for teacher insight capabilities."""

import asyncio
from unittest.mock import patch

import pytest

from common.db.session import SessionLocal
from common.models.learning import LearningPath, TeachingScope
from services.teacher_service.app.schemas.teacher import TeachingScopeCreate
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
    # When EVALUATION_SERVICE_URL is empty (default), the teacher manager
    # makes a request to an empty URL which httpx rejects.  The method
    # should surface a clear error rather than silently returning partial
    # data, so we assert the expected exception here.
    with patch(
        "services.teacher_service.app.services.teacher_manager.httpx.AsyncClient",
        side_effect=RuntimeError("evaluation_service_url is not configured"),
    ):
        with pytest.raises(RuntimeError, match="evaluation_service_url"):
            asyncio.run(manager.get_student_learning_detail(1, 1))


def test_teacher_manager_uses_teacher_mistake_detail_endpoint() -> None:
    """Teacher detail should request the teacher-side mistake notebook endpoint."""

    manager = TeacherManager()

    requested_urls: list[str] = []
    forwarded_headers: list[dict] = []

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

        async def get(self, url: str, headers: dict | None = None):
            requested_urls.append(url)
            forwarded_headers.append(headers or {})
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


def test_teacher_manager_forwards_caller_token_to_evaluation() -> None:
    """Evaluation-service calls must carry the teacher's bearer token."""

    manager = TeacherManager()
    forwarded: list[dict] = []

    class DummyResponse:
        def __init__(self, url: str) -> None:
            self._url = url

        def raise_for_status(self) -> None:
            return None

        def json(self):
            if self._url.endswith("/teacher-detail"):
                return {"data": {"user_id": 1, "mistake_count": 0, "items": []}}
            return {
                "data": {
                    "report_type": "stage" if "/stage/" in self._url else "comprehensive",
                    "user_id": 1,
                    "title": "ok",
                    "summary": "ok",
                    "strengths": [],
                    "weaknesses": [],
                    "next_actions": [],
                }
            }

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers: dict | None = None):
            forwarded.append(headers or {})
            return DummyResponse(url)

    with patch(
        "services.teacher_service.app.services.teacher_manager.httpx.AsyncClient",
        return_value=DummyClient(),
    ):
        asyncio.run(
            manager.get_student_learning_detail(1, 1, auth_header="Bearer teacher-token")
        )

    assert forwarded, "no internal evaluation call was made"
    assert all(h.get("Authorization") == "Bearer teacher-token" for h in forwarded)


def test_teacher_scope_is_visible_to_target_student(test_user) -> None:
    """Teacher-created scopes should be persisted and readable by students."""

    manager = TeacherManager()
    created = manager.create_teaching_scope(
        TeachingScopeCreate(
            class_id=1,
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


def test_teacher_scope_publishes_active_student_path(test_user) -> None:
    """Creating a teaching scope should directly update the student's active path."""

    manager = TeacherManager()
    created = manager.create_teaching_scope(
        TeachingScopeCreate(
            class_id=1,
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
