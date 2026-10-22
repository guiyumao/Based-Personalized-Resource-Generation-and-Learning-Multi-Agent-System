"""Live HTTP acceptance for check-ins against the running teacher service.

Creates two temporary accounts in the configured database, drives the real
student/teacher flow over HTTP, verifies persistence and then removes every
row it created. Requires the service on 127.0.0.1:8005 and the user service on
127.0.0.1:8001.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx

from common.db.session import SessionLocal
from common.models.checkin import (
    AttendanceRecord,
    AttendanceSession,
    CheckinAuditLog,
    CheckinSubmissionRevision,
    CheckinTask,
    CheckinTaskSubmission,
    ClassScheduleException,
    ClassSession,
    PlatformDailyCheckin,
)
from common.models.learning import ClassEnrollment, Classroom, Course, Notification, User
from common.security.auth import hash_password

USER_BASE = "http://127.0.0.1:8001"
TEACHER_BASE = "http://127.0.0.1:8005"
PASSWORD = "Checkin-live-2026"


def login(client: httpx.Client, username: str) -> str:
    response = client.post(
        f"{USER_BASE}/users/login", json={"username": username, "password": PASSWORD}
    )
    response.raise_for_status()
    return response.json()["access_token"]


def call(
    client: httpx.Client,
    token: str,
    method: str,
    path: str,
    *,
    json_body=None,
    expected: int = 200,
):
    response = client.request(
        method, TEACHER_BASE + path, json=json_body, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == expected, (path, response.status_code, response.text)
    payload = response.json()
    return payload.get("data", payload)


def main() -> None:
    suffix = uuid.uuid4().hex[:10]
    teacher_name = f"chk-teacher-{suffix}"
    student_name = f"chk-student-{suffix}"
    with SessionLocal() as db:
        teacher = User(
            username=teacher_name,
            password_hash=hash_password(PASSWORD),
            role="teacher",
            is_active=True,
        )
        student = User(
            username=student_name,
            password_hash=hash_password(PASSWORD),
            role="student",
            is_active=True,
        )
        db.add_all([teacher, student])
        db.commit()
        teacher_id, student_id = teacher.id, student.id

    results: dict[str, object] = {}
    class_id = course_id = task_id = submission_id = session_id = None
    try:
        with httpx.Client(timeout=30.0) as client:
            teacher_token = login(client, teacher_name)
            student_token = login(client, student_name)
            results["login"] = True

            before = call(client, student_token, "GET", "/learning/checkin/daily")
            first = call(
                client,
                student_token,
                "POST",
                "/learning/checkin/daily",
                json_body={"goal": "完成平台学习", "reflection": "状态良好"},
            )
            again = call(
                client,
                student_token,
                "POST",
                "/learning/checkin/daily",
                json_body={"goal": "重复提交"},
            )
            results["platform_checkin"] = {
                "before": before["total_days"],
                "after": first["total_days"],
                "same_record": first["today_checkin"]["id"] == again["today_checkin"]["id"],
                "one_per_day": again["total_days"] == 1,
                "no_class_needed": before["checked_in"] is False,
            }

            room = call(
                client,
                teacher_token,
                "POST",
                "/teacher/classes",
                json_body={
                    "name": f"打卡验收班{suffix}",
                    "subject": "数据结构",
                    "join_mode": "open",
                },
            )
            class_id = room["id"]
            plaza = call(client, student_token, "GET", "/learning/classrooms/plaza")
            plaza_card = next(item for item in plaza if item["id"] == class_id)
            results["plaza_visible"] = (
                plaza_card["join_mode"] == "open" and "invite_code" not in plaza_card
            )
            call(
                client,
                student_token,
                "POST",
                f"/learning/classrooms/{class_id}/join",
            )
            visible_classes = call(client, student_token, "GET", "/teacher/students/me/classes")
            results["join_visible"] = any(item["id"] == class_id for item in visible_classes)

            monday = date.today() - timedelta(days=date.today().weekday())
            session = call(
                client,
                teacher_token,
                "POST",
                f"/learning/classes/{class_id}/schedule",
                json_body={
                    "topic": "验收课程 · 图论",
                    "weekday": 1,
                    "start_time": "09:00",
                    "end_time": "10:00",
                    "week_start": monday.isoformat(),
                    "week_end": (monday + timedelta(days=27)).isoformat(),
                    "location": "线上",
                    "mode": "online",
                },
            )
            timetable = call(client, student_token, "GET", "/learning/schedule/me")
            results["schedule_synced"] = any(
                item["session_id"] == session["id"] for item in timetable["entries"]
            )
            call(
                client,
                teacher_token,
                "POST",
                f"/learning/classes/{class_id}/schedule/{session['id']}/exceptions",
                json_body={
                    "date": monday.isoformat(),
                    "kind": "cancel",
                    "reason": "验收停课",
                },
            )
            after_cancel = call(client, student_token, "GET", "/learning/schedule/me")
            results["cancel_removes_occurrence"] = all(
                item["session_id"] != session["id"] for item in after_cancel["entries"]
            )

            now = datetime.now(UTC)
            task = call(
                client,
                teacher_token,
                "POST",
                "/learning/checkin/manage/tasks",
                json_body={
                    "class_id": class_id,
                    "title": "二叉树遍历验收任务",
                    "goal": "掌握三种遍历",
                    "description": "完成练习并写总结",
                    "frequency": "once",
                    "start_at": (now - timedelta(hours=1)).isoformat(),
                    "end_at": (now + timedelta(days=1)).isoformat(),
                    "review_mode": "manual",
                },
            )
            task_id = task["id"]
            call(
                client, teacher_token, "POST", f"/learning/checkin/manage/tasks/{task_id}/publish"
            )
            student_tasks = call(client, student_token, "GET", "/learning/checkin/tasks")
            results["task_visible"] = any(item["id"] == task_id for item in student_tasks)
            submission = call(
                client,
                student_token,
                "POST",
                f"/learning/checkin/tasks/{task_id}/submit",
                json_body={"content": "完成前中后序遍历，附总结"},
            )
            submission_id = submission["id"]
            completion = call(
                client,
                teacher_token,
                "GET",
                f"/learning/checkin/manage/tasks/{task_id}/completion",
            )
            results["teacher_sees_submission"] = any(
                row["submission_id"] == submission_id for row in completion["rows"]
            )
            reviewed = call(
                client,
                teacher_token,
                "POST",
                f"/learning/checkin/manage/submissions/{submission_id}/review",
                json_body={"verdict": "approve", "comment": "遍历正确", "score": 96},
            )
            results["review_status"] = reviewed["status"]
            home = call(client, student_token, "GET", "/learning/checkin/home")
            results["student_feedback"] = any(
                item["id"] == submission_id for item in home["latest_feedback"]
            )
            call(
                client,
                student_token,
                "POST",
                f"/learning/checkin/tasks/{task_id}/submit",
                json_body={"content": "覆盖"},
                expected=409,
            )

            session = call(
                client,
                teacher_token,
                "POST",
                "/learning/checkin/manage/attendance",
                json_body={
                    "class_id": class_id,
                    "title": "现场签到验收",
                    "start_at": (now - timedelta(minutes=5)).isoformat(),
                    "end_at": (now + timedelta(minutes=30)).isoformat(),
                },
            )
            session_id = session["id"]
            checked = call(
                client,
                student_token,
                "POST",
                "/learning/checkin/attendance/checkin",
                json_body={"code": session["code"]},
            )
            results["attendance_status"] = checked["my_record"]["status"]
            again = call(
                client,
                student_token,
                "POST",
                "/learning/checkin/attendance/checkin",
                json_body={"code": session["code"]},
            )
            results["attendance_idempotent"] = again["my_record"]["id"] == checked["my_record"]["id"]
            call(
                client,
                teacher_token,
                "POST",
                f"/learning/checkin/manage/attendance/{session_id}/close",
            )
            call(
                client,
                student_token,
                "POST",
                "/learning/checkin/attendance/checkin",
                json_body={"code": session["code"]},
                expected=409,
            )
            results["closed_code_rejected"] = True

            inbox = call(client, student_token, "GET", "/learning/notifications/inbox?size=50")
            results["notified"] = any(
                "打卡任务已通过" in item["title"] for item in inbox["items"]
            )

        with SessionLocal() as db:
            course_id = (
                db.query(Classroom.course_id).filter(Classroom.id == class_id).scalar()
            )
            results["persisted_rows"] = {
                "task": db.query(CheckinTask).filter_by(id=task_id).count(),
                "submission": db.query(CheckinTaskSubmission).filter_by(id=submission_id).count(),
                "attendance": db.query(AttendanceRecord)
                .filter_by(session_id=session_id, student_user_id=student_id)
                .count(),
            }
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        with SessionLocal() as db:
            user_ids = [teacher_id, student_id]
            db.query(Notification).filter(
                (Notification.user_id.in_(user_ids)) | (Notification.sender_id.in_(user_ids))
            ).delete(synchronize_session=False)
            if session_id:
                db.query(AttendanceRecord).filter_by(session_id=session_id).delete(
                    synchronize_session=False
                )
                db.query(AttendanceSession).filter_by(id=session_id).delete(
                    synchronize_session=False
                )
            if task_id:
                submission_ids = [
                    row[0]
                    for row in db.query(CheckinTaskSubmission.id)
                    .filter_by(task_id=task_id)
                    .all()
                ]
                if submission_ids:
                    db.query(CheckinSubmissionRevision).filter(
                        CheckinSubmissionRevision.submission_id.in_(submission_ids)
                    ).delete(synchronize_session=False)
                db.query(CheckinTaskSubmission).filter_by(task_id=task_id).delete(
                    synchronize_session=False
                )
                db.query(CheckinTask).filter_by(id=task_id).delete(synchronize_session=False)
            db.query(CheckinAuditLog).filter(
                CheckinAuditLog.actor_user_id.in_(user_ids)
            ).delete(synchronize_session=False)
            db.query(PlatformDailyCheckin).filter(
                PlatformDailyCheckin.user_id.in_(user_ids)
            ).delete(synchronize_session=False)
            if class_id:
                db.query(ClassScheduleException).filter_by(class_id=class_id).delete(
                    synchronize_session=False
                )
                db.query(ClassSession).filter_by(class_id=class_id).delete(
                    synchronize_session=False
                )
                db.query(ClassEnrollment).filter_by(class_id=class_id).delete(
                    synchronize_session=False
                )
                db.query(Classroom).filter_by(id=class_id).delete(synchronize_session=False)
            if course_id:
                db.query(Course).filter_by(id=course_id).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
            db.commit()
        print("cleanup: temporary accounts and business rows removed")


if __name__ == "__main__":
    main()
