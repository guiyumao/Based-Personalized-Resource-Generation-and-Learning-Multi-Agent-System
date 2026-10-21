"""Privacy boundaries shared by assistant generation and real practice feedback."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.models.learning import AnswerRecord, ClassEnrollment, Classroom, Exercise, KnowledgePoint, User, UserProfile
from common.schemas.agent import CoordinationRequest, ExerciseGenerationRequest
from common.security.auth import create_access_token
from services.agent_service.app.agents import coordinator as coordinator_module
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.services import assistant_tasks
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.personalization import LearnerPersonalizationSnapshot
from services.agent_service.app.services.resource_generation import ResourceGenerationService
from services.evaluation_service.app.api.routes import reports
from services.evaluation_service.app.main import app
from services.evaluation_service.app.services.report_service import ReportService


@pytest.fixture
def privacy_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'privacy.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        users = [User(username=name, password_hash="test", role=role) for name, role in (
            ("private_owner", "student"), ("private_other", "student"), ("bound_teacher", "teacher"),
        )]
        db.add_all(users)
        db.flush()
        owner, other, teacher = users
        point = KnowledgePoint(name="TCP", difficulty=1, importance=1)
        classroom = Classroom(name="Networks", subject="TCP", teacher_name="Teacher", teacher_user_id=teacher.id)
        db.add_all([point, classroom])
        db.flush()
        db.add(ClassEnrollment(class_id=classroom.id, student_user_id=owner.id))
        db.add(UserProfile(user_id=owner.id, mastery_json={"TCP": 95}, habits={"secret_preference": "private-marker"}))
        question = Exercise(knowledge_point_id=point.id, type="choice", difficulty=1,
                            content=json.dumps({"prompt": "private-owner-example", "options": ["A. wrong", "B. correct"],
                                                "generated_for_user_id": owner.id}), answer="B", analysis="Stored explanation")
        db.add(question)
        db.commit()
        ids = {"owner": owner.id, "other": other.id, "teacher": teacher.id, "exercise": question.id, "point": point.id}
        original_content = question.content

    def override_db():
        with factory() as db:
            yield db

    old_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    service = ReportService(session_factory=factory, llm_client=SimpleNamespace(), publisher=SimpleNamespace(publish=lambda *_args: None))
    monkeypatch.setattr(reports, "ReportService", lambda: service)
    try:
        yield TestClient(app), ids, factory, original_content
    finally:
        if old_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = old_override
        engine.dispose()


def _headers(user_id):
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def _submissions(user_id, exercise_id):
    practice = {"user_id": user_id, "exercise_id": exercise_id, "knowledge_point": "TCP", "question_type": "choice",
                "user_answer": "A", "correct_answer": "A", "analysis": "Forged explanation", "difficulty": "basic"}
    answer = {"user_id": str(user_id), "exercise_id": str(exercise_id), "user_answer": "A", "time_spent": 0,
              "exercise_type": "choice", "difficulty": "basic", "standard_answer": "A", "knowledge_point_ids": ["forged-topic"]}
    return [
        ("/evaluation/practice/submit", practice),
        ("/evaluation/submit", answer),
        ("/evaluation/batch_submit", {"records": [answer]}),
        ("/evaluation/answers", {"user_id": user_id, "exercise_id": exercise_id, "answer": "A"}),
        ("/evaluation/mistakes/qa", {"user_id": user_id, "exercise_id": exercise_id, "knowledge_point": "TCP",
                                    "question_summary": "private", "wrong_answer": "A", "correct_answer": "B",
                                    "analysis": "Stored", "suggested_action": "review"}),
    ]


def test_evaluation_rejects_anonymous_and_forged_user_ids_before_writing(privacy_client):
    client, ids, factory, _original = privacy_client
    for url, body in _submissions(ids["other"], ids["exercise"]):
        assert client.post(url, json=body).status_code == 401, url
        assert client.post(url, headers=_headers(ids["owner"]), json=body).status_code == 403, url
    for url in (f"/evaluation/stage-report/{ids['owner']}/chapter", f"/evaluation/monthly-report/{ids['owner']}"):
        assert client.get(url).status_code == 401
        assert client.get(url, headers=_headers(ids["other"])).status_code == 403
    own_answer = _submissions(ids["owner"], ids["exercise"])[1][1]
    other_answer = {**own_answer, "user_id": str(ids["other"])}
    assert client.post("/evaluation/batch_submit", headers=_headers(ids["owner"]), json={"records": [own_answer, other_answer]}).status_code == 403
    with factory() as db:
        assert db.query(AnswerRecord).count() == 0


def test_stored_answer_is_authoritative_and_private_question_is_not_shared(privacy_client):
    client, ids, factory, original = privacy_client
    url, body = _submissions(ids["owner"], ids["exercise"])[0]
    result = client.post(url, headers=_headers(ids["owner"]), json=body)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["is_correct"] is False
    assert result.json()["data"]["analysis"] == "Stored explanation"
    other_body = {**body, "user_id": ids["other"]}
    assert client.post(url, headers=_headers(ids["other"]), json=other_body).status_code == 404
    favorite = f"/evaluation/practice/favorites/{ids['exercise']}"
    assert client.post(favorite, headers=_headers(ids["other"])).status_code == 404
    saved = client.post(favorite, headers=_headers(ids["owner"]))
    assert saved.status_code == 200 and saved.json()["data"]["options"] == ["A. wrong", "B. correct"]
    with factory() as db:
        question = db.get(Exercise, ids["exercise"])
        assert question.content == original and question.answer == "B"
        assert db.query(AnswerRecord).filter(AnswerRecord.user_id == ids["owner"]).count() == 1


def test_practice_attempt_replay_survives_new_service_and_rejects_changed_answer(privacy_client, monkeypatch):
    client, ids, factory, _original = privacy_client
    url, body = _submissions(ids["owner"], ids["exercise"])[0]
    body["client_request_id"] = "practice-attempt-0001"
    first = client.post(url, headers=_headers(ids["owner"]), json=body)
    assert first.status_code == 200, first.text
    # Recreate the service: receipt recovery must come from the database.
    service = ReportService(session_factory=factory, llm_client=SimpleNamespace(), publisher=SimpleNamespace())
    monkeypatch.setattr(reports, "ReportService", lambda: service)
    repeated = client.post(url, headers=_headers(ids["owner"]), json={**body, "time_spent": 80})
    assert repeated.status_code == 200 and repeated.json() == first.json()
    changed = client.post(url, headers=_headers(ids["owner"]), json={**body, "user_answer": "B"})
    assert changed.status_code == 409, changed.text
    with factory() as db:
        assert db.query(AnswerRecord).count() == 1
    retake = client.post(url, headers=_headers(ids["owner"]), json={**body, "client_request_id": "practice-attempt-0002", "user_answer": "B"})
    assert retake.status_code == 200 and retake.json()["data"]["is_correct"] is True
    with factory() as db:
        assert db.query(AnswerRecord).count() == 2


def test_concurrent_attempts_update_profile_and_publish_only_once(privacy_client, monkeypatch):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from services.evaluation_service.app.schemas.report import AnswerRecordSubmission

    _client, ids, factory, _original = privacy_client
    service = reports.ReportService()
    published = []
    service._publisher = SimpleNamespace(publish=lambda queue, event: published.append((queue, event)))
    barrier = Barrier(2)
    persist = service._persist_submission

    def simultaneous_persist(prepared, outcome):
        barrier.wait(timeout=10)
        return persist(prepared, outcome)

    monkeypatch.setattr(service, "_persist_submission", simultaneous_persist)
    payload = AnswerRecordSubmission(**{
        **_submissions(ids["owner"], ids["exercise"])[1][1], "client_request_id": "concurrent-attempt-0001",
    })
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: asyncio.run(service.submit_answer(payload)), range(2)))
    assert results[0].model_dump(mode="json") == results[1].model_dump(mode="json")
    assert len(published) == 1 and published[0][0] == "profile_updates"
    with factory() as db:
        assert db.query(AnswerRecord).count() == 1
        profile = db.query(UserProfile).filter_by(user_id=ids["owner"]).one()
        assert len(profile.mastery_json["TCP"]["history"]) == 1


def test_teacher_can_read_only_students_in_owned_classes(privacy_client):
    client, ids, _factory, _original = privacy_client
    headers = _headers(ids["teacher"])
    assert client.get(f"/evaluation/profiles/{ids['owner']}/snapshot", headers=headers).status_code == 200
    assert client.get(f"/evaluation/profiles/{ids['other']}/snapshot", headers=headers).status_code == 403
    assert client.get(f"/evaluation/mistakes/{ids['other']}/teacher-detail", headers=headers).status_code == 403


def test_custom_external_question_identifiers_are_namespaced_per_user(privacy_client):
    client, ids, factory, _original = privacy_client
    body = _submissions(ids["owner"], ids["exercise"])[1][1]
    body["exercise_id"] = "same-external-question"
    for user_id in (ids["owner"], ids["other"]):
        response = client.post("/evaluation/submit", headers=_headers(user_id), json={**body, "user_id": str(user_id)})
        assert response.status_code == 200, response.text
    with factory() as db:
        records = db.query(AnswerRecord).order_by(AnswerRecord.id).all()
        assert len(records) == 2 and records[0].exercise_id != records[1].exercise_id


def test_recent_question_context_contains_only_the_current_users_generated_questions(privacy_client):
    _client, ids, factory, _original = privacy_client
    with factory() as db:
        db.add_all([
            Exercise(knowledge_point_id=ids["point"], type="choice", difficulty=1, answer="A", content=json.dumps({
                "prompt": "other-private-example", "generated_for_user_id": ids["other"],
            })),
            Exercise(knowledge_point_id=ids["point"], type="choice", difficulty=1, answer="A", content=json.dumps({"prompt": "legacy-unknown-origin"})),
        ])
        db.commit()
        service = ExerciseGenerationService.__new__(ExerciseGenerationService)
        signatures = service._load_recent_exercise_signatures(db, ids["point"], ids["owner"])
        assert len(signatures) == 1 and "private-owner-example" in next(iter(signatures))


def test_history_opt_out_skips_profile_loading_and_does_not_report_zero_mastery(monkeypatch, db_session):
    workflow = CoordinatorWorkflow(db=db_session)
    monkeypatch.setattr(workflow, "_build_profile_snapshot", lambda **_kwargs: pytest.fail("History must not be loaded"))
    seen = []

    def resource_agent(**kwargs):
        seen.append(kwargs["snapshot"])
        return {"status": "completed", "resource": {"id": 1}}, {"id": 1}

    monkeypatch.setattr(workflow, "_run_resource_agent", resource_agent)
    monkeypatch.setattr(coordinator_module, "KnowledgeGraphRepository", lambda: SimpleNamespace(sync_courseware_to_graph=lambda *_args: None))
    result = workflow._execute_agents(CoordinationRequest(user_id=1, intent="Generate", knowledge_point="TCP", payload={
        "use_learning_context": False, "learner_profile": {"secret_preference": "private-marker"},
    }), {"selected_agents": ["learner_profiling_agent", "resource_generation_agent"], "outputs": {}, "route_reason": "test"})
    assert result["outputs"]["learner_profiling_agent"]["status"] == "skipped"
    snapshot = seen[0]
    assert snapshot.learner_profile == {"history_disabled": True} and snapshot.recent_mistakes == []
    resource = ResourceGenerationService.__new__(ResourceGenerationService)
    exercise = ExerciseGenerationService.__new__(ExerciseGenerationService)
    assert resource._build_personalization_payload("TCP", snapshot)["mastery_score"] is None
    assert exercise._build_personalization_payload(snapshot)["mastery_score"] is None
    assert "未读取" in resource._build_recent_mistakes_text(snapshot)
    assert resource._infer_difficulty("复习 TCP", snapshot) == "intermediate"
    summary = exercise._build_summary_text(ExerciseGenerationRequest(user_id=1, knowledge_point="TCP"), 3, snapshot)
    assert "未读取" in summary and "没有" not in summary


@pytest.mark.parametrize("message, expected", [("生成 TCP 课件", False), ("根据我的学习情况生成 TCP 课件", True)])
def test_generation_uses_history_only_when_enabled_or_explicitly_requested(monkeypatch, message, expected):
    class CaptureCoordinator:
        def __init__(self, _db):
            pass

        def run(self, request):
            assert request.payload["use_learning_context"] is expected
            return {"status": "success", "agent_calls": [], "outputs": {
                "resource_generation_agent": {"resource": {"id": 1}},
            }}

    monkeypatch.setattr(assistant_tasks, "CoordinatorWorkflow", CaptureCoordinator)
    result, _calls = assistant_tasks._coordinated_result(SimpleNamespace(), SimpleNamespace(
        user_id=1, task_type="courseware", request_json={"message": message, "knowledge_point": "TCP", "use_learning_context": False},
    ))
    assert result["evidence"]["learning_context_used"] is expected


def test_public_knowledge_sources_and_pending_review_are_visible(monkeypatch):
    class CaptureCoordinator:
        def __init__(self, _db):
            pass

        def run(self, request):
            return {"status": "success", "agent_calls": [], "outputs": {
                "resource_generation_agent": {"resource": {"id": 1}},
                "knowledge_acquisition": {"coverage": {"state": "PARTIAL"}, "sources": [
                    {"url": "https://example.com/course", "title": "课程来源", "review_status": "PENDING"},
                ]},
            }}

    monkeypatch.setattr(assistant_tasks, "CoordinatorWorkflow", CaptureCoordinator)
    result, _ = assistant_tasks._coordinated_result(SimpleNamespace(), SimpleNamespace(
        user_id=1, task_type="courseware", request_json={"message": "生成 TCP 课件", "knowledge_point": "TCP"},
    ))
    assert result["sources"][0]["url"] == "https://example.com/course"
    assert "尚待管理员审核" in result["content"]
    assert "缺口" in result["content"]
