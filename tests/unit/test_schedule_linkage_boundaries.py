"""Cross-week timetable and exception conflict acceptance regressions."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.learning import User
from common.security.auth import create_access_token
from services.teacher_service.app.main import app


@pytest.fixture
def linkage():
    with SessionLocal() as db:
        users = [
            User(
                username=f"linkage-{uuid4().hex}",
                password_hash="disabled-test-login",
                role=role,
                is_active=True,
            )
            for role in ("teacher", "student", "student")
        ]
        db.add_all(users)
        db.commit()
        tokens = [create_access_token(str(user.id)) for user in users]
    with TestClient(app) as client:

        def request(who, method, path, data=None, status=200):
            response = client.request(
                method, path, json=data, headers={"Authorization": f"Bearer {tokens[who]}"}
            )
            assert response.status_code == status, response.text
            return response.json().get("data")

        room = request(
            0,
            "POST",
            "/teacher/classes",
            {
                "name": "跨周联动验收",
                "subject": "算法",
                "join_mode": "open",
            },
        )
        request(1, "POST", f"/learning/classrooms/{room['id']}/join")
        monday = date.today() - timedelta(days=date.today().weekday())
        yield request, room["id"], monday


def session(request, room_id, monday, weekday=1):
    return request(
        0,
        "POST",
        f"/learning/classes/{room_id}/schedule",
        {
            "topic": "跨周联动",
            "weekday": weekday,
            "start_time": "09:00",
            "end_time": "10:00",
            "week_start": monday.isoformat(),
            "week_end": (monday + timedelta(days=20)).isoformat(),
        },
    )


def test_rescheduled_class_appears_in_destination_week(linkage):
    req, room_id, monday = linkage
    item = session(req, room_id, monday)
    target = monday + timedelta(days=9)
    req(
        0,
        "POST",
        f"/learning/classes/{room_id}/schedule/{item['id']}/exceptions",
        {
            "date": monday.isoformat(),
            "kind": "reschedule",
            "new_date": target.isoformat(),
            "new_start_time": "14:00",
            "new_end_time": "15:00",
            "reason": "跨周调课验收",
        },
    )
    source = req(1, "GET", f"/learning/schedule/me?week_start={monday}")
    assert not any(e["session_id"] == item["id"] for e in source["entries"])
    inbox = req(1, "GET", "/learning/notifications/inbox?size=50")
    assert any("调课" in n["title"] for n in inbox["items"])
    destination = req(1, "GET", f"/learning/schedule/me?week_start={target}")
    assert any(
        e["session_id"] == item["id"]
        and e["date"] == target.isoformat()
        and e["status"] == "rescheduled"
        for e in destination["entries"]
    ), (
        "Student received reschedule notification but destination week lost the moved class",
        destination,
    )


def test_reschedule_conflict_includes_existing_adjustments(linkage):
    req, room_id, monday = linkage
    first = session(req, room_id, monday, weekday=1)
    second = session(req, room_id, monday, weekday=2)
    target = monday + timedelta(days=2)
    for item, offset in ((first, 0), (second, 1)):
        req(
            0,
            "POST",
            f"/learning/classes/{room_id}/schedule/{item['id']}/exceptions",
            {
                "date": (monday + timedelta(days=offset)).isoformat(),
                "kind": "reschedule",
                "new_date": target.isoformat(),
                "new_start_time": "14:00",
                "new_end_time": "15:00",
                "reason": "同教师同课堂调整冲突验收",
            },
            status=200 if offset == 0 else 409,
        )


def personal_payload(room_id, monday, **changes):
    return {
        "topic": "学生自排算法", "class_id": room_id, "weekday": 1,
        "start_time": "16:00", "end_time": "17:00",
        "week_start": monday.isoformat(), "week_end": (monday + timedelta(days=20)).isoformat(),
        **changes,
    }


def test_auto_import_without_teacher_schedule_and_personal_crud(linkage):
    req, room_id, monday = linkage
    data = req(1, "GET", "/learning/schedule/me")
    assert len(data["classrooms"]) == 1
    assert data["classrooms"][0]["class_id"] == room_id
    assert data["classrooms"][0]["scheduled"] is False and not data["entries"]
    created = req(1, "POST", "/learning/schedule/me/personal", personal_payload(room_id, monday))
    own = req(1, "GET", "/learning/schedule/me")
    assert own["classrooms"][0]["scheduled"] is True
    assert any(e["personal_id"] == created["id"] and e["source"] == "personal" for e in own["entries"])
    assert req(0, "GET", f"/learning/classes/{room_id}/schedule")["sessions"] == []
    req(2, "PUT", f"/learning/schedule/me/personal/{created['id']}", personal_payload(None, monday), status=403)
    req(2, "DELETE", f"/learning/schedule/me/personal/{created['id']}", status=403)
    assert not req(2, "GET", "/learning/schedule/me")["personal"]
    req(1, "PUT", f"/learning/schedule/me/personal/{created['id']}", personal_payload(room_id, monday, topic="学生已修改"))
    assert any(e["topic"] == "学生已修改" for e in req(1, "GET", "/learning/schedule/me")["entries"])
    req(1, "DELETE", f"/learning/schedule/me/personal/{created['id']}")
    assert not req(1, "GET", "/learning/schedule/me")["entries"]


def test_private_override_hide_restore_and_other_students_unaffected(linkage):
    req, room_id, monday = linkage
    req(2, "POST", f"/learning/classrooms/{room_id}/join")
    official = session(req, room_id, monday)
    payload = personal_payload(room_id, monday, source_session_id=official["id"],
                               source_date=monday.isoformat(), week_end=monday.isoformat())
    created = req(1, "POST", "/learning/schedule/me/personal", payload)
    own = req(1, "GET", "/learning/schedule/me")["entries"]
    assert len(own) == 1 and own[0]["start_time"] == "16:00"
    other = req(2, "GET", "/learning/schedule/me")["entries"]
    assert len(other) == 1 and other[0]["start_time"] == "09:00"
    teacher = req(0, "GET", f"/learning/classes/{room_id}/schedule")["sessions"][0]
    assert teacher["start_time"] == "09:00"
    req(1, "POST", "/learning/schedule/me/personal", payload, status=409)
    req(1, "PUT", f"/learning/schedule/me/personal/{created['id']}", {**payload, "hidden": True})
    assert not req(1, "GET", "/learning/schedule/me")["entries"]
    req(1, "DELETE", f"/learning/schedule/me/personal/{created['id']}")
    assert req(1, "GET", "/learning/schedule/me")["entries"][0]["start_time"] == "09:00"


def test_leave_class_removes_bound_entries_but_keeps_private_course(linkage):
    req, room_id, monday = linkage
    req(1, "POST", "/learning/schedule/me/personal", personal_payload(room_id, monday))
    req(1, "POST", "/learning/schedule/me/personal", personal_payload(None, monday, topic="独立自习"))
    req(1, "POST", f"/learning/classrooms/{room_id}/leave")
    data = req(1, "GET", "/learning/schedule/me")
    assert not data["classrooms"]
    assert [e["topic"] for e in data["entries"]] == ["独立自习"]
    req(1, "POST", "/learning/schedule/me/personal", personal_payload(room_id, monday), status=403)
    req(1, "POST", f"/learning/classrooms/{room_id}/join")
    assert len(req(1, "GET", "/learning/schedule/me")["entries"]) == 2


def test_personal_invalid_dates_and_roles_rejected(linkage):
    req, room_id, monday = linkage
    req(0, "POST", "/learning/schedule/me/personal", personal_payload(None, monday), status=403)
    req(1, "POST", "/learning/schedule/me/personal", personal_payload(room_id, monday, week_start="2026-02-30"), status=422)
    req(1, "POST", "/learning/schedule/me/personal", personal_payload(room_id, monday, start_time="18:00"), status=422)
    req(1, "POST", "/learning/schedule/me/personal", personal_payload(room_id, monday, week_end=monday.isoformat(), weekday=2), status=422)
