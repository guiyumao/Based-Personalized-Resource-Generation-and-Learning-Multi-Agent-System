"""Read-only existing teacher/student verification on current 5175, sharing one browser."""
# ruff: noqa: E402
import json
import os
import subprocess
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
process = next(p for p in psutil.process_iter(['cmdline']) if 'services.teacher_service.app.main:app' in (p.info['cmdline'] or []))
os.environ.update(process.environ())
os.environ['APP_LOAD_DOTENV'] = 'false'
from common.db.session import SessionLocal
from common.models.learning import User
from common.security.auth import create_access_token

accounts = {}
with SessionLocal() as db:
    for name in ['teacher111', 'student']:
        user = db.query(User).filter_by(username=name, is_active=True).one()
        accounts[name] = {'token': create_access_token(str(user.id)), 'user': {'userId': user.id, 'username': name, 'role': user.role}}
out = ROOT / 'artifacts/auth-tabs-current'
out.mkdir(parents=True, exist_ok=False)
env = os.environ.copy()
env['CURRENT_ROLE_AUTH'] = json.dumps(accounts)
result = subprocess.run(['node', 'tests/e2e/run-current-role-tabs.mjs', str(out)], cwd=ROOT, env=env)
sys.exit(result.returncode)
