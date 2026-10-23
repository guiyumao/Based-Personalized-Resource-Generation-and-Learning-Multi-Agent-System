"""Back up and rehearse the additive async table before reloading local services."""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

import httpx
import psutil
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]


def counts(path):
    with closing(sqlite3.connect(path)) as db:
        return {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def main():
    out = ROOT / "artifacts" / ("path-fusion-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir()
    targets = []
    for p in psutil.process_iter(["cmdline"]):
        cmd = p.info["cmdline"] or []
        if (("services.agent_service.app.main:app" in cmd and any(port in cmd for port in ("8002", "8007")))
                or "services.teacher_service.app.main:app" in cmd
                or "services.agent_service.app.services.assistant_worker" in cmd):
            targets.append((p, cmd, p.environ(), p.cwd()))
    assert targets, "No managed running services found"
    env = next(e for _, cmd, e, _ in targets if "services.agent_service.app.main:app" in cmd)
    os.environ.update(env)
    os.environ["APP_LOAD_DOTENV"] = "false"
    sys.path.insert(0, str(ROOT))
    path = Path(sa.engine.make_url(env["DATABASE_URL"]).database).resolve()
    assert path == (ROOT / "artifacts/local-start-20261019/runtime.sqlite").resolve()
    before = counts(path)
    with closing(sqlite3.connect(path)) as db:
        for table in ("assistant_tasks", "knowledge_build_tasks", "coordination_tasks"):
            if table in before:
                assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE status IN ('QUEUED','RUNNING','PENDING','RETRYING')").fetchone()[0] == 0, "Active work exists; retry later"
        for name in ("before", "rehearsal"):
            with closing(sqlite3.connect(out / (name + ".sqlite"))) as backup:
                db.backup(backup)
    spec = importlib.util.spec_from_file_location("fusion_migration", ROOT / "alembic/versions/20261022_0042_coordination_tasks.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(file):
        engine = sa.create_engine("sqlite:///" + Path(file).as_posix())
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        engine.dispose()
        with closing(sqlite3.connect(file)) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        after = counts(file)
        assert all(after[k] == v for k, v in before.items())
        assert after["coordination_tasks"] == 0

    migrate(out / "rehearsal.sqlite")
    migrate(out / "rehearsal.sqlite")
    migrate(path)
    pids = []
    for p, cmd, service_env, cwd in targets:
        p.terminate()
        p.wait(timeout=20)
        service_env["LLM_PREWARM_ENABLED"] = "false"
        with (out / (str(p.pid) + ".log")).open("w", encoding="utf-8") as log:
            child = subprocess.Popen(cmd, cwd=cwd, env=service_env, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        pids.append(child.pid)
        if "--port" in cmd:
            port = cmd[cmd.index("--port") + 1]
            for _ in range(120):
                if child.poll() is not None:
                    raise RuntimeError(f"Service {port} exited; inspect {out}")
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError(f"Service {port} did not become healthy; inspect {out}")
    with (out / "path-worker.log").open("w", encoding="utf-8") as log:
        child = subprocess.Popen([sys.executable, "-m", "services.agent_service.app.services.path_worker"],
                                 cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    pids.append(child.pid)
    for port in (8002, 8005, 8007):
        for _ in range(60):
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Reload failed on {port}; inspect {out}")
    paths = httpx.get("http://127.0.0.1:8002/openapi.json", timeout=10).json()["paths"]
    assert "/agents/coordinate/async" in paths and "/paths/history/{user_id}" in paths
    after = counts(path)
    changed_counts = {k: {"before": v, "after": after[k]} for k, v in before.items() if after[k] != v}
    result = {"pids": pids, "backup_and_rehearsal": True, "existing_counts_preserved": all(after[k] == v for k, v in before.items()),
              "business_counts_preserved": all(k == "worker_instances" for k in changed_counts), "changed_counts": changed_counts,
              "new_tables": sorted(set(after) - set(before)), "model_calls_unchanged": after.get("model_calls") == before.get("model_calls")}
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({**result, "evidence": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
