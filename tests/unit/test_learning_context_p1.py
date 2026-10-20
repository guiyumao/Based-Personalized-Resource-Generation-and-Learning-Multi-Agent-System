"""Persistent context boundaries and atomic grading, without external models."""

import asyncio
import json
from copy import deepcopy
from datetime import datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.learning_context import (
    bind_generated_exercises,
    context_snapshot,
    create_context,
    validate_context,
)
from common.models.learning import (
    AnswerRecord,
    AssistantTask,
    ChatSession,
    Exercise,
    KnowledgePoint,
    LearningPath,
    Resource,
    SystemSubject,
    User,
)
from common.resource_version import resource_version
from services.agent_service.app.main import app
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


@pytest.fixture
def workspace(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'workspace.sqlite'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all(
            [
                User(id=1, username="owner", password_hash="unused"),
                User(id=2, username="other", password_hash="unused"),
            ]
        )
        db.add(SystemSubject(id=1, name="计算机网络", code="network", description="fixture"))
        db.flush()
        db.add(KnowledgePoint(id=1, name="TCP", subject_id=1))
        db.add(
            LearningPath(
                id=1,
                user_id=1,
                status="active",
                path_data_json={
                    "subject": "计算机网络",
                    "path_revision": 0,
                    "stages": [
                        {
                            "stage_id": "s1",
                            "tasks": [
                                {"task_id": "t1", "knowledge_point": "TCP"},
                                {"task_id": "t2", "knowledge_point": "TCP"},
                            ],
                        }
                    ],
                },
            )
        )
        db.add_all(
            [
                Resource(
                    id=1,
                    title="owner source",
                    type="article",
                    content="# TCP\nFixture",
                    knowledge_point_id=1,
                    generated_for_user_id=1,
                ),
                Resource(
                    id=2,
                    title="other source",
                    type="article",
                    content="private",
                    knowledge_point_id=1,
                    generated_for_user_id=2,
                ),
            ]
        )
        db.add(ChatSession(id=1, user_id=1, title="fixture"))
        db.flush()
        db.add(
            AssistantTask(
                id=1,
                user_id=1,
                session_id=1,
                client_request_id="fixture-task",
                task_type="exercise",
                status="COMPLETED",
            )
        )
        db.add(
            Exercise(
                id=1,
                knowledge_point_id=1,
                type="choice",
                content=json.dumps(
                    {
                        "generated_for_user_id": 1,
                        "prompt": "TCP?",
                        "options": ["A. reliable", "B. unreliable"],
                    }
                ),
                answer="A",
                assistant_operation_key="assistant:1:exercise:0",
            )
        )
        db.commit()

    def database():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username="owner", password_hash="unused"
    )
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


def open_context(db, key="context-request", **kwargs):
    return create_context(
        db,
        1,
        client_request_id=key,
        plan_id=1,
        module_id="s1",
        task_key=kwargs.pop("task_key", "t1"),
        **kwargs,
    )


def test_api_refresh_idempotency_private_and_cross_user(workspace):
    client = TestClient(app)
    with workspace() as db:
        version = resource_version(db.get(Resource, 1))
    body = dict(
        client_request_id="open-context-one",
        plan_id=1,
        module_id="s1",
        task_key="t1",
        resource_id=1,
        expected_resource_version=version,
    )
    first = client.post("/learning/contexts", json=body)
    assert first.status_code == 201, first.text
    context_id = first.json()["id"]
    assert client.post("/learning/contexts", json=body).json()["id"] == context_id
    assert client.get(f"/learning/contexts/{context_id}").json()["resource"]["version"] == version
    assert [row["id"] for row in first.json()["resource_candidates"]] == [1]
    assert client.post("/learning/contexts", json={**body, "task_key": "t2"}).status_code == 409
    assert (
        client.post(
            "/learning/contexts",
            json={**body, "client_request_id": "other-resource", "resource_id": 2},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/learning/contexts",
            json={**body, "client_request_id": "bad-task-key", "task_key": "missing"},
        ).status_code
        == 409
    )
    app.dependency_overrides[get_current_user] = lambda: User(
        id=2, username="other", password_hash="unused"
    )
    assert client.get(f"/learning/contexts/{context_id}").status_code == 404
    assert client.get("/learning/contexts/catalog").json()["plans"] == []


