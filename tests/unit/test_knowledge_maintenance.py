from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import KnowledgeBuildTask, KnowledgeMaintenancePlan, User
from services.agent_service.app.main import app
from services.agent_service.app.services import knowledge_maintenance


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'maintenance.db'}")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    with maker() as db:
        db.add(User(id=1, username="plan-admin", password_hash="unused", role="admin"))
        db.commit()
    monkeypatch.setattr(knowledge_maintenance, "SessionLocal", maker)
    yield maker
    engine.dispose()


def test_recurring_plan_dispatch_is_idempotent(factory) -> None:
    first = datetime.now(timezone.utc) + timedelta(hours=1)
    with factory() as db:
        plan = knowledge_maintenance.create_plan(
            db, actor_user_id=1, name="Weekly inspection", subject="python",
            next_run_at=first, interval_hours=168,
        )
        plan_id = plan.id
    due = first.replace(tzinfo=None) + timedelta(minutes=1)
    assert knowledge_maintenance.dispatch_due_plans(due) == 1
    assert knowledge_maintenance.dispatch_due_plans(due) == 0
    with factory() as db:
        plan = db.get(KnowledgeMaintenancePlan, plan_id)
        task = db.get(KnowledgeBuildTask, plan.last_task_id)
        assert task.trigger_source == "ADMIN_SCHEDULED"
        assert task.status == "QUEUED"
        assert plan.next_run_at == first.replace(tzinfo=None) + timedelta(hours=168)


def test_one_time_plan_disables_after_dispatch(factory) -> None:
    first = datetime.now(timezone.utc) + timedelta(hours=1)
    with factory() as db:
        plan = knowledge_maintenance.create_plan(
            db, actor_user_id=1, name="Once", subject="", next_run_at=first,
            interval_hours=None,
        )
        plan_id = plan.id
    assert knowledge_maintenance.dispatch_due_plans(first.replace(tzinfo=None)) == 1
    with factory() as db:
        plan = db.get(KnowledgeMaintenancePlan, plan_id)
        assert plan.enabled is False
        assert plan.next_run_at is None
        assert db.get(KnowledgeBuildTask, plan.last_task_id).trigger_source == "ADMIN_ONE_TIME_SCHEDULED"


def test_paused_plan_is_not_dispatched(factory) -> None:
    first = datetime.now(timezone.utc) + timedelta(hours=1)
    with factory() as db:
        plan = knowledge_maintenance.create_plan(
            db, actor_user_id=1, name="Paused", subject="python",
            next_run_at=first, interval_hours=24,
        )
        plan.enabled = False
        db.commit()
    assert knowledge_maintenance.dispatch_due_plans(first.replace(tzinfo=None)) == 0


def test_plan_api_permission_and_pause(factory) -> None:
    client = TestClient(app)
    payload = {
        "name": "Inspect Python", "subject": "python",
        "next_run_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "interval_hours": 168,
    }
    assert client.post("/knowledge-base/maintenance-plans", json=payload).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[get_db] = lambda: factory()
    try:
        created = client.post("/knowledge-base/maintenance-plans", json=payload)
        assert created.status_code == 201
        plan_id = created.json()["id"]
        assert client.patch(f"/knowledge-base/maintenance-plans/{plan_id}", json={"enabled": False}).json()["enabled"] is False
        assert len(client.get("/knowledge-base/maintenance-plans").json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_policy_plan_dispatches_one_bounded_maintenance_task(factory):
    first = datetime.now(timezone.utc) + timedelta(hours=1)
    with factory() as db:
        plan = knowledge_maintenance.create_plan(db, actor_user_id=1, name="point maintenance", subject="python",
                    next_run_at=first, interval_hours=168,
                    policy={"mode": "AUTO_SUPPLEMENT_REVIEW", "point_ids": [1, 2], "max_supplement_points": 1})
        plan_id = plan.id
    assert knowledge_maintenance.dispatch_due_plans(first.replace(tzinfo=None)) == 1
    assert knowledge_maintenance.dispatch_due_plans(first.replace(tzinfo=None)) == 0
    with factory() as db:
        task = db.get(KnowledgeBuildTask, db.get(KnowledgeMaintenancePlan, plan_id).last_task_id)
        assert task.operation_type == "MAINTENANCE_RUN"
        assert task.requirements_json["policy"]["max_supplement_points"] == 1


def test_large_course_inspection_continues_after_fifty_points(factory, monkeypatch):
    from common.models.learning import KnowledgePoint, SystemSubject
    from services.agent_service.app.services import knowledge_acquisition

    with factory() as db:
        subject = SystemSubject(name="Large course", code="large_course", description="pagination")
        db.add(subject); db.flush()
        db.add_all([KnowledgePoint(name=f"Point {index}", subject_id=subject.id) for index in range(51)])
        db.commit()
    monkeypatch.setattr(knowledge_acquisition, "assess_coverage", lambda *_args, **_kwargs: {"state": "COMPLETE", "missing_facets": []})
    task = SimpleNamespace(id=999, subject="large_course", requirements_json={"plan_id": 0, "policy": {"mode": "INSPECT_ONLY"}})
    first = knowledge_maintenance.run_maintenance(task, lambda *_args: None)
    assert first["scanned_points"] == 50 and first["remaining_points"] == 1
    task.requirements_json["policy"]["scan_after_point_id"] = first["next_scan_after_point_id"]
    second = knowledge_maintenance.run_maintenance(task, lambda *_args: None)
    assert second["scanned_points"] == 1 and second["remaining_points"] == 0
    assert not ({row["point_id"] for row in first["issues"]} & {row["point_id"] for row in second["issues"]})
