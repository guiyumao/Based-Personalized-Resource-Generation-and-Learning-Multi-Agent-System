"""Read-only browser acceptance using a real database snapshot or the activated API.

Tokens and inherited environment are kept in memory. No Provider requests or DB seed data.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import httpx
import psutil
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--live', action='store_true')
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
owners = {c.pid for c in psutil.net_connections('tcp') if c.status == 'LISTEN' and c.laddr.port == 8002}
assert len(owners) == 1
api = psutil.Process(owners.pop())
assert 'services.agent_service.app.main:app' in api.cmdline()
environment = api.environ()
source = Path(make_url(environment['DATABASE_URL']).database).resolve(strict=True)
assert source == (ROOT / 'artifacts/local-start-20261019/runtime.sqlite').resolve()
port = 8002 if args.live else 18222
database = source if args.live else out / 'real-data-snapshot.sqlite'
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as db:
    assert db.execute('pragma quick_check').fetchone()[0] == 'ok'
    before = db.execute('select count(*) from model_calls').fetchone()[0]
    if not args.live:
        with sqlite3.connect(database) as destination:
            db.backup(destination)
    identity = db.execute("select id,username,role from users where role='admin' and is_active=1 order by id limit 1").fetchone()
assert identity
for key in ('JWT_SECRET_KEY', 'JWT_ALGORITHM'):
    if key in environment:
        os.environ[key] = environment[key]
os.environ['APP_LOAD_DOTENV'] = 'false'
from common.security.auth import create_access_token  # noqa: E402
token = create_access_token(str(identity[0]))
server = None
try:
    if not args.live:
        environment.update(DATABASE_URL='sqlite+pysqlite:///' + database.as_posix(), APP_LOAD_DOTENV='false',
            LLM_PREWARM_ENABLED='false', GRAPH_LLM_ENRICH_ENABLED='false', PYTHONUTF8='1')
        with (out / 'server.log').open('wb') as log:
            server = subprocess.Popen([api.exe(), '-m', 'uvicorn', 'services.agent_service.app.main:app',
                '--host', '127.0.0.1', '--port', str(port), '--lifespan', 'off'], env=environment, cwd=ROOT,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(80):
            assert server.poll() is None, 'Inspect server.log'
            try:
                if httpx.get(f'http://127.0.0.1:{port}/health', timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.25)
        else:
            raise RuntimeError('Isolated API not ready')
    payload = {'output': str(out), 'port': port, 'live': args.live,
        'auth': {'token': token, 'user': {'userId': identity[0], 'username': identity[1], 'role': identity[2]}}}
    with (out / 'browser.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(['node', 'tests/e2e/run-admin-dashboard.mjs'], input=json.dumps(payload), text=True,
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as db:
        after = db.execute('select count(*) from model_calls').fetchone()[0]
    assert before == after, 'Provider ledger changed during read-only verification'
    (out / 'provider-count.json').write_text(json.dumps({'before': before, 'after': after, 'new_calls': 0}))
    print(json.dumps({'browser_exit': result.returncode, 'real_snapshot': not args.live, 'live': args.live, 'new_calls': 0}))
    raise SystemExit(result.returncode)
finally:
    if server:
        server.terminate()
        server.wait(timeout=15)
