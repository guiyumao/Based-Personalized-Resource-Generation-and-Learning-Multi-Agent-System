"""Authenticated assistant task lifecycle against an isolated SQLite database."""

from __future__ import annotations

from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import io
import threading
from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.models.learning import AnswerRecord, AssistantAttachment, AssistantMemory, AssistantTask, ChatMessage, ChatSession, Exercise, KnowledgePoint, LearningPath, Resource, User
from common.security.auth import create_access_token
from services.agent_service.app.main import app
from services.agent_service.app.services import assistant_tasks
from services.agent_service.app.services import assistant_execution
from services.agent_service.app.services import assistant_worker
from services.agent_service.app.services.assistant_tasks import _profile_result, detect_action, infer_exercise_count, infer_topic
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.chat_service import ChatService
from services.agent_service.app.services.assistant_attachments import extract_document_text
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.learning_path import LearningPathService
from common.schemas.agent import ExerciseGenerationRequest, LearningPathRequest, ResourceGenerationRequest
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.resource_generation import ResourceGenerationService


def test_replayed_task_includes_public_knowledge_preferences(assistant_client, monkeypatch):
    client, user_id, _ = assistant_client
    monkeypatch.setenv("ASSISTANT_TASK_EXECUTION_MODE", "worker")
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    payload = {"client_request_id": "knowledge-replay-v83", "message": "生成BBR课件", "action": "courseware",
               "knowledge_point": "BBR", "course_key": "computer_networks", "allow_web_knowledge": True}
    first = client.post("/assistant/chat", headers=headers, json=payload)
    second = client.post("/assistant/chat", headers=headers, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["task"]["id"] == second.json()["task"]["id"]
    payload["allow_web_knowledge"] = False
    assert client.post("/assistant/chat", headers=headers, json=payload).status_code == 409


@pytest.fixture
def assistant_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'assistant.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        user = User(username=f"student_{uuid4().hex[:8]}", password_hash="test", role="student")
        other = User(username=f"other_{uuid4().hex[:8]}", password_hash="test", role="student")
        db.add_all([user, other])
        db.commit()
        db.refresh(user)
        db.refresh(other)
        user_id, other_id = user.id, other.id

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(assistant_tasks, "SessionLocal", factory)
    monkeypatch.setattr(assistant_execution, "SessionLocal", factory)
    try:
        yield TestClient(app), user_id, other_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_bounded_action_router():
    assert detect_action("帮我生成 TCP 课件和练习，并制定计划") == "combined"
    assert detect_action("分析我的学情") == "profile"
    assert detect_action("根据我的学习情况推荐学习资源") == "recommend"
    assert detect_action("解释二叉树前序遍历") == "qa"
    assert infer_topic("帮我生成计算机网络 TCP 协议的复习课件，并附带练习题") == "计算机网络 TCP 协议"
    assert infer_topic("生成 TCP 协议课件和三道练习题") == "TCP 协议"
    assert infer_topic("依据附件中的三段数据案例生成 TCP 可靠传输复习课件") == "TCP 可靠传输"
    assert infer_topic("生成20道 TCP 协议强化练习") == "TCP 协议"
    assert infer_exercise_count("生成二十道练习题") == 20
    assert infer_exercise_count("生成15道强化练习") == 15
    assert infer_exercise_count("生成15道 TCP 协议练习题") == 15
    assert infer_exercise_count("解释 TCP 三次握手", 5) == 5


def test_teacher_capabilities_expose_only_supported_assistant_tasks(assistant_client):
    client, _user_id, teacher_id = assistant_client
    with assistant_tasks.SessionLocal() as db:
        db.get(User, teacher_id).role = "teacher"
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(str(teacher_id))}"}
    capabilities = client.get("/assistant/capabilities", headers=headers).json()
    assert capabilities["actions"] == ["qa", "search"]
    assert capabilities["attachment_actions"] == ["qa"]
    assert client.post("/assistant/chat", headers=headers, json={"message": "分析我的学情", "action": "profile"}).status_code == 403
    response = client.post("/assistant/chat", headers=headers, json={"message": "查找二叉树资料", "action": "search"})
    assert response.status_code == 200
    task_id = response.json()["task"]["id"]
    assert client.get(f"/assistant/tasks/{task_id}", headers=headers).json()["status"] == "SUCCEEDED"


def test_assistant_splits_large_exercise_request_into_existing_service_batches(monkeypatch):
    requested_batches = []

    class FakeCoordinator:
        def __init__(self, _db):
            pass

        def run(self, request):
            count = request.payload["exercise_count"]
            requested_batches.append(count)
            start = sum(requested_batches[:-1])
            return {
                "status": "success", "agent_calls": [], "citations": [], "selected_agents": ["exercise_generation_agent"],
                "outputs": {"exercise_generation_agent": {"exercise_set": {
                    "exercises": [{"exercise_id": value} for value in range(start + 1, start + count + 1)],
                }}},
            }

    monkeypatch.setattr(assistant_tasks, "CoordinatorWorkflow", FakeCoordinator)
    db = SimpleNamespace(commit=lambda: None)
    task = SimpleNamespace(user_id=1, task_type="exercise", current_step="", request_json={
        "message": "生成二十道 TCP 练习题", "knowledge_point": "TCP", "exercise_count": 20,
    })
    result, _calls = assistant_tasks._coordinated_result(db, task)
    assert requested_batches == [10, 10]
    assert len(result["exercise_set"]["exercises"]) == 20
    assert result["cards"][0]["exercise_ids"] == list(range(1, 21))


def test_combined_courseware_and_exercises_does_not_generate_an_unrequested_path(monkeypatch):
    calls = []

    class RequestedCoordinator:
        def __init__(self, _db):
            pass

        def run(self, request):
            calls.append(request.payload["force_agents"])
            return {"status": "success", "agent_calls": [], "citations": [], "selected_agents": calls[-1], "outputs": {
                "resource_generation_agent": {"resource": {"id": 1, "title": "TCP"}},
                "exercise_generation_agent": {"exercise_set": {"exercises": [{"exercise_id": i} for i in range(1, 4)]}},
            }}

    monkeypatch.setattr(assistant_tasks, "CoordinatorWorkflow", RequestedCoordinator)
    result, _calls = assistant_tasks._coordinated_result(SimpleNamespace(commit=lambda: None), SimpleNamespace(
        user_id=1, task_type="combined", request_json={"message": "生成 TCP 课件和三道练习题", "knowledge_point": "TCP", "exercise_count": 3},
    ))
    assert len(calls) == 1
    assert calls[0] == ["learner_profiling_agent", "knowledge_base_agent", "resource_generation_agent", "exercise_generation_agent"]
    assert result["path_draft"] is None
    assert {card["type"] for card in result["cards"]} == {"courseware", "exercise"}


