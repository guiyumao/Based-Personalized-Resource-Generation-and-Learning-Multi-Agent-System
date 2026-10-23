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


def test_new_path_preserves_other_topics_and_busy_workspace(workspace):
    from services.agent_service.app.services.learning_path import LearningPathService
    with workspace() as db:
        context = open_context(db)
        plan = db.get(LearningPath, 1)
        original = deepcopy(plan.path_data_json)
        original["knowledge_point"] = "TCP"
        plan.path_data_json = original
        db.get(AssistantTask, 1).status = "PENDING"
        db.get(AssistantTask, 1).request_json = {"learning_context_id": context.id}
        db.commit()
        service = LearningPathService(db)
        service._persist_generated_path(1, {**original, "knowledge_point": "UDP"})
        service._persist_generated_path(1, original)
        assert db.get(LearningPath, 1).status == "active"
        assert validate_context(db, 1, context.id)[1].id == 1
        db.get(AssistantTask, 1).status = "SUCCEEDED"
        db.commit()
        service._persist_generated_path(1, original)
        assert db.get(LearningPath, 1).status == "archived"
        assert db.query(LearningPath).filter_by(status="active").count() == 2


def test_workspace_task_lookup_is_context_and_owner_scoped(workspace):
    with workspace() as db:
        context = open_context(db)
        task = db.get(AssistantTask, 1)
        task.request_json = {"learning_context_id": context.id}
        other = AssistantTask(user_id=2, session_id=1, client_request_id="foreign-task",
                              task_type="exercise", status="SUCCEEDED", request_json=task.request_json)
        db.add(other)
        db.commit()
        context_id = context.id
    client = TestClient(app)
    assert [t["id"] for t in client.get('/assistant/tasks', params={"learning_context_id": context_id}).json()] == [1]
    assert client.get('/assistant/tasks', params={"learning_context_id": "missing"}).json() == []


def test_task_catalog_keeps_resource_binding_and_exercises_when_opening_courseware(workspace):
    with workspace() as db:
        source = open_context(db, "quiz-origin")
        bind_generated_exercises(db, 1, source.id, 1, [1])
        resource = db.get(Resource, 1)
        opened = open_context(db, "courseware-open", resource_id=1,
                              expected_resource_version=resource_version(resource))
        assert [quiz["exercise_id"] for quiz in context_snapshot(db, 1, opened.id)["exercises"]] == [1]
        other = open_context(db, "other-task", task_key="t2")
        assert context_snapshot(db, 1, other.id)["exercises"] == []
    catalog = TestClient(app).get('/learning/contexts/catalog').json()
    assert [(row['task_id'], row['id']) for row in catalog['task_resources']] == [('t1', 1)]
    with workspace() as db:
        db.get(Resource, 1).content = 'changed source'
        db.commit()
    assert TestClient(app).get('/learning/contexts/catalog').json()['task_resources'] == []


def test_workspace_generation_uses_authoritative_subject_and_point(workspace, monkeypatch):
    from services.agent_service.app.services import assistant_tasks
    with workspace() as db:
        origin = open_context(db, 'generation-context')
        task = db.get(AssistantTask, 1)
        task.task_type = 'exercise'
        task.request_json = {'learning_context_id': origin.id, 'knowledge_point': 'TCP',
                             'knowledge_subject': 'wrong subject', 'message': '生成3道练习',
                             'exercise_count': 3, 'allow_web_knowledge': True}
        def workflow(db, task, request):
            assert request.payload['subject'] == '计算机网络'
            assert request.payload['knowledge_point_id'] == '1'
            assert request.payload['dynamic_knowledge'] is True
            assert request.payload['allow_web_knowledge'] is True
            return {'status': 'success', 'outputs': {'exercise_generation_agent': {
                'exercise_set': {'exercises': [{'exercise_id': 1}]}}}}
        monkeypatch.setattr(assistant_tasks, '_run_task_workflow', workflow)
        result, _ = assistant_tasks._coordinated_result(db, task)
        assert result['cards'][0]['exercise_ids'] == [1]


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


def test_personal_draft_plan_can_open_workspace_context(tmp_path):
    """A personal-draft plan has no public subject/point, but the workspace must
    still open it by creating an owner-scoped personal knowledge point."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'personal.sqlite'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=1, username="owner", password_hash="unused"))
        db.add(
            LearningPath(
                id=1, user_id=1, status="active",
                path_data_json={
                    "subject": "数据结构", "knowledge_scope": "personal_draft", "path_revision": 0,
                    "stages": [{"stage_id": "s1", "tasks": [{"task_id": "t1", "knowledge_point": "链表"}]}],
                },
            )
        )
        db.commit()
        # No public SystemSubject / KnowledgePoint exists for 数据结构.
        assert db.query(SystemSubject).count() == 0
        row = create_context(
            db, 1, client_request_id="personal-ctx-1",
            plan_id=1, module_id="s1", task_key="t1",
        )
        point = db.get(KnowledgePoint, row.knowledge_point_id)
        assert point is not None
        assert point.subject_id is None
        assert point.construction_status == "PERSONAL_DRAFT"
        snap = context_snapshot(db, 1, row.id)
        assert snap["knowledge_point"] == "链表"
        assert snap["subject"] == "数据结构"
        # No public catalog entry was created for the personal draft.
        assert db.query(SystemSubject).count() == 0
    engine.dispose()


def test_legacy_plan_with_unknown_subject_can_open_workspace_context(tmp_path):
    """Old plans whose subject was never catalogued must still open in the workspace."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'legacy.sqlite'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=1, username="owner", password_hash="unused"))
        db.add(
            LearningPath(
                id=1, user_id=1, status="active",
                path_data_json={
                    "subject": "Python 程序设计", "path_revision": 0,
                    "stages": [{"stage_id": "s1", "tasks": [{"task_id": "t1", "knowledge_point": "Python 循环"}]}],
                },
            )
        )
        db.commit()
        assert db.query(SystemSubject).count() == 0
        row = create_context(
            db, 1, client_request_id="legacy-ctx-1",
            plan_id=1, module_id="s1", task_key="t1",
        )
        point = db.get(KnowledgePoint, row.knowledge_point_id)
        assert point is not None
        assert point.subject_id is None
        assert db.query(SystemSubject).count() == 0
    engine.dispose()


def test_legacy_owned_resource_point_is_reused_not_replaced(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-resource.sqlite'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=1, username="legacy-resource-owner", password_hash="unused"))
        db.add(KnowledgePoint(id=1, name="legacy-point", subject_id=None))
        db.add(LearningPath(id=1, user_id=1, status="active", path_data_json={
            "subject":"legacy-subject", "stages":[{"stage_id":"s1", "tasks":[{"task_id":"t1", "knowledge_point":"legacy-point"}]}]}))
        db.add(Resource(id=1, title="existing resource", type="courseware", content="source", knowledge_point_id=1,
                        generated_for_user_id=1, publish_status="draft", audit_status="passed"))
        db.commit()
        no_resource = create_context(db, 1, client_request_id="legacy-no-resource", plan_id=1, module_id="s1", task_key="t1")
        assert no_resource.knowledge_point_id == 1
        assert len(context_snapshot(db, 1, no_resource.id)["resource_candidates"]) == 1
        resource = db.get(Resource,1)
        selected = create_context(db, 1, client_request_id="legacy-selected-resource", plan_id=1, module_id="s1", task_key="t1",
                                  resource_id=1, expected_resource_version=resource_version(resource))
        assert context_snapshot(db, 1, selected.id)["resource"]["id"] == 1
    engine.dispose()
