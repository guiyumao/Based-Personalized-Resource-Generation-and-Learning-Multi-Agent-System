"""Back up and rehearse additive notification migration against the verified runtime.
No Alembic stamp or upgrade of unrelated historical schemas is performed.
"""

import importlib.util
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / (
    "artifacts/notifications-20261021/runtime-final"
    if "--reload-only" in sys.argv
    else "artifacts/notifications-20261021/runtime"
)
TARGET = (ROOT / "artifacts/local-start-20261019/runtime.sqlite").resolve()

if "--output" in sys.argv:
    OUTPUT = ROOT / sys.argv[sys.argv.index("--output") + 1]


def counts(connection):
    return {
        name: connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
        for name in (
            "users",
            "resources",
            "learning_paths",
            "study_notes",
            "notifications",
            "model_calls",
        )
    }


def active(connection):
    return sum(
        connection.execute(
            "SELECT COUNT(*) FROM "
            + name
            + " WHERE status IN ('PENDING','QUEUED','RUNNING','CANCEL_REQUESTED')"
        ).fetchone()[0]
        for name in ("assistant_tasks", "knowledge_build_tasks")
    )


def migrate(path):
    engine = create_engine("sqlite:///" + path.as_posix())
    spec = importlib.util.spec_from_file_location(
        "notification_migration", ROOT / "alembic/versions/20261021_0034_unified_notifications.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        with Operations.context(MigrationContext.configure(db)):
            module.upgrade()
    engine.dispose()


def main():
    if "--apply" not in sys.argv:
        raise SystemExit("Explicit --apply required")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    targets = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        command = process.info["cmdline"] or []
        if process.info["name"] != "python.exe":
            continue
        if "services.teacher_service.app.main:app" in command:
            name = "teacher"
        elif "services.agent_service.app.main:app" in command:
            name = "agent" if command[command.index("--port") + 1] == "8002" else "qa"
        elif "services.agent_service.app.services.assistant_worker" in command:
            name = "assistant-and-knowledge-worker"
        else:
            continue
        env = process.environ()
        expected = "sqlite+pysqlite:///" + TARGET.as_posix()
        if env.get("DATABASE_URL") != expected:
            raise RuntimeError("Unexpected runtime database for " + name)
        targets.append(
            dict(process=process, env=env, command=command, name=name, cwd=process.cwd())
        )
    if {t["name"] for t in targets} != {"teacher", "agent", "qa", "assistant-and-knowledge-worker"}:
        raise RuntimeError("Unexpected process inventory")
    if "--reload-only" in sys.argv:
        with sqlite3.connect(TARGET) as db:
            if active(db):
                raise RuntimeError("Active tasks: postpone reload")
            before = counts(db)
            assert any(c[1] == "event_key" for c in db.execute("PRAGMA table_info(notifications)"))
    else:
        with sqlite3.connect(TARGET) as db:
            if active(db):
                raise RuntimeError("Active tasks: postpone reload")
            before = counts(db)
            if any(c[1] == "event_key" for c in db.execute("PRAGMA table_info(notifications)")):
                raise RuntimeError("Already migrated")
            with sqlite3.connect(OUTPUT / "before.sqlite") as copy:
                db.backup(copy)
        with (
            sqlite3.connect(OUTPUT / "before.sqlite") as db,
            sqlite3.connect(OUTPUT / "rehearsal.sqlite") as copy,
        ):
            db.backup(copy)
        migrate(OUTPUT / "rehearsal.sqlite")
        with sqlite3.connect(OUTPUT / "rehearsal.sqlite") as db:
            assert counts(db) == before
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        with sqlite3.connect(TARGET) as db:
            if active(db):
                raise RuntimeError("New active tasks: postpone reload")
        migrate(TARGET)
    replacements = []
    for item in targets:
        old = item["process"]
        old.terminate()
        try:
            old.wait(timeout=15)
        except psutil.TimeoutExpired:
            raise RuntimeError("Process did not stop") from None
        command = list(item["command"])
        if "-m" in command and "uvicorn" in command and "--lifespan" not in command:
            command += ["--lifespan", "off"]
        item["env"]["LLM_PREWARM_ENABLED"] = "false"
        out = (OUTPUT / (item["name"] + ".stdout.log")).open("w", encoding="utf-8")
        err = (OUTPUT / (item["name"] + ".stderr.log")).open("w", encoding="utf-8")
        child = subprocess.Popen(
            command,
            env=item["env"],
            cwd=item["cwd"],
            stdout=out,
            stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out.close()
        err.close()
        replacements.append(dict(name=item["name"], old_pid=old.pid, pid=child.pid))
        if "--port" in command:
            port = command[command.index("--port") + 1]
            for _ in range(80):
                if child.poll() is not None:
                    raise RuntimeError("Reload exited: " + item["name"])
                try:
                    urllib.request.urlopen(
                        "http://127.0.0.1:" + port + "/health", timeout=1
                    ).close()
                    break
                except Exception:
                    time.sleep(0.25)
            else:
                raise RuntimeError("Health unavailable: " + item["name"])
    with sqlite3.connect(TARGET) as db:
        after = counts(db)
        assert after == before
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # Keep existing launch manifest fields, updating only matching processes.
    manifest = ROOT / "artifacts/local-start-20261019/processes.json"
    records = json.loads(manifest.read_text(encoding="utf-8-sig"))
    for row in records:
        match = next((x for x in replacements if x["name"] == row["Name"]), None)
        if match:
            row["PID"] = match["pid"]
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    result = dict(
        before=before,
        after=after,
        processes=replacements,
        integrity="ok",
        alembic_stamp_changed=False,
        paid_calls=0,
    )
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
