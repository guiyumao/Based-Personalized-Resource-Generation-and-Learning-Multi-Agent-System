"""Controlled temporary-account real-model + UI acceptance (up to two model calls).

Synthetic learning evidence belongs only to these disposable accounts. This is
provider integration evidence, not a claim about real learners' content quality.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("SUPPORT_LIVE_OUT", "artifacts/teacher-support-20261022/live")


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    proc = next(p for p in psutil.process_iter(["cmdline"])
                if "services.teacher_service.app.main:app" in (p.info["cmdline"] or []) and "8005" in (p.info["cmdline"] or []))
    os.environ.update(proc.environ())
    os.environ["APP_LOAD_DOTENV"] = "false"
    sys.path.insert(0, str(ROOT))
    from common.db.session import SessionLocal, engine
    from common.models.learning import (
        AnswerRecord,
        Assignment,
        AssignmentSubmission,
        ClassEnrollment,
        Classroom,
        Course,
        Exercise,
        KnowledgePoint,
        Notification,
        ResourceInteraction,
        StudyActivity,
        StudySession,
        SubmissionRevision,
        SystemSubject,
        User,
        UserProfile,
    )
    from common.models.operations import ModelCall
    from common.models.teacher_support import (
        CourseResourceDelivery,
        ReinforcementAttempt,
        ReinforcementDraft,
    )
    from common.security.auth import create_access_token
    database = Path(engine.url.database).resolve()
    with sqlite3.connect(database) as db, sqlite3.connect(OUT / "before.sqlite") as backup:
        db.backup(backup)

    tables = ["users", "system_subjects", "knowledge_points", "exercises", "answer_records", "user_profiles", "classrooms", "courses", "class_enrollments", "assignments", "assignment_submissions", "submission_revisions", "notifications", "study_activities", "study_sessions", "course_resource_deliveries", "reinforcement_drafts", "reinforcement_attempts"]
    def counts():
        with sqlite3.connect(database) as db:
            return {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}
    before = counts()
    suffix = uuid4().hex[:10]
    room = None
    ids = []
    subject_id = point_id = historical_exercise_id = None
    result = {"controlled_synthetic_evidence": True}
    try:
        with SessionLocal() as db:
            base_id = 2000000000 + int(suffix[:6], 16) * 3
            users = [User(id=base_id+i, username=f"support-live-{role}-{suffix}-{i}", password_hash="disabled-test-login", role=role, is_active=True)
                     for i, role in enumerate(("teacher", "student", "student"))]
            db.add_all(users)
            subject = SystemSubject(name=f"数据结构验收-{suffix}", description="临时模型联动验收学科")
            db.add(subject)
            db.flush()
            subject_id = subject.id
            point = KnowledgePoint(name="二叉树遍历", subject_id=subject.id)
            db.add(point)
            db.flush()
            point_id = point.id
            exercise = Exercise(knowledge_point_id=point.id, type="choice", content=json.dumps({"prompt": "二叉树的中序遍历先访问哪里？", "options": ["A.左子树", "B.根节点"], "generated_for_user_id": users[1].id, "subject": subject.name}), answer="A", analysis="中序遍历是左、根、右。")
            db.add(exercise)
            db.flush()
            historical_exercise_id = exercise.id
            db.add(AnswerRecord(user_id=users[1].id, exercise_id=exercise.id, user_answer="B", is_correct=False, time_spent=45))
            now = datetime.now(UTC).replace(tzinfo=None)
            db.add(StudyActivity(user_id=users[1].id, page="practice", started_at=now-timedelta(minutes=20), ended_at=now-timedelta(minutes=5)))
            db.commit()
            ids = [u.id for u in users]
            auths = [{"token": create_access_token(str(u.id)), "user": {"userId": u.id, "username": u.username, "role": u.role}} for u in users]
            subject_name = subject.name
        with httpx.Client(timeout=30) as client:
            response = client.post("http://127.0.0.1:8005/teacher/classes", headers={"Authorization": f"Bearer {auths[0]['token']}"}, json={"name": f"教师补强验收班-{suffix}", "subject": subject_name, "join_mode": "open"})
            response.raise_for_status()
            room = response.json()["data"]
            for auth in auths[1:]:
                client.post(f"http://127.0.0.1:8005/learning/classrooms/{room['id']}/join", headers={"Authorization": f"Bearer {auth['token']}"}).raise_for_status()
        env = os.environ.copy()
        env.update(SUPPORT_TEACHER_AUTH=json.dumps(auths[0]), SUPPORT_STUDENT_AUTH=json.dumps(auths[1]),
                   SUPPORT_PEER_AUTH=json.dumps(auths[2]), SUPPORT_CLASS=json.dumps(room), SUPPORT_OUT=str(OUT / "browser"))
        browser = subprocess.run(["node", "tests/e2e/run-teacher-reinforcement-live.mjs"], cwd=ROOT, env=env)
        result["browser_exit_code"] = browser.returncode
        assert browser.returncode == 0, "Browser acceptance failed; inspect browser/result.json"
    finally:
        # Never remove data beneath a model job that is still writing.
        if ids:
            for _ in range(180):
                with SessionLocal() as db:
                    active = db.query(ModelCall).filter(ModelCall.user_id == ids[0], ModelCall.status == "STARTED").count()
                if active == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Model call still running; preserve temporary data for inspection")
        with SessionLocal() as db:
            calls = db.query(ModelCall).filter(ModelCall.user_id == ids[0]).all() if ids else []
            result["model_calls"] = [{"id": c.id, "model": c.model, "status": c.status, "feature": c.feature} for c in calls]
            if room:
                class_id = room["id"]
                assignment_ids = [r[0] for r in db.query(Assignment.id).filter_by(class_id=class_id)]
                submission_ids = [r[0] for r in db.query(AssignmentSubmission.id).filter(AssignmentSubmission.assignment_id.in_(assignment_ids))]
                drafts = db.query(ReinforcementDraft).filter_by(class_id=class_id).all()
                exercise_ids = [q["exercise_id"] for d in drafts for q in (d.questions or []) if "exercise_id" in q]
                db.query(ReinforcementAttempt).filter(ReinforcementAttempt.submission_id.in_(submission_ids)).delete(synchronize_session=False)
                db.query(AnswerRecord).filter(AnswerRecord.user_id.in_(ids)).delete(synchronize_session=False)
                db.query(SubmissionRevision).filter(SubmissionRevision.submission_id.in_(submission_ids)).delete(synchronize_session=False)
                db.query(ReinforcementDraft).filter_by(class_id=class_id).delete(synchronize_session=False)
                db.query(CourseResourceDelivery).filter_by(class_id=class_id).delete(synchronize_session=False)
                db.query(AssignmentSubmission).filter(AssignmentSubmission.id.in_(submission_ids)).delete(synchronize_session=False)
                db.query(Assignment).filter(Assignment.id.in_(assignment_ids)).delete(synchronize_session=False)
                db.query(Exercise).filter(Exercise.id.in_(exercise_ids)).delete(synchronize_session=False)
                db.query(ClassEnrollment).filter_by(class_id=class_id).delete(synchronize_session=False)
                db.query(Classroom).filter_by(id=class_id).delete(synchronize_session=False)
                db.query(Course).filter_by(id=room["course_id"]).delete(synchronize_session=False)
            db.query(Notification).filter((Notification.user_id.in_(ids)) | (Notification.sender_id.in_(ids))).delete(synchronize_session=False)
            for model in (ResourceInteraction, StudyActivity, StudySession, UserProfile):
                db.query(model).filter(model.user_id.in_(ids)).delete(synchronize_session=False)
            if historical_exercise_id:
                db.query(AnswerRecord).filter_by(exercise_id=historical_exercise_id).delete(synchronize_session=False)
                db.query(Exercise).filter_by(id=historical_exercise_id).delete(synchronize_session=False)
            if point_id:
                db.query(KnowledgePoint).filter_by(id=point_id).delete(synchronize_session=False)
            if subject_id:
                db.query(SystemSubject).filter_by(id=subject_id).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
        after = counts()
        result.update(before_counts=before, after_counts=after, counts_restored=before == after)
        (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result["counts_restored"], "Inspect temporary-data cleanup"
    assert len(result["model_calls"]) <= 2, "Unexpected extra model traffic"


if __name__ == "__main__":
    main()
