from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import KnowledgeBuildTask, User
from services.agent_service.app.main import app
from services.agent_service.app.services import knowledge_tasks
from services.agent_service.app.services.deepseek_search import DeepSeekSearchUnavailable


@pytest.fixture
def task_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge-tasks.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        db.add(User(id=1, username="kb-admin", password_hash="unused", role="admin"))
        db.commit()
    monkeypatch.setattr(knowledge_tasks, "SessionLocal", factory)
    yield factory
    engine.dispose()


def test_admin_task_idempotency_and_worker_result(task_db, monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge_tasks, "knowledge_base_status",
        lambda: {"corpus": {"documents": 2}, "index": {"chunks": 3}},
    )
    monkeypatch.setattr(
        knowledge_tasks, "list_knowledge_subject_catalog",
        lambda: [{"value": "python", "resource_count": 2}],
    )
    monkeypatch.setattr(
        knowledge_tasks, "list_knowledge_sources",
        lambda: [{"subject": "python", "topic": "Loops", "status": "not_crawled"}],
    )
    with task_db() as db:
        task = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="same-click",
            operation_type="KNOWLEDGE_HEALTH_CHECK", subject="python",
        )
        same = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="same-click",
            operation_type="KNOWLEDGE_HEALTH_CHECK", subject="python",
        )
        assert same.id == task.id
        repeated_click = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="another-click",
            operation_type="KNOWLEDGE_HEALTH_CHECK", subject="python",
        )
        assert repeated_click.id == task.id
        with pytest.raises(knowledge_tasks.KnowledgeTaskConflict):
            knowledge_tasks.create_task(
                db, actor_user_id=1, client_request_id="same-click",
                operation_type="INDEX_REPAIR", subject="python",
            )
        task_id = task.id
    assert knowledge_tasks.run_pending_tasks() == 1
    assert knowledge_tasks.run_pending_tasks() == 0
    with task_db() as db:
        completed = db.get(KnowledgeBuildTask, task_id)
        assert completed.status == "COMPLETED"
        assert completed.result_json["subject_found"] is True
        assert completed.result_json["subjects"][0]["value"] == "python"
        assert any(
            issue["code"] == "CONFIGURED_SOURCE_NOT_CRAWLED"
            for issue in completed.result_json["issues"]
        )


def test_queued_cancel_prevents_execution(task_db) -> None:
    with task_db() as db:
        task = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="cancel-me",
            operation_type="INDEX_REPAIR",
        )
        knowledge_tasks.cancel_task(db, task)
        assert task.status == "CANCELLED"
        assert knowledge_tasks.execute_task(task.id) is False


def test_admin_api_requires_auth_and_rejects_student(task_db) -> None:
    client = TestClient(app)
    assert client.post(
        "/knowledge-base/tasks",
        json={"client_request_id": "a", "operation_type": "KNOWLEDGE_HEALTH_CHECK"},
    ).status_code == 401

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2, role="student")
    try:
        assert client.get("/knowledge-base/tasks").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_api_creates_and_reads_task(task_db) -> None:
    def db_override():
        with task_db() as db:
            yield db

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[get_db] = db_override
    client = TestClient(app)
    try:
        response = client.post(
            "/knowledge-base/tasks",
            json={"client_request_id": "api-one", "operation_type": "KNOWLEDGE_HEALTH_CHECK"},
        )
        assert response.status_code == 202
        task_id = response.json()["id"]
        assert client.get(f"/knowledge-base/tasks/{task_id}").json()["status"] == "QUEUED"
        assert client.post(f"/knowledge-base/tasks/{task_id}/cancel").json()["status"] == "CANCELLED"
    finally:
        app.dependency_overrides.clear()


