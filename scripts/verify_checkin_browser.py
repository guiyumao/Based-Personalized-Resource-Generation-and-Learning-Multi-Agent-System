"""Real browser acceptance for the check-in pages with temporary live data."""

import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.db.session import SessionLocal  # noqa: E402
from common.models.checkin import (  # noqa: E402
    AttendanceRecord,
    AttendanceSession,
    CheckinAuditLog,
    CheckinSubmissionRevision,
    CheckinTask,
    CheckinTaskSubmission,
    ClassScheduleException,
    ClassSession,
    PersonalSchedule,
    PlatformDailyCheckin,
)
from common.models.learning import ClassEnrollment, Classroom, Course, Notification, User  # noqa: E402
from common.security.auth import create_access_token, hash_password  # noqa: E402

PASSWORD = "Checkin-live-2026"
USER_BASE = "http://127.0.0.1:8001"
TEACHER_BASE = "http://127.0.0.1:8005"


def main() -> int:
    suffix = uuid4().hex[:10]
    out = Path(os.environ.get("CHECKIN_OUT", str(ROOT / "artifacts" / "checkin-20261022" / "browser")))
    out.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        teacher = User(
            username=f"chk-ui-teacher-{suffix}",
            password_hash=hash_password(PASSWORD),
            role="teacher",
            is_active=True,
        )
        student = User(
            username=f"chk-ui-student-{suffix}",
            password_hash=hash_password(PASSWORD),
            role="student",
            is_active=True,
        )
        db.add_all([teacher, student])
        db.commit()
        teacher_id, student_id = teacher.id, student.id
        teacher_auth = {
            "token": create_access_token(str(teacher_id)),
            "user": {"userId": teacher_id, "username": teacher.username, "role": "teacher"},
        }
        student_auth = {
            "token": create_access_token(str(student_id)),
            "user": {"userId": student_id, "username": student.username, "role": "student"},
        }

    class_id = course_id = task_id = session_id = None
    try:
        with httpx.Client(timeout=30.0) as client:
            teacher_token = teacher_auth["token"]
            student_token = student_auth["token"]
            headers_t = {"Authorization": f"Bearer {teacher_token}"}
            headers_s = {"Authorization": f"Bearer {student_token}"}
            room = client.post(
                f"{TEACHER_BASE}/teacher/classes",
                json={
                    "name": f"打卡界面验收班{suffix}",
                    "subject": "数据结构",
                    "join_mode": "open",
                    "description": "界面验收公开课堂",
                    "semester": "2026秋",
                    "capacity": 30,
                },
                headers=headers_t,
            ).json()["data"]
            class_id = room["id"]
            client.post(
                f"{TEACHER_BASE}/learning/classrooms/{class_id}/join",
                headers=headers_s,
            ).raise_for_status()
            monday = date.today() - timedelta(days=date.today().weekday())
            client.post(
                f"{TEACHER_BASE}/learning/classes/{class_id}/schedule",
                json={
                    "topic": "界面验收 · 图论",
                    "weekday": 1,
                    "start_time": "09:00",
                    "end_time": "10:00",
                    "week_start": monday.isoformat(),
                    "week_end": (monday + timedelta(days=27)).isoformat(),
                    "location": "线上",
                    "mode": "online",
                },
                headers=headers_t,
            ).raise_for_status()
            now = datetime.now(UTC)
            task = client.post(
                f"{TEACHER_BASE}/learning/checkin/manage/tasks",
                json={
                    "class_id": class_id,
                    "title": "界面验收 · 二叉树遍历",
                    "goal": "掌握前中后序遍历",
                    "description": "完成三道练习并提交总结",
                    "frequency": "once",
                    "start_at": (now - timedelta(hours=1)).isoformat(),
                    "end_at": (now + timedelta(days=1)).isoformat(),
                    "review_mode": "manual",
                },
                headers=headers_t,
            ).json()["data"]
            task_id = task["id"]
            client.post(
                f"{TEACHER_BASE}/learning/checkin/manage/tasks/{task_id}/publish",
                headers=headers_t,
            ).raise_for_status()
            submission = client.post(
                f"{TEACHER_BASE}/learning/checkin/tasks/{task_id}/submit",
                json={"content": "完成遍历练习并总结"},
                headers=headers_s,
            ).json()["data"]
            client.post(
                f"{TEACHER_BASE}/learning/checkin/manage/submissions/{submission['id']}/review",
                json={"verdict": "approve", "comment": "遍历顺序正确", "score": 95},
                headers=headers_t,
            ).raise_for_status()
            session = client.post(
                f"{TEACHER_BASE}/learning/checkin/manage/attendance",
                json={
                    "class_id": class_id,
                    "title": "界面验收现场签到",
                    "start_at": (now - timedelta(minutes=5)).isoformat(),
                    "end_at": (now + timedelta(minutes=30)).isoformat(),
                },
                headers=headers_t,
            ).json()["data"]
            session_id = session["id"]
            client.post(
                f"{TEACHER_BASE}/learning/checkin/attendance/checkin",
                json={"code": session["code"]},
                headers=headers_s,
            ).raise_for_status()

        env = os.environ.copy()
        env["CHECKIN_TEACHER_AUTH"] = json.dumps(teacher_auth)
        env["CHECKIN_STUDENT_AUTH"] = json.dumps(student_auth)
        env["CHECKIN_CLASS_NAME"] = room["name"]
        env["CHECKIN_STUDENT_NAME"] = student_auth["user"]["username"]
        env["CHECKIN_OUT"] = str(out)
        result = subprocess.run(
            ["node", os.environ.get("CHECKIN_E2E_SCRIPT", "tests/e2e/run-checkin-pages.mjs")],
            cwd=ROOT,
            env=env,
        )
        return result.returncode
    finally:
        with SessionLocal() as db:
            user_ids = [teacher_id, student_id]
            db.query(PersonalSchedule).filter(PersonalSchedule.user_id.in_(user_ids)).delete(synchronize_session=False)
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
                ids = [
                    row[0]
                    for row in db.query(CheckinTaskSubmission.id).filter_by(task_id=task_id).all()
                ]
                if ids:
                    db.query(CheckinSubmissionRevision).filter(
                        CheckinSubmissionRevision.submission_id.in_(ids)
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
            if class_id:
                course_id = (
                    db.query(Course.id)
                    .filter(Course.title == f"打卡界面验收班{suffix}")
                    .scalar()
                )
                if course_id:
                    db.query(Course).filter_by(id=course_id).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
            db.commit()
        print("cleanup: temporary UI accounts and business rows removed")


if __name__ == "__main__":
    raise SystemExit(main())
