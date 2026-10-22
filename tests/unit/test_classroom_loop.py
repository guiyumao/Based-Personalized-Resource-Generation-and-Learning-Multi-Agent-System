"""Real HTTP/SQL cross-role loop, isolation, lifecycle and repeat-request checks."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.learning import AssignmentSubmission, ClassEnrollment, User
from common.security.auth import create_access_token, hash_password
from services.teacher_service.app.main import app


@pytest.fixture
def loop():
    ids = []
    with SessionLocal() as db:
        for role in ["teacher", "teacher", "student", "student"]:
            user = User(
                username="loop-" + uuid4().hex[:12],
                password_hash=hash_password("Loop-test-123"),
                role=role,
                is_active=True,
            )
            db.add(user)
            db.flush()
            ids.append(user.id)
        db.commit()
    client = TestClient(app)

    def req(index, method, path, data=None, status=200):
        response = client.request(
            method,
            "/teacher" + path,
            json=data,
            headers={"Authorization": "Bearer " + create_access_token(str(ids[index]))},
        )
        assert response.status_code == status, response.text
        return response.json().get("data")

    yield req, ids
    # Dedicated test database is discarded by the no-cost runner; no shared DB touched.
    client.close()


def test_cross_role_persisted_loop(loop):
    r, ids = loop
    c = r(0, "POST", "/classes", {"name": "业务闭环班", "subject": "数学"})
    assert c["invite_code"] and c["student_count"] == 0
    r(2, "POST", "/students/me/classes/lookup", {"invite_code": c["invite_code"]})
    r(2, "POST", "/students/me/classes/join", {"invite_code": c["invite_code"]})
    r(2, "POST", "/students/me/classes/join", {"invite_code": c["invite_code"]})
    assert r(0, "GET", f"/classes/{c['id']}/members")[0]["user_id"] == ids[2]
    assert r(2, "GET", "/students/me/classes")[0]["invite_code"] is None
    a = r(
        0,
        "POST",
        "/homework/assign",
        {"class_id": c["id"], "title": "闭环作业", "description": "请解答"},
    )
    assert any(x["id"] == a["id"] for x in r(2, "GET", "/students/me/homework"))
    assert not r(3, "GET", "/students/me/homework")
    s = r(2, "POST", f"/students/me/homework/{a['id']}/submit", {"content": "初稿"})
    again = r(2, "POST", f"/students/me/homework/{a['id']}/submit", {"content": "初稿"})
    assert again["id"] == s["id"] and not again["history"]
    updated = r(2, "POST", f"/students/me/homework/{a['id']}/submit", {"content": "最终答案"})
    assert updated["history"][0]["content"] == "初稿"
    assert r(0, "GET", f"/homework/{a['id']}/submissions")[0]["content"] == "最终答案"
    reviewed = r(0, "POST", f"/homework/{s['id']}/review", {"score": 93, "comment": "逻辑完整"})
    own = next(x for x in r(2, "GET", "/students/me/homework") if x["id"] == a["id"])[
        "my_submission"
    ]
    assert own == reviewed and own["score"] == 93 and own["teacher_comment"] == "逻辑完整"
    r(2, "POST", f"/students/me/homework/{a['id']}/submit", {"content": "覆盖成绩"}, 409)
    r(1, "GET", f"/classes/{c['id']}/members", status=403)
    r(1, "PATCH", f"/classes/{c['id']}", {"name": "越权班级", "subject": "数学"}, 404)
    r(1, "GET", f"/homework/{a['id']}/submissions", status=404)
    r(2, "POST", f"/homework/{s['id']}/review", {"score": 100, "comment": "越权"}, 403)
    r(3, "POST", f"/students/me/homework/{a['id']}/submit", {"content": "越权"}, 403)
    with SessionLocal() as db:
        assert (
            db.query(ClassEnrollment).filter_by(class_id=c["id"], student_user_id=ids[2]).count()
            == 1
        )
        row = db.get(AssignmentSubmission, s["id"])
        assert row.score == 93 and row.student_user_id == ids[2]
    analytics = r(0, "GET", f"/classes/{c['id']}/teaching-analytics")
    assert analytics["homework_average_score"] == 93 and analytics["homework_reviewed"] == 1


def test_invite_lifecycle_and_concurrent_join(loop):
    r, ids = loop
    c = r(0, "POST", "/classes", {"name": "邀请码测试班", "subject": "物理"})
    new = r(0, "POST", f"/classes/{c['id']}/invite")
    r(2, "POST", "/students/me/classes/join", {"invite_code": c["invite_code"]}, 404)
    r(2, "POST", "/students/me/classes/join", {"invite_code": "INVALID"}, 404)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: r(
                    2, "POST", "/students/me/classes/join", {"invite_code": new["invite_code"]}
                ),
                range(2),
            )
        )
    assert all(x["student_count"] == 1 for x in results)
    r(
        0,
        "PATCH",
        f"/classes/{c['id']}",
        {"name": "停用测试班", "subject": "物理", "status": "inactive"},
    )
    r(3, "POST", "/students/me/classes/join", {"invite_code": new["invite_code"]}, 409)
    r(0, "DELETE", f"/classes/{c['id']}/members/{ids[2]}")
    assert not r(2, "GET", "/students/me/classes")
    with SessionLocal() as db:
        assert db.query(ClassEnrollment).filter_by(class_id=c["id"]).count() == 0


def test_concurrent_submit_deadline_and_transaction_rollback(loop, monkeypatch):
    from common.models.learning import Assignment
    from services.teacher_service.app.schemas.teacher import HomeworkAssign
    from services.teacher_service.app.services.teacher_manager import TeacherManager

    r, ids = loop
    c = r(0, "POST", "/classes", {"name": "并发事务班", "subject": "数学"})
    r(2, "POST", "/students/me/classes/join", {"invite_code": c["invite_code"]})
    a = r(
        0,
        "POST",
        "/homework/assign",
        {"class_id": c["id"], "title": "并发作业", "description": "证明"},
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: r(
                    2, "POST", f"/students/me/homework/{a['id']}/submit", {"content": "同一答案"}
                ),
                range(2),
            )
        )
    assert results[0]["id"] == results[1]["id"]
    with SessionLocal() as db:
        assert db.query(AssignmentSubmission).filter_by(assignment_id=a["id"]).count() == 1
    expired = r(
        0,
        "POST",
        "/homework/assign",
        {
            "class_id": c["id"],
            "title": "截止作业",
            "description": "已过期",
            "due_at": "2020-01-01T08:00:00+08:00",
        },
    )
    r(2, "POST", f"/students/me/homework/{expired['id']}/submit", {"content": "过期答案"}, 409)

    def fail_emit(*args, **kwargs):
        raise RuntimeError("transaction verification")

    monkeypatch.setattr("services.teacher_service.app.services.teacher_manager.emit", fail_emit)
    with pytest.raises(RuntimeError, match="transaction verification"):
        TeacherManager().create_assignment(
            HomeworkAssign(class_id=c["id"], title="必须回滚", description="测试失败事务"), ids[0]
        )
    with SessionLocal() as db:
        assert db.query(Assignment).filter_by(class_id=c["id"], title="必须回滚").count() == 0


def test_scope_evidence_does_not_mix_unrelated_points_or_students(loop):
    from common.models.learning import (
        AnswerRecord,
        Exercise,
        KnowledgePoint,
        LearningPath,
        SystemSubject,
    )

    r, ids = loop
    subject = "学情测试科目-" + uuid4().hex[:8]
    c = r(0, "POST", "/classes", {"name": "学情隔离班", "subject": subject})
    r(2, "POST", "/students/me/classes/join", {"invite_code": c["invite_code"]})
    with SessionLocal() as db:
        catalog = SystemSubject(name=subject, description="隔离测试科目")
        db.add(catalog)
        db.flush()
        points = [
            KnowledgePoint(subject_id=catalog.id, name="本班知识点-" + uuid4().hex[:8]),
            KnowledgePoint(name="其他科目-" + uuid4().hex[:8]),
        ]
        db.add_all(points)
        db.flush()
        exercises = [
            Exercise(knowledge_point_id=p.id, type="short_answer", content="问题", answer="答案")
            for p in points
        ]
        db.add_all(exercises)
        db.flush()
        db.add_all(
            [
                AnswerRecord(
                    user_id=ids[2],
                    exercise_id=exercises[0].id,
                    user_answer="错误",
                    is_correct=False,
                ),
                AnswerRecord(
                    user_id=ids[2], exercise_id=exercises[1].id, user_answer="正确", is_correct=True
                ),
                AnswerRecord(
                    user_id=ids[3],
                    exercise_id=exercises[0].id,
                    user_answer="错误",
                    is_correct=False,
                ),
            ]
        )
        db.commit()
        point_name = points[0].name
    scope = {
        "class_id": c["id"],
        "knowledge_points": [point_name],
        "learning_direction": "本班教学方向",
        "courseware_title": "本班教师课件",
        "courseware_content": "真实课件正文",
    }
    r(0, "POST", "/teaching-scopes", dict(scope, student_user_id=ids[3]), 404)
    saved = r(0, "POST", "/teaching-scopes", scope)
    stats = r(0, "GET", f"/classes/{c['id']}/teaching-analytics")
    assert (
        stats["student_count"] == 1 and stats["total_answers"] == 1 and stats["total_mistakes"] == 1
    )
    assert stats["weak_knowledge_points"][0]["knowledge_point"] == point_name
    assert any(s["id"] == saved["id"] for s in r(2, "GET", "/students/me/teaching-scopes"))
    assert r(3, "GET", "/students/me/teaching-scopes") == []
    # A student joining after publication also gets the existing class scope/path.
    r(3, "POST", "/students/me/classes/join", {"invite_code": c["invite_code"]})
    with SessionLocal() as db:
        path = db.query(LearningPath).filter_by(user_id=ids[3], status="active").first()
        assert path.path_data_json["teacher_scope"]["id"] == saved["id"]
    r(0, "DELETE", f"/classes/{c['id']}/members/{ids[3]}")
    assert r(3, "GET", "/students/me/teaching-scopes") == []
    with SessionLocal() as db:
        assert not db.query(LearningPath).filter_by(user_id=ids[3], status="active").first()