def test_failed_task_retry_is_persistent_idempotent_and_user_scoped(assistant_client, monkeypatch):
    client, user_id, other_id = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}

    original_profile_result = assistant_tasks._profile_result
    monkeypatch.setattr(assistant_tasks, "_profile_result", lambda *_args: (_ for _ in ()).throw(ValueError("No source data")))
    created = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": "retry-original-request",
    })
    assert created.status_code == 200
    original_id = created.json()["task"]["id"]
    assert client.get(f"/assistant/tasks/{original_id}", headers=headers).json()["status"] == "FAILED"
    assert client.post(f"/assistant/tasks/{original_id}/retry", headers=other_headers, json={
        "client_request_id": "retry-other-request",
    }).status_code == 404

    monkeypatch.setattr(assistant_tasks, "_profile_result", original_profile_result)
    retry_payload = {"client_request_id": "retry-unique-request"}
    retried = client.post(f"/assistant/tasks/{original_id}/retry", headers=headers, json=retry_payload)
    assert retried.status_code == 200
    retried_id = retried.json()["task"]["id"]
    assert retried_id != original_id
    assert client.get(f"/assistant/tasks/{retried_id}", headers=headers).json()["status"] == "SUCCEEDED"
    replay = client.post(f"/assistant/tasks/{original_id}/retry", headers=headers, json=retry_payload)
    assert replay.status_code == 200
    assert replay.json()["task"]["id"] == retried_id
    assert client.post(f"/assistant/tasks/{original_id}/retry", headers=headers, json={
        "client_request_id": "retry-original-request",
    }).status_code == 409


def test_failed_generation_retry_requires_explicit_duplicate_risk_confirmation(assistant_client, monkeypatch):
    client, user_id, _other_id = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    with assistant_tasks.SessionLocal() as db:
        session = ChatSession(user_id=user_id, title="retry", subject="TCP")
        db.add(session)
        db.flush()
        original = AssistantTask(
            user_id=user_id, session_id=session.id, client_request_id="generation-original",
            task_type="courseware", status="FAILED", error_code="WORKER_INTERRUPTED",
            request_json={"message": "生成 TCP 课件", "knowledge_point": "TCP", "exercise_count": 5}, result_json={},
        )
        db.add(original)
        db.commit()
        original_id = original.id

    monkeypatch.setattr(assistant_tasks, "_coordinated_result", lambda *_args: (
        {"content": "课件已保存", "cards": [], "sources": []}, [],
    ))
    retry_url = f"/assistant/tasks/{original_id}/retry"
    payload = {"client_request_id": "generation-retry-unique"}
    rejected = client.post(retry_url, headers=headers, json=payload)
    assert rejected.status_code == 409
    assert "可能已保存" in rejected.json()["detail"]
    with assistant_tasks.SessionLocal() as db:
        assert db.query(AssistantTask).count() == 1

    accepted = client.post(retry_url, headers=headers, json={**payload, "confirm_side_effects": True})
    assert accepted.status_code == 200
    retried_id = accepted.json()["task"]["id"]
    assert client.get(f"/assistant/tasks/{retried_id}", headers=headers).json()["status"] == "SUCCEEDED"
    with assistant_tasks.SessionLocal() as db:
        assert db.get(AssistantTask, retried_id).request_json["side_effect_root_task_id"] == original_id
    replay = client.post(retry_url, headers=headers, json=payload)
    assert replay.status_code == 200
    assert replay.json()["task"]["id"] == retried_id


def test_learning_path_draft_only_replaces_active_path_after_owner_confirms(assistant_client, monkeypatch):
    client, user_id, other_id = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    with assistant_tasks.SessionLocal() as db:
        previous = LearningPath(user_id=user_id, status="active", path_data_json={
            "subject": "old", "stages": [{"title": "原计划", "tasks": []}],
        })
        db.add(previous)
        db.commit()
        previous_id = previous.id

    class DraftCoordinator:
        def __init__(self, _db):
            pass

        def run(self, request):
            assert request.payload["persist_path"] is False
            return {
                "status": "success", "agent_calls": [], "citations": [],
                "selected_agents": ["path_planning_agent"],
                "outputs": {"path_planning_agent": {"status": "completed", "learning_path": {
                    "subject": "TCP", "stages": [{"title": "运输层复习", "tasks": [{"title": "复习 TCP"}]}],
                }}},
            }

    monkeypatch.setattr(assistant_tasks, "CoordinatorWorkflow", DraftCoordinator)
    created = client.post("/assistant/chat", headers=headers, json={
        "message": "制定 TCP 学习计划", "action": "plan", "knowledge_point": "TCP",
        "client_request_id": "plan-draft-request",
    })
    assert created.status_code == 200
    task_id = created.json()["task"]["id"]
    task = client.get(f"/assistant/tasks/{task_id}", headers=headers).json()
    assert task["status"] == "SUCCEEDED"
    assert task["result"]["cards"][0]["type"] == "plan_draft"
    with assistant_tasks.SessionLocal() as db:
        assert db.get(LearningPath, previous_id).status == "active"
        assert db.query(LearningPath).filter(LearningPath.user_id == user_id).count() == 1

    url = f"/assistant/tasks/{task_id}/confirm-path"
    assert client.post(url, headers=other_headers).status_code == 404
    with ThreadPoolExecutor(max_workers=4) as executor:
        confirmations = list(executor.map(lambda _index: client.post(url, headers=headers), range(4)))
    assert all(response.status_code == 200 for response in confirmations)
    confirmed = confirmations[0]
    assert confirmed.json()["result"]["path_saved"] is True
    assert confirmed.json()["result"]["cards"][0]["route"] == "/student/learning-path"
    assert client.post(url, headers=headers).status_code == 200
    with assistant_tasks.SessionLocal() as db:
        paths = db.query(LearningPath).filter(LearningPath.user_id == user_id).order_by(LearningPath.id).all()
        assert len(paths) == 2
        assert paths[0].status == "archived"
        assert paths[1].status == "active"
        assert paths[1].path_data_json["assistant_task_id"] == task_id
        assistant_message = db.query(ChatMessage).filter(ChatMessage.session_id == task["conversation_id"], ChatMessage.role == "assistant").first()
        assert assistant_message is not None and "已确认保存" in assistant_message.content


def test_learning_path_service_can_generate_a_draft_without_persisting(assistant_client, monkeypatch):
    # Draft persistence unit boundary; catalog/index policy has real DB tests.
    from services.agent_service.app.services import plan_knowledge
    monkeypatch.setattr(plan_knowledge, "require_plan_knowledge", lambda *_: {
        "knowledge_point": "TCP", "subject_id": 1, "point_id": 1,
        "published_versions": [1], "usable_chunks": [],
    })
    _client, user_id, _other_id = assistant_client
    payload = {"subject": "计算机网络", "knowledge_point": "TCP", "overview": "复习运输层", "estimated_days": 3,
               "stages": [{"title": "基础", "tasks": [{"title": "阅读 TCP 资料", "depends_on": []}]}]}
    monkeypatch.setattr(LearningPathService, "_generate_path_with_llm", lambda *_args: payload)
    monkeypatch.setattr(LearningPathService, "find_dependency_problems", lambda *_args: [])
    with assistant_tasks.SessionLocal() as db:
        result = LearningPathService(db).generate_path(LearningPathRequest(
            user_id=user_id, subject="计算机网络", knowledge_point="TCP", learner_profile={},
        ), persist=False)
        assert result["stages"][0]["title"] == "基础"
        assert db.query(LearningPath).filter(LearningPath.user_id == user_id).count() == 0


