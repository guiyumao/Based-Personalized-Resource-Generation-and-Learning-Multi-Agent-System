"""Admin-only persisted task metrics; usage unknown and no prompt disclosure."""

from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import (
    AssistantAgentExecution,
    AssistantTask,
    ChatSession,
    KnowledgeBudgetCounter,
)
from services.agent_service.app.main import app


def test_task_counts_unknown_usage_details_and_role_boundary(db_session, test_user):
    session = ChatSession(user_id=test_user.id, title="private title")
    db_session.add(session)
    db_session.flush()
    task = AssistantTask(
        user_id=test_user.id,
        session_id=session.id,
        client_request_id="operations-fixture",
        task_type="exercise",
        status="FAILED",
        request_json={"message": "PRIVATE_PROMPT_SECRET", "token": "PRIVATE_API_SECRET"},
        result_json={"prompt_tokens": 999},
        error_code="Bearer PRIVATE_API_SECRET",
        execution_attempt=2,
        heartbeat_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    stage = AssistantAgentExecution(
        task_id=task.id,
        agent_code="exercise_generation_agent",
        status="failed",
        error_code="MODEL_TIMEOUT",
        elapsed_ms=42,
    )
    db_session.add(stage)
    budget = KnowledgeBudgetCounter(
        scope_key=f"day:{datetime.utcnow():%Y%m%d}",
        model_calls=2,
        input_tokens=6000,
        output_tokens=3000,
    )
    db_session.add(budget)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    try:
        assert client.get("/admin/operations").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=test_user.id, role="student"
        )
        assert client.get("/admin/operations").status_code == 403
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=test_user.id, role="admin"
        )
        response = client.get("/admin/operations")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["counts"]["assistant"]["FAILED"] >= 1
        assert payload["actual_model_usage"]["input_tokens"] is None
        assert payload["actual_model_usage"]["status"] == "UNKNOWN"
        assert payload["knowledge_budget_reservations"][0]["reserved_input_tokens"] == 6000
        assert "PRIVATE_" not in response.text
        detail = client.get(f"/admin/operations/tasks/assistant/{task.id}").json()
        assert detail["attempt"] == 2
        assert detail["error_code"] == "REDACTED"
        assert detail["stages"][0]["elapsed_ms"] == 42
        assert client.get("/admin/operations/tasks/assistant/999999").status_code == 404
        assert client.get("/admin/operations?days=999").status_code == 422
    finally:
        app.dependency_overrides.clear()
        db_session.delete(stage)
        db_session.delete(task)
        db_session.delete(budget)
        db_session.commit()
        db_session.delete(session)
        db_session.commit()


def test_operations_handles_knowledge_task_without_started_at(db_session, test_user):
    """KnowledgeBuildTask has no started_at; the overview must not 500 on it."""
    from common.models.learning import KnowledgeBuildTask

    knowledge_task = KnowledgeBuildTask(
        actor_user_id=test_user.id,
        client_request_id="knowledge-ops-fixture",
        request_hash="f" * 64,
        trigger_source="manual",
        operation_type="SEARCH_SOURCES",
        subject="fixture",
        status="COMPLETED",
    )
    db_session.add(knowledge_task)
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=test_user.id, role="admin"
    )
    client = TestClient(app)
    try:
        response = client.get("/admin/operations")
        assert response.status_code == 200, response.text
        kinds = {row["kind"] for row in response.json()["recent_tasks"]}
        assert "knowledge" in kinds
    finally:
        app.dependency_overrides.clear()
        db_session.delete(knowledge_task)
        db_session.commit()
