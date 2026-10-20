"""Real SQLite evidence for activity accounting, ownership and plan progress."""

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import (
    AnswerRecord,
    Exercise,
    KnowledgePoint,
    LearningPath,
    LearningTask,
    Resource,
    ReviewCard,
    StudyActivity,
    StudySession,
    User,
)
from common.schemas.agent import LearningPathAdjustRequest
from services.agent_service.app.services.learning_path import LearningPathService
from services.evaluation_service.app.main import app
from services.evaluation_service.app.services.learning_analytics import (
    build_learning_analytics,
    build_learning_overview,
)
from services.evaluation_service.app.services.study_activity import (
    ActivityHeartbeat,
    measured_daily_seconds,
    record_heartbeat,
)


@pytest.fixture
def activity_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all([User(id=1, username="learner", password_hash="unused"), User(id=2, username="other", password_hash="unused")])
        db.commit()
        yield db
    engine.dispose()


def beat(tab, seq, active=True):
    return ActivityHeartbeat(tab_id=tab, sequence=seq, active=active, page="exercise")


def test_server_time_replay_out_of_order_and_idle(activity_db):
    db = activity_db
    tab = uuid4()
    start = datetime(2026, 10, 20, 1)
    assert record_heartbeat(db, 1, beat(tab, 1), now=start)["credited_seconds"] == 0
    assert record_heartbeat(db, 1, beat(tab, 2), now=start + timedelta(seconds=15))["credited_seconds"] == 15
    assert record_heartbeat(db, 1, beat(tab, 2), now=start + timedelta(seconds=20))["status"] == "replayed"
    assert record_heartbeat(db, 1, beat(tab, 1), now=start + timedelta(seconds=25))["status"] == "replayed"
    assert record_heartbeat(db, 1, beat(tab, 3, False), now=start + timedelta(seconds=30))["credited_seconds"] == 0
    assert record_heartbeat(db, 1, beat(tab, 4), now=start + timedelta(seconds=45))["credited_seconds"] == 0
    assert record_heartbeat(db, 1, beat(tab, 5), now=start + timedelta(seconds=60))["credited_seconds"] == 15
    assert db.query(StudyActivity).count() == 2


def test_multiple_tabs_share_one_cursor_and_takeover_does_not_count_gap(activity_db):
    db = activity_db
    first, second = uuid4(), uuid4()
    now = datetime(2026, 10, 20, 1)
    record_heartbeat(db, 1, beat(first, 1), now=now)
    assert record_heartbeat(db, 1, beat(second, 1), now=now + timedelta(seconds=15))["status"] == "another_tab"
    assert record_heartbeat(db, 1, beat(first, 2), now=now + timedelta(seconds=15))["credited_seconds"] == 15
    assert record_heartbeat(db, 1, beat(second, 2, False), now=now + timedelta(seconds=80))["status"] == "another_tab"
    assert record_heartbeat(db, 1, beat(second, 3), now=now + timedelta(seconds=80))["credited_seconds"] == 0
    assert record_heartbeat(db, 1, beat(second, 4), now=now + timedelta(seconds=95))["credited_seconds"] == 15
    assert record_heartbeat(db, 1, beat(first, 3), now=now + timedelta(seconds=96))["status"] == "another_tab"
    assert db.query(StudySession).count() == 1
    assert db.query(StudyActivity).count() == 2


def test_clock_rollback_stale_gap_and_owner_release(activity_db):
    db = activity_db
    tab, other = uuid4(), uuid4()
    now = datetime(2026, 10, 20, 1)
    record_heartbeat(db, 1, beat(tab, 1), now=now)
    assert record_heartbeat(db, 1, beat(tab, 2), now=now - timedelta(seconds=1))["status"] == "clock_rollback"
    assert record_heartbeat(db, 1, beat(tab, 3), now=now + timedelta(seconds=46))["credited_seconds"] == 0
    record_heartbeat(db, 1, beat(tab, 4, False), now=now + timedelta(seconds=47))
    assert record_heartbeat(db, 1, beat(other, 1), now=now + timedelta(seconds=48))["status"] == "resumed"
    assert db.query(StudyActivity).count() == 0


def test_midnight_split_clipping_and_user_isolation(activity_db):
    db = activity_db
    # 23:59:50 -> 00:00:10 in Asia/Shanghai.
    start = datetime(2026, 10, 19, 15, 59, 50)
    tab = uuid4()
    record_heartbeat(db, 1, beat(tab, 1), now=start)
    record_heartbeat(db, 1, beat(tab, 2), now=start + timedelta(seconds=20))
    db.add(StudyActivity(user_id=2, started_at=start, ended_at=start + timedelta(seconds=20), page="qa"))
    db.commit()
    assert measured_daily_seconds(db, 1, start, start + timedelta(seconds=20), ZoneInfo("Asia/Shanghai")) == {"2026-10-19": 10, "2026-10-20": 10}
    assert measured_daily_seconds(db, 1, start + timedelta(seconds=5), start + timedelta(seconds=15), ZoneInfo("Asia/Shanghai")) == {"2026-10-19": 5, "2026-10-20": 5}


