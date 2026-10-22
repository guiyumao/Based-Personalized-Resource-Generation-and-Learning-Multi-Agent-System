"""Classroom plaza: student self-enrollment and invitation-code isolation."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.learning import ClassEnrollment, User
from common.security.auth import create_access_token, hash_password
from services.teacher_service.app.main import app


@pytest.fixture
def plaza():
    ids = {}
    with SessionLocal() as db:
        for key, role in (("teacher", "teacher"), ("teacher_b", "teacher"), ("student", "student"), ("student_b", "student")):
            user = User(
                username="plaza-" + uuid4().hex[:12],
                password_hash=hash_password("Plaza-test-123"),
                role=role,
                is_active=True,
            )
            db.add(user)
            db.flush()
            ids[key] = user.id
        db.commit()
    client = TestClient(app)

    def req(who, method, path, data=None, status=200):
        response = client.request(
            method,
            path,
            json=data,
            headers={"Authorization": "Bearer " + create_access_token(str(ids[who]))},
        )
        assert response.status_code == status, response.text
        return response.json().get("data")

    yield req, ids
    client.close()


def test_open_class_self_enrollment_and_invite_isolation(plaza):
    req, ids = plaza
    open_room = req(
        "teacher",
        "POST",
        "/teacher/classes",
        {"name": "公开选课班", "subject": "操作系统", "join_mode": "open"},
    )
    invite_room = req(
        "teacher",
        "POST",
        "/teacher/classes",
        {"name": "邀请制班级", "subject": "数据结构", "join_mode": "invite"},
    )
    assert open_room["join_mode"] == "open" and invite_room["join_mode"] == "invite"

    cards = req("student", "GET", "/learning/classrooms/plaza")
    open_card = next(item for item in cards if item["id"] == open_room["id"])
    invite_card = next(item for item in cards if item["id"] == invite_room["id"])
    assert invite_card["join_mode"] == "invite" and not invite_card["joined"]
    assert open_card["join_mode"] == "open" and not open_card["joined"]
    assert "invite_code" not in open_card
    assert open_card["course_title"] and open_card["student_count"] == 0

    joined = req("student", "POST", f"/learning/classrooms/{open_room['id']}/join")
    assert joined["student_count"] == 1 and joined["invite_code"] is None
    again = req("student", "POST", f"/learning/classrooms/{open_room['id']}/join")
    assert again["student_count"] == 1
    with SessionLocal() as db:
        assert (
            db.query(ClassEnrollment)
            .filter_by(class_id=open_room["id"], student_user_id=ids["student"])
            .count()
            == 1
        )
    cards = req("student", "GET", "/learning/classrooms/plaza")
    assert next(item for item in cards if item["id"] == open_room["id"])["joined"] is True
    assert next(item for item in cards if item["id"] == invite_room["id"])["joined"] is False

    req("student", "POST", f"/learning/classrooms/{invite_room['id']}/join", status=403)
    req(
        "student",
        "POST",
        "/teacher/students/me/classes/join",
        {"invite_code": invite_room["invite_code"]},
    )
    assert any(
        item["id"] == invite_room["id"] for item in req("student", "GET", "/teacher/students/me/classes")
    )

    filtered = req("student", "GET", "/learning/classrooms/plaza?query=公开选课")
    assert [item["id"] for item in filtered] == [open_room["id"]]
    by_subject = req("student", "GET", "/learning/classrooms/plaza?subject=数据结构")
    assert invite_room["id"] in [item["id"] for item in by_subject]
    assert open_room["id"] not in [item["id"] for item in by_subject]

    req("teacher_b", "PATCH", f"/teacher/classes/{open_room['id']}", {"name": "越权", "subject": "操作系统", "join_mode": "invite"}, status=404)
    req(
        "teacher",
        "PATCH",
        f"/teacher/classes/{open_room['id']}",
        {"name": "公开选课班", "subject": "操作系统", "join_mode": "invite"},
    )
    assert (
        next(item for item in req("student", "GET", "/learning/classrooms/plaza") if item["id"] == open_room["id"])["join_mode"]
        == "invite"
    )


def test_plaza_requires_student_role_and_hides_codes(plaza):
    req, _ids = plaza
    req("teacher", "GET", "/learning/classrooms/plaza", status=403)
    req("teacher", "POST", "/learning/classrooms/1/join", status=403)
    cards = req("student", "GET", "/learning/classrooms/plaza")
    assert all("invite_code" not in item for item in cards)


def test_capacity_leave_private_class_and_metadata(plaza):
    req, _ids = plaza
    room = req(
        "teacher",
        "POST",
        "/teacher/classes",
        {
            "name": "限额公开课堂",
            "subject": "Python",
            "join_mode": "open",
            "description": "面向零基础",
            "objective": "掌握语法与项目",
            "syllabus": "第1周 基础语法",
            "semester": "2026秋",
            "capacity": 1,
        },
    )
    assert room["description"] == "面向零基础" and room["capacity"] == 1
    card = next(
        item
        for item in req("student", "GET", "/learning/classrooms/plaza")
        if item["id"] == room["id"]
    )
    assert card["syllabus"] == "第1周 基础语法" and card["semester"] == "2026秋"

    detail = req("student", "GET", f"/learning/classrooms/{room['id']}")
    assert detail["objective"] == "掌握语法与项目" and detail["joined"] is False

    req("student", "POST", f"/learning/classrooms/{room['id']}/join")
    req("student_b", "POST", f"/learning/classrooms/{room['id']}/join", status=409)
    assert req("student", "GET", "/learning/classrooms/mine")
    left = req("student", "POST", f"/learning/classrooms/{room['id']}/leave")
    assert left["student_count"] == 0
    req("student_b", "POST", f"/learning/classrooms/{room['id']}/join")
    assert not any(
        item["id"] == room["id"] for item in req("student", "GET", "/learning/classrooms/mine")
    )

    private = req(
        "teacher",
        "POST",
        "/teacher/classes",
        {"name": "非公开课堂", "subject": "算法", "join_mode": "invite", "is_public": False},
    )
    assert private["id"] not in [
        item["id"] for item in req("student", "GET", "/learning/classrooms/plaza")
    ]
    req("student", "GET", f"/learning/classrooms/{private['id']}", status=403)

    req(
        "teacher",
        "PATCH",
        f"/teacher/classes/{room['id']}",
        {
            "name": "限额公开课堂",
            "subject": "Python",
            "join_mode": "open",
            "description": "已更新简介",
            "capacity": 0,
            "is_public": True,
        },
    )
    updated = next(
        item
        for item in req("student", "GET", "/learning/classrooms/plaza")
        if item["id"] == room["id"]
    )
    assert updated["description"] == "已更新简介" and updated["capacity"] == 0


def test_invite_search_private_class_join_and_timetable(plaza):
    req, ids = plaza
    room = req("teacher", "POST", "/teacher/classes", {
        "name": "邀请码搜索私密课堂", "subject": "算法", "join_mode": "invite",
        "is_public": False, "capacity": 1,
    })
    code = room["invite_code"]
    for query in ("", "邀请码搜索私密课堂", code[:8], "INVALID-CODE"):
        cards = req("student", "GET", f"/learning/classrooms/plaza?query={query}")
        assert all(c["id"] != room["id"] for c in cards)
    cards = req("student", "GET", f"/learning/classrooms/plaza?query=%20{code.lower()}%20&subject=其他学科")
    assert len(cards) == 1 and cards[0]["id"] == room["id"]
    assert cards[0]["invite_matched"] is True and cards[0]["joined"] is False
    assert "invite_code" not in cards[0]
    req("student", "POST", f"/learning/classrooms/{room['id']}/join", status=403)
    payload = {"invite_code": f" {code.lower()} "}
    first = req("student", "POST", "/teacher/students/me/classes/join", payload)
    again = req("student", "POST", "/teacher/students/me/classes/join", payload)
    assert first["student_count"] == again["student_count"] == 1
    cards = req("student", "GET", f"/learning/classrooms/plaza?query={code}")
    assert cards[0]["joined"] is True
    assert any(c["id"] == room["id"] for c in req("student", "GET", "/learning/classrooms/mine"))
    assert any(c["class_id"] == room["id"] for c in req("student", "GET", "/learning/schedule/me")["classrooms"])
    req("student_b", "POST", "/teacher/students/me/classes/join", payload, status=409)
    with SessionLocal() as db:
        assert db.query(ClassEnrollment).filter_by(class_id=room["id"], student_user_id=ids["student"]).count() == 1


def test_invite_search_rotation_and_inactive_class(plaza):
    req, _ = plaza
    room = req("teacher", "POST", "/teacher/classes", {
        "name": "轮换邀请码课堂", "subject": "算法", "join_mode": "invite", "is_public": False,
    })
    old_code = room["invite_code"]
    updated = req("teacher", "POST", f"/teacher/classes/{room['id']}/invite")
    new_code = updated["invite_code"]
    assert old_code != new_code
    assert not req("student", "GET", f"/learning/classrooms/plaza?query={old_code}")
    req("student", "POST", "/teacher/students/me/classes/join", {"invite_code": old_code}, status=404)
    assert req("student", "GET", f"/learning/classrooms/plaza?query={new_code}")[0]["invite_matched"]
    req("teacher", "PATCH", f"/teacher/classes/{room['id']}", {
        "name": room["name"], "subject": "算法", "join_mode": "invite", "is_public": False, "status": "inactive",
    })
    assert not req("student", "GET", f"/learning/classrooms/plaza?query={new_code}")
    req("student", "POST", "/teacher/students/me/classes/join", {"invite_code": new_code}, status=409)
