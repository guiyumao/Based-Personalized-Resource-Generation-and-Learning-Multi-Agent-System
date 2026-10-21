"""Back up and reload the verified local API/Worker without changing its database target."""
import argparse
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import psutil
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-pid', type=int, required=True)
    parser.add_argument('--worker-pid', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--activate-current-runtime', action='store_true', required=True)
    parser.add_argument('--api-only', action='store_true')
    args = parser.parse_args()
    api, worker = psutil.Process(args.api_pid), psutil.Process(args.worker_pid)
    assert 'services.agent_service.app.main:app' in api.cmdline()
    assert 'services.agent_service.app.services.assistant_worker' in worker.cmdline()
    env = api.environ()
    assert worker.environ().get('DATABASE_URL') == env.get('DATABASE_URL')
    source = Path(make_url(env['DATABASE_URL']).database).resolve(strict=True)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as original:
        for table in ('assistant_tasks', 'knowledge_build_tasks'):
            active = original.execute(f"select count(*) from {table} where status in ('PENDING','RUNNING','CANCEL_REQUESTED')").fetchone()[0]
            assert active == 0, 'Refusing reload while work is pending or running'
        assert original.execute('select count(*) from knowledge_maintenance_plans').fetchone()[0] == 0, 'Review maintenance dispatch before reload'
        with sqlite3.connect(root/'runtime-backup.sqlite') as backup:
            original.backup(backup)
            assert backup.execute('pragma quick_check').fetchone()[0] == 'ok'
    cwd = api.cwd()
    launch = {'api': (api.exe(), api.cmdline()[1:], env),
              'worker': (worker.exe(), worker.cmdline()[1:], worker.environ())}
    if args.api_only:
        launch.pop('worker')
    # Runtime environment remains in memory only, including credentials.
    state = {'source_database': str(source), 'backup': str(root/'runtime-backup.sqlite'), 'old_api_pid': api.pid, 'old_worker_pid': worker.pid}
    if args.api_only:
        state['worker_pid'] = worker.pid
    for process in ((api,) if args.api_only else (worker, api)):
        process.terminate()
        process.wait(timeout=20)
    for name, (executable, command, environment) in launch.items():
        with (root/f'{name}.log').open('wb') as log:
            child = subprocess.Popen([executable, *command], cwd=cwd, env=environment,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        state[name+'_pid'] = child.pid
        time.sleep(2)
        if child.poll() is not None:
            state[name+'_exit_code'] = child.returncode
            (root/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
            raise RuntimeError(name+' failed to start; preserved backup and launch logs')
    (root/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'api_pid':state['api_pid'],'worker_pid':state['worker_pid'],'backup_verified':True}))


if __name__ == '__main__':
    main()
