"""Task-level execution feedback: deterministic revisions through the shared proposal model."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import LearningPath, User
from services.agent_service.app.main import app
from services.agent_service.app.services.task_feedback import TaskFeedbackService


def _base_path() -> dict:
    return {"user_id": 1, "subject": "数据结构", "knowledge_point": "栈与队列", "overview": "学习栈与队列",
            "estimated_days": 7, "daily_minutes": 60, "generation_source": "llm", "path_revision": 0,
            "stages": [
                {"stage_id": "s1", "title": "基础", "description": "入门", "tasks": [
                    {"task_id": "t1", "title": "栈基础", "task_type": "courseware", "knowledge_point": "栈",
                     "objective": "理解栈", "estimated_minutes": 30, "difficulty": "intermediate",
                     "completed": False, "status": "pending", "depends_on": []},
                    {"task_id": "t2", "title": "队列基础", "task_type": "courseware", "knowledge_point": "队列",
                     "objective": "理解队列", "estimated_minutes": 30, "difficulty": "foundation",
                     "completed": False, "status": "pending", "depends_on": ["t1"]},
                ]},
            ]}


def _flat_ids(path: dict) -> list[str]:
    return [t["task_id"] for s in path["stages"] for t in s["tasks"]]


@pytest.fixture
def task_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all([User(id=1, username="learner", password_hash="unused"), User(id=2, username="other", password_hash="unused")])
        path = LearningPath(user_id=1, status="active", path_data_json=_base_path())
        db.add(path)
        db.commit()
        yield db, path.id
    engine.dispose()


def _apply(db, user_id, task_id, feedback_type, note=None):
    proposal = TaskFeedbackService(db).preview(user_id, task_id, feedback_type, note)
    assert proposal["status"] == "proposed"
    result = TaskFeedbackService(db).confirm(user_id, proposal["proposal_id"])
    assert result["status"] == "applied"
    return result["path"]


def _task(path, task_id):
    for s in path["stages"]:
        for t in s["tasks"]:
            if t["task_id"] == task_id:
                return t
    return None


def test_too_hard_downshifts_intermediate(task_db):
    db, _ = task_db
    # t1 is intermediate -> downshift only, no extra task
    path = _apply(db, 1, "t1", "too_hard")
    assert _task(path, "t1")["difficulty"] == "foundation"
    assert len(_flat_ids(path)) == 2


def test_too_hard_adds_prerequisite_for_foundation(task_db):
    db, _ = task_db
    # t2 is already foundation -> insert a prerequisite review task before it
    base_ids = _flat_ids(_base_path())
    path = _apply(db, 1, "t2", "too_hard")
    ids = _flat_ids(path)
    assert len(ids) == len(base_ids) + 1
    assert ids.index("t2") == 2
    prereq = ids[1]
    assert prereq not in base_ids
    assert _task(path, prereq)["task_type"] == "review"
    assert prereq in _task(path, "t2")["depends_on"]


def test_too_easy_upshifts_and_not_enough_time_halves(task_db):
    db, _ = task_db
    path = _apply(db, 1, "t2", "too_easy")
    assert _task(path, "t2")["difficulty"] == "intermediate"
    path2 = _apply(db, 1, "t1", "not_enough_time")
    assert _task(path2, "t1")["estimated_minutes"] == 15
    assert path2["estimated_days"] == 8


def test_not_understood_adds_explainer_and_more_practice_adds_exercise(task_db):
    db, _ = task_db
    path = _apply(db, 1, "t1", "not_understood")
    ids = _flat_ids(path)
    assert len(ids) == 3
    assert _task(path, ids[0])["task_type"] == "courseware"
    assert ids[0] in _task(path, "t1")["depends_on"]
    path2 = _apply(db, 1, "t1", "more_practice")
    added = [t for t in path2["stages"][0]["tasks"] if t["task_id"] not in _flat_ids(_base_path())]
    assert added and added[-1]["task_type"] == "exercise"


def test_already_mastered_marks_completed_without_touching_mastery(task_db):
    db, _ = task_db
    path = _apply(db, 1, "t1", "already_mastered")
    assert _task(path, "t1")["completed"] is True
    assert _task(path, "t1")["status"] == "completed"


def test_unknown_task_and_invalid_type(task_db):
    db, _ = task_db
    with pytest.raises(HTTPException) as exc:
        TaskFeedbackService(db).preview(1, "missing", "too_hard")
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        TaskFeedbackService(db).preview(1, "t1", "bogus_type")
    assert exc.value.status_code == 422


def test_task_feedback_route_auth_and_confirm_reuse(task_db):
    db, _ = task_db
    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: db
    try:
        assert client.post("/paths/task-feedback/preview", json={"task_id": "t1", "feedback_type": "too_hard"}).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
        assert client.post("/paths/task-feedback/preview", json={"task_id": "t1", "feedback_type": "bogus"}).status_code == 422
        proposal = client.post("/paths/task-feedback/preview", json={"task_id": "t1", "feedback_type": "too_easy"}).json()
        # confirm through the shared feedback confirm endpoint
        result = client.post(f"/paths/feedback/{proposal['proposal_id']}/confirm")
        assert result.status_code == 200
        assert result.json()["path"]["stages"][0]["tasks"][0]["difficulty"] == "advanced"
    finally:
        app.dependency_overrides.clear()
