"""Isolated Alembic upgrade / downgrade / backup-restore drill.

This script NEVER touches the application's configured database. It creates two
throwaway PostgreSQL databases on the local compose Postgres container, runs the
full migration cycle against them, performs a pg_dump/pg_restore round trip, and
then leaves the evidence in ``artifacts/global-testing/``.

Safety rules enforced here:
* The target database name must start with ``learning_system_r4`` — anything else
  aborts before a single statement runs.
* Databases are created and dropped by this script only, and only those two.
* ``alembic downgrade base`` is executed against the drill database only.

Usage:
    python scripts/db_migration_drill.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
DRILL_DB = "learning_system_r4drill"
RESTORE_DB = "learning_system_r4restore"
SAFE_PREFIX = "learning_system_r4"
ARTIFACTS = PROJECT_ROOT / "artifacts" / "global-testing"
DUMP_PATH = ARTIFACTS / "_r4-drill-dump.sql"


def _env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    path = PROJECT_ROOT / ".env"
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


ENV = _env_file()
PG_HOST = ENV.get("POSTGRES_HOST", "127.0.0.1")
PG_PORT = ENV.get("POSTGRES_PORT", "5432")
PG_USER = ENV.get("POSTGRES_USER", "postgres")
PG_PASSWORD = ENV.get("POSTGRES_PASSWORD", "")

ADMIN_URL = f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/postgres"
DRILL_URL = f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{DRILL_DB}"
RESTORE_URL = f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{RESTORE_DB}"

steps: list[dict[str, object]] = []


def _assert_safe(name: str) -> None:
    if not name.startswith(SAFE_PREFIX):
        raise SystemExit(
            f"ABORT: refusing to operate on database {name!r}; "
            f"only {SAFE_PREFIX}* databases are allowed."
        )


def run(cmd: list[str], *, env: dict[str, str] | None = None, label: str = "") -> tuple[int, str]:
    merged = {**os.environ, **(env or {})}
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT, env=merged)
    output = (proc.stdout or "") + (proc.stderr or "")
    steps.append(
        {
            "label": label or " ".join(cmd[:3]),
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "output_tail": output.strip().splitlines()[-25:],
        }
    )
    print(f"--- {label or cmd[0]} (exit {proc.returncode})")
    for line in output.strip().splitlines()[-25:]:
        print(f"    {line}")
    return proc.returncode, output


def psql_sql(sql: str, dbname: str, label: str) -> tuple[int, str]:
    """Run SQL through docker exec psql against a specific database."""

    cmd = [
        "docker",
        "exec",
        "-e",
        f"PGPASSWORD={PG_PASSWORD}",
        "learning-postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        PG_USER,
        "-d",
        dbname,
        "-tAc",
        sql,
    ]
    return run(cmd, label=label)


def table_count(dbname: str) -> int:
    code, out = psql_sql(
        "select count(*) from information_schema.tables "
        "where table_schema='public' and table_type='BASE TABLE'",
        dbname,
        f"table count in {dbname}",
    )
    if code != 0:
        return -1
    match = re.search(r"\d+", out)
    return int(match.group()) if match else -1


def alembic_current(env: dict[str, str]) -> str:
    code, out = run(
        [sys.executable, "-m", "alembic", "current"],
        env=env,
        label="alembic current",
    )
    return out.strip().splitlines()[-1] if out.strip() else ""


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _assert_safe(DRILL_DB)
    _assert_safe(RESTORE_DB)

    print("=" * 72)
    print("Isolated DB migration drill")
    print(f"  drill   : {DRILL_DB}   (isolated, created by this script)")
    print(f"  restore : {RESTORE_DB} (isolated, created by this script)")
    print(f"  live app database is NOT used: {ENV.get('DATABASE_URL', '')!r}")
    print("=" * 72)

    # 0. Recreate both drill databases from scratch.
    for db in (DRILL_DB, RESTORE_DB):
        psql_sql(f'DROP DATABASE IF EXISTS "{db}"', "postgres", f"drop {db}")
        psql_sql(f'CREATE DATABASE "{db}"', "postgres", f"create {db}")

    baseline_tables = table_count(DRILL_DB)

    # 1. upgrade head on the empty drill database
    drill_env = {"DATABASE_URL": DRILL_URL}
    code, _ = run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=drill_env,
        label="alembic upgrade head (empty -> head)",
    )
    upgrade_head_ok = code == 0
    head_tables = table_count(DRILL_DB)
    head_revision = alembic_current(drill_env)

    # 2. downgrade all the way to base (the round-4 addition)
    code, _ = run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        env=drill_env,
        label="alembic downgrade base (head -> empty)",
    )
    downgrade_ok = code == 0
    downgraded_tables = table_count(DRILL_DB)

    # 3. upgrade head again to prove downgrade left a migratable schema
    code, _ = run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=drill_env,
        label="alembic upgrade head (re-apply after downgrade)",
    )
    reupgrade_ok = code == 0
    reupgraded_tables = table_count(DRILL_DB)

    # 4. backup -> restore round trip
    dump_cmd = [
        "docker",
        "exec",
        "-e",
        f"PGPASSWORD={PG_PASSWORD}",
        "learning-postgres",
        "pg_dump",
        "-U",
        PG_USER,
        "-d",
        DRILL_DB,
        "--no-owner",
        "--no-privileges",
    ]
    proc = subprocess.run(dump_cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    DUMP_PATH.write_text(proc.stdout, encoding="utf-8")
    steps.append(
        {
            "label": "pg_dump drill database",
            "command": " ".join(dump_cmd),
            "exit_code": proc.returncode,
            "bytes": len(proc.stdout),
        }
    )
    print(f"--- pg_dump (exit {proc.returncode}) -> {DUMP_PATH.name} ({len(proc.stdout)} bytes)")

    restore_cmd = [
        "docker",
        "exec",
        "-i",
        "-e",
        f"PGPASSWORD={PG_PASSWORD}",
        "learning-postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        PG_USER,
        "-d",
        RESTORE_DB,
    ]
    restore = subprocess.run(
        restore_cmd, input=proc.stdout, capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    steps.append(
        {
            "label": "restore dump into isolated database",
            "command": " ".join(restore_cmd),
            "exit_code": restore.returncode,
            "output_tail": (restore.stdout + restore.stderr).strip().splitlines()[-15:],
        }
    )
    print(f"--- psql restore (exit {restore.returncode})")
    restored_tables = table_count(RESTORE_DB)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "target": f"{PG_HOST}:{PG_PORT} (docker container learning-postgres)",
        "live_app_database_untouched": ENV.get("DATABASE_URL", ""),
        "drill_database": DRILL_DB,
        "restore_database": RESTORE_DB,
        "results": {
            "baseline_tables_empty_db": baseline_tables,
            "upgrade_head": {
                "ok": upgrade_head_ok,
                "tables_after": head_tables,
                "revision": head_revision,
            },
            "downgrade_base": {"ok": downgrade_ok, "tables_after": downgraded_tables},
            "reupgrade_head": {"ok": reupgrade_ok, "tables_after": reupgraded_tables},
            "backup_restore": {
                "dump_bytes": len(proc.stdout),
                "tables_after_restore": restored_tables,
                "restore_exit_code": restore.returncode,
            },
        },
        "steps": steps,
    }
    out = ARTIFACTS / "db-migration-drill.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport written to {out}")
    print(json.dumps(report["results"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
