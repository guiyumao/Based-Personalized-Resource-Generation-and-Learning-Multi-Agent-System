"""Real DB/JWT notification contracts; unrelated learner data must stay isolated."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.db.session import get_db
from common.models.learning import ClassEnrollment, Notification, User
from common.notifications import emit
from common.security.auth import create_access_token
from services.teacher_service.app.main import app
from services.teacher_service.app.schemas.teacher import (
    ClassCreate,
    HomeworkAssign,
    ReviewPayload,
    SubmissionCreate,
)
from services.teacher_service.app.services.teacher_manager import TeacherManager


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(
        "services.teacher_service.app.services.teacher_manager.SessionLocal", factory
    )

    def session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = session
    with factory() as db:
        for uid, role in [
            (1, "admin"),
            (2, "teacher"),
            (3, "student"),
            (4, "student"),
            (5, "teacher"),
        ]:
            db.add(
                User(id=uid, username=f"notice-{uid}", role=role, password_hash="x", is_active=True)
            )
        db.commit()
    client = TestClient(app)

    def headers(uid):
        return {"Authorization": f"Bearer {create_access_token(str(uid))}"}

    yield client, factory, headers
    app.dependency_overrides.clear()
    engine.dispose()


def post(client, headers, uid, **changes):
    payload = dict(
        request_key=uuid4().hex, scope="students", title="平台公告", content="真实公告正文"
    )
    payload.update(changes)
    return client.post("/learning/notifications/publish", json=payload, headers=headers(uid))


def inbox(client, headers, uid, **params):
    r = client.get("/learning/notifications/inbox", params=params, headers=headers(uid))
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_roles_scopes_and_retry(setup):
    c, f, h = setup
    assert c.get("/learning/notifications/inbox").status_code == 401
    assert post(c, h, 3).status_code == 403
    key = uuid4().hex
    assert post(c, h, 1, request_key=key).json()["data"]["recipient_count"] == 2
    assert post(c, h, 1, request_key=key).status_code == 200
    assert post(c, h, 1, request_key=key, title="冲突内容").status_code == 422
    assert inbox(c, h, 3)["unread_count"] == 1
    assert inbox(c, h, 2)["unread_count"] == 0
    assert post(c, h, 1, scope="teachers").status_code == 200
    assert inbox(c, h, 2)["unread_count"] == 1
    assert post(c, h, 2, scope="teachers").status_code == 403
    assert post(c, h, 2, scope="student", target_id=4).status_code == 422
    assert post(c, h, 1, scope="student", target_id=3).json()["data"]["recipient_count"] == 1
    assert inbox(c, h, 4)["unread_count"] == 1


def test_page_read_and_persistence_isolation(setup):
    c, f, h = setup
    for _ in range(12):
        assert post(c, h, 1, scope="student", target_id=3).status_code == 200
    first = inbox(c, h, 3, size=5)
    second = inbox(c, h, 3, size=5, page=2)
    assert first["total"] == 12 and len(first["items"]) == 5
    assert not ({x["id"] for x in first["items"]} & {x["id"] for x in second["items"]})
    nid = first["items"][0]["id"]
    assert c.patch(f"/learning/notifications/{nid}/read", headers=h(4)).status_code == 404
    assert c.get(f"/learning/notifications/{nid}/detail", headers=h(4)).status_code == 404
    for _ in range(2):
        assert c.patch(f"/learning/notifications/{nid}/read", headers=h(3)).status_code == 200
    assert inbox(c, h, 3)["unread_count"] == 11
    with f() as db:
        stamp = db.get(Notification, nid).read_at
        assert stamp is not None
    assert (
        c.get(f"/learning/notifications/{nid}/detail", headers=h(3)).json()["data"]["target_path"]
        is None
    )
    assert c.post("/learning/notifications/read-all", headers=h(3)).status_code == 200
    assert inbox(c, h, 3)["unread_count"] == 0
    assert inbox(c, h, 3, unread=True)["total"] == 0
    with f() as db:
        assert db.get(Notification, nid).read_at == stamp


def test_real_homework_review_and_revocation(setup):
    c, f, h = setup
    manager = TeacherManager()
    cls = manager.create_class(ClassCreate(name="通知班级", subject="数学", teacher_name="老师"), 2)
    manager.enroll_student(cls.id, 3, 2)
    assignment = manager.create_assignment(
        HomeworkAssign(class_id=cls.id, title="练习作业", description="解答题目"), 2
    )
    assert any(n["type"] == "assignment" for n in inbox(c, h, 3)["items"])
    assert inbox(c, h, 4)["total"] == 0
    with pytest.raises(PermissionError):
        manager.submit_assignment(assignment.id, SubmissionCreate(content="无权提交"), 4)
    submission = manager.submit_assignment(assignment.id, SubmissionCreate(content="完成作业"), 3)
    manager.submit_assignment(assignment.id, SubmissionCreate(content="更新答案"), 3)
    teacher_notices = inbox(c, h, 2)["items"]
    assert len(teacher_notices) == 1
    assert (
        c.get(f"/learning/notifications/{teacher_notices[0]['id']}/detail", headers=h(2)).json()[
            "data"
        ]["target_path"]
        == f"/teacher/homework?assignment={assignment.id}"
    )
    assert inbox(c, h, 5)["total"] == 0
    manager.review_submission(submission.id, ReviewPayload(score=95, comment="很好"), 2)
    manager.review_submission(submission.id, ReviewPayload(score=95, comment="很好"), 2)
    notices = inbox(c, h, 3)["items"]
    assert len([n for n in notices if n["type"] == "review"]) == 1
    nid = next(n["id"] for n in notices if n["type"] == "review")
    assert (
        c.get(f"/learning/notifications/{nid}/detail", headers=h(3)).json()["data"]["target_path"]
        == f"/student/classroom?assignment={assignment.id}"
    )
    assert post(c, h, 5, scope="class", target_id=cls.id).status_code == 403
    assert post(c, h, 2, scope="class", target_id=cls.id).json()["data"]["recipient_count"] == 2
    assert post(c, h, 1, scope="course", target_id=cls.course_id).status_code == 200
    with f() as db:
        db.query(ClassEnrollment).filter_by(class_id=cls.id).delete()
        db.commit()
    assert inbox(c, h, 3)["total"] == 0
    assert c.get(f"/learning/notifications/{nid}/detail", headers=h(3)).status_code == 404


def test_event_idempotency_rollback_and_inactive_user(setup):
    c, f, h = setup
    with f() as db:
        for _ in range(2):
            emit(db, user_id=3, event_key="same-event", title="结果", content="结果")
        db.commit()
        emit(db, user_id=3, event_key="rolled-back", title="错误成功", content="不可见")
        db.rollback()
    assert inbox(c, h, 3)["total"] == 1
    with f() as db:
        db.get(User, 3).is_active = False
        db.commit()
    assert c.get("/learning/notifications/inbox", headers=h(3)).status_code == 401
    assert post(c, h, 1).json()["data"]["recipient_count"] == 1


def test_input_bounds(setup):
    c, f, h = setup
    for params in ({"page": 0}, {"size": 51}, {"size": 0}):
        assert (
            c.get("/learning/notifications/inbox", params=params, headers=h(3)).status_code == 422
        )
    assert post(c, h, 1, title=" ").status_code == 422
    assert post(c, h, 1, scope="class", target_id=999).status_code == 422


def test_existing_course_question_and_reply_loop(setup):
    from services.teacher_service.app.schemas.teacher import DiscussionCreate, DiscussionReplyCreate

    c, f, h = setup
    manager = TeacherManager()
    cls = manager.create_class(
        ClassCreate(name="课程提问班", subject="数学", teacher_name="老师"), 2
    )
    manager.enroll_student(cls.id, 3, 2)
    topic = manager.create_discussion(
        DiscussionCreate(class_id=cls.id, title="问题讨论", content="如何理解递归？"), 3, "student"
    )
    notice = next(n for n in inbox(c, h, 2)["items"] if n["related_type"] == "discussion")
    detail = c.get(f"/learning/notifications/{notice['id']}/detail", headers=h(2)).json()["data"]
    assert detail["discussion"]["id"] == topic.id
    assert detail["target_path"] is None
    manager.reply_discussion(
        topic.id, DiscussionReplyCreate(content="先明确终止条件"), 2, "teacher"
    )
    notice = next(n for n in inbox(c, h, 3)["items"] if n["related_type"] == "discussion")
    detail = c.get(f"/learning/notifications/{notice['id']}/detail", headers=h(3)).json()["data"]
    assert detail["discussion"]["replies"][0]["content"] == "先明确终止条件"
    assert inbox(c, h, 4)["total"] == 0
    assert inbox(c, h, 5)["total"] == 0


def test_large_publication_fails_atomically(setup):
    c, f, h = setup
    with f() as db:
        db.bulk_insert_mappings(
            User,
            [
                dict(username=f"fanout-{n}", password_hash="x", role="student", is_active=True)
                for n in range(5000)
            ],
        )
        db.commit()
    response = post(c, h, 1)
    assert response.status_code == 422
    with f() as db:
        assert db.query(Notification).count() == 0


def test_concurrent_replay_creates_one_durable_notification(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine = create_engine(
        f"sqlite:///{tmp_path / 'notification-concurrent.sqlite'}", connect_args={"timeout": 30}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(User(id=1, username="concurrent-notice", password_hash="x", role="student"))
        db.commit()
    barrier = Barrier(6)

    def deliver(_):
        barrier.wait(timeout=10)
        with factory() as db:
            emit(
                db,
                user_id=1,
                event_key="concurrent-event",
                title="事务通知",
                content="重复投递应当只保存一次",
            )
            db.commit()

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(deliver, range(6)))
    with factory() as db:
        assert (
            db.query(Notification).filter_by(user_id=1, event_key="concurrent-event").count() == 1
        )
    engine.dispose()
