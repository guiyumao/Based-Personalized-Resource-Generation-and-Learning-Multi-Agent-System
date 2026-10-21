"""Evidence -> persisted preview -> explicit confirmation -> plan task linkage."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import AnswerRecord, Exercise, KnowledgePoint, LearningPath, User, SystemSubject
from common.schemas.agent import LearningPathAdjustRequest
from services.agent_service.app.main import app
from services.agent_service.app.services.learning_path import (
    LearningPathRevisionConflict,
    LearningPathService,
)
from services.agent_service.app.services.path_adaptation import PathAdaptationService


@pytest.fixture
def adaptation_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all([User(id=1, username="learner", password_hash="unused"), User(id=2, username="other", password_hash="unused")])
        db.add(SystemSubject(id=1, name="计算机网络", code="networks", description="confirmed catalog"))
        point = KnowledgePoint(name="TCP 三次握手", subject_id=1)
        db.add(point)
        db.flush()
        exercise = Exercise(knowledge_point_id=point.id, type="choice", content="SYN?", answer="A")
        db.add(exercise)
        db.flush()
        path = LearningPath(user_id=1, status="active", path_data_json={"user_id": 1, "subject": "计算机网络", "knowledge_point": point.name,
            "overview": "学习TCP", "estimated_days": 3, "daily_minutes": 45,
            "stages": [{"stage_id": "s1", "title": "TCP", "description": "基础", "tasks": [
                {"task_id": "read", "title": "学习握手", "task_type": "courseware", "knowledge_point": point.name,
                 "objective": "理解原理", "difficulty": "foundation", "estimated_minutes": 30, "completed": False, "status": "pending", "depends_on": []}]}]})
        db.add(path)
        db.commit()
        yield db, exercise.id, path.id
    engine.dispose()


def add_answers(db, exercise_id, count, *, user_id=1, correct=False, when=None, repeat=False):
    for index in range(count):
        if not repeat:
            source = db.get(Exercise, exercise_id)
            question = Exercise(knowledge_point_id=source.knowledge_point_id, type=source.type,
                content=f"TCP握手判定问题 {db.query(Exercise).count()+1}", answer=source.answer)
            db.add(question)
            db.flush()
            question_id = question.id
        else:
            question_id = exercise_id
        db.add(AnswerRecord(user_id=user_id, exercise_id=question_id, user_answer="B", is_correct=correct,
                            created_at=when or datetime.now(UTC).replace(tzinfo=None)))
    db.commit()


def test_preview_does_not_mutate_tasks_confirmation_persists_once(adaptation_db):
    db, exercise_id, path_id = adaptation_db
    add_answers(db, exercise_id, 3)
    service = PathAdaptationService(db)
    before = deepcopy(db.get(LearningPath, path_id).path_data_json["stages"])
    proposal = service.preview(1, 20)
    assert proposal["status"] == "proposed"
    assert proposal["evidence"][0]["graded_answers"] == 3
    assert db.get(LearningPath, path_id).path_data_json["stages"] == before
    assert proposal["after"]["task_count"] == 2
    result = service.confirm(1, proposal["proposal_id"])
    assert result["status"] == "applied"
    assert result["path"]["daily_minutes"] == 20
    assert len(result["path"]["stages"]) == 2
    assert result["path"]["stages"][0] == before[0]
    assert result["path"]["stages"][1]["tasks"][0]["knowledge_point"] == "TCP 三次握手"
    assert service.confirm(1, proposal["proposal_id"])["status"] == "already_applied"
    assert service.preview(1, 20)["status"] == "no_change"


def test_no_change_insufficient_evidence_other_user_and_old_future_answers_excluded(adaptation_db):
    db, exercise_id, _ = adaptation_db
    now = datetime.now(UTC).replace(tzinfo=None)
    add_answers(db, exercise_id, 2)
    add_answers(db, exercise_id, 10, user_id=2)
    add_answers(db, exercise_id, 10, when=now - timedelta(days=31))
    add_answers(db, exercise_id, 10, when=now + timedelta(days=1))
    assert PathAdaptationService(db).preview(1)["status"] == "no_change"
    add_answers(db, exercise_id, 1)
    assert PathAdaptationService(db).preview(1)["status"] == "proposed"


def test_completion_invalidates_proposal_and_replaced_id_cannot_apply(adaptation_db):
    db, exercise_id, path_id = adaptation_db
    add_answers(db, exercise_id, 3)
    service = PathAdaptationService(db)
    proposal = service.preview(1)
    LearningPathService(db).adjust_path(LearningPathAdjustRequest(user_id=1, task_id="read", action="complete"))
    with pytest.raises(HTTPException) as conflict:
        service.confirm(1, proposal["proposal_id"])
    assert conflict.value.status_code == 409
    assert len(db.get(LearningPath, path_id).path_data_json["stages"]) == 1
    service.preview(1, 30)
    with pytest.raises(HTTPException) as missing:
        service.confirm(1, proposal["proposal_id"])
    assert missing.value.status_code == 404


def test_stale_database_revision_cannot_overwrite_fresh_plan(adaptation_db):
    db, _, path_id = adaptation_db
    record = db.get(LearningPath, path_id)
    stale = deepcopy(record.path_data_json)
    with sessionmaker(bind=db.get_bind())() as second:
        latest = second.get(LearningPath, path_id)
        data = deepcopy(latest.path_data_json)
        data["overview"] = "newer update"
        LearningPathService(second).commit_path_update(latest, data)
    with pytest.raises(LearningPathRevisionConflict):
        LearningPathService(db).commit_path_update(record, stale)
    db.expire_all()
    assert db.get(LearningPath, path_id).path_data_json["overview"] == "newer update"


def test_adaptation_routes_auth_isolation_and_validation(adaptation_db):
    db, exercise_id, _ = adaptation_db
    add_answers(db, exercise_id, 3)
    client = TestClient(app)
    def database():
        yield db
    app.dependency_overrides[get_db] = database
    try:
        assert client.post("/paths/adaptation/preview", json={}).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
        assert client.post("/paths/adaptation/preview", json={"daily_minutes": 0}).status_code == 422
        proposal = client.post("/paths/adaptation/preview", json={}).json()
        app.dependency_overrides[get_current_user] = lambda: db.get(User, 2)
        assert client.post(f"/paths/adaptation/{proposal['proposal_id']}/confirm").status_code == 404
        app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
        result = client.post(f"/paths/adaptation/{proposal['proposal_id']}/confirm")
        assert result.status_code == 200
        assert result.json()["path"]["stages"][-1]["tasks"][0]["task_type"] == "exercise"
    finally:
        app.dependency_overrides.clear()


def test_repeated_single_question_cannot_trigger_remedial_plan(adaptation_db):
    db, exercise_id, _ = adaptation_db
    add_answers(db, exercise_id, 12, repeat=True)
    assert PathAdaptationService(db).preview(1)["status"] == "no_change"
