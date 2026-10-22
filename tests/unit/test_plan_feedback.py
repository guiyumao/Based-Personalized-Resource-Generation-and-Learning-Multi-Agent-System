"""Natural-language plan feedback: diff, persisted proposal, CAS confirm, history preservation."""
from copy import deepcopy

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
from common.schemas.agent import LearningPathAdjustRequest
from services.agent_service.app.main import app
from services.agent_service.app.services.learning_path import LearningPathService
from services.agent_service.app.services.plan_feedback import PlanFeedbackService, compute_plan_diff


def _base_path() -> dict:
    return {"user_id": 1, "subject": "数据结构", "knowledge_point": "栈与队列", "overview": "学习栈与队列",
            "estimated_days": 7, "daily_minutes": 60, "generation_source": "llm", "path_revision": 0,
            "stages": [
                {"stage_id": "s1", "title": "基础", "description": "入门", "tasks": [
                    {"task_id": "t1", "title": "栈基础", "task_type": "courseware", "knowledge_point": "栈",
                     "objective": "理解栈", "estimated_minutes": 30, "difficulty": "foundation",
                     "completed": False, "status": "pending", "depends_on": []},
                    {"task_id": "t2", "title": "队列基础", "task_type": "courseware", "knowledge_point": "队列",
                     "objective": "理解队列", "estimated_minutes": 30, "difficulty": "foundation",
                     "completed": False, "status": "pending", "depends_on": ["t1"]},
                ]},
                {"stage_id": "s2", "title": "进阶", "description": "应用", "tasks": [
                    {"task_id": "t3", "title": "栈与队列练习", "task_type": "exercise", "knowledge_point": "栈与队列",
                     "objective": "做题", "estimated_minutes": 40, "difficulty": "intermediate",
                     "completed": False, "status": "pending", "depends_on": ["t2"]},
                ]},
            ]}


@pytest.fixture
def feedback_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all([User(id=1, username="learner", password_hash="unused"), User(id=2, username="other", password_hash="unused")])
        path = LearningPath(user_id=1, status="active", path_data_json=_base_path())
        db.add(path)
        db.commit()
        yield db, path.id
    engine.dispose()


def test_compute_plan_diff_detects_every_change_class():
    before = _base_path()
    after = deepcopy(before)
    # difficulty change on t1
    after["stages"][0]["tasks"][0]["difficulty"] = "intermediate"
    # duration change on t2
    after["stages"][0]["tasks"][1]["estimated_minutes"] = 20
    # remove t3
    after["stages"][1]["tasks"] = []
    # add a new task
    after["stages"][1]["tasks"].append({"task_id": "t4", "title": "综合复习", "task_type": "review",
                                        "knowledge_point": "栈与队列", "objective": "复盘", "estimated_minutes": 20,
                                        "difficulty": "foundation", "completed": False, "status": "pending", "depends_on": []})
    # reorder: swap t1 and t2
    after["stages"][0]["tasks"][0], after["stages"][0]["tasks"][1] = after["stages"][0]["tasks"][1], after["stages"][0]["tasks"][0]
    after["overview"] = "新的概述"
    after["estimated_days"] = 5
    diff = compute_plan_diff(before, after)
    assert [t["task_id"] for t in diff["removed_tasks"]] == ["t3"]
    assert [t["task_id"] for t in diff["added_tasks"]] == ["t4"]
    assert diff["difficulty_changes"][0]["task_id"] == "t1"
    assert diff["duration_changes"][0]["task_id"] == "t2"
    assert diff["reordered_task_ids"] == ["t1", "t2"]
    assert diff["overview_changed"] is True
    assert diff["impact"]["total_tasks_before"] == 3
    assert diff["impact"]["total_tasks_after"] == 3
    assert diff["impact"]["estimated_days_after"] == 5


def test_preview_persists_proposal_without_applying_and_confirm_applies_once(feedback_db, monkeypatch):
    db, path_id = feedback_db
    revised = deepcopy(_base_path())
    revised["daily_minutes"] = 30
    revised["stages"][0]["tasks"][0]["difficulty"] = "intermediate"
    monkeypatch.setattr(PlanFeedbackService, "_revise_with_llm", lambda self, cur, fb: revised)

    service = PlanFeedbackService(db)
    before = db.get(LearningPath, path_id).path_data_json["stages"]
    proposal = service.preview(1, "太难了，每天只有半小时")
    assert proposal["status"] == "proposed"
    assert proposal["diff"]["difficulty_changes"][0]["task_id"] == "t1"
    assert db.get(LearningPath, path_id).path_data_json["stages"] == before  # preview does not mutate tasks
    assert "feedback_proposal" in db.get(LearningPath, path_id).path_data_json

    result = service.confirm(1, proposal["proposal_id"])
    assert result["status"] == "applied"
    assert result["path"]["daily_minutes"] == 30
    assert result["path"]["stages"][0]["tasks"][0]["difficulty"] == "intermediate"
    assert "feedback_proposal" not in result["path"]
    assert service.confirm(1, proposal["proposal_id"])["status"] == "already_applied"
    from common.models.learning import Notification
    notices = db.query(Notification).filter_by(user_id=1, related_type="plan").all()
    assert len(notices) == 1
    assert notices[0].related_id == path_id


