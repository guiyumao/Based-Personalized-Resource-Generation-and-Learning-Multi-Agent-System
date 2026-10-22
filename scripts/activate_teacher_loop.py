"""Rehearse additive migration on SQLite backup, then explicitly apply and reload teacher."""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import psutil
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/teacher-loop-runtime"
TARGET = ROOT / "artifacts/local-start-20261019/runtime.sqlite"
OUT.mkdir(parents=True, exist_ok=True)


def counts(db):
    return {
        name: db.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
        for name in [
            "users",
            "classrooms",
            "class_enrollments",
            "assignments",
            "assignment_submissions",
            "resources",
            "learning_paths",
            "notifications",
            "model_calls",
        ]
    }


def migrate(file):
    spec = importlib.util.spec_from_file_location(
        "classroom_loop_migration", ROOT / "alembic/versions/20261022_0035_classroom_loop.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite:///" + file.as_posix())
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
    engine.dispose()


if "--apply" not in sys.argv:
    if (OUT / "before.sqlite").exists():
        raise RuntimeError("Rehearsal already exists; inspect instead of overwriting")
    with sqlite3.connect(TARGET) as db:
        before = counts(db)
        assert not any(c[1] == "invite_code" for c in db.execute("PRAGMA table_info(classrooms)"))
        with sqlite3.connect(OUT / "before.sqlite") as copy:
            db.backup(copy)
        with sqlite3.connect(OUT / "rehearsal.sqlite") as copy:
            db.backup(copy)
    migrate(OUT / "rehearsal.sqlite")
    with sqlite3.connect(OUT / "rehearsal.sqlite") as db:
        assert counts(db) == before
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            db.execute(
                'SELECT COUNT(*) FROM classrooms WHERE invite_code IS NULL OR status != "active"'
            ).fetchone()[0]
            == 0
        )
    (OUT / "rehearsal.json").write_text(
        json.dumps(
            {"before": before, "after": before, "integrity": "ok", "old_classes_backfilled": True}
        ),
        encoding="utf-8",
    )
    print("Backup and isolated migration rehearsal passed")
else:
    assert (OUT / "rehearsal.json").exists()
    process = next(
        p
        for p in psutil.process_iter(["cmdline"])
        if "services.teacher_service.app.main:app" in (p.info["cmdline"] or [])
    )
    env, command, cwd = process.environ(), process.cmdline(), process.cwd()
    assert Path(env["DATABASE_URL"].split("///", 1)[1]).resolve() == TARGET.resolve()
    with sqlite3.connect(TARGET) as db:
        active = sum(
            db.execute(
                "SELECT COUNT(*) FROM "
                + table
                + " WHERE status IN ('PENDING','QUEUED','RUNNING','CANCEL_REQUESTED')"
            ).fetchone()[0]
            for table in ["assistant_tasks", "knowledge_build_tasks"]
        )
        assert active == 0, "Active tasks; postpone runtime changes"
        before = counts(db)
        if "--reload-only" not in sys.argv:
            with sqlite3.connect(OUT / "before-apply.sqlite") as copy:
                db.backup(copy)
    if "--reload-only" not in sys.argv:
        migrate(TARGET)
    with sqlite3.connect(TARGET) as db:
        after = counts(db)
        assert before == after
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    process.terminate()
    process.wait(timeout=15)
    if "--lifespan" not in command:
        command += ["--lifespan", "off"]
    env["LLM_PREWARM_ENABLED"] = "false"
    with (OUT / ("teacher-reloaded.log" if "--reload-only" in sys.argv else "teacher.log")).open(
        "w", encoding="utf-8"
    ) as log:
        child = subprocess.Popen(
            command,
            env=env,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    os.environ.update(env)
    os.environ["APP_LOAD_DOTENV"] = "false"
    sys.path.insert(0, str(ROOT))
    import httpx

    from common.db.session import SessionLocal
    from common.models.learning import User
    from common.security.auth import create_access_token

    with SessionLocal() as db:
        uid = db.query(User).filter_by(username="teacher111").one().id
    results = []
    for _ in range(80):
        try:
            if httpx.get("http://127.0.0.1:8005/health", timeout=1).is_success:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    for endpoint in ["/teacher/classes", "/teacher/homework"]:
        r = httpx.get(
            "http://127.0.0.1:8005" + endpoint,
            headers={"Authorization": "Bearer " + create_access_token(str(uid))},
        )
        assert r.status_code == 200, r.text
        results.append({"path": endpoint, "status": r.status_code, "rows": len(r.json()["data"])})
    (OUT / ("reload.json" if "--reload-only" in sys.argv else "applied.json")).write_text(
        json.dumps(
            {"before": before, "after": after, "pid": child.pid, "api": results, "integrity": "ok"}
        ),
        encoding="utf-8",
    )
    print(
        "Applied migration and reloaded teacher service; records preserved; current APIs return 200"
    )
