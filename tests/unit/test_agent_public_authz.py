"""User scoped agent routes must reject anonymous and cross-account calls."""

from fastapi.testclient import TestClient

from services.agent_service.app.main import app


CLIENT = TestClient(app)


def test_anonymous_generation_is_rejected() -> None:
    response = CLIENT.post(
        "/resources/generate",
        json={"user_id": 1, "knowledge_point": "fractions"},
    )
    assert response.status_code == 401


def test_other_student_cannot_read_path(auth_headers, other_user) -> None:
    response = CLIENT.get(f"/paths/{other_user.id}", headers=auth_headers)
    assert response.status_code == 403


def test_other_student_cannot_run_coordinator(auth_headers, other_user) -> None:
    response = CLIENT.post(
        "/agents/coordinate",
        json={"user_id": other_user.id, "intent": "learning path plan"},
        headers=auth_headers,
    )
    assert response.status_code == 403