def test_no_change_feedback_returns_no_change(feedback_db, monkeypatch):
    db, _ = feedback_db
    monkeypatch.setattr(PlanFeedbackService, "_revise_with_llm", lambda self, cur, fb: deepcopy(cur))
    assert PlanFeedbackService(db).preview(1, "保持原样")["status"] == "no_change"


def test_confirm_preserves_completed_history_and_records_removed(feedback_db, monkeypatch):
    db, path_id = feedback_db
    # complete t1 first
    LearningPathService(db).adjust_path(LearningPathAdjustRequest(user_id=1, task_id="t1", action="complete"))
    revised = deepcopy(_base_path())
    revised["stages"][0]["tasks"][0]["completed"] = False
    revised["stages"][0]["tasks"][0]["status"] = "pending"
    del revised["stages"][0]["tasks"][1]  # remove t2 entirely
    monkeypatch.setattr(PlanFeedbackService, "_revise_with_llm", lambda self, cur, fb: revised)

    service = PlanFeedbackService(db)
    proposal = service.preview(1, "删掉队列基础，只保留栈")
    result = service.confirm(1, proposal["proposal_id"])
    # t1 survives and its completed flag is restored
    t1 = next(t for s in result["path"]["stages"] for t in s["tasks"] if t["task_id"] == "t1")
    assert t1["completed"] is True and t1["status"] == "completed"
    # t2 was not completed, so no removed-completed record for it
    assert "removed_completed_history" not in result["path"]
    # path revision advanced past base
    assert result["path"]["path_revision"] >= 2


def test_completion_invalidates_feedback_proposal(feedback_db, monkeypatch):
    from common.schemas.agent import LearningPathAdjustRequest
    db, _ = feedback_db
    revised = deepcopy(_base_path())
    revised["daily_minutes"] = 20
    monkeypatch.setattr(PlanFeedbackService, "_revise_with_llm", lambda self, cur, fb: revised)
    service = PlanFeedbackService(db)
    proposal = service.preview(1, "每天二十分钟")
    LearningPathService(db).adjust_path(LearningPathAdjustRequest(user_id=1, task_id="t1", action="complete"))
    with pytest.raises(HTTPException) as conflict:
        service.confirm(1, proposal["proposal_id"])
    assert conflict.value.status_code == 409


def test_feedback_routes_auth_validation_and_cross_user(feedback_db, monkeypatch):
    db, _ = feedback_db
    revised = deepcopy(_base_path())
    revised["daily_minutes"] = 25
    monkeypatch.setattr(PlanFeedbackService, "_revise_with_llm", lambda self, cur, fb: revised)
    client = TestClient(app)
    app.dependency_overrides[get_db] = lambda: db
    try:
        assert client.post("/paths/feedback/preview", json={"feedback_text": "太难"}).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
        assert client.post("/paths/feedback/preview", json={"feedback_text": ""}).status_code == 422
        proposal = client.post("/paths/feedback/preview", json={"feedback_text": "太难"}).json()
        app.dependency_overrides[get_current_user] = lambda: db.get(User, 2)
        assert client.post(f"/paths/feedback/{proposal['proposal_id']}/confirm").status_code == 404
        app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
        result = client.post(f"/paths/feedback/{proposal['proposal_id']}/confirm")
        assert result.status_code == 200
        assert result.json()["path"]["daily_minutes"] == 25
    finally:
        app.dependency_overrides.clear()


def test_revise_without_credentials_raises_blocked(feedback_db, monkeypatch):
    db, _ = feedback_db
    # Simulate an unconfigured deployment: the feedback loop must surface a clear
    # 503 rather than pretending to revise the plan (no paid call is made).
    from services.agent_service.app.services.llm_factory import LLMFactory
    monkeypatch.setattr(LLMFactory, "build_chat_model",
                        lambda self, *a, **k: (_ for _ in ()).throw(ValueError("No LLM credentials configured.")))
    service = PlanFeedbackService(db)
    with pytest.raises(HTTPException) as exc:
        service.preview(1, "太难了")
    assert exc.value.status_code == 503
