"""Cross-role check-in, teacher task and classroom attendance acceptance tests.

Everything here runs against the real FastAPI app and the isolated pytest
database; there is no mocked business response.
"""

from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.checkin import (
    AttendanceRecord,
    AttendanceSession,
    CheckinAuditLog,
    CheckinTaskSubmission,
    PlatformDailyCheckin,
)
from common.models.learning import ClassEnrollment, User
from common.security.auth import create_access_token, hash_password
from services.teacher_service.app.main import app
from services.teacher_service.app.services.checkin_manager import _period_due, _task_periods

TZ = ZoneInfo("Asia/Shanghai")


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


@pytest.fixture
def checkin():
    ids: dict[str, int] = {}
    with SessionLocal() as db:
        for key, role in (
            ("teacher", "teacher"),
            ("teacher_b", "teacher"),
            ("student", "student"),
            ("student_b", "student"),
            ("student_c", "student"),
        ):
            user = User(
                username="checkin-" + uuid4().hex[:12],
                password_hash=hash_password("Checkin-test-123"),
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
            "/learning/checkin" + path,
            json=data,
            headers={"Authorization": "Bearer " + create_access_token(str(ids[who]))},
        )
        assert response.status_code == status, response.text
        return response.json().get("data")

    def teacher_req(who, method, path, data=None, status=200):
        response = client.request(
            method,
            path,
            json=data,
            headers={"Authorization": "Bearer " + create_access_token(str(ids[who]))},
        )
        assert response.status_code == status, response.text
        return response.json().get("data")

    yield req, teacher_req, ids
    client.close()


def _make_class(teacher_req, student_req, ids, name="打卡验收班"):
    room = teacher_req("teacher", "POST", "/teacher/classes", {"name": name, "subject": "数据结构"})
    for who in ("student", "student_b"):
        teacher_req(
            who,
            "POST",
            "/teacher/students/me/classes/join",
            {"invite_code": room["invite_code"]},
        )
    return room


def test_task_publish_submit_review_and_isolation(checkin):
    req, teacher_req, ids = checkin
    room = _make_class(teacher_req, req, ids)
    now = datetime.now(UTC)
    task = teacher_req(
        "teacher",
        "POST",
        "/learning/checkin/manage/tasks",
        {
            "class_id": room["id"],
            "title": "二叉树遍历练习",
            "goal": "掌握前中后序遍历",
            "description": "完成三道遍历题并写总结",
            "frequency": "once",
            "start_at": _iso(now - timedelta(hours=1)),
            "end_at": _iso(now + timedelta(days=1)),
            "review_mode": "manual",
        },
    )
    assert task["status"] == "draft"
    assert not req("student", "GET", "/tasks")
    published = teacher_req(
        "teacher", "POST", f"/learning/checkin/manage/tasks/{task['id']}/publish"
    )
    assert published["status"] == "published"

    visible = req("student", "GET", "/tasks")
    mine = next(item for item in visible if item["id"] == task["id"])
    assert mine["my_state"] in ("pending", "not_started")
    assert mine["can_submit"] is True
    assert mine["student_count"] == 2

    detail = req("student", "GET", f"/tasks/{task['id']}")
    assert detail["teacher_name"] and detail["periods"]

    first = req(
        "student",
        "POST",
        f"/tasks/{task['id']}/submit",
        {"content": "已完成前中后序遍历"},
    )
    assert first["status"] == "submitted"
    repeat = req(
        "student",
        "POST",
        f"/tasks/{task['id']}/submit",
        {"content": "已完成前中后序遍历"},
    )
    assert repeat["id"] == first["id"] and repeat["version"] == 1

    revised = req(
        "student",
        "POST",
        f"/tasks/{task['id']}/submit",
        {"content": "补充了层序遍历"},
    )
    assert revised["version"] == 2 and revised["history"][0]["content"] == "已完成前中后序遍历"

    completion = teacher_req(
        "teacher", "GET", f"/learning/checkin/manage/tasks/{task['id']}/completion"
    )
    row = next(item for item in completion["rows"] if item["student_user_id"] == ids["student"])
    assert row["state"] == "pending_review" and row["submission_id"] == first["id"]

    reviewed = teacher_req(
        "teacher",
        "POST",
        f"/learning/checkin/manage/submissions/{first['id']}/review",
        {"verdict": "approve", "comment": "遍历顺序正确", "score": 95},
    )
    assert reviewed["status"] == "approved" and reviewed["score"] == 95

    home = req("student", "GET", "/home")
    assert any(item["id"] == first["id"] for item in home["latest_feedback"])
    assert home["due_today"] == 0 and home["completed_today"] == 1
    approved = next(item for item in req("student", "GET", "/tasks") if item["id"] == task["id"])
    assert approved["my_state"] == "approved" and approved["can_submit"] is False

    req(
        "student",
        "POST",
        f"/tasks/{task['id']}/submit",
        {"content": "覆盖已通过的内容"},
        status=409,
    )

    teacher_req(
        "teacher_b",
        "GET",
        f"/learning/checkin/manage/tasks/{task['id']}/completion",
        status=403,
    )
    teacher_req("teacher_b", "GET", "/learning/checkin/manage/tasks", status=200)
    assert not req("student_c", "GET", "/tasks")
    req(
        "student_c",
        "POST",
        f"/tasks/{task['id']}/submit",
        {"content": "非本班学生"},
        status=403,
    )

    notifications = teacher_req("teacher", "GET", "/learning/notifications/inbox?size=50")["items"]
    assert any(item["title"].startswith("学生提交打卡任务") for item in notifications)
    student_notifications = teacher_req(
        "student", "GET", "/learning/notifications/inbox?size=50"
    )["items"]
    assert any("打卡任务已通过" in item["title"] for item in student_notifications)