@pytest.mark.parametrize("change", ["resource", "archive", "subject", "task", "plan"])
def test_invalidated_context_rejects_old_bindings(workspace, change):
    with workspace() as db:
        context = open_context(
            db, resource_id=1, expected_resource_version=resource_version(db.get(Resource, 1))
        )
        context_id = context.id
        if change == "resource":
            db.get(Resource, 1).content = "new version"
        elif change == "archive":
            db.get(Resource, 1).publish_status = "archived"
        elif change == "plan":
            db.get(LearningPath, 1).status = "archived"
        else:
            plan = db.get(LearningPath, 1)
            payload = deepcopy(plan.path_data_json)
            if change == "subject":
                payload["subject"] = "unknown"
            else:
                payload["stages"][0]["tasks"] = []
            plan.path_data_json = payload
        db.commit()
        with pytest.raises(HTTPException) as caught:
            validate_context(db, 1, context_id)
        assert caught.value.status_code == 409


def test_grading_receipt_and_task_evidence_commit_once(workspace):
    with workspace() as db:
        context_id = open_context(db).id
        bind_generated_exercises(db, 1, context_id, 1, [1])
        db.commit()

    class Publisher:
        def publish(self, *_):
            pass

    service = ReportService(session_factory=workspace, publisher=Publisher())
    request = PracticeSubmission(
        user_id=1,
        exercise_id=1,
        knowledge_point="forged",
        question_type="choice",
        user_answer="A",
        correct_answer="B",
        analysis="forged",
        client_request_id="context-answer-one",
        learning_context_id=context_id,
    )
    first = asyncio.run(service.evaluate_practice(request))
    assert first.is_correct is True
    assert asyncio.run(service.evaluate_practice(request)) == first
    with workspace() as db:
        assert db.query(AnswerRecord).count() == 1
        snapshot = context_snapshot(db, 1, context_id)
        assert snapshot["task"]["learning_evidence"]["graded_exercises"] == 1
        assert snapshot["plan_revision"] == 1
        assert snapshot["exercises"][0]["feedback"]["is_correct"] is True
        second_id = open_context(db, key="context-second", task_key="t2").id
    with pytest.raises(HTTPException):
        asyncio.run(
            service.evaluate_practice(
                request.model_copy(
                    update={
                        "learning_context_id": second_id,
                        "client_request_id": "cross-context-answer",
                    }
                )
            )
        )
    with workspace() as db:
        assert db.query(AnswerRecord).count() == 1


def test_worker_cannot_write_after_source_changes(workspace):
    from services.agent_service.app.services.assistant_execution import (
        ExecutionStopped,
        current_execution,
        ensure_write_allowed,
    )

    with workspace() as db:
        context_id = open_context(
            db, resource_id=1, expected_resource_version=resource_version(db.get(Resource, 1))
        ).id
        task = db.get(AssistantTask, 1)
        task.status, task.worker_id, task.execution_attempt = "RUNNING", "worker-test", 1
        task.heartbeat_at = datetime.utcnow()
        task.request_json = {"learning_context_id": context_id}
        db.commit()
        db.get(Resource, 1).content = "changed during generation"
        db.commit()
        guard = current_execution.set((1, "worker-test", 1))
        try:
            with pytest.raises(ExecutionStopped):
                ensure_write_allowed(db)
        finally:
            current_execution.reset(guard)
        assert db.query(Resource).count() == 2