def test_progress_reads_authoritative_json_and_tracks_real_adjustment(activity_db):
    db = activity_db
    path = LearningPath(user_id=1, status="active", path_data_json={
        "subject": "计算机网络", "knowledge_point": "TCP", "stages": [{"tasks": [
            {"task_id": "read", "completed": True, "status": "completed"},
            {"task_id": "practice", "completed": False, "depends_on": ["read"]},
        ]}],
    })
    db.add(path)
    db.commit()
    # A legacy row must not be combined with the authoritative JSON.
    db.add(LearningTask(path_id=path.id, task_type="stale", completed=False))
    db.commit()
    assert build_learning_analytics(db, 1)["path_progress"]["completion_percent"] == 50
    LearningPathService(db).adjust_path(LearningPathAdjustRequest(user_id=1, task_id="practice", action="complete"))
    assert build_learning_overview(db, 1)["active_plans"][0]["completion_percent"] == 100
    assert build_learning_overview(db, 2)["active_plans"] == []


def test_overview_uses_existing_resources_reviews_and_answer_evidence(activity_db):
    db = activity_db
    point = KnowledgePoint(name="TCP 三次握手")
    db.add(point)
    db.flush()
    exercise = Exercise(knowledge_point_id=point.id, type="choice", content="SYN?", answer="A")
    db.add(exercise)
    db.flush()
    db.add_all([
        AnswerRecord(user_id=1, exercise_id=exercise.id, user_answer="B", is_correct=False),
        ReviewCard(user_id=1, front="SYN?", back="同步序号", due_at=datetime.utcnow() - timedelta(days=1)),
        ReviewCard(user_id=2, front="other", back="secret"),
        Resource(title="我的课件", type="article", content="TCP", generated_for_user_id=1),
        Resource(title="别人的私有课件", type="article", content="secret", generated_for_user_id=2),
    ])
    db.commit()
    overview = build_learning_overview(db, 1)
    assert overview["due_cards"] == 1
    assert [row["title"] for row in overview["recent_resources"]] == ["我的课件"]
    assert overview["weak_points"][0]["confidence"] == "low"
    assert overview["weak_points"][0]["accuracy_percent"] == 0
    assert "TCP 三次握手" in str(overview["suggestions"])


def test_routes_auth_validation_no_client_duration_and_missing_migration(activity_db):
    db = activity_db
    user = db.get(User, 1)
    def database():
        yield db
    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    try:
        assert client.get("/evaluation/overview/me").status_code == 401
        assert client.post("/evaluation/activity/heartbeat", json={}).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: user
        assert client.get("/evaluation/overview/me").status_code == 200
        payload = {"tab_id": str(uuid4()), "sequence": 1, "active": True, "page": "exercise"}
        for field, value in [("sequence", 0), ("sequence", True), ("page", "admin"), ("active", "yes"), ("tab_id", "invalid")]:
            assert client.post("/evaluation/activity/heartbeat", json={**payload, field: value}).status_code == 422
        assert client.post("/evaluation/activity/heartbeat", json={**payload, "duration_seconds": 99999}).status_code == 422
        assert client.post("/evaluation/activity/heartbeat", json={**payload, "user_id": 2}).status_code == 422
        response = client.post("/evaluation/activity/heartbeat", json=payload)
        assert response.status_code == 200
        assert response.json()["data"]["credited_seconds"] == 0
        assert db.get(StudySession, 2) is None
        StudyActivity.__table__.drop(db.get_bind())
        StudySession.__table__.drop(db.get_bind())
        assert client.post("/evaluation/activity/heartbeat", json=payload).status_code == 503
        analytics = client.get("/evaluation/analytics/1").json()["data"]
        assert analytics["summary"]["study_seconds"] is None
    finally:
        app.dependency_overrides.clear()


def test_concurrent_heartbeats_commit_one_interval(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine = create_engine(f"sqlite:///{(tmp_path / 'concurrent.sqlite').as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    now = datetime(2026, 10, 20, 1)
    tab = uuid4()
    with factory() as db:
        db.add(User(id=1, username="parallel", password_hash="unused"))
        db.commit()
        record_heartbeat(db, 1, beat(tab, 1), now=now)
    barrier = Barrier(4)
    def work(_):
        with factory() as db:
            barrier.wait(timeout=10)
            return record_heartbeat(db, 1, beat(tab, 2), now=now + timedelta(seconds=15))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(work, range(4)))
    with factory() as db:
        assert db.query(StudyActivity).count() == 1
        assert sum(result["credited_seconds"] for result in results) == 15
        assert db.get(StudySession, 1).sequence == 2
    engine.dispose()


def test_failed_interval_insert_cannot_advance_cursor(activity_db):
    from sqlalchemy import event
    from sqlalchemy.exc import StatementError

    db = activity_db
    now = datetime(2026, 10, 20, 1)
    tab = uuid4()
    record_heartbeat(db, 1, beat(tab, 1), now=now)
    def fail(*_):
        raise ValueError("injected storage failure")
    event.listen(StudyActivity, "before_insert", fail)
    try:
        with pytest.raises((ValueError, StatementError)):
            record_heartbeat(db, 1, beat(tab, 2), now=now + timedelta(seconds=15))
    finally:
        db.rollback()
        event.remove(StudyActivity, "before_insert", fail)
    assert db.get(StudySession, 1).sequence == 1
    assert db.query(StudyActivity).count() == 0
    assert record_heartbeat(db, 1, beat(tab, 2), now=now + timedelta(seconds=15))["credited_seconds"] == 15
