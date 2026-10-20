"""Isolated HTTP/browser acceptance with real application routers, no Worker/LLM.

Invoke through scripts/run_no_cost_tests.py; never against the shared database.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

assert os.environ.get('NO_COST_GUARD_ACTIVE') == '1'
from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import KnowledgeBuildTask, KnowledgeCandidate, Resource, SystemConfig, User, UserProfile
from common.security.auth import hash_password
from services.user_service.app.main import app as user_app
from services.system_service.app.main import app as system_app
from services.resource_service.app.main import app as resource_app
from services.agent_service.app.main import app as agent_app
from services.teacher_service.app.main import app as teacher_app
from services.evaluation_service.app.main import app as evaluation_app

root = Path(os.environ['KNOWLEDGE_RUNTIME_ROOT'])
ensure_database_schema()
password = secrets.token_urlsafe(20)
with SessionLocal() as db:
    hashed = hash_password(password)
    for role in ['admin', 'student', 'teacher']:
        db.add(User(username='navigation-' + role, role=role, password_hash=hashed))
    for index in range(13):
        db.add(User(username=f'navigation-learner-{index:02}', role='student', password_hash=hashed))
    db.add(SystemConfig(key='ui.theme', value='light'))
    db.commit()
    learner = db.query(User).filter_by(username='navigation-student').one()
    db.add(UserProfile(user_id=learner.id))
    db.add(Resource(title='隔离验收资源', type='article', content='# 隔离验收资源\n\n本内容仅用于隔离导航测试。', generated_for_user_id=learner.id, audit_status='passed', publish_status='draft'))
    admin = db.query(User).filter_by(username='navigation-admin').one()
    task = KnowledgeBuildTask(actor_user_id=admin.id, client_request_id='navigation-fixture', request_hash='nav-fixture', trigger_source='ADMIN', operation_type='FETCH_SOURCE', subject='python', status='COMPLETED')
    db.add(task)
    db.flush()
    db.add(KnowledgeCandidate(creator_user_id=admin.id, source_task_id=task.id, subject='python', knowledge_point='导航测试', title='隔离审核候选', content='# 隔离审核候选\n\n本内容仅用于隔离验收。', source_url='https://example.com/isolated-fixture', source_hash='fixture', content_hash='fixture', license_name='INTERNAL_TEST_ONLY', license_evidence_url='https://example.com/license', publication_allowed=True))
    db.commit()

# Mount unmodified service apps on one isolated listener. Their route dependencies,
# schemas, persistence, login and RBAC are real; service deployment is not tested.
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:15187'], allow_methods=['*'], allow_headers=['*'])
for prefix, service in [('user', user_app), ('system', system_app), ('resource', resource_app), ('agent', agent_app), ('teacher', teacher_app), ('evaluation', evaluation_app)]:
    app.mount('/' + prefix, service)
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18206, log_level='warning'))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
env = dict(os.environ)
for service in ['USER', 'SYSTEM', 'RESOURCE', 'AGENT', 'TEACHER', 'EVALUATION']:
    env[f'VITE_{service}_API_BASE_URL'] = f'http://127.0.0.1:18206/{service.lower()}'
env.update(E2E_BASE_URL='http://127.0.0.1:15187', ADMIN_NAV_API='http://127.0.0.1:18206', ADMIN_NAV_PASSWORD=password, ADMIN_NAV_ARTIFACTS=str(root))
with (root / 'vite.log').open('w', encoding='utf-8') as log:
    vite = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15187', '--strictPort'], cwd='web-app', env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                if server.started and httpx.get(env['E2E_BASE_URL'], timeout=1).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('Isolated runtime did not become ready')
        result = subprocess.run(['node', 'tests/e2e/run-admin-navigation.mjs'], env=env, timeout=240)
        raise SystemExit(result.returncode)
    finally:
        vite.terminate()
        vite.wait(timeout=20)
        server.should_exit = True
        thread.join(timeout=15)