def test_stale_task_is_marked_failed_when_owner_polls_after_restart(assistant_client):
    client, user_id, other_id = assistant_client
    old_time = datetime.utcnow() - timedelta(minutes=31)
    with assistant_tasks.SessionLocal() as db:
        own_session = ChatSession(user_id=user_id, title="stale", subject="test")
        other_session = ChatSession(user_id=other_id, title="other", subject="test")
        db.add_all([own_session, other_session])
        db.flush()
        own_task = AssistantTask(user_id=user_id, session_id=own_session.id, client_request_id="stale-own-task", task_type="profile", status="RUNNING", request_json={}, result_json={}, updated_at=old_time)
        other_task = AssistantTask(user_id=other_id, session_id=other_session.id, client_request_id="stale-other-task", task_type="profile", status="RUNNING", request_json={}, result_json={}, updated_at=old_time)
        db.add_all([own_task, other_task])
        db.commit()
        own_id, other_id_task = own_task.id, other_task.id
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    result = client.get(f"/assistant/tasks/{own_id}", headers=headers)
    assert result.status_code == 200
    assert result.json()["status"] == "TIMED_OUT"
    assert result.json()["error_code"] == "WORKER_INTERRUPTED"
    with assistant_tasks.SessionLocal() as db:
        assert db.get(AssistantTask, other_id_task).status == "RUNNING"


def test_worker_mode_keeps_pending_tasks_durable_and_honors_cancellation(assistant_client, monkeypatch):
    client, user_id, _other_id = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(assistant_task_execution_mode="worker"))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    queued = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": "worker-durable-queue",
    }).json()
    task_id = queued["task"]["id"]
    assert client.get(f"/assistant/tasks/{task_id}", headers=headers).json()["status"] == "PENDING"
    with assistant_tasks.SessionLocal() as db:
        db.get(AssistantTask, task_id).updated_at = datetime.utcnow() - timedelta(hours=2)
        db.commit()
        assert assistant_tasks.expire_stale_tasks(db, user_id) == 0
    assert assistant_worker.run_pending_tasks() == 1
    assert client.get(f"/assistant/tasks/{task_id}", headers=headers).json()["status"] == "SUCCEEDED"
    cancelled = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": "worker-cancelled-queue",
    }).json()["task"]["id"]
    assert client.post(f"/assistant/tasks/{cancelled}/cancel", headers=headers).json()["status"] == "CANCELLED"
    assert assistant_worker.run_pending_tasks() == 0


def test_multiple_executors_claim_one_task_once(assistant_client, monkeypatch):
    client, user_id, _other_id = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(assistant_task_execution_mode="worker"))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    response = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": "worker-atomic-claim",
    }).json()
    task_id = response["task"]["id"]
    invocations = []

    def count_profile(*_args):
        invocations.append(task_id)
        return {"content": "无学习记录", "cards": [], "sources": []}

    monkeypatch.setattr(assistant_tasks, "_profile_result", count_profile)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(assistant_tasks.execute_task, [task_id] * 4))
    assert invocations == [task_id]
    with assistant_tasks.SessionLocal() as db:
        assert db.get(AssistantTask, task_id).status == "SUCCEEDED"
        assert db.query(ChatMessage).filter(ChatMessage.session_id == response["conversation_id"], ChatMessage.role == "assistant").count() == 1


def test_concurrent_duplicate_requests_create_one_conversation_message_and_task(assistant_client, monkeypatch):
    client, user_id, _other_id = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(assistant_task_execution_mode="worker"))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    payload = {"message": "分析我的学情", "action": "profile", "knowledge_point": "TCP",
               "client_request_id": "concurrent-first-conversation"}
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda _index: client.post("/assistant/chat", headers=headers, json=payload), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["task"]["id"] for response in responses}) == 1
    assert len({response.json()["conversation_id"] for response in responses}) == 1
    assert client.post("/assistant/chat", headers=headers, json={**payload, "knowledge_point": "UDP"}).status_code == 409
    with assistant_tasks.SessionLocal() as db:
        assert db.query(AssistantTask).filter(AssistantTask.user_id == user_id).count() == 1
        assert db.query(ChatSession).filter(ChatSession.user_id == user_id).count() == 1
        assert db.query(ChatMessage).count() == 1


def test_document_attachment_is_user_scoped_and_sent_as_untrusted_reference(assistant_client, monkeypatch):
    from services.agent_service.app.api.routes import assistant as assistant_route

    client, user_id, other_id = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    uploaded = client.post("/assistant/attachments", headers=headers, files={
        "file": ("note.txt", b"Course note: preorder visits root before children.", "text/plain"),
    })
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()["id"]
    assert client.post("/assistant/attachments", headers=headers, files={"file": ("bad.exe", b"bad")}).status_code == 422
    assert client.get("/assistant/attachments", headers=other_headers).json() == []
    assert client.delete(f"/assistant/attachments/{attachment_id}", headers=other_headers).status_code == 404

    monkeypatch.setattr(assistant_route, "SessionLocal", assistant_tasks.SessionLocal)
    seen = []

    class FakeModel:
        def stream(self, messages):
            seen.append(str(messages[-1].content))
            yield SimpleNamespace(content="先访问根节点。")

    monkeypatch.setattr(LLMFactory, "build_chat_model", lambda self, **_kwargs: FakeModel())
    payload = {"message": "解释文件中的前序遍历", "action": "qa", "attachment_ids": [attachment_id], "client_request_id": str(uuid4())}
    assert client.post("/assistant/chat/stream", json=payload, headers=other_headers).status_code == 404
    response = client.post("/assistant/chat/stream", json=payload, headers=headers)
    assert response.status_code == 200 and "event: final" in response.text
    assert seen and "preorder visits root before children" in seen[0]
    with assistant_tasks.SessionLocal() as db:
        saved = db.query(ChatMessage).filter(ChatMessage.role == "user").first()
        assert saved.metadata_json["attachments"][0]["id"] == attachment_id
        assert "attachment_context" not in saved.metadata_json
        assert db.get(AssistantAttachment, attachment_id) is not None
    assert client.delete(f"/assistant/attachments/{attachment_id}", headers=headers).status_code == 200


def test_docx_text_is_extracted_and_unsupported_content_rejected():
    from docx import Document
    from fastapi import HTTPException

    document = Document()
    document.add_paragraph("TCP transmission lesson")
    stream = io.BytesIO()
    document.save(stream)
    kind, text = extract_document_text("lesson.docx", stream.getvalue())
    assert "wordprocessingml" in kind and "TCP transmission lesson" in text
    with pytest.raises(HTTPException) as invalid:
        extract_document_text("lesson.pdf", b"not a PDF")
    assert invalid.value.status_code == 422


