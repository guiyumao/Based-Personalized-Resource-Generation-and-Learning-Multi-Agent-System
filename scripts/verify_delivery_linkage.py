"""Re-run delivered linkage acceptance using the running service's configuration."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("DELIVERY_LINKAGE_OUT", "artifacts/linkage-20261022/live")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    process = next(
        p
        for p in psutil.process_iter(["cmdline"])
        if "services.teacher_service.app.main:app" in (p.info["cmdline"] or [])
        and "8005" in (p.info["cmdline"] or [])
    )
    os.environ.update(process.environ())
    os.environ["APP_LOAD_DOTENV"] = "false"
    os.environ["CHECKIN_OUT"] = str(OUT / "browser")
    sys.path.insert(0, str(ROOT))
    from common.db.session import engine
    from scripts import verify_checkin_browser, verify_checkin_runtime

    assert engine.dialect.name == "sqlite", "This runner backs up SQLite only"
    database = Path(engine.url.database).resolve()
    with sqlite3.connect(database) as source, sqlite3.connect(OUT / "before.sqlite") as target:
        source.backup(target)

    tables = (
        "users",
        "courses",
        "classrooms",
        "class_enrollments",
        "notifications",
        "platform_daily_checkins",
        "class_sessions",
        "class_schedule_exceptions",
        "personal_schedules",
        "checkin_tasks",
        "checkin_task_submissions",
        "checkin_submission_revisions",
        "attendance_sessions",
        "attendance_records",
        "checkin_audit_logs",
        "model_calls",
    )

    def counts():
        with sqlite3.connect(database) as db:
            existing = {
                r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            return {
                t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                for t in tables
                if t in existing
            }

    before = counts()
    result = {"teacher_pid": process.pid, "http": None, "browser_exit_code": None}
    try:
        capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(capture):
                verify_checkin_runtime.main()
        finally:
            (OUT / "http.log").write_text(capture.getvalue(), encoding="utf-8")
        raw = capture.getvalue()
        payload = json.JSONDecoder().raw_decode(raw[raw.index("{") :])[0]
        result["http"] = payload
        for key, value in payload.items():
            if isinstance(value, bool):
                assert value, key
        assert payload["platform_checkin"] == {
            "before": 0,
            "after": 1,
            "same_record": True,
            "one_per_day": True,
            "no_class_needed": True,
        }
        assert payload["review_status"] == "approved"
        assert payload["attendance_status"] in ("present", "late")
        assert all(value == 1 for value in payload["persisted_rows"].values())
        result["browser_exit_code"] = verify_checkin_browser.main()
        assert result["browser_exit_code"] == 0
    finally:
        after = counts()
        result.update(before_counts=before, after_counts=after, counts_restored=before == after)
        (OUT / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    assert before == after, "Row counts changed; inspect cleanup before proceeding"


if __name__ == "__main__":
    main()
