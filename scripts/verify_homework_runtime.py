"""Audit already-loaded homework support; preserve the runtime and rehearse on copies."""
import json
import os
import sqlite3
import sys
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/homework-files-runtime'
TARGET = ROOT / 'artifacts/local-start-20261019/runtime.sqlite'


def structure(db):
    return {
        'columns': sorted((r[1], r[2], r[3], r[5]) for r in db.execute('PRAGMA table_info(homework_attachments)')),
        'foreign_keys': sorted(tuple(r[2:]) for r in db.execute('PRAGMA foreign_key_list(homework_attachments)')),
        'indexes': sorted((r[1], r[2]) for r in db.execute('PRAGMA index_list(homework_attachments)')),
    }


if __name__ == '__main__':
    assert (OUT / 'rehearsal.json').exists(), 'Retain backup and rehearsal evidence first'
    with sqlite3.connect(TARGET) as live, sqlite3.connect(OUT / 'rehearsal.sqlite') as rehearsal:
        assert structure(live) == structure(rehearsal), 'Runtime schema differs from migration rehearsal'
        assert live.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        before = {t: live.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in ['users', 'classrooms', 'class_enrollments', 'assignments', 'assignment_submissions', 'homework_attachments', 'model_calls']}
    process = next(p for p in psutil.process_iter(['cmdline']) if 'services.teacher_service.app.main:app' in (p.info['cmdline'] or []))
    assert Path(process.environ()['DATABASE_URL'].split('///', 1)[1]).resolve() == TARGET.resolve()
    os.environ.update(process.environ())
    os.environ['APP_LOAD_DOTENV'] = 'false'
    sys.path.insert(0, str(ROOT))
    from common.db.session import SessionLocal
    from common.models.learning import User
    from common.security.auth import create_access_token

    paths = httpx.get('http://127.0.0.1:8005/openapi.json').json()['paths']
    assert '/teacher/homework/attachments/{file_id}/preview' in paths
    api = []
    with SessionLocal() as db:
        for username, endpoints in [('teacher111', ['/teacher/classes', '/teacher/homework']), ('student', ['/teacher/students/me/homework'])]:
            user = db.query(User).filter_by(username=username, is_active=True).one()
            headers = {'Authorization': 'Bearer ' + create_access_token(str(user.id))}
            for path in endpoints:
                response = httpx.get('http://127.0.0.1:8005' + path, headers=headers, timeout=15)
                assert response.status_code == 200, response.status_code
                api.append({'role': user.role, 'path': path, 'status': 200})
    response = httpx.get('http://127.0.0.1:8005/teacher/homework/attachments/1')
    assert response.status_code in (401, 403)
    with sqlite3.connect(TARGET) as live:
        after = {t: live.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in before}
    assert before == after
    result = {'already_loaded': True, 'schema_matches_migration': True, 'integrity': 'ok', 'before': before, 'after': after, 'api': api, 'anonymous_download': response.status_code, 'service_restarted': False, 'runtime_migrated_this_run': False}
    (OUT / 'current-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))