def test_uploaded_reference_is_user_scoped_in_generation_and_deleted_files_fail_queued_tasks(assistant_client, monkeypatch):
    client, user_id, other_id = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    uploaded = client.post("/assistant/attachments", headers=headers, files={
        "file": ("TCP-reference.txt", "TCP 通过序号与确认机制实现可靠传输。".encode("utf-8"), "text/plain"),
    }).json()
    seen = []

    class ReferenceCoordinator:
        def __init__(self, _db):
            pass

        def run(self, request):
            seen.append(request.payload["reference_materials"])
            return {"status": "success", "agent_calls": [], "citations": [], "outputs": {
                "resource_generation_agent": {"resource": {"id": 42, "title": "TCP"}},
            }}

    monkeypatch.setattr(assistant_tasks, "CoordinatorWorkflow", ReferenceCoordinator)
    payload = {"message": "基于上传资料生成 TCP 课件", "action": "courseware", "knowledge_point": "TCP",
               "attachment_ids": [uploaded["id"]], "client_request_id": "attachment-courseware-request"}
    assert client.post("/assistant/chat", headers=other_headers, json=payload).status_code == 404
    accepted = client.post("/assistant/chat", headers=headers, json=payload)
    assert accepted.status_code == 200
    task_id = accepted.json()["task"]["id"]
    result = client.get(f"/assistant/tasks/{task_id}", headers=headers).json()["result"]
    assert seen and "序号与确认机制" in seen[0]
    assert result["sources"][0]["title"] == "TCP-reference.txt"
    with assistant_tasks.SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        assert task.request_json["attachment_ids"] == [uploaded["id"]]
        assert "序号与确认机制" not in str(task.request_json)
        message = db.query(ChatMessage).filter(ChatMessage.session_id == task.session_id, ChatMessage.role == "user").first()
        assert message.metadata_json["attachments"][0]["file_name"] == "TCP-reference.txt"
    assert client.post("/assistant/chat", headers=headers, json={**payload, "attachment_ids": []}).status_code == 409
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(assistant_task_execution_mode="worker"))
    queued = client.post("/assistant/chat", headers=headers, json={**payload, "client_request_id": "attachment-deleted-before-worker"}).json()["task"]["id"]
    assert client.delete(f"/assistant/attachments/{uploaded['id']}", headers=headers).status_code == 200
    assistant_worker.run_pending_tasks()
    failed = client.get(f"/assistant/tasks/{queued}", headers=headers).json()
    assert failed["status"] == "FAILED" and "资料已删除" in failed["result"]["content"]
    assert len(seen) == 1