def test_qa_server_excerpt_and_conversations_cannot_cross_contexts(workspace, monkeypatch):
    from services.agent_service.app.services.chat_service import ChatService

    with workspace() as db:
        first = open_context(
            db, resource_id=1, expected_resource_version=resource_version(db.get(Resource, 1))
        ).id
        second = open_context(db, key="qa-second-context", task_key="t2").id
    monkeypatch.setattr(
        ChatService, "_search_knowledge_base", lambda *_: {"found": True, "articles": []}
    )
    monkeypatch.setattr(ChatService, "_should_use_large_model", lambda *_: False)
    calls = []

    def answer(
        self, question, history, kb_result, learning_context, teaching_mode, attachment_context
    ):
        calls.append(attachment_context)
        return "controlled context answer", "test-stub"

    monkeypatch.setattr(ChatService, "_generate_with_small_model", answer)
    client = TestClient(app)
    body = {
        "message": "解释当前内容",
        "action": "qa",
        "client_request_id": "context-qa-one",
        "learning_context_id": first,
        "use_learning_context": False,
    }
    response = client.post("/assistant/chat", json=body)
    assert response.status_code == 200, response.text
    assert "# TCP\nFixture" in calls[0]
    conversation = response.json()["conversation_id"]
    assert (
        client.post(
            "/assistant/chat",
            json={**body, "conversation_id": conversation, "learning_context_id": second},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/assistant/chat",
            json={**body, "conversation_id": conversation, "learning_context_id": None},
        ).status_code
        == 409
    )
    assert (
        client.post("/assistant/chat", json={**body, "knowledge_point": "UDP"}).status_code == 409
    )
    assert len(calls) == 1


def test_note_keeps_historical_source_version_when_edited(workspace):
    from common.security.auth import create_access_token
    from services.user_service.app.main import app as user_app

    with workspace() as db:
        version = resource_version(db.get(Resource, 1))
        context_id = open_context(db, resource_id=1, expected_resource_version=version).id

    def database():
        with workspace() as db:
            yield db

    user_app.dependency_overrides[get_db] = database
    try:
        client = TestClient(user_app)
        headers = {"Authorization": f"Bearer {create_access_token('1')}"}
        note = client.post(
            "/study/notes",
            headers=headers,
            json={"title": "source", "body": "original", "learning_context_id": context_id},
        )
        assert note.status_code == 201, note.text
        note_id = note.json()["id"]
        assert note.json()["source_resource_version"] == version
        with workspace() as db:
            db.get(Resource, 1).content = "changed after note"
            db.commit()
        changed = client.put(
            f"/study/notes/{note_id}",
            headers=headers,
            json={"title": "edited", "body": "historical note"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["source_resource_version"] == version
        assert changed.json()["learning_context_id"] == context_id
        assert (
            client.post(
                "/study/notes",
                headers=headers,
                json={"title": "late", "body": "rejected", "learning_context_id": context_id},
            ).status_code
            == 409
        )
    finally:
        user_app.dependency_overrides.clear()


def test_appended_plan_task_preserves_existing_context(workspace):
    with workspace() as db:
        context_id = open_context(db).id
        plan = db.get(LearningPath, 1)
        payload = deepcopy(plan.path_data_json)
        payload["path_revision"] = 1
        payload["stages"][0]["tasks"].append({"task_id": "adapted-task", "knowledge_point": "TCP"})
        plan.path_data_json = payload
        db.commit()
        assert context_snapshot(db, 1, context_id)["plan_revision"] == 1
        assert context_snapshot(db, 1, context_id)["task_id"] == "t1"


def test_generated_exercise_binding_rejects_another_owner(workspace):
    with workspace() as db:
        context_id = open_context(db).id
        exercise = db.get(Exercise, 1)
        exercise.content = json.dumps({"prompt": "private", "generated_for_user_id": 2})
        db.commit()
        with pytest.raises(HTTPException) as caught:
            bind_generated_exercises(db, 1, context_id, 1, [1])
        assert caught.value.status_code == 404
