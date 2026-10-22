"""Start isolated services, run real browser checks, then stop owned processes."""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_no_cost_tests import isolated_environment

root = Path(
    sys.argv[1] if len(sys.argv) > 1 else "artifacts/upstream-fusion-a6f5e783/browser"
).resolve()
root.mkdir(parents=True, exist_ok=False)
env = isolated_environment(root, [18235])
env.update(
    FUSION_BROWSER_OUTPUT=str(root),
    JWT_SECRET_KEY="upstream-fusion-isolated-test",
    CORS_ALLOW_ORIGINS="http://127.0.0.1:15205",
)
processes = []
handles = []


def start(command, env, cwd, log):
    handle = (root / log).open("w", encoding="utf-8")
    handles.append(handle)
    p = subprocess.Popen(command, env=env, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT)
    processes.append(p)
    return p


def ready(url, p):
    for _ in range(100):
        if p.poll() is not None:
            raise RuntimeError("Service exited: " + url)
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("Service unavailable: " + url)


try:
    p = start(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "upstream_fusion_server:app",
            "--app-dir",
            "tests/e2e",
            "--host",
            "127.0.0.1",
            "--port",
            "18235",
            "--lifespan",
            "off",
        ],
        env,
        None,
        "api.log",
    )
    ready("http://127.0.0.1:18235/teacher/health", p)
    front = {
        **os.environ,
        "VITE_USER_API_BASE_URL": "http://127.0.0.1:18235/user",
        "VITE_TEACHER_API_BASE_URL": "http://127.0.0.1:18235/teacher",
        "VITE_EVALUATION_API_BASE_URL": "http://127.0.0.1:18235/evaluation",
        "VITE_AGENT_API_BASE_URL": "http://127.0.0.1:18235/agent",
        "VITE_RESOURCE_API_BASE_URL": "http://127.0.0.1:18235/agent",
        "VITE_SYSTEM_API_BASE_URL": "http://127.0.0.1:18235/teacher",
        "VITE_SAKURAFRP_SAME_ORIGIN": "false",
    }
    p = start(
        ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "15205"],
        front,
        "web-app",
        "vite.log",
    )
    ready("http://127.0.0.1:15205", p)
    result = subprocess.run(["node", "tests/e2e/run-upstream-fusion.mjs", str(root)])
    sys.exit(result.returncode)
finally:
    for p in reversed(processes):
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    for h in handles:
        h.close()
