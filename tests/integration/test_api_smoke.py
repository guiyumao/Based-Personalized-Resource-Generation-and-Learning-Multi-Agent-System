"""API smoke tests for FastAPI applications."""

from fastapi.testclient import TestClient

from services.agent_service.app.main import app as agent_app
from services.evaluation_service.app.main import app as evaluation_app
from services.system_service.app.main import app as system_app
from services.teacher_service.app.main import app as teacher_app
from services.user_service.app.main import app as user_app


def test_user_service_health() -> None:
    """User service should expose a health endpoint."""

    client = TestClient(user_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "user-service"


def test_agent_service_health() -> None:
    """Agent service should expose a health endpoint."""

    client = TestClient(agent_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "agent-service"


def test_evaluation_service_health() -> None:
    """Evaluation service should expose a health endpoint."""

    client = TestClient(evaluation_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "evaluation-service"


def test_teacher_service_health() -> None:
    """Teacher service should expose a health endpoint."""

    client = TestClient(teacher_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "teacher-service"


def test_system_service_health() -> None:
    """System service should expose a health endpoint."""

    client = TestClient(system_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "system-service"
