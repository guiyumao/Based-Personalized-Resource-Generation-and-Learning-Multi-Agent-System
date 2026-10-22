"""Current 5175 verification with private disposable accounts; no real broadcasts."""

# ruff: noqa: E402 -- load the verified service environment before application configuration
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (
    sys.argv[1] if len(sys.argv) > 1 else "artifacts/notifications-20261021/current-browser"
)
OUT.mkdir(parents=True, exist_ok=False)
# Use the authenticated service's existing configuration without printing credentials.
process = next(
    p
    for p in psutil.process_iter(["cmdline"])
    if "services.teacher_service.app.main:app" in (p.info["cmdline"] or [])
)
env = process.environ()
os.environ.update(env)
os.environ["APP_LOAD_DOTENV"] = "false"
sys.path.insert(0, str(ROOT))
from common.db.session import SessionLocal
from common.models.learning import (
    Assignment,
    AssignmentSubmission,
    ClassEnrollment,
    Classroom,
    Course,
    DiscussionReply,
    DiscussionThread,
    Notification,
    NotificationDispatch,
    User,
    UserProfile,
)
from common.security.auth import create_access_token

suffix = uuid.uuid4().hex[:10]
ids = []
with SessionLocal() as db:
    for role in ["admin", "teacher", "student", "student"]:
        u = User(
            username=f"notice-verify-{suffix}-{len(ids)}",
            password_hash="disabled-verification-login",
            role=role,
            is_active=True,
        )
        db.add(u)
        db.flush()
        ids.append(u.id)
    db.commit()
    auth = {
        role: {
            "token": create_access_token(str(uid)),
            "user": {"userId": uid, "username": f"notice-verify-{suffix}-{index}", "role": role},
        }
        for index, (uid, role) in enumerate(
            zip(ids, ["admin", "teacher", "student", "outsider"], strict=True)
        )
    }
    # Outsider is still a student in the durable database.
    auth["outsider"]["user"]["role"] = "student"
(OUT / "auth.json").write_text(json.dumps(auth), encoding="utf-8")
code = 1
try:
    result = subprocess.run(["node", "tests/e2e/run-notifications-current.mjs", str(OUT)])
    code = result.returncode
finally:
    with SessionLocal() as db:
        class_ids = [
            r[0] for r in db.query(Classroom.id).filter(Classroom.teacher_user_id == ids[1])
        ]
        course_ids = [r[0] for r in db.query(Course.id).filter(Course.teacher_user_id == ids[1])]
        assignment_ids = [
            r[0] for r in db.query(Assignment.id).filter(Assignment.teacher_user_id == ids[1])
        ]
        threads = [
            r[0]
            for r in db.query(DiscussionThread.id).filter(DiscussionThread.class_id.in_(class_ids))
        ]
        db.query(DiscussionReply).filter(DiscussionReply.thread_id.in_(threads)).delete(
            synchronize_session=False
        )
        db.query(DiscussionThread).filter(DiscussionThread.id.in_(threads)).delete(
            synchronize_session=False
        )
        db.query(Notification).filter(Notification.user_id.in_(ids)).delete(
            synchronize_session=False
        )
        db.query(NotificationDispatch).filter(NotificationDispatch.sender_id.in_(ids)).delete(
            synchronize_session=False
        )
        db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids)
        ).delete(synchronize_session=False)
        db.query(Assignment).filter(Assignment.id.in_(assignment_ids)).delete(
            synchronize_session=False
        )
        db.query(ClassEnrollment).filter(ClassEnrollment.class_id.in_(class_ids)).delete(
            synchronize_session=False
        )
        db.query(Classroom).filter(Classroom.id.in_(class_ids)).delete(synchronize_session=False)
        db.query(Course).filter(Course.id.in_(course_ids)).delete(synchronize_session=False)
        db.query(UserProfile).filter(UserProfile.user_id.in_(ids)).delete(synchronize_session=False)
        db.query(User).filter(
            User.id.in_(ids), User.username.like(f"notice-verify-{suffix}-%")
        ).delete(synchronize_session=False)
        db.commit()
        assert not db.query(User.id).filter(User.id.in_(ids)).first()
    (OUT / "cleanup.json").write_text(
        json.dumps(
            {
                "temporary_accounts_remaining": 0,
                "temporary_class_ids": class_ids,
                "temporary_assignment_ids": assignment_ids,
                "paid_calls": 0,
            }
        ),
        encoding="utf-8",
    )
sys.exit(code)