def test_attendance_lifecycle_code_late_absence_and_duplicates(checkin):
    req, teacher_req, ids = checkin
    room = _make_class(teacher_req, req, ids, name="课堂签到验收班")
    now = datetime.now(UTC)
    session = teacher_req(
        "teacher",
        "POST",
        "/learning/checkin/manage/attendance",
        {
            "class_id": room["id"],
            "title": "第 3 次课签到",
            "start_at": _iso(now - timedelta(minutes=10)),
            "end_at": _iso(now + timedelta(minutes=30)),
            "late_after_at": _iso(now + timedelta(minutes=5)),
        },
    )
    assert session["status"] == "open" and len(session["code"]) == 6 and session["token"]

    available = req("student", "GET", "/attendance")
    assert any(item["id"] == session["id"] for item in available)

    checked = req("student", "POST", "/attendance/checkin", {"code": session["code"]})
    assert checked["my_record"]["status"] == "present"
    same = req("student", "POST", "/attendance/checkin", {"code": session["code"]})
    assert same["my_record"]["id"] == checked["my_record"]["id"]

    req("student_c", "POST", "/attendance/checkin", {"code": session["code"]}, status=403)
    req("student", "POST", "/attendance/checkin", {"code": "WRONG1"}, status=404)
    teacher_req(
        "teacher_b",
        "POST",
        f"/learning/checkin/manage/attendance/{session['id']}/close",
        status=403,
    )

    late_session = teacher_req(
        "teacher",
        "POST",
        "/learning/checkin/manage/attendance",
        {
            "class_id": room["id"],
            "title": "迟到判定签到",
            "start_at": _iso(now - timedelta(minutes=20)),
            "end_at": _iso(now + timedelta(minutes=20)),
            "late_after_at": _iso(now - timedelta(minutes=5)),
        },
    )
    late = req("student_b", "POST", "/attendance/checkin", {"token": late_session["token"]})
    assert late["my_record"]["status"] == "late"

    closed = teacher_req(
        "teacher", "POST", f"/learning/checkin/manage/attendance/{session['id']}/close"
    )
    assert closed["status"] == "closed"
    live = teacher_req(
        "teacher", "GET", f"/learning/checkin/manage/attendance/{session['id']}/live"
    )
    rows = {row["student_user_id"]: row for row in live["rows"]}
    assert rows[ids["student"]]["status"] == "present"
    assert rows[ids["student_b"]]["status"] == "absent"
    assert rows[ids["student_b"]]["note"] == "签到结束未签到"

    req("student", "POST", "/attendance/checkin", {"code": session["code"]}, status=409)

    teacher_req(
        "teacher",
        "POST",
        f"/learning/checkin/manage/attendance/{session['id']}/students/{ids['student_b']}",
        {"status": "leave", "reason": "病假已提交证明", "note": "病假"},
    )
    with SessionLocal() as db:
        rows = db.query(AttendanceRecord).filter_by(session_id=session["id"]).all()
        assert len(rows) == 2
        target = next(row for row in rows if row.student_user_id == ids["student_b"])
        assert target.status == "leave" and target.source == "manual"
        audit = (
            db.query(CheckinAuditLog)
            .filter_by(action="attendance.manual_update", target_id=target.id)
            .first()
        )
        assert audit is not None and audit.reason == "病假已提交证明"
        assert (
            db.query(AttendanceSession).filter_by(id=session["id"]).one().status == "closed"
        )


