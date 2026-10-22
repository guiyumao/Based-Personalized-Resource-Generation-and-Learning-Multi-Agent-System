"""Classroom schedule: recurring sessions, conflicts, exceptions and isolation."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.learning import User
from common.security.auth import create_access_token, hash_password
from services.teacher_service.app.main import app


@pytest.fixture
def sched():
    ids = {}
    with SessionLocal() as db:
        for key, role in (
            ("teacher", "teacher"),
            ("teacher_b", "teacher"),
            ("student", "student"),
            ("student_b", "student"),
        ):
            user = User(
                username="sched-" + uuid4().hex[:12],
                password_hash=hash_password("Sched-test-123"),
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


def _monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _payload(weekday: int = 1, start: str = "09:00", end: str = "10:00", topic: str = "图论"):
    monday = _monday()
    return {
        "topic": topic,
        "weekday": weekday,
        "start_time": start,
        "end_time": end,
        "week_start": monday.isoformat(),
        "week_end": (monday + timedelta(days=27)).isoformat(),
        "location": "线上",
        "mode": "online",
    }


def test_schedule_sync_conflict_and_membership(sched):
    req, ids = sched
    room = req(
        "teacher",
        "POST",
        "/teacher/classes",
        {"name": "课程表验收班", "subject": "算法", "join_mode": "open"},
    )
    req("student", "POST", f"/learning/classrooms/{room['id']}/join")
    session = req(
        "teacher", "POST", f"/learning/classes/{room['id']}/schedule", _payload()
    )
    assert session["weekday"] == 1 and session["class_name"] == "课程表验收班"

    own = req("student", "GET", "/learning/schedule/me")
    entry = next(item for item in own["entries"] if item["session_id"] == session["id"])
    assert entry["topic"] == "图论" and entry["status"] == "normal"
    assert entry["date"] == _monday().isoformat()

    outsider = req("student_b", "GET", "/learning/schedule/me")
    assert all(item["session_id"] != session["id"] for item in outsider["entries"])

    req(
        "teacher",
        "POST",
        f"/learning/classes/{room['id']}/schedule",
        _payload(weekday=1, start="09:30", end="10:30", topic="冲突"),
        status=409,
    )
    other_room = req(
        "teacher",
        "POST",
        "/teacher/classes",
        {"name": "第二课堂", "subject": "算法", "join_mode": "open"},
    )
    req(
        "teacher",
        "POST",
        f"/learning/classes/{other_room['id']}/schedule",
        _payload(weekday=1, start="09:30", end="10:30", topic="跨课堂冲突"),
        status=409,
    )
    req(
        "teacher_b",
        "POST",
        f"/learning/classes/{room['id']}/schedule",
        _payload(weekday=2),
        status=403,
    )

    schedule = req("teacher", "GET", f"/learning/classes/{room['id']}/schedule")
    assert len(schedule["sessions"]) == 1


def test_cancel_and_reschedule_update_student_timetable(sched):
    req, ids = sched
    room = req(
        "teacher",
        "POST",
        "/teacher/classes",
        {"name": "调课验收班", "subject": "操作系统", "join_mode": "open"},
    )
    req("student", "POST", f"/learning/classrooms/{room['id']}/join")
    session = req(
        "teacher",
        "POST",
        f"/learning/classes/{room['id']}/schedule",
        _payload(weekday=1, start="08:00", end="09:00", topic="进程调度"),
    )
    monday = _monday()

    cancelled = req(
        "teacher",
        "POST",
        f"/learning/classes/{room['id']}/schedule/{session['id']}/exceptions",
        {"date": monday.isoformat(), "kind": "cancel", "reason": "教师出差"},
    )
    assert cancelled["kind"] == "cancel"
    own = req("student", "GET", "/learning/schedule/me")
    assert all(item["session_id"] != session["id"] for item in own["entries"])
    req(
        "teacher",
        "POST",
        f"/learning/classes/{room['id']}/schedule/{session['id']}/exceptions",
        {"date": monday.isoformat(), "kind": "cancel", "reason": "重复"},
        status=409,
    )
    req(
        "teacher",
        "DELETE",
        f"/learning/classes/{room['id']}/schedule/exceptions/{cancelled['id']}",
    )

    wednesday = monday + timedelta(days=2)
    moved = req(
        "teacher",
        "POST",
        f"/learning/classes/{room['id']}/schedule/{session['id']}/exceptions",
        {
            "date": monday.isoformat(),
            "kind": "reschedule",
            "new_date": wednesday.isoformat(),
            "new_start_time": "14:00",
            "new_end_time": "15:00",
            "reason": "临时调课",
        },
    )
    assert moved["new_date"] == wednesday.isoformat()
    own = req("student", "GET", "/learning/schedule/me")
    moved_entry = next(item for item in own["entries"] if item["session_id"] == session["id"])
    assert moved_entry["date"] == wednesday.isoformat()
    assert moved_entry["start_time"] == "14:00" and moved_entry["status"] == "rescheduled"

    notifications = req("student", "GET", "/learning/notifications/inbox?size=50")
    assert any("调课" in item["title"] for item in notifications["items"])

    second = req(
        "teacher",
        "POST",
        f"/learning/classes/{room['id']}/schedule",
        _payload(weekday=2, start="10:00", end="11:00", topic="补课源课程"),
    )
    friday = monday + timedelta(days=4)
    makeup = req(
        "teacher",
        "POST",
        f"/learning/classes/{room['id']}/schedule/{second['id']}/exceptions",
        {
            "date": (monday + timedelta(days=1)).isoformat(),
            "kind": "makeup",
            "new_date": friday.isoformat(),
            "new_start_time": "18:00",
            "new_end_time": "19:00",
            "reason": "补足实验课",
        },
    )
    assert makeup["kind"] == "makeup"
    own = req("student", "GET", "/learning/schedule/me")
    makeup_entry = next(item for item in own["entries"] if item["session_id"] == second["id"])
    assert makeup_entry["date"] == friday.isoformat() and makeup_entry["status"] == "makeup"

    req("student", "POST", f"/learning/classrooms/{room['id']}/leave")
    own = req("student", "GET", "/learning/schedule/me")
    assert all(item["session_id"] != session["id"] for item in own["entries"])

    req(
        "teacher_b",
        "DELETE",
        f"/learning/classes/{room['id']}/schedule/{session['id']}",
        status=403,
    )