def test_profile_task_persists_and_is_user_scoped(assistant_client):
    client, user_id, other_id = assistant_client
    auth_headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    request_id = str(uuid4())
    response = client.post("/assistant/chat", json={
        "client_request_id": request_id,
        "message": "分析我的学情",
        "action": "profile",
    }, headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kind"] == "task"
    task_id = payload["task"]["id"]

    own = client.get(f"/assistant/tasks/{task_id}", headers=auth_headers)
    assert own.status_code == 200
    assert own.json()["status"] == "SUCCEEDED"
    assert own.json()["result"]["evidence"]["answer_records"] == 0
    assert "没有可用于分析" in own.json()["result"]["content"]

    repeated = client.post("/assistant/chat", json={
        "client_request_id": request_id,
        "message": "分析我的学情",
        "action": "profile",
    }, headers=auth_headers)
    assert repeated.status_code == 200
    assert repeated.json()["task"]["id"] == task_id

    other_headers = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    assert client.get(f"/assistant/tasks/{task_id}", headers=other_headers).status_code == 404
    assert client.post(f"/assistant/tasks/{task_id}/cancel", headers=other_headers).status_code == 404


def test_assistant_requires_login(assistant_client):
    client, _, _ = assistant_client
    assert client.get("/assistant/tasks").status_code == 401
    assert client.post("/assistant/chat", json={"message": "分析我的学情"}).status_code == 401


def test_confirmed_memory_can_be_corrected_deleted_and_not_read_by_other_user(assistant_client):
    client, user_id, other_id = assistant_client
    own = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    other = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    payload = {"memory_type": "goal", "content": "本周复习二叉树", "course_key": "数据结构"}
    created = client.post("/assistant/memory", json=payload, headers=own)
    assert created.status_code == 201
    memory_id = created.json()["id"]
    assert created.json()["source_reference"] == "user_confirmed"
    assert client.get("/assistant/memory", headers=other).json() == []
    assert client.put(f"/assistant/memory/{memory_id}", json={**payload, "content": "本周复习图算法"}, headers=other).status_code == 404
    corrected = client.put(f"/assistant/memory/{memory_id}", json={**payload, "content": "本周复习图算法"}, headers=own)
    assert corrected.status_code == 200
    assert corrected.json()["content"] == "本周复习图算法"
    assert client.delete(f"/assistant/memory/{memory_id}", headers=other).status_code == 404
    assert client.delete(f"/assistant/memory/{memory_id}", headers=own).status_code == 200
    assert client.get("/assistant/memory", headers=own).json() == []


def test_recommendation_does_not_invent_resources_when_database_is_empty(assistant_client):
    client, user_id, _ = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    response = client.post("/assistant/chat", json={
        "message": "根据我的学习情况推荐学习资源", "action": "recommend",
    }, headers=headers)
    assert response.status_code == 200
    result = client.get(f"/assistant/tasks/{response.json()['task']['id']}", headers=headers).json()
    assert result["status"] == "SUCCEEDED"
    assert result["result"]["evidence"]["recommendation_count"] == 0
    assert result["result"]["cards"] == []


def test_profile_uses_only_real_answers_of_current_learner(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'answers.sqlite'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        learner = User(username="learner", password_hash="test", role="student")
        other = User(username="other", password_hash="test", role="student")
        point = KnowledgePoint(name="二叉树前序遍历")
        db.add_all([learner, other, point])
        db.flush()
        exercise = Exercise(knowledge_point_id=point.id, type="choice", content="遍历顺序？", answer="根左右")
        db.add(exercise)
        db.flush()
        db.add_all([
            AnswerRecord(user_id=learner.id, exercise_id=exercise.id, user_answer="左右根", is_correct=False),
            AnswerRecord(user_id=learner.id, exercise_id=exercise.id, user_answer="左根右", is_correct=False),
            AnswerRecord(user_id=other.id, exercise_id=exercise.id, user_answer="根左右", is_correct=True),
        ])
        db.commit()
        result = _profile_result(db, learner.id)
        assert result["evidence"]["answer_records"] == 2
        assert "二叉树前序遍历（0/2）" in result["content"]
        assert _profile_result(db, other.id)["evidence"]["answer_records"] == 1
    engine.dispose()


def test_knowledge_search_understands_chinese_question_without_spaces():
    rows = KnowledgeBaseService().search_by_keywords("用简单例子解释二叉树的前序遍历")
    assert any("二叉树" in article.concepts for article in rows)


def test_learning_context_keeps_course_and_user_memories_separate(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'memory.sqlite'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        learner = User(username="learner", password_hash="test", role="student")
        other = User(username="other", password_hash="test", role="student")
        db.add_all([learner, other])
        db.flush()
        db.add_all([
            AssistantMemory(user_id=learner.id, course_key="", memory_type="preference", content="喜欢图解"),
            AssistantMemory(user_id=learner.id, course_key="数据结构", memory_type="goal", content="掌握二叉树"),
            AssistantMemory(user_id=learner.id, course_key="计算机网络", memory_type="goal", content="掌握 TCP"),
            AssistantMemory(user_id=other.id, course_key="数据结构", memory_type="goal", content="其他学生私有目标"),
        ])
        db.commit()
        context = ChatService(db)._learning_context(learner.id, "数据结构")
        assert "喜欢图解" in context and "掌握二叉树" in context
        assert "掌握 TCP" not in context and "其他学生私有目标" not in context
    engine.dispose()


def test_streaming_question_persists_one_answer_and_replay_is_idempotent(assistant_client, monkeypatch):
    from services.agent_service.app.api.routes import assistant as assistant_route

    client, user_id, other_id = assistant_client
    monkeypatch.setattr(assistant_route, "SessionLocal", assistant_tasks.SessionLocal)

    class FakeModel:
        def stream(self, _messages):
            yield SimpleNamespace(content="根节点")
            yield SimpleNamespace(content="，左子树，右子树。")

    monkeypatch.setattr(LLMFactory, "build_chat_model", lambda self, **_kwargs: FakeModel())
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    payload = {"message": "解释二叉树前序遍历", "action": "qa", "client_request_id": str(uuid4())}
    response = client.post("/assistant/chat/stream", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count("event: delta") == 2
    assert "event: final" in response.text
    import re
    session_id = int(re.search(r'"conversation_id": (\d+)', response.text).group(1))
    with assistant_tasks.SessionLocal() as db:
        db.add_all(ChatMessage(session_id=session_id, role="user", content=f"filler {index}", model_used="", metadata_json={}) for index in range(101))
        db.commit()
    replay = client.post("/assistant/chat/stream", json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.text.count("event: final") == 1
    assert "event: delta" not in replay.text
    with assistant_tasks.SessionLocal() as db:
        assert db.query(ChatMessage).count() == 103
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
    assert client.post("/assistant/chat/stream", json={**payload, "client_request_id": str(uuid4()), "conversation_id": session_id}, headers=other_headers).status_code == 404


@pytest.mark.parametrize("stop_after,exercise_count,expected_agents,expected_cards", [
    ("knowledge", 3, ["knowledge"], []),
    ("resource", 3, ["knowledge", "resource"], ["courseware"]),
    ("exercise", 15, ["knowledge", "resource", "exercise"], ["courseware", "exercise"]),
    ("plan", 3, ["knowledge", "resource", "exercise", "plan"], ["courseware", "exercise", "plan_draft"]),
])
def test_running_cancellation_stops_later_agents_and_keeps_saved_results(
    assistant_client, monkeypatch, stop_after, exercise_count, expected_agents, expected_cards,
):
    from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
    from services.agent_service.app.services import plan_knowledge
    # This parametrized test controls all agent stages to examine cancellation.
    monkeypatch.setattr(plan_knowledge, "require_plan_knowledge", lambda *_: {})

    client, user_id, other_id = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(assistant_task_execution_mode="worker"))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    queued = client.post("/assistant/chat", headers=headers, json={
        "message": f"生成 TCP 课件、{exercise_count}道练习题和学习计划", "action": "combined",
        "knowledge_point": "TCP", "exercise_count": exercise_count,
        "use_learning_context": False, "client_request_id": str(uuid4()),
    }).json()
    task_id = queued["task"]["id"]
    entered, release = threading.Event(), threading.Event()
    seen = []

    def stage(name):
        seen.append(name)
        if name == stop_after:
            entered.set()
            assert release.wait(10), "test did not release active agent"

    def knowledge(*_args):
        stage("knowledge")
        return {"status": "completed"}

    def resource(*_args, **_kwargs):
        stage("resource")
        return {"status": "completed", "resource": {"id": 42, "title": "TCP"}}, None

    def exercise(*_args, **kwargs):
        stage("exercise")
        return {"status": "completed", "exercise_set": {"exercises": [
            {"exercise_id": index + 1} for index in range(kwargs["context"]["exercise_count"])
        ]}}

    def plan(*_args, **kwargs):
        assert kwargs.get("persist") is False
        stage("plan")
        return {"subject": "计算机网络", "knowledge_point": "TCP", "overview": "TCP", "stages": [
            {"title": "基础", "tasks": [{"title": "学习 TCP", "depends_on": []}]},
        ]}

    monkeypatch.setattr(LearningPathService, "generate_path", plan)
    monkeypatch.setattr(CoordinatorWorkflow, "_run_knowledge_base_agent", knowledge)
    monkeypatch.setattr(CoordinatorWorkflow, "_run_resource_agent", resource)
    monkeypatch.setattr(CoordinatorWorkflow, "_run_exercise_agent", exercise)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(assistant_tasks.execute_task, task_id)
        try:
            assert entered.wait(10), "worker did not enter requested agent"
            other = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
            assert client.post(f"/assistant/tasks/{task_id}/request-cancel", headers=other).status_code == 404
            assert client.post(f"/assistant/tasks/{task_id}/cancel", headers=headers).status_code == 409
            for _ in range(2):
                cancelled = client.post(f"/assistant/tasks/{task_id}/request-cancel", headers=headers)
                assert cancelled.status_code == 200, cancelled.text
                assert cancelled.json()["status"] == "CANCEL_REQUESTED"
                assert cancelled.json()["completed_at"] is None
        finally:
            release.set()
        future.result(timeout=10)
    result = client.get(f"/assistant/tasks/{task_id}", headers=headers).json()
    assert result["status"] == "CANCELLED", result
    assert result["completed_at"]
    assert seen == expected_agents
    assert [card["type"] for card in result["result"]["cards"]] == expected_cards
    assert "任务已取消" in result["result"]["content"]
    assert client.post(f"/assistant/tasks/{task_id}/cancel", headers=headers).json()["status"] == "CANCELLED"
    if stop_after != "plan":
        assert client.post(f"/assistant/tasks/{task_id}/confirm-path", headers=headers).status_code == 409
    else:
        with assistant_tasks.SessionLocal() as db:
            assert db.query(LearningPath).filter(LearningPath.user_id == user_id).count() == 0
        saved = client.post(f"/assistant/tasks/{task_id}/confirm-path", headers=headers)
        assert saved.status_code == 200, saved.text
        assert saved.json()["result"]["path_saved"] is True
        result = client.get(f"/assistant/tasks/{task_id}", headers=headers).json()
    assistant_tasks.execute_task(task_id)
    assert seen == expected_agents
    with assistant_tasks.SessionLocal() as db:
        messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == queued["conversation_id"], ChatMessage.role == "assistant",
        ).all()
        assert len(messages) == 1
        assert messages[0].metadata_json["cards"] == result["result"]["cards"]


def test_cancel_during_failing_call_stays_cancelled(assistant_client, monkeypatch):
    client, user_id, _other = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(assistant_task_execution_mode="worker"))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    task_id = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": str(uuid4()),
    }).json()["task"]["id"]

    def fail_after_cancel(*_args):
        assert client.post(f"/assistant/tasks/{task_id}/request-cancel", headers=headers).json()["status"] == "CANCEL_REQUESTED"
        raise RuntimeError("active service failed after cancellation")

    monkeypatch.setattr(assistant_tasks, "_profile_result", fail_after_cancel)
    assistant_tasks.execute_task(task_id)
    result = client.get(f"/assistant/tasks/{task_id}", headers=headers).json()
    assert result["status"] == "CANCELLED"
    assert result["error_code"] == ""


