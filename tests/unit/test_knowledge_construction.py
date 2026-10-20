from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import KnowledgeBuildTask, KnowledgePoint, SystemSubject, User
from services.agent_service.app.main import app
from services.agent_service.app.services.knowledge_construction import SubjectOutline, confirm_outline


def outline_payload():
    return {"name": "机器学习", "code": "machine_learning", "aliases": ["ML"], "description": "本科基础课程",
            "chapters": [{"name": "监督学习", "points": [{"name": "线性回归", "objectives": ["理解最小二乘"], "prerequisites": ["线性代数"]}]}]}


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'construction.db'}")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    with maker() as db:
        db.add(User(id=1, username="construction-admin", password_hash="unused", role="admin"))
        db.add(KnowledgeBuildTask(id=1, actor_user_id=1, client_request_id="plan", request_hash="a" * 64,
                                 operation_type="AI_SUBJECT_PLAN", trigger_source="ADMIN_MANUAL", status="COMPLETED",
                                 result_json={"outline": outline_payload()}, requirements_json={}))
        db.commit()
    yield maker
    engine.dispose()


def test_confirm_outline_is_idempotent_and_keeps_unbuilt_points_planned(factory):
    with factory() as db:
        task = db.get(KnowledgeBuildTask, 1)
        outline = SubjectOutline.model_validate(outline_payload())
        subject = confirm_outline(db, task, outline)
        assert confirm_outline(db, task, outline).id == subject.id
        assert db.query(SystemSubject).count() == 1
        point = db.query(KnowledgePoint).one()
        assert point.chapter == "监督学习"
        assert point.construction_status == "PLANNED"
        assert point.prerequisites_json == ["线性代数"]
        changed = outline_payload(); changed["description"] = "changed"
        with pytest.raises(ValueError, match="already been confirmed"):
            confirm_outline(db, task, SubjectOutline.model_validate(changed))


def test_outline_schema_rejects_duplicate_or_unbounded_points():
    payload = outline_payload()
    payload["chapters"][0]["points"] *= 2
    with pytest.raises(ValueError):
        SubjectOutline.model_validate(payload)


def test_construction_http_auth_confirmation_and_bounded_batch(factory):
    client = TestClient(app)
    assert client.get("/knowledge-base/construction/subjects").status_code == 401
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[get_db] = lambda: factory()
    try:
        confirmed = client.post("/knowledge-base/construction/subject-plans/1/confirm", json=outline_payload())
        assert confirmed.status_code == 200
        point_id = client.get(f"/knowledge-base/construction/subjects/{confirmed.json()['subject_id']}/points").json()["items"][0]["id"]
        built = client.post("/knowledge-base/construction/points/build", json={"client_request_id": "batch-1", "point_ids": [point_id]})
        assert built.status_code == 202
        replay = client.post("/knowledge-base/construction/points/build", json={"client_request_id": "batch-1", "point_ids": [point_id]})
        assert replay.json()["items"][0]["id"] == built.json()["items"][0]["id"]
        assert client.post("/knowledge-base/construction/points/build", json={"client_request_id": "bad", "point_ids": list(range(11))}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_manual_subject_and_point_reuse_canonical_names(factory):
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[get_db] = lambda: factory()
    try:
        subject = client.post("/knowledge-base/construction/subjects", json={"name": "计算机网络", "code": "computer_networks", "aliases": ["Computer Networks"]}).json()
        repeated = client.post("/knowledge-base/construction/subjects", json={"name": "Computer Networks", "code": "computer_networks"}).json()
        assert repeated["id"] == subject["id"]
        payload = {"name": "BBR", "aliases": ["BBR拥塞控制"], "chapter": "传输层", "objectives": ["理解带宽与时延模型"]}
        point = client.post(f"/knowledge-base/construction/subjects/{subject['id']}/points", json=payload).json()
        payload["name"] = "BBR拥塞控制"
        assert client.post(f"/knowledge-base/construction/subjects/{subject['id']}/points", json=payload).json()["id"] == point["id"]
    finally:
        app.dependency_overrides.clear()
