"""Activate the two learner pages on the verified existing local runtime.

Reuses the running user/evaluation process environments. No schema bootstrap,
model calls, data repair or migrations. Never persists process environment/JWT.
"""

import json
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/learner-insights-20261021/activation"
OUT.mkdir(exist_ok=False)
targets = [
    ("user", 8001, "services.user_service.app.main:app"),
    ("evaluation", 8004, "services.evaluation_service.app.main:app"),
]
verified = []
for name, port, module in targets:
    owners = {
        connection.pid
        for connection in psutil.net_connections(kind="tcp")
        if connection.status == "LISTEN" and connection.laddr.port == port
    }
    assert len(owners) == 1, f"Unexpected listener count on {port}"
    process = psutil.Process(owners.pop())
    args = process.cmdline()
    assert module in args and str(port) in args, f"Unexpected process on {port}"
    environment = process.environ()
    database = environment.get("DATABASE_URL", "")
    assert database.endswith("/artifacts/local-start-20261019/runtime.sqlite"), (
        "Unexpected runtime database"
    )
    verified.append((name, port, module, process, environment, process.exe()))
assert len({item[4]["DATABASE_URL"] for item in verified}) == 1
database_path = ROOT / "artifacts/local-start-20261019/runtime.sqlite"
with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True) as source:
    assert source.execute("pragma quick_check").fetchone()[0] == "ok"
    assert (
        source.execute("select count(*) from assistant_tasks where status='RUNNING'").fetchone()[0]
        == 0
    ), "Assistant work is active; defer restart"
    with sqlite3.connect(OUT / "before-activation.sqlite") as backup:
        source.backup(backup)
results = []
for name, port, module, previous, environment, executable in verified:
    environment.update(
        LLM_PREWARM_ENABLED="false",
        GRAPH_LLM_ENRICH_ENABLED="false",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    old_pid = previous.pid
    previous.terminate()
    previous.wait(timeout=15)
    with (
        (OUT / f"{name}.stdout.log").open("w", encoding="utf-8") as stdout,
        (OUT / f"{name}.stderr.log").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            [
                executable,
                "-m",
                "uvicorn",
                module,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--lifespan",
                "off",
            ],
            cwd=ROOT,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    for _ in range(60):
        assert process.poll() is None, f"{name} exited; inspect logs"
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    else:
        raise RuntimeError(f"{name} did not become ready")
    paths = httpx.get(f"http://127.0.0.1:{port}/openapi.json").json()["paths"]
    required = (
        "/users/{user_id}/learning-portrait"
        if name == "user"
        else "/evaluation/analytics/{user_id}/insights"
    )
    assert required in paths
    results.append(
        {
            "name": name,
            "port": port,
            "previous_pid": old_pid,
            "pid": process.pid,
            "health": "ok",
            "new_endpoint": required,
            "lifespan": "off",
        }
    )
    (OUT / "processes.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(
    json.dumps(
        {"activated": True, "ports": [8001, 8004], "schema_changed": False, "model_calls": 0}
    )
)