def test_cancellation_does_not_overwrite_completed_task(assistant_client):
    client, user_id, _other = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    task_id = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": str(uuid4()),
    }).json()["task"]["id"]
    completed = client.get(f"/assistant/tasks/{task_id}", headers=headers).json()
    assert completed["status"] == "SUCCEEDED"
    cancelled = client.post(f"/assistant/tasks/{task_id}/cancel", headers=headers).json()
    assert cancelled["status"] == "SUCCEEDED"
    assert cancelled["result"] == completed["result"]


def test_assistant_side_effect_keys_reuse_saved_resource_and_exercises(assistant_client, monkeypatch):
    _client, user_id, _other = assistant_client
    with assistant_tasks.SessionLocal() as db:
        db.add(KnowledgePoint(name="TCP", description="TCP"))
        db.commit()
    resource_service = ResourceGenerationService.__new__(ResourceGenerationService)
    monkeypatch.setattr(resource_service, "_resolve_or_create_knowledge_point",
                        lambda db, _name: db.query(KnowledgePoint).filter_by(name="TCP").first())
    resource_request = ResourceGenerationRequest(
        user_id=user_id, knowledge_point="TCP", assistant_operation_key="assistant:77:resource",
    )
    plan = {"knowledge_point": "TCP", "resource_type": "courseware"}
    with assistant_tasks.SessionLocal() as db:
        first = resource_service._persist_generated_resource(db, resource_request, plan, {"title": "TCP", "content": "original"})
    restarted_resource_service = ResourceGenerationService.__new__(ResourceGenerationService)
    monkeypatch.setattr(restarted_resource_service, "_resolve_or_create_knowledge_point",
                        lambda db, _name: db.query(KnowledgePoint).filter_by(name="TCP").first())
    with assistant_tasks.SessionLocal() as db:
        replay = restarted_resource_service._persist_generated_resource(db, resource_request, plan, {"title": "TCP", "content": "duplicate"})
        assert replay == first
        assert db.query(Resource).filter_by(assistant_operation_key="assistant:77:resource").count() == 1
        assert db.get(Resource, first).content == "original"

    exercise_service = ExerciseGenerationService.__new__(ExerciseGenerationService)
    exercise_request = ExerciseGenerationRequest(
        user_id=user_id, knowledge_point="TCP", exercise_count=3,
        assistant_operation_key="assistant:77:exercise:0",
    )
    items = [{"knowledge_point": "TCP", "question_type": "choice", "difficulty": "foundation",
              "prompt": f"question-{i}", "options": ["A", "B"], "answer": "A", "analysis": "why"}
             for i in range(3)]
    with assistant_tasks.SessionLocal() as db:
        point = db.query(KnowledgePoint).filter_by(name="TCP").first()
        saved = exercise_service._persist_exercises(db, exercise_request, items, point)
    with assistant_tasks.SessionLocal() as db:
        point = db.query(KnowledgePoint).filter_by(name="TCP").first()
        repeated = ExerciseGenerationService.__new__(ExerciseGenerationService)._persist_exercises(db, exercise_request, [
            {**item, "prompt": "must not replace"} for item in items
        ], point)
        assert [item["exercise_id"] for item in repeated] == [item["exercise_id"] for item in saved]
        assert db.query(Exercise).filter(Exercise.assistant_operation_key.like("assistant:77:exercise:0:%")).count() == 3
        assert repeated[0]["prompt"] == "question-0"
    with assistant_tasks.SessionLocal() as db:
        point = db.query(KnowledgePoint).filter_by(name="TCP").first()
        another = exercise_service._persist_exercises(db, ExerciseGenerationRequest(
            user_id=user_id, knowledge_point="TCP", exercise_count=3,
            assistant_operation_key="assistant:77:exercise:1",
        ), items, point)
        assert set(item["exercise_id"] for item in another).isdisjoint(item["exercise_id"] for item in saved)


def test_two_agents_concurrently_save_one_resource(assistant_client, monkeypatch):
    _client, user_id, _other = assistant_client
    with assistant_tasks.SessionLocal() as db:
        db.add(KnowledgePoint(name="TCP", description="TCP"))
        session = ChatSession(user_id=user_id, title="concurrent", subject="TCP")
        db.add(session)
        db.flush()
        tasks = [AssistantTask(
            user_id=user_id, session_id=session.id, client_request_id=f"concurrent-agent-{index}",
            task_type="courseware", status="RUNNING", worker_id=f"worker-{index}",
            execution_attempt=1, request_json={}, result_json={},
        ) for index in range(2)]
        db.add_all(tasks)
        db.commit()
        task_ids = [task.id for task in tasks]
    service = ResourceGenerationService.__new__(ResourceGenerationService)
    monkeypatch.setattr(service, "_resolve_or_create_knowledge_point",
                        lambda db, _name: db.query(KnowledgePoint).filter_by(name="TCP").first())
    request = ResourceGenerationRequest(user_id=user_id, knowledge_point="TCP",
                                        assistant_operation_key="assistant:shared:resource")
    barrier = threading.Barrier(2)

    def save(index):
        token = assistant_execution.current_execution.set((task_ids[index], f"worker-{index}", 1))
        try:
            barrier.wait(timeout=10)
            with assistant_tasks.SessionLocal() as db:
                primary = {"title": "TCP", "content": f"agent-{index}"}
                saved_id = service._persist_generated_resource(db, request,
                    {"knowledge_point": "TCP", "resource_type": "courseware"},
                    primary)
                return saved_id, primary["content"]
        finally:
            assistant_execution.current_execution.reset(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(save, range(2)))
    assert ids[0] == ids[1]
    with assistant_tasks.SessionLocal() as db:
        assert db.query(Resource).filter_by(assistant_operation_key="assistant:shared:resource").count() == 1


def test_stale_worker_is_fenced_and_read_only_task_recovers(assistant_client, monkeypatch):
    client, user_id, _other = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(
        assistant_task_execution_mode="worker", assistant_worker_stale_seconds=30,
        assistant_task_max_seconds=1800, assistant_safe_retry_limit=2,
        assistant_worker_heartbeat_seconds=5, assistant_safe_retry_backoff_seconds=0,
    ))
    monkeypatch.setattr(assistant_tasks, "_heartbeat", lambda *_args: None)
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    task_id = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": str(uuid4()),
    }).json()["task"]["id"]
    entered, release = threading.Event(), threading.Event()
    calls = []

    def profile(_db, _user_id):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
            return {"content": "old worker", "cards": [], "sources": []}
        return {"content": "new worker", "cards": [], "sources": []}

    monkeypatch.setattr(assistant_tasks, "_profile_result", profile)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(assistant_tasks.execute_task, task_id)
        try:
            assert entered.wait(10)
            with assistant_tasks.SessionLocal() as db:
                db.get(AssistantTask, task_id).heartbeat_at = datetime.utcnow() - timedelta(minutes=2)
                db.commit()
                assert assistant_tasks.expire_stale_tasks(db) == 1
                assert db.get(AssistantTask, task_id).status == "PENDING"
            assistant_tasks.execute_task(task_id)
        finally:
            release.set()
        future.result(timeout=10)
    with assistant_tasks.SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        assert task.status == "SUCCEEDED"
        assert task.execution_attempt == 2
        assert task.result_json["content"] == "new worker"
        assert db.query(ChatMessage).filter(ChatMessage.role == "assistant", ChatMessage.session_id == task.session_id).count() == 1


