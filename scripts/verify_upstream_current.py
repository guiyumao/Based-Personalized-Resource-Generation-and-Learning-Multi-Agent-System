"""Read-only current UI/schema/graph verification using one disposable learner."""

# ruff: noqa: E402 -- configure the verified runtime before importing application settings
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psutil
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "artifacts/upstream-fusion-a6f5e783/current-browser"
OUT.mkdir(parents=True, exist_ok=False)
process = next(
    p
    for p in psutil.process_iter(["cmdline"])
    if "services.agent_service.app.main:app" in (p.info["cmdline"] or [])
    and "8002" in (p.info["cmdline"] or [])
)
os.environ.update(process.environ())
os.environ["APP_LOAD_DOTENV"] = "false"
from common.db.session import SessionLocal
from common.models.learning import StudyActivity, StudySession, User, UserProfile
from common.security.auth import create_access_token

name = "fusion-verify-" + uuid4().hex[:12]
with SessionLocal() as db:
    user = User(
        username=name, password_hash="disabled-verification-login", role="student", is_active=True
    )
    db.add(user)
    db.commit()
    uid = user.id
    before_calls = db.execute(text("SELECT COUNT(*) FROM model_calls")).scalar()
(OUT / "auth.json").write_text(
    json.dumps(
        {
            "token": create_access_token(str(uid)),
            "user": {"userId": uid, "username": name, "role": "student"},
        }
    ),
    encoding="utf-8",
)
try:
    result = subprocess.run(["node", "tests/e2e/run-upstream-current.mjs", str(OUT)])
finally:
    with SessionLocal() as db:
        db.query(StudyActivity).filter_by(user_id=uid).delete()
        db.query(StudySession).filter_by(user_id=uid).delete()
        db.query(UserProfile).filter_by(user_id=uid).delete()
        db.query(User).filter_by(id=uid, username=name).delete()
        db.commit()
        after_calls = db.execute(text("SELECT COUNT(*) FROM model_calls")).scalar()
        remaining = db.query(User).filter_by(username=name).count()
    (OUT / "cleanup.json").write_text(
        json.dumps(
            {
                "temporary_accounts_remaining": remaining,
                "model_calls_before": before_calls,
                "model_calls_after": after_calls,
                "paid_requests_sent_by_test": 0,
            }
        ),
        encoding="utf-8",
    )
sys.exit(result.returncode)
