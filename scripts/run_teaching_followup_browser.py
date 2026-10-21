"""Run actual local API/browser assertions without real provider credentials."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_no_cost_tests import isolated_environment

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='artifacts/teaching-followup-20261021/browser-v2')
parser.add_argument('--browser-test', default='tests/e2e/run-teaching-followup.mjs')
parser.add_argument('--local-artifacts', action='store_true')
args = parser.parse_args()
root = Path(args.output).resolve()
root.mkdir(parents=True, exist_ok=False)
source = Path("artifacts/local-start-20261019/runtime.sqlite").resolve()
with sqlite3.connect(source.as_uri()+"?mode=ro", uri=True) as connection, sqlite3.connect(root/"runtime.sqlite") as target:
    connection.backup(target)
env = isolated_environment(root, [18221])
env.update(TEACHING_BROWSER_OUTPUT=str(root), CORS_ALLOW_ORIGINS="http://127.0.0.1:15189",
           ASSISTANT_TASK_EXECUTION_MODE="background" if args.local_artifacts else "worker", JWT_SECRET_KEY="teaching-isolated-browser-only")
processes = []
logs = []
try:
    log = (root/"api.log").open("w", encoding="utf-8"); logs.append(log)
    processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "teaching_followup_server:app", "--app-dir", "tests/e2e", "--host", "127.0.0.1", "--port", "18221", "--lifespan", "off"], env=env, stdout=log, stderr=subprocess.STDOUT))
    # tests/ is not a Python package; resolve the test harness via its directory.
    # The normal services still import from the unchanged repository root.
    if processes[-1].poll() is not None:
        raise RuntimeError("API process exited")
    for _ in range(90):
        if processes[-1].poll() is not None:
            raise RuntimeError("API process exited; inspect api.log")
        try:
            urllib.request.urlopen("http://127.0.0.1:18221/agent/health", timeout=1).close(); break
        except Exception:
            time.sleep(.5)
    front = {**os.environ, "FRONTEND_PORT": "15189", "VITE_USER_API_BASE_URL": "http://127.0.0.1:18221/user",
             "VITE_AGENT_API_BASE_URL": "http://127.0.0.1:18221/agent", "VITE_RESOURCE_API_BASE_URL": "http://127.0.0.1:18221/resource",
             "VITE_EVALUATION_API_BASE_URL": "http://127.0.0.1:18221/evaluation", "VITE_TEACHER_API_BASE_URL": "http://127.0.0.1:18221/user",
             "VITE_SYSTEM_API_BASE_URL": "http://127.0.0.1:18221/user", "VITE_SAKURAFRP_SAME_ORIGIN": "false"}
    log = (root/"vite.log").open("w", encoding="utf-8"); logs.append(log)
    processes.append(subprocess.Popen(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "15189"], cwd="web-app", env=front, stdout=log, stderr=subprocess.STDOUT))
    for _ in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:15189", timeout=1).close(); break
        except Exception:
            time.sleep(.5)
    browser = subprocess.run(["node", args.browser_test, str(root)], timeout=240)
    assert browser.returncode == 0, "Browser assertions failed"
finally:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill()
    for log in logs:
        log.close()
