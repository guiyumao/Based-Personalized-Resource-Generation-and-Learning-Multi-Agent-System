"""Read-only browser verification on the activated local learner pages."""
import json
import os
import subprocess
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
out = ROOT / "artifacts/learner-insights-20261021/activation"
processes = []
for name, port, module in (
    ("user", 8001, "services.user_service.app.main:app"),
    ("evaluation", 8004, "services.evaluation_service.app.main:app"),
):
    owners = {
        connection.pid
        for connection in psutil.net_connections(kind="tcp")
        if connection.status == "LISTEN" and connection.laddr.port == port
    }
    assert len(owners) == 1, f"Unexpected listener count on {port}"
    process = psutil.Process(owners.pop())
    assert module in process.cmdline(), f"Unexpected process on {port}"
    processes.append({"name": name, "port": port, "pid": process.pid})
    if name == "user":
        live_env = process.environ()
        assert live_env.get("DATABASE_URL", "").endswith(
            "/artifacts/local-start-20261019/runtime.sqlite"
        ), "Unexpected runtime database"
(out / "verification-processes.json").write_text(json.dumps(processes, indent=2), encoding="utf-8")
for key in ("DATABASE_URL", "JWT_SECRET_KEY", "JWT_ALGORITHM", "APP_LOAD_DOTENV"):
    if key in live_env:
        os.environ[key] = live_env[key]

from common.db.session import SessionLocal  # noqa: E402
from common.models.learning import User  # noqa: E402
from common.security.auth import create_access_token  # noqa: E402

with SessionLocal() as db:
    learner = db.query(User).filter_by(role="student", is_active=True).order_by(User.id).first()
    assert learner is not None
    token = create_access_token(str(learner.id))
    identity = {"userId": learner.id, "username": learner.username, "role": learner.role}
env = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "COMSPEC"}}
env.update(LIVE_INSIGHTS_TOKEN=token, LIVE_INSIGHTS_USER=json.dumps(identity), LIVE_INSIGHTS_OUTPUT=str(out))
result = subprocess.run(["node", "tests/e2e/run-learner-insights-live.mjs"], cwd=ROOT, env=env, timeout=120)
raise SystemExit(result.returncode)