def test_worker_heartbeat_keeps_long_active_task_and_fences_cancelled_write(assistant_client, monkeypatch):
    client, user_id, _other = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(
        assistant_task_execution_mode="worker", assistant_worker_stale_seconds=30,
        assistant_task_max_seconds=1800, assistant_cancel_wait_seconds=60,
        assistant_worker_heartbeat_seconds=1,
    ))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    task_id = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": str(uuid4()),
    }).json()["task"]["id"]
    with assistant_tasks.SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        task.status = "RUNNING"
        task.worker_id = "test-worker"
        task.execution_attempt = 1
        task.started_at = datetime.utcnow() - timedelta(minutes=5)
        task.heartbeat_at = datetime.utcnow() - timedelta(seconds=20)
        db.commit()
        assert assistant_tasks.expire_stale_tasks(db) == 0

    class OneBeat:
        calls = 0
        def wait(self, _interval):
            self.calls += 1
            return self.calls > 1

    assistant_tasks._heartbeat(task_id, "test-worker", 1, OneBeat())
    with assistant_tasks.SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        assert task.heartbeat_at > datetime.utcnow() - timedelta(seconds=10)
    assert client.post(f"/assistant/tasks/{task_id}/request-cancel", headers=headers).json()["status"] == "CANCEL_REQUESTED"
    token = assistant_execution.current_execution.set((task_id, "test-worker", 1))
    try:
        with pytest.raises(assistant_execution.ExecutionStopped):
            assistant_execution.ensure_execution_active()
        with assistant_tasks.SessionLocal() as db:
            with pytest.raises(assistant_execution.ExecutionStopped):
                assistant_execution.ensure_write_allowed(db)
    finally:
        assistant_execution.current_execution.reset(token)


def test_worker_retry_limit_and_cancel_wait_have_distinct_terminal_states(assistant_client, monkeypatch):
    client, user_id, _other = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(
        assistant_task_execution_mode="worker", assistant_worker_stale_seconds=30,
        assistant_task_max_seconds=1800, assistant_cancel_wait_seconds=10,
        assistant_safe_retry_limit=2,
    ))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    task_ids = [client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": str(uuid4()),
    }).json()["task"]["id"] for _ in range(2)]
    with assistant_tasks.SessionLocal() as db:
        timed_out, cancelling = (db.get(AssistantTask, task_id) for task_id in task_ids)
        timed_out.status = "RUNNING"
        timed_out.worker_id = "lost-worker"
        timed_out.execution_attempt = 2
        timed_out.heartbeat_at = datetime.utcnow() - timedelta(minutes=2)
        cancelling.status = "CANCEL_REQUESTED"
        cancelling.worker_id = "slow-worker"
        cancelling.execution_attempt = 1
        cancelling.heartbeat_at = datetime.utcnow()
        cancelling.updated_at = datetime.utcnow() - timedelta(minutes=2)
        db.commit()
        assert assistant_tasks.expire_stale_tasks(db) == 2
        assert db.get(AssistantTask, task_ids[0]).status == "TIMED_OUT"
        assert db.get(AssistantTask, task_ids[1]).status == "CANCELLED"


def test_read_only_recovery_respects_backoff(assistant_client, monkeypatch):
    client, user_id, _other = assistant_client
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: SimpleNamespace(
        assistant_task_execution_mode="worker", assistant_worker_stale_seconds=30,
        assistant_task_max_seconds=1800, assistant_safe_retry_limit=2,
        assistant_safe_retry_backoff_seconds=5,
    ))
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    task_id = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": str(uuid4()),
    }).json()["task"]["id"]
    with assistant_tasks.SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        task.status = "RUNNING"
        task.worker_id = "lost-worker"
        task.execution_attempt = 1
        task.heartbeat_at = datetime.utcnow() - timedelta(minutes=2)
        db.commit()
        assert assistant_tasks.expire_stale_tasks(db) == 1
        task = db.get(AssistantTask, task_id)
        assert task.next_attempt_at > datetime.utcnow()
    assert assistant_worker.run_pending_tasks() == 0
    with assistant_tasks.SessionLocal() as db:
        db.get(AssistantTask, task_id).next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert assistant_worker.run_pending_tasks() == 1
    assert client.get(f"/assistant/tasks/{task_id}", headers=headers).json()["status"] == "SUCCEEDED"


