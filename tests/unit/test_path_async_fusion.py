"""Persisted async paths, broker fallback and ownership without model calls."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.models.learning import CoordinationTask, LearningPath, Resource, User
from common.schemas.agent import CoordinationRequest
from services.agent_service.app.api.routes import agents, learning
from services.agent_service.app.services import path_worker as worker


@pytest.fixture
def sessions(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    with factory() as db:
        db.add_all([User(id=i, username=f"async-{i}", password_hash="unused", role="student") for i in (1, 2)])
        db.commit()
    yield factory
    engine.dispose()


def test_enqueue_broker_failure_execution_and_owner_poll(sessions, monkeypatch):
    def unavailable(*args):
        raise ConnectionError("broker unavailable")
    monkeypatch.setattr(agents.RabbitMQPublisher, "publish", unavailable)
    owner = SimpleNamespace(id=1, role="student")
    peer = SimpleNamespace(id=2, role="student")
    with sessions() as db:
        result = agents.coordinate_async(CoordinationRequest(user_id=1, intent="learning path"), db, owner)
        task_id = result["task_id"]
        assert result["status"] == "QUEUED"
        with pytest.raises(HTTPException) as denied:
            agents.coordination_task(task_id, db, peer)
        assert denied.value.status_code == 403
        assert agents.coordination_task_list(db, peer)["items"] == []
    calls = []
    def run(payload, db):
        calls.append(payload.user_id)
        # A second consumer must not execute a RUNNING request.
        worker.execute_task(task_id)
        return {"status": "success", "outputs": {"path_planning_agent": {"learning_path": {"subject": "数学"}}}}
    monkeypatch.setattr(worker, "run_coordination", run)
    worker.execute_task(task_id)
    worker.execute_task(task_id)
    with sessions() as db:
        data = agents.coordination_task(task_id, db, owner)
        assert data["status"] == "SUCCEEDED"
        assert data["result"]["outputs"]["path_planning_agent"]["learning_path"]["subject"] == "数学"
    assert calls == [1]


def test_sweep_persists_failure(sessions, monkeypatch):
    with sessions() as db:
        db.add(CoordinationTask(user_id=1, request_json={"user_id": 1, "intent": "path"},
                                created_at=datetime.utcnow() - timedelta(minutes=1)))
        db.commit()
    def fail(*args):
        raise ValueError("controlled failure")
    monkeypatch.setattr(worker, "run_coordination", fail)
    assert worker.sweep_stale() == 1
    with sessions() as db:
        row = db.query(CoordinationTask).one()
        assert row.status == "FAILED" and row.error_code == "ValueError"
        assert row.completed_at is not None


def test_connection_failure_runs_database_sweep(monkeypatch):
    import pika
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(rabbitmq_url="amqp://guest:guest@localhost/"))
    def unavailable(*args):
        raise ConnectionError("controlled broker failure")
    monkeypatch.setattr(pika, "BlockingConnection", unavailable)
    sweeps = []
    monkeypatch.setattr(worker, "sweep_stale", lambda: sweeps.append(True))
    def stop(_):
        raise KeyboardInterrupt
    monkeypatch.setattr(worker.time, "sleep", stop)
    with pytest.raises(KeyboardInterrupt):
        worker.consume_forever()
    assert sweeps == [True]


def test_history_is_owner_scoped_and_read_only(sessions):
    owner = SimpleNamespace(id=1, role="student")
    peer = SimpleNamespace(id=2, role="student")
    with sessions() as db:
        row = LearningPath(user_id=1, status="archived", path_data_json={"subject": "数学", "teacher_scope": None,
                           "stages": [{"tasks": [{"title": "练习"}]}]})
        db.add(row)
        db.commit()
        data = learning.list_path_history(1, db, owner, limit=10, offset=0)
        assert data["total"] == 1 and data["items"][0]["task_count"] == 1
        assert learning.get_path_history_item(row.id, db, owner)["subject"] == "数学"
        with pytest.raises(HTTPException):
            learning.get_path_history_item(row.id, db, peer)
        with pytest.raises(HTTPException):
            learning.list_path_history(1, db, peer, limit=10, offset=0)
        assert db.get(LearningPath, row.id).status == "archived"


def test_history_attaches_the_closest_owned_courseware(sessions):
    """Each history row opens the courseware generated around that run."""

    owner = SimpleNamespace(id=1, role="student")
    early = datetime(2026, 10, 22, 12, 56, 45)
    late = early + timedelta(hours=2)
    with sessions() as db:
        db.add(LearningPath(user_id=1, created_at=early, path_data_json={
            "subject": "计算机组成原理",
            "knowledge_point": "存储系统",
            "stages": [{"tasks": [{"knowledge_point_id": 518}]}],
        }))
        db.add(LearningPath(user_id=1, created_at=late, path_data_json={
            "subject": "计算机组成原理",
            "knowledge_point": "存储系统",
            "stages": [{"tasks": [{"knowledge_point_id": 518}]}],
        }))
        db.add_all([
            Resource(id=237, title="早期课件", type="courseware", content="old",
                     knowledge_point_id=518, generated_for_user_id=1,
                     generation_status="generated", publish_status="draft", created_at=early),
            Resource(id=240, title="后期课件", type="courseware", content="new",
                     knowledge_point_id=518, generated_for_user_id=1,
                     generation_status="generated", publish_status="draft", created_at=late),
            Resource(id=241, title="已归档", type="courseware", content="archived",
                     knowledge_point_id=518, generated_for_user_id=1,
                     generation_status="generated", publish_status="archived", created_at=early),
            Resource(id=250, title="别人的", type="courseware", content="other",
                     knowledge_point_id=518, generated_for_user_id=2,
                     generation_status="generated", publish_status="draft", created_at=late),
        ])
        db.commit()

        items = learning.list_path_history(1, db, owner, limit=10, offset=0)["items"]
        by_id = {item["id"]: item for item in items}
        assert by_id[1]["courseware_resource_id"] == 237
        assert by_id[1]["courseware_title"] == "早期课件"
        assert by_id[1]["courseware_created_at"] is not None
        assert by_id[2]["courseware_resource_id"] == 240
        assert by_id[2]["courseware_title"] == "后期课件"


def test_history_never_links_another_learners_courseware(sessions):
    owner = SimpleNamespace(id=1, role="student")
    with sessions() as db:
        db.add(LearningPath(user_id=1, path_data_json={
            "subject": "计算机网络",
            "knowledge_point": "UDP",
            "stages": [{"tasks": [{"knowledge_point_id": 600}]}],
        }))
        db.add(Resource(id=300, title="别人的", type="courseware", content="x",
                        knowledge_point_id=600, generated_for_user_id=2,
                        generation_status="generated", publish_status="draft"))
        db.commit()

        item = learning.list_path_history(1, db, owner, limit=10, offset=0)["items"][0]
        assert item["courseware_resource_id"] is None

