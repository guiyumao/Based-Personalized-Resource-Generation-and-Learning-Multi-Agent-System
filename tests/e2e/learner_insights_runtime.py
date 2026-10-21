"""Guarded real HTTP + browser acceptance for the learner analytics/portrait."""

import json
import os
import secrets
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
# ruff: noqa: E402 -- configure isolation before app imports
os.environ["CORS_ALLOW_ORIGINS"] = "http://127.0.0.1:15301"
import httpx
import uvicorn
from fastapi import FastAPI

from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import (
    AnswerRecord,
    Exercise,
    KnowledgePoint,
    ReviewCard,
    StudyActivity,
    StudyNote,
    User,
    UserProfile,
)
from common.security.auth import hash_password
from services.evaluation_service.app.main import app as evaluation_app
from services.user_service.app.main import app as user_app

root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
ensure_database_schema()
password = secrets.token_urlsafe(20)
now = datetime.now(UTC).replace(tzinfo=None)
with SessionLocal() as db:
    db.add_all(
        [
            User(
                id=1,
                username="insights-learner",
                role="student",
                password_hash=hash_password(password),
            ),
            User(
                id=2,
                username="insights-other",
                role="student",
                password_hash=hash_password(password),
            ),
        ]
    )
    db.add(
        UserProfile(
            user_id=1,
            habits={"profile_skipped": True},
            mastery_json={},
            cognitive_abilities={},
            learning_style="",
        )
    )
    db.add(KnowledgePoint(id=1, name="分数运算"))
    db.add(
        Exercise(
            id=1,
            knowledge_point_id=1,
            type="choice",
            content='{"knowledge_point":"分数运算"}',
            answer="A",
            difficulty=1,
        )
    )
    db.commit()
    db.add_all(
        [
            AnswerRecord(
                user_id=1,
                exercise_id=1,
                user_answer="A",
                is_correct=True,
                time_spent=20,
                created_at=now,
            ),
            AnswerRecord(
                user_id=1,
                exercise_id=1,
                user_answer="B",
                is_correct=False,
                time_spent=30,
                created_at=now,
            ),
            AnswerRecord(
                user_id=2, exercise_id=1, user_answer="A", is_correct=True, created_at=now
            ),
            ReviewCard(user_id=1, front="分数", back="通分", due_at=now - timedelta(days=1)),
            StudyNote(user_id=1, title="分数笔记", body="统一分母"),
            StudyActivity(
                user_id=1, started_at=now - timedelta(seconds=300), ended_at=now, page="exercise"
            ),
        ]
    )
    db.commit()
app = FastAPI()
app.mount("/user", user_app)
app.mount("/evaluation", evaluation_app)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18301, log_level="warning"))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
env = dict(os.environ)
for service in ["USER", "EVALUATION", "AGENT", "RESOURCE", "SYSTEM", "TEACHER"]:
    env[f"VITE_{service}_API_BASE_URL"] = f"http://127.0.0.1:18301/{service.lower()}"
env.update(
    VITE_SAKURAFRP_SAME_ORIGIN="false",
    E2E_BASE_URL="http://127.0.0.1:15301",
    INSIGHTS_API="http://127.0.0.1:18301",
    INSIGHTS_PASSWORD=password,
    INSIGHTS_ARTIFACTS=str(root),
)
with (root / "vite.log").open("w", encoding="utf-8") as log:
    vite = subprocess.Popen(
        [
            "node",
            "node_modules/vite/bin/vite.js",
            "--host",
            "127.0.0.1",
            "--port",
            "15301",
            "--strictPort",
        ],
        cwd="web-app",
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(100):
            if vite.poll() is not None:
                raise RuntimeError("Vite exited")
            try:
                if server.started and httpx.get(env["E2E_BASE_URL"], timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Isolated runtime did not start")
        result = subprocess.run(
            ["node", "tests/e2e/run-learner-insights.mjs"], env=env, timeout=180
        )
        if result.returncode == 0:
            with SessionLocal() as db:
                profile = db.get(UserProfile, 1)
                assert (
                    profile.habits["profile_dimensions"]["goalOrientation"]
                    == "掌握分数计算并完成练习"
                )
                assert profile.habits["learning_style_axes"]["input"] == 0.65
                (root / "db-evidence.json").write_text(
                    json.dumps(
                        {
                            "passed": True,
                            "profile_persisted": True,
                            "user_id": 1,
                            "shared_db_touched": False,
                        }
                    ),
                    encoding="utf-8",
                )
        raise SystemExit(result.returncode)
    finally:
        vite.terminate()
        vite.wait(timeout=15)
        server.should_exit = True
        thread.join(timeout=15)
