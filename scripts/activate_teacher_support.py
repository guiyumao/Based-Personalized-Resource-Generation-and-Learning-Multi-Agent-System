"""Rehearse additive teacher support tables, then reload only teacher service."""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/teacher-support-20261022/activation"


def counts(file):
    with sqlite3.connect(file) as db:
        return {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    proc = next(p for p in psutil.process_iter(["cmdline"])
                if "services.teacher_service.app.main:app" in (p.info["cmdline"] or []) and "8005" in (p.info["cmdline"] or []))
    env, command, cwd = proc.environ(), proc.cmdline(), proc.cwd()
    os.environ.update(env)
    os.environ["APP_LOAD_DOTENV"] = "false"
    sys.path.insert(0, str(ROOT))
    database = Path(sa.engine.make_url(env["DATABASE_URL"]).database).resolve()
    assert database == (ROOT / "artifacts/local-start-20261019/runtime.sqlite").resolve()
    before = counts(database)
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        for name in ("before", "rehearsal"):
            with sqlite3.connect(OUT / f"{name}.sqlite") as backup:
                db.backup(backup)
    spec = importlib.util.spec_from_file_location("teacher_support_migration", ROOT / "alembic/versions/20261022_0041_teacher_support.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(file):
        engine = sa.create_engine("sqlite:///" + Path(file).as_posix())
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        engine.dispose()
        after = counts(file)
        assert all(after[k] == v for k, v in before.items())
        assert all(after[t] == 0 for t in ("course_resource_deliveries", "reinforcement_drafts", "reinforcement_attempts"))
        with sqlite3.connect(file) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    migrate(OUT / "rehearsal.sqlite")
    migrate(OUT / "rehearsal.sqlite")  # verify additive creation is idempotent
    migrate(database)
    proc.terminate()
    proc.wait(timeout=15)
    env["LLM_PREWARM_ENABLED"] = "false"
    with (OUT / "teacher.log").open("w", encoding="utf-8") as log:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(60):
        try:
            paths = httpx.get("http://127.0.0.1:8005/openapi.json", timeout=1).json()["paths"]
            if "/teacher/classes/{class_id}/reinforcement-attempts" in paths:
                break
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError("Teacher API reload failed; inspect teacher.log")
    after = counts(database)
    result = {"teacher_pid": child.pid, "backup_and_rehearsal": True,
              "existing_counts_preserved": all(after[k] == v for k, v in before.items()),
              "new_tables": {t: after[t] for t in after if t not in before}}
    (OUT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
