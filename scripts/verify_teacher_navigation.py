"""Read-only navigation checks against the running teacher workspace; no model calls."""
# ruff: noqa: E402
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
process = next(
    p for p in psutil.process_iter(["cmdline"])
    if "services.teacher_service.app.main:app" in (p.info["cmdline"] or [])
    and "8005" in (p.info["cmdline"] or [])
)
os.environ.update(process.environ())
os.environ["APP_LOAD_DOTENV"] = "false"
from common.db.session import SessionLocal
from common.models.learning import User
from common.security.auth import create_access_token

with SessionLocal() as db:
    teacher = db.query(User).filter_by(username="teacher111", role="teacher", is_active=True).one()
    auth = {
        "token": create_access_token(str(teacher.id)),
        "user": {"userId": teacher.id, "username": teacher.username, "role": "teacher"},
    }
out = ROOT / "artifacts" / ("teacher-navigation-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
out.mkdir(parents=True)
env = os.environ.copy()
env["TEACHER_VERIFY_AUTH"] = json.dumps(auth)
result = subprocess.run(["node", "tests/e2e/run-teacher-navigation.mjs", str(out)], cwd=ROOT, env=env)
print("Evidence:", out)
sys.exit(result.returncode)