def test_platform_daily_checkin_is_one_per_day_and_independent(checkin):
    req, teacher_req, ids = checkin
    today = datetime.now(TZ).date()
    status = req("student_c", "GET", "/daily")
    assert status["checked_in"] is False and status["total_days"] == 0

    first = req(
        "student_c",
        "POST",
        "/daily",
        {"goal": "完成算法练习", "reflection": "状态不错"},
    )
    assert first["checked_in"] is True
    assert first["total_days"] == 1 and first["current_streak"] == 1
    assert first["today_checkin"]["goal"] == "完成算法练习"

    again = req("student_c", "POST", "/daily", {})
    assert again["checked_in"] is True
    assert again["today_checkin"]["id"] == first["today_checkin"]["id"]
    assert again["total_days"] == 1
    assert again["today_checkin"]["goal"] == "完成算法练习"

    history = req("student_c", "GET", "/daily/history")
    assert len(history) == 1
    calendar = req("student_c", "GET", f"/daily/calendar?month={today.strftime('%Y-%m')}")
    assert [item["date"] for item in calendar["days"]] == [today.isoformat()]
    assert calendar["streak"] == 1

    other = req("student", "GET", "/daily")
    assert other["total_days"] == 0 and other["checked_in"] is False
    teacher_req("teacher", "GET", "/learning/checkin/daily", status=403)

    home = req("student_c", "GET", "/home")
    assert home["today_checked_in"] is True and home["total_days"] == 1
    with SessionLocal() as db:
        assert (
            db.query(PlatformDailyCheckin).filter_by(user_id=ids["student_c"]).count() == 1
        )


def test_repeating_task_periods_and_auto_review(checkin):
    req, teacher_req, ids = checkin
    room = _make_class(teacher_req, req, ids, name="每日打卡验收班")
    today = datetime.now(TZ).date()
    yesterday = today - timedelta(days=1)
    task = teacher_req(
        "teacher",
        "POST",
        "/learning/checkin/manage/tasks",
        {
            "class_id": room["id"],
            "title": "每日算法练习",
            "frequency": "daily",
            "start_at": _iso(datetime.combine(yesterday, datetime.min.time(), tzinfo=TZ)),
            "end_at": _iso(datetime.combine(today, datetime.max.time(), tzinfo=TZ)),
            "due_time": "23:59",
            "allow_late": True,
            "review_mode": "auto",
        },
    )
    teacher_req("teacher", "POST", f"/learning/checkin/manage/tasks/{task['id']}/publish")
    for key in (yesterday.isoformat(), today.isoformat()):
        result = req(
            "student",
            "POST",
            f"/tasks/{task['id']}/submit",
            {"content": f"{key} 完成练习", "period_key": key},
        )
        assert result["status"] == "approved"
        assert result["period_key"] == key
    with SessionLocal() as db:
        assert (
            db.query(CheckinTaskSubmission)
            .filter_by(task_id=task["id"], student_user_id=ids["student"])
            .count()
            == 2
        )
    completion = teacher_req(
        "teacher",
        "GET",
        f"/learning/checkin/manage/tasks/{task['id']}/completion"
        f"?period={yesterday.isoformat()}",
    )
    assert completion["period_key"] == yesterday.isoformat()
    row = next(item for item in completion["rows"] if item["student_user_id"] == ids["student"])
    assert row["state"] == "approved"
    today_row = next(
        item
        for item in teacher_req(
            "teacher",
            "GET",
            f"/learning/checkin/manage/tasks/{task['id']}/completion?period={today.isoformat()}",
        )["rows"]
        if item["student_user_id"] == ids["student"]
    )
    assert today_row["state"] == "approved"

    home = req("student", "GET", "/home")
    # Teacher task approvals are not platform check-ins and must not inflate streak.
    assert home["total_days"] == 0 and home["today_checked_in"] is False
    stats = teacher_req("teacher", "GET", "/learning/checkin/overview")
    assert stats["class_count"] >= 1
    assert stats["active_task_count"] >= 1

    # Reminder fan-out is idempotent and never targets approved students.
    other = teacher_req(
        "teacher",
        "GET",
        f"/learning/checkin/manage/tasks/{task['id']}/completion?period={today.isoformat()}",
    )
    pending_ids = [row["student_user_id"] for row in other["rows"] if row["state"] != "approved"]
    if pending_ids:
        first = teacher_req(
            "teacher",
            "POST",
            f"/learning/checkin/manage/tasks/{task['id']}/remind",
            {"period_key": today.isoformat()},
        )
        second = teacher_req(
            "teacher",
            "POST",
            f"/learning/checkin/manage/tasks/{task['id']}/remind",
            {"period_key": today.isoformat()},
        )
        assert first["reminded"] == second["reminded"] == len(pending_ids)


