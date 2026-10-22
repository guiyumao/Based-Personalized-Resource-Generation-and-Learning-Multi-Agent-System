"""Activate reviewed a6f5e783 source changes without migrating the live database."""

import json
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/upstream-fusion-a6f5e783/activation"
DB = (ROOT / "artifacts/local-start-20261019/runtime.sqlite").resolve()


def statistics(db):
    return {
        table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        for table in (
            "users",
            "resources",
            "learning_paths",
            "study_notes",
            "notifications",
            "model_calls",
        )
    }


def idle(db):
    return not any(
        db.execute(
            "SELECT COUNT(*) FROM "
            + table
            + " WHERE status IN ('PENDING','QUEUED','RUNNING','CANCEL_REQUESTED')"
        ).fetchone()[0]
        for table in ("assistant_tasks", "knowledge_build_tasks")
    )


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    targets = []
    for p in psutil.process_iter(["name", "cmdline"]):
        args = p.info["cmdline"] or []
        if p.info["name"] != "python.exe":
            continue
        if "services.agent_service.app.services.assistant_worker" in args:
            name = "assistant-and-knowledge-worker"
        elif any(
            module in args
            for module in (
                "services.agent_service.app.main:app",
                "services.evaluation_service.app.main:app",
                "services.teacher_service.app.main:app",
            )
        ):
            name = {"8002": "agent", "8004": "evaluation", "8005": "teacher", "8007": "qa"}.get(
                args[args.index("--port") + 1]
            )
        else:
            continue
        if not name:
            continue
        env = p.environ()
        if (
            env.get("DATABASE_URL") != "sqlite+pysqlite:///" + DB.as_posix()
            or Path(p.cwd()).resolve() != ROOT
        ):
            raise RuntimeError("Unexpected runtime for " + name)
        targets.append((name, p, args, env))
    if {item[0] for item in targets} != {
        "agent",
        "evaluation",
        "teacher",
        "qa",
        "assistant-and-knowledge-worker",
    }:
        raise RuntimeError("Unexpected service inventory")
    with sqlite3.connect(DB) as db:
        if not idle(db):
            raise RuntimeError("Active tasks: reload postponed")
        before = statistics(db)
        with sqlite3.connect(OUT / "before.sqlite") as backup:
            db.backup(backup)
    with sqlite3.connect(OUT / "before.sqlite") as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # Validate again immediately before replacing owned idle processes.
    with sqlite3.connect(DB) as db:
        if not idle(db):
            raise RuntimeError("New active task: reload postponed")
    records = []
    for name, p, args, env in targets:
        p.terminate()
        p.wait(timeout=20)
        if name != "assistant-and-knowledge-worker" and "--lifespan" not in args:
            args = [*args, "--lifespan", "off"]
        env["LLM_PREWARM_ENABLED"] = "false"
        with (
            (OUT / (name + ".stdout.log")).open("w", encoding="utf-8") as stdout,
            (OUT / (name + ".stderr.log")).open("w", encoding="utf-8") as stderr,
        ):
            child = subprocess.Popen(
                args,
                env=env,
                cwd=ROOT,
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        if "--port" in args:
            port = args[args.index("--port") + 1]
            for _ in range(100):
                if child.poll() is not None:
                    raise RuntimeError("Service exited: " + name)
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1).close()
                    break
                except Exception:
                    time.sleep(0.25)
            else:
                raise RuntimeError("Health unavailable: " + name)
        records.append({"name": name, "old_pid": p.pid, "pid": child.pid})
    with sqlite3.connect(DB) as db:
        after = statistics(db)
        assert after == before
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    manifest = ROOT / "artifacts/local-start-20261019/processes.json"
    rows = json.loads(manifest.read_text(encoding="utf-8-sig"))
    for row in rows:
        match = next((item for item in records if item["name"] == row["Name"]), None)
        if match:
            row["PID"] = match["pid"]
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "before": before,
        "after": after,
        "processes": records,
        "migration": False,
        "paid_calls": 0,
    }
    (OUT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