def test_search_then_fetch_creates_review_candidate(task_db, monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge_tasks, "search_sources",
        lambda query: [{"title": "Course", "url": "https://example.edu/course", "summary": query}],
    )
    monkeypatch.setattr(
        knowledge_tasks, "fetch_source",
        lambda url: {"url": url, "title": "Course", "content": "Reviewed source text"},
    )
    with task_db() as db:
        search = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="search-1",
            operation_type="SEARCH_SOURCES", subject="python",
            requirements={"query": "Python loops"},
        )
        search_id = search.id
    assert knowledge_tasks.execute_task(search_id)
    with task_db() as db:
        repeated_search = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="search-again",
            operation_type="SEARCH_SOURCES", subject="python",
            requirements={"query": "Python loops"},
        )
        assert repeated_search.id == search_id
        fetched = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="fetch-1",
            operation_type="FETCH_SOURCE",
            requirements={"source_task_id": search_id, "source_index": 0},
        )
        fetch_id = fetched.id
    assert knowledge_tasks.execute_task(fetch_id)
    with task_db() as db:
        result = db.get(KnowledgeBuildTask, fetch_id).result_json
        assert result["review_status"] == "PENDING"
        assert result["source"]["content"] == "Reviewed source text"


def test_unavailable_search_fails_without_publishing(task_db, monkeypatch) -> None:
    def unavailable(_query):
        raise DeepSeekSearchUnavailable("No configured key")

    monkeypatch.setattr(knowledge_tasks, "search_sources", unavailable)
    with task_db() as db:
        task = knowledge_tasks.create_task(
            db, actor_user_id=1, client_request_id="search-no-key",
            operation_type="SEARCH_SOURCES", requirements={"query": "Python loops"},
        )
        task_id = task.id
    assert knowledge_tasks.run_pending_tasks() == 1
    with task_db() as db:
        failed = db.get(KnowledgeBuildTask, task_id)
        assert failed.status == "FAILED"
        assert failed.error_code == "DEEPSEEK_SEARCH_UNAVAILABLE"
        assert failed.result_json == {}


def test_stale_worker_cannot_overwrite_recovered_task(task_db) -> None:
    with task_db() as db:
        task = knowledge_tasks.create_task(db, actor_user_id=1, client_request_id="expired",
                                         operation_type="KNOWLEDGE_HEALTH_CHECK")
        task.status = "RUNNING"; task.worker_id = "dead"; task.execution_attempt = 1
        task.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit(); task_id = task.id
    assert not knowledge_tasks.renew_lease(task_id, "dead", 1)
    assert knowledge_tasks.expire_interrupted_tasks() == 1
    assert not knowledge_tasks._finish(task_id, "dead", 1, status="COMPLETED", result_json={"stale": True})
    with task_db() as db:
        item = db.get(KnowledgeBuildTask, task_id)
        assert item.status == "QUEUED"
        assert item.next_attempt_at > datetime.utcnow()
        assert item.result_json == {}


def test_running_cancel_discards_result_and_prevents_replay(task_db, monkeypatch) -> None:
    def cancel_during_search(_query):
        with task_db() as db:
            item = db.query(KnowledgeBuildTask).filter_by(status="RUNNING").one()
            knowledge_tasks.request_cancel(db, item)
        return [{"title": "must not save", "url": "https://example.edu"}]

    monkeypatch.setattr(knowledge_tasks, "search_sources", cancel_during_search)
    with task_db() as db:
        task = knowledge_tasks.create_task(db, actor_user_id=1, client_request_id="running-cancel",
                                         operation_type="SEARCH_SOURCES", requirements={"query": "BBR"})
        task_id = task.id
    knowledge_tasks.execute_task(task_id)
    with task_db() as db:
        item = db.get(KnowledgeBuildTask, task_id)
        assert item.status == "CANCELLED"
        assert item.result_json == {}
    assert not knowledge_tasks.execute_task(task_id)


def test_uncertain_index_write_is_not_retried(task_db) -> None:
    with task_db() as db:
        task = knowledge_tasks.create_task(db, actor_user_id=1, client_request_id="index-crash", operation_type="INDEX_REPAIR")
        task.status = "RUNNING"; task.execution_attempt = 1
        task.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit(); task_id = task.id
    assert knowledge_tasks.expire_interrupted_tasks() == 1
    with task_db() as db:
        assert db.get(KnowledgeBuildTask, task_id).status == "FAILED"