def test_cancel_waits_for_inflight_database_commit(assistant_client):
    client, user_id, _other = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    with assistant_tasks.SessionLocal() as db:
        session = ChatSession(user_id=user_id, title="write race", subject="TCP")
        db.add(session)
        db.flush()
        task = AssistantTask(user_id=user_id, session_id=session.id, client_request_id=str(uuid4()),
                             task_type="courseware", status="RUNNING", worker_id="write-worker",
                             execution_attempt=1, request_json={}, result_json={})
        db.add(task)
        db.commit()
        task_id = task.id
    write_locked, release_write, cancel_sql_started = threading.Event(), threading.Event(), threading.Event()
    engine = assistant_tasks.SessionLocal.kw["bind"]

    def observe_cancel(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "UPDATE assistant_tasks SET status" in statement:
            cancel_sql_started.set()

    event.listen(engine, "before_cursor_execute", observe_cancel)
    try:
        def save():
            token = assistant_execution.current_execution.set((task_id, "write-worker", 1))
            try:
                with assistant_tasks.SessionLocal() as db:
                    assistant_execution.ensure_write_allowed(db)
                    db.add(Resource(title="saved", type="courseware", content="saved before cancellation",
                                    generated_for_user_id=user_id, assistant_operation_key="assistant:write-race:resource"))
                    write_locked.set()
                    assert release_write.wait(10)
                    db.commit()
            finally:
                assistant_execution.current_execution.reset(token)

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(save)
            try:
                assert write_locked.wait(10)
                cancel = pool.submit(lambda: client.post(f"/assistant/tasks/{task_id}/request-cancel", headers=headers))
                assert cancel_sql_started.wait(10)
            finally:
                release_write.set()
            writer.result(timeout=10)
            assert cancel.result(timeout=10).json()["status"] == "CANCEL_REQUESTED"
    finally:
        event.remove(engine, "before_cursor_execute", observe_cancel)
    with assistant_tasks.SessionLocal() as db:
        assert db.query(Resource).filter_by(assistant_operation_key="assistant:write-race:resource").count() == 1
        assert db.get(AssistantTask, task_id).status == "CANCEL_REQUESTED"


@pytest.mark.parametrize("expired", ["heartbeat", "deadline", "cancel_wait"])
def test_heartbeat_enforces_expiry_without_status_polling(assistant_client, monkeypatch, expired):
    _client, user_id, _other = assistant_client
    settings = SimpleNamespace(
        assistant_task_execution_mode="worker", assistant_worker_heartbeat_seconds=1,
        assistant_worker_stale_seconds=10, assistant_task_max_seconds=60,
        assistant_cancel_wait_seconds=10,
    )
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(assistant_execution, "get_settings", lambda: settings)
    now = datetime.utcnow()
    with assistant_tasks.SessionLocal() as db:
        session = ChatSession(user_id=user_id, title="lease expiry", subject="TCP")
        db.add(session)
        db.flush()
        task = AssistantTask(
            user_id=user_id, session_id=session.id, client_request_id=str(uuid4()),
            task_type="courseware", worker_id="paused-worker", execution_attempt=1,
            status="CANCEL_REQUESTED" if expired == "cancel_wait" else "RUNNING",
            request_json={}, result_json={}, updated_at=now - timedelta(seconds=20),
            heartbeat_at=now - timedelta(seconds=20) if expired == "heartbeat" else now,
            started_at=now - timedelta(seconds=120) if expired == "deadline" else now,
        )
        db.add(task)
        db.commit()
        task_id = task.id
    token = assistant_execution.current_execution.set((task_id, "paused-worker", 1))
    try:
        if expired != "cancel_wait":
            with pytest.raises(assistant_execution.ExecutionStopped):
                assistant_execution.ensure_execution_active()
            with assistant_tasks.SessionLocal() as db:
                with pytest.raises(assistant_execution.ExecutionStopped):
                    assistant_execution.ensure_write_allowed(db)
    finally:
        assistant_execution.current_execution.reset(token)

    class OneBeat:
        count = 0
        def wait(self, _interval):
            self.count += 1
            return self.count > 1

    assistant_tasks._heartbeat(task_id, "paused-worker", 1, OneBeat())
    with assistant_tasks.SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        assert task.status == ("CANCELLED" if expired == "cancel_wait" else "TIMED_OUT")
        if expired == "heartbeat":
            assert task.heartbeat_at < now - timedelta(seconds=10)


def test_public_coordinator_payload_cannot_select_assistant_operation_root(assistant_client, monkeypatch):
    from common.schemas.agent import CoordinationRequest
    from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
    _client, user_id, _other = assistant_client
    seen = []
    monkeypatch.setattr(CoordinatorWorkflow, "_run_knowledge_base_agent", lambda _self, context: (
        seen.append(context["assistant_operation_root"]) or {"status": "completed", "items": []}
    ))
    request = CoordinationRequest(user_id=user_id, intent="search", payload={
        "assistant_operation_root": "forged-task", "use_learning_context": False,
    })
    with assistant_tasks.SessionLocal() as db:
        workflow = CoordinatorWorkflow(db)
        workflow._execute_agents(request, {"selected_agents": ["knowledge_base_agent"], "route_reason": "test"})
    assert seen == [""]


def test_exercise_flush_conflict_replays_concurrent_winner(assistant_client, monkeypatch):
    _client, user_id, _other = assistant_client
    service = ExerciseGenerationService.__new__(ExerciseGenerationService)
    request = ExerciseGenerationRequest(user_id=user_id, knowledge_point="TCP", exercise_count=3,
                                        assistant_operation_key="assistant:flush-race:exercise:0")
    items = [{"knowledge_point": "TCP", "question_type": "choice", "difficulty": "foundation",
              "prompt": f"winner-{i}", "options": ["A", "B"], "answer": "A", "analysis": "why"}
             for i in range(3)]
    with assistant_tasks.SessionLocal() as db:
        db.add(KnowledgePoint(name="TCP", description="TCP"))
        db.commit()
    with assistant_tasks.SessionLocal() as db:
        point = db.query(KnowledgePoint).filter_by(name="TCP").first()
        real_flush = db.flush
        injected = []

        def concurrent_flush(*args, **kwargs):
            if not injected:
                injected.append(True)
                with assistant_tasks.SessionLocal() as winner_db:
                    winner_point = winner_db.query(KnowledgePoint).filter_by(name="TCP").first()
                    service._persist_exercises(winner_db, request, items, winner_point)
            return real_flush(*args, **kwargs)

        monkeypatch.setattr(db, "flush", concurrent_flush)
        result = service._persist_exercises(db, request,
                    [{**item, "prompt": "loser"} for item in items], point)
        assert [item["prompt"] for item in result] == [item["prompt"] for item in items]
        assert db.query(Exercise).count() == 3


def test_model_reply_after_cancellation_stops_later_model_calls(assistant_client, monkeypatch):
    from langchain_core.runnables import RunnableLambda
    from services.agent_service.app.services import resource_generation
    client, user_id, _other = assistant_client
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    with assistant_tasks.SessionLocal() as db:
        session = ChatSession(user_id=user_id, title="model cancellation", subject="TCP")
        db.add(session)
        db.flush()
        task = AssistantTask(user_id=user_id, session_id=session.id, client_request_id=str(uuid4()),
                             task_type="courseware", status="RUNNING", worker_id="model-worker",
                             execution_attempt=1, request_json={}, result_json={})
        db.add(task)
        db.commit()
        task_id = task.id
    service = ResourceGenerationService.__new__(ResourceGenerationService)
    service.prompt_template = "teacher"
    service.llm_factory = SimpleNamespace(build_chat_model=lambda **_kwargs: RunnableLambda(lambda _x: "unused"))
    calls = []

    def reply_after_cancel(*_args, **_kwargs):
        calls.append("provider")
        response = client.post(f"/assistant/tasks/{task_id}/request-cancel", headers=headers)
        assert response.json()["status"] == "CANCEL_REQUESTED"
        return "late provider reply"

    monkeypatch.setattr(resource_generation, "traced_invoke", reply_after_cancel)
    token = assistant_execution.current_execution.set((task_id, "model-worker", 1))
    try:
        for _ in range(2):
            with pytest.raises(resource_generation.ResourceGenerationError):
                service._invoke_llm({})
    finally:
        assistant_execution.current_execution.reset(token)
    assert calls == ["provider"]
    with assistant_tasks.SessionLocal() as db:
        assert db.query(Resource).count() == 0


def test_late_result_cannot_complete_after_task_deadline(assistant_client, monkeypatch):
    client, user_id, _other = assistant_client
    settings = SimpleNamespace(assistant_task_execution_mode="worker", assistant_task_max_seconds=60)
    monkeypatch.setattr(assistant_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(assistant_execution, "get_settings", lambda: settings)
    monkeypatch.setattr(assistant_tasks, "_heartbeat", lambda *_args: None)
    headers = {"Authorization": f"Bearer {create_access_token(str(user_id))}"}
    queued = client.post("/assistant/chat", headers=headers, json={
        "message": "分析我的学情", "action": "profile", "client_request_id": str(uuid4()),
    }).json()
    task_id = queued["task"]["id"]

    def late_result(db, _user_id):
        task = db.get(AssistantTask, task_id)
        task.started_at = datetime.utcnow() - timedelta(minutes=2)
        db.commit()
        return {"content": "too late", "cards": [], "sources": []}

    monkeypatch.setattr(assistant_tasks, "_profile_result", late_result)
    assistant_tasks.execute_task(task_id)
    with assistant_tasks.SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        assert task.status == "TIMED_OUT"
        assert task.error_code == "TASK_DEADLINE_EXCEEDED"
        assert db.query(ChatMessage).filter_by(session_id=queued["conversation_id"], role="assistant").count() == 0