def test_state_persists_across_new_client_and_concurrent_attendance(checkin):
    req, teacher_req, ids = checkin
    room = _make_class(teacher_req, req, ids, name="持久化验收班")
    now = datetime.now(UTC)
    session = teacher_req(
        "teacher",
        "POST",
        "/learning/checkin/manage/attendance",
        {
            "class_id": room["id"],
            "title": "并发签到",
            "start_at": _iso(now - timedelta(minutes=5)),
            "end_at": _iso(now + timedelta(minutes=10)),
        },
    )
    barrier = Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait()
            req("student", "POST", "/attendance/checkin", {"code": session["code"]})
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    with SessionLocal() as db:
        assert (
            db.query(AttendanceRecord)
            .filter_by(session_id=session["id"], student_user_id=ids["student"])
            .count()
            == 1
        )

    second_client = TestClient(app)
    try:
        response = second_client.get(
            "/learning/checkin/attendance",
            headers={"Authorization": "Bearer " + create_access_token(str(ids["student"]))},
        )
        assert response.status_code == 200
        assert any(item["id"] == session["id"] for item in response.json()["data"])
    finally:
        second_client.close()


def test_weekly_schedule_and_period_deadline_use_school_timezone():
    today = date(2026, 10, 22)  # Thursday
    due = _period_due(today, "23:59")
    assert due == datetime(2026, 10, 22, 15, 59)  # 23:59 Asia/Shanghai -> UTC

    class FakeTask:
        frequency = "weekly"
        weekly_days = [1, 4]
        start_at = datetime(2026, 10, 20, 0, 0)
        end_at = datetime(2026, 10, 27, 15, 59)
        due_time = "20:00"

    periods = _task_periods(FakeTask())
    assert [key for key, _ in periods] == [
        "2026-10-22",  # Thursday
        "2026-10-26",  # Monday
    ]
    assert all(item[1].tzinfo is None for item in periods)


def test_platform_checkin_is_private_per_student(checkin):
    req, teacher_req, ids = checkin
    created = req(
        "student",
        "POST",
        "/daily",
        {"goal": "操作系统进程调度", "reflection": "复习完成"},
    )
    assert created["today_checkin"]["id"]
    other = req("student_b", "GET", "/daily")
    assert other["checked_in"] is False and other["total_days"] == 0
    with SessionLocal() as db:
        own = db.query(PlatformDailyCheckin).filter_by(id=created["today_checkin"]["id"]).one()
        assert own.user_id == ids["student"]
        assert db.query(PlatformDailyCheckin).filter_by(user_id=ids["student_b"]).count() == 0
    teacher_req("teacher", "GET", "/learning/checkin/daily", status=403)
    teacher_req("teacher", "GET", "/learning/checkin/daily/history", status=403)


def test_concurrent_platform_checkin_creates_one_row(checkin):
    req, _teacher_req, ids = checkin
    barrier = Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait()
            req("student_b", "POST", "/daily", {"goal": "并发打卡"})
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    status = req("student_b", "GET", "/daily")
    assert status["total_days"] == 1 and status["checked_in"] is True
    with SessionLocal() as db:
        assert (
            db.query(PlatformDailyCheckin).filter_by(user_id=ids["student_b"]).count() == 1
        )


def test_enrollment_is_required_after_leaving_class(checkin):
    req, teacher_req, ids = checkin
    room = _make_class(teacher_req, req, ids, name="退班验收班")
    now = datetime.now(UTC)
    task = teacher_req(
        "teacher",
        "POST",
        "/learning/checkin/manage/tasks",
        {
            "class_id": room["id"],
            "title": "退班后不可提交",
            "start_at": _iso(now - timedelta(hours=1)),
            "end_at": _iso(now + timedelta(days=1)),
        },
    )
    teacher_req("teacher", "POST", f"/learning/checkin/manage/tasks/{task['id']}/publish")
    teacher_req(
        "teacher", "DELETE", f"/teacher/classes/{room['id']}/members/{ids['student']}"
    )
    with SessionLocal() as db:
        assert (
            db.query(ClassEnrollment)
            .filter_by(class_id=room["id"], student_user_id=ids["student"])
            .count()
            == 0
        )
    req(
        "student",
        "POST",
        f"/tasks/{task['id']}/submit",
        {"content": "退班后提交"},
        status=403,
    )
    assert not req("student", "GET", "/tasks")
