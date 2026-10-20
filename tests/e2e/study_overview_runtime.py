"""Isolated real routers + SQLite + Chromium; no models or shared services."""
# ruff: noqa: E402 -- establish environment boundary before project imports
import json
import os
import secrets
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
os.environ["EVALUATION_SERVICE_URL"] = "http://127.0.0.1:18306/evaluation"
from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import (
    AnswerRecord,
    Exercise,
    KnowledgePoint,
    LearningPath,
    Resource,
    ReviewCard,
    StudyActivity,
    User,
    UserProfile,
)
from common.security.auth import hash_password
from services.agent_service.app.main import app as agent_app
from services.evaluation_service.app.main import app as evaluation_app
from services.resource_service.app.main import app as resource_app
from services.system_service.app.main import app as system_app
from services.teacher_service.app.main import app as teacher_app
from services.user_service.app.main import app as user_app

root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
ensure_database_schema()
password = secrets.token_urlsafe(20)
now = datetime.now(UTC).replace(tzinfo=None)
with SessionLocal() as db:
    hashed = hash_password(password)
    learner = User(username="overview-student", role="student", password_hash=hashed)
    other = User(username="overview-empty", role="student", password_hash=hashed)
    private_owner = User(username="overview-private", role="student", password_hash=hashed)
    db.add_all([learner, other, private_owner])
    db.flush()
    learner_id, other_id = learner.id, other.id
    for user in [learner, other]:
        db.add(UserProfile(user_id=user.id, habits={"profile_setup_skipped": True}))
    point = KnowledgePoint(name="TCP 三次握手")
    db.add(point)
    db.flush()
    exercise = Exercise(knowledge_point_id=point.id, type="choice", content="SYN的含义?", answer="A")
    db.add(exercise)
    db.flush()
    for _ in range(3):
        db.add(AnswerRecord(user_id=learner.id, exercise_id=exercise.id, user_answer="B", is_correct=False, created_at=now))
    db.add(LearningPath(user_id=learner.id, status="active", path_data_json={"user_id": learner.id, "subject": "计算机网络", "knowledge_point": "TCP 三次握手", "overview": "隔离浏览器测试计划", "estimated_days": 2, "stages": [{"stage_id": "s1", "title": "TCP", "description": "test", "tasks": [
        {"task_id": "read", "title": "阅读握手课件", "task_type": "courseware", "knowledge_point": "TCP 三次握手", "objective": "理解", "estimated_minutes": 15, "difficulty": "foundation", "completed": True, "status": "completed", "depends_on": []},
        {"task_id": "practice", "title": "完成握手练习", "task_type": "exercise", "knowledge_point": "TCP 三次握手", "objective": "练习", "estimated_minutes": 15, "difficulty": "foundation", "completed": False, "status": "pending", "depends_on": ["read"]},
    ]}]}))
    for i in range(2):
        db.add(ReviewCard(user_id=learner.id, front=f"TCP卡片{i}", back="测试答案", due_at=now - timedelta(days=1)))
    db.add(Resource(title="TCP隔离课件", type="article", content="# TCP 三次握手\n\n隔离测试内容。", generated_for_user_id=learner.id, knowledge_point_id=point.id, audit_status="passed"))
    db.add(Resource(title="不可泄露资源", type="article", content="other", generated_for_user_id=private_owner.id))
    # Explicit fixture intervals, not real user history or generated data.
    for offset in [45, 90, 135]:
        db.add(StudyActivity(user_id=learner.id, started_at=now-timedelta(seconds=offset), ended_at=now-timedelta(seconds=offset-40), page="exercise"))
    db.commit()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:15189"], allow_methods=["*"], allow_headers=["*"])
for prefix, service in [("user", user_app), ("evaluation", evaluation_app), ("agent", agent_app), ("resource", resource_app), ("teacher", teacher_app), ("system", system_app)]:
    app.mount("/" + prefix, service)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18306, log_level="warning"))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
env = dict(os.environ)
for service in ["USER", "EVALUATION", "AGENT", "RESOURCE", "TEACHER", "SYSTEM"]:
    env[f"VITE_{service}_API_BASE_URL"] = f"http://127.0.0.1:18306/{service.lower()}"
env.update(E2E_BASE_URL="http://127.0.0.1:15189", OVERVIEW_API="http://127.0.0.1:18306", OVERVIEW_PASSWORD=password,
           OVERVIEW_ARTIFACTS=str(root), OVERVIEW_USER_ID=str(learner_id), OVERVIEW_OTHER_ID=str(other_id))
with (root / "vite.log").open("w", encoding="utf-8") as log:
    vite = subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "15189", "--strictPort"], cwd="web-app", env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                if server.started and httpx.get(env["E2E_BASE_URL"], timeout=1).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError("Isolated runtime unavailable")
        result = subprocess.run(["node", "tests/e2e/run-study-overview.mjs"], env=env, timeout=220)
        if result.returncode == 0:
            with SessionLocal() as db:
                intervals = db.query(StudyActivity).filter(StudyActivity.user_id == learner_id).all()
                assert len(intervals) > 3, "Browser heartbeat did not persist intervals"
                (root / "db-evidence.json").write_text(json.dumps({"user_id": learner_id, "activity_rows": len(intervals), "fixture_rows": 3, "actual_browser_intervals": len(intervals)-3, "seconds": sum((row.ended_at-row.started_at).total_seconds() for row in intervals)}), encoding="utf-8")
        raise SystemExit(result.returncode)
    finally:
        vite.terminate()
        vite.wait(timeout=20)
        server.should_exit = True
        thread.join(timeout=15)
