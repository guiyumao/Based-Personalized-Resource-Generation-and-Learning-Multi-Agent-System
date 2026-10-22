"""Rebuild existing local videos, then reload only their API/worker after backup."""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/video-math-20261021/activation'


def active(db):
    return sum(db.execute('SELECT COUNT(*) FROM ' + table + " WHERE status IN ('PENDING','QUEUED','RUNNING','CANCEL_REQUESTED')").fetchone()[0]
               for table in ('assistant_tasks', 'knowledge_build_tasks'))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    targets = []
    for process in psutil.process_iter(['cmdline']):
        command = process.info['cmdline'] or []
        if 'services.agent_service.app.main:app' in command or 'services.agent_service.app.services.assistant_worker' in command:
            targets.append((process, command, process.environ(), process.cwd()))
    api = next(t for t in targets if '--port' in t[1] and t[1][t[1].index('--port') + 1] == '8002')
    database = Path(api[2]['DATABASE_URL'].split('///', 1)[1]).resolve()
    assert len(targets) == 3 and all(Path(t[2]['DATABASE_URL'].split('///', 1)[1]).resolve() == database for t in targets)
    with sqlite3.connect(database) as db:
        if active(db):
            raise RuntimeError('Active tasks: postpone activation')
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        before_calls = db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0]
        with sqlite3.connect(OUTPUT / 'before.sqlite') as backup:
            db.backup(backup)
    os.environ.update(api[2])
    os.environ.update(APP_LOAD_DOTENV='false', RUN_LIVE_LLM='0', DEEPSEEK_LIVE_PAID_ACK='0', LLM_PREWARM_ENABLED='false')
    sys.path.insert(0, str(ROOT))
    from common.db.session import SessionLocal
    from common.models.learning import Resource
    from common.resource_version import resource_version
    from common.security.auth import create_access_token
    from services.agent_service.app.services.resource_artifacts import (
        ARTIFACT_ROOT,
        ensure_resource_video,
        resource_video_path,
    )

    ids = set()
    for file in ARTIFACT_ROOT.rglob('resource-*.webm'):
        match = re.fullmatch(r'resource-(\d+)-([a-f0-9]{64})\.webm', file.name)
        if match:
            ids.add(int(match[1]))
    videos = []
    for resource_id in sorted(ids):
        with SessionLocal() as db:
            resource = db.get(Resource, resource_id)
            if not resource or resource.type != 'courseware' or resource.generation_status != 'generated' or resource.publish_status == 'archived':
                continue
            version = resource_version(resource)
            result = ensure_resource_video(resource)
            db.expire_all()
            if resource_version(db.get(Resource, resource_id)) != version:
                raise RuntimeError('Source changed during rendering')
            videos.append({'id': resource_id, 'owner': resource.generated_for_user_id, 'size': result['size'], 'path': str(resource_video_path(resource))})
        print('Typeset resource', resource_id, flush=True)
    with sqlite3.connect(database) as db:
        if active(db):
            raise RuntimeError('New active tasks: postpone reload; new videos retained')
    replacements = []
    for process, command, env, cwd in targets:
        name = 'worker' if '--port' not in command else command[command.index('--port') + 1]
        process.terminate()
        process.wait(timeout=15)
        env['LLM_PREWARM_ENABLED'] = 'false'
        with (OUTPUT / f'{name}.stdout.log').open('w', encoding='utf-8') as out, (OUTPUT / f'{name}.stderr.log').open('w', encoding='utf-8') as err:
            child = subprocess.Popen(command, env=env, cwd=cwd, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        replacements.append({'name': name, 'old_pid': process.pid, 'pid': child.pid})
        if name != 'worker':
            for _ in range(100):
                if child.poll() is not None:
                    raise RuntimeError('Service exited: ' + name)
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{name}/health', timeout=1).close()
                    break
                except OSError:
                    time.sleep(.3)
            else:
                raise RuntimeError('Health timeout: ' + name)
    for video in videos:
        token = create_access_token(subject=str(video['owner']))
        request = urllib.request.Request(f"http://127.0.0.1:8002/resources/{video['id']}/video", headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.headers['Content-Type'] == 'video/webm'
            assert response.read() == Path(video['path']).read_bytes()
        video['http_status'] = 200
    with sqlite3.connect(database) as db:
        after_calls = db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0]
    result = {'videos': videos, 'processes': replacements, 'model_calls_before': before_calls, 'model_calls_after': after_calls}
    (OUTPUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
