"""Real external-service verification (PostgreSQL / Neo4j / Chroma).

This script is deliberately **separate from pytest**: the ordinary unit suite must
never require Docker.  It performs real connections, real migrations and real
reads/writes against the services this project actually runs, and writes the raw
evidence (commands, exit codes, output tails, verdicts) to

    artifacts/upstream-integration/external-services/

Safety rules enforced here
--------------------------
* Every throwaway PostgreSQL database must start with ``learning_system_verify``;
  anything else aborts before a single statement runs.
* The application's configured ``DATABASE_URL`` is never used as a write target.
* Chroma is exercised against a scratch collection inside a scratch directory, so
  the real knowledge-base index is not modified.
* Child processes receive the overridden environment explicitly, because
  ``common.config.Settings`` reads its values at import time.

Usage
-----
    python scripts/verify_external_services.py                # all three
    python scripts/verify_external_services.py --only postgres
    python scripts/verify_external_services.py --only neo4j --only chroma
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import textwrap
import time
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "upstream-integration" / "external-services"
SCRATCH_DIR = ARTIFACT_DIR / "chroma-scratch"

VERIFY_DB_PREFIX = "learning_system_verify"
VERIFY_DB = f"{VERIFY_DB_PREFIX}_pg"

SUMMARY: list[dict[str, Any]] = []


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #


def env_file_values() -> dict[str, str]:
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


ENV = env_file_values()


def record(label: str, command: list[str] | str, exit_code: int, output: str, **extra: Any) -> dict:
    """One auditable step: the exact command, its exit code and an output tail."""

    entry: dict[str, Any] = {
        "label": label,
        "command": command if isinstance(command, str) else " ".join(command),
        "exit_code": exit_code,
        "output_tail": [line for line in (output or "").strip().splitlines()[-30:]],
    }
    entry.update(extra)
    return entry


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 300,
    label: str = "",
) -> tuple[int, str]:
    merged = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=merged,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return 124, f"TIMEOUT after {timeout}s\n{output}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_child(
    source: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 300,
    name: str = "child",
    python: str | None = None,
) -> tuple[int, str]:
    """Run a self-contained Python snippet in a fresh interpreter.

    The snippet is written to a UTF-8 ``.py`` file instead of being passed through
    ``python -c``: on Windows the command line is re-encoded with the console code
    page, which corrupts the Chinese text this project's data contains.
    """

    child_dir = ARTIFACT_DIR / "_child"
    child_dir.mkdir(parents=True, exist_ok=True)
    path = child_dir / f"{name}.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    # Running a file (rather than ``python -c``) puts the script's own directory on
    # sys.path, so the repository root has to be supplied explicitly.
    child_env = {"PYTHONPATH": str(PROJECT_ROOT), **(env or {})}
    return run([python or sys.executable, str(path)], env=child_env, timeout=timeout)


def _extract_json_line(output: str, key: str) -> Any:
    """Return ``payload[key]`` from the last JSON object printed on stdout."""

    value: Any = None
    for line in (output or "").strip().splitlines():
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and key in payload:
            value = payload[key]
    return value


PINNED_VENV = ARTIFACT_DIR / "chroma-pinned-venv"
PINNED_VENV_BLOCKER = ARTIFACT_DIR / "chroma-pinned-venv-BLOCKED.txt"
#: The constraint declared in pyproject.toml for the pinned Chroma server image.
PINNED_CHROMA_REQUIREMENT = "chromadb>=0.5.5,<1.0"


def _ensure_pinned_chroma_venv(log_lines: list[str]) -> tuple[str | None, str]:
    """Create (once) an isolated venv holding the *declared* chromadb version.

    The verification environment has drifted from ``pyproject.toml``; this venv
    answers the separate question "is the http path sound when the declared
    constraint is honoured?" without mutating the developer's interpreter.

    A previously recorded toolchain blocker is reused instead of re-downloading a
    large dependency tree on every run.
    """

    scripts_dir = PINNED_VENV / ("Scripts" if os.name == "nt" else "bin")
    python_path = scripts_dir / ("python.exe" if os.name == "nt" else "python")
    if PINNED_VENV_BLOCKER.is_file():
        return None, PINNED_VENV_BLOCKER.read_text(encoding="utf-8").strip()
    if python_path.is_file():
        code, out = run(
            [str(python_path), "-c", "import chromadb; print(chromadb.__version__)"],
            timeout=120,
        )
        if code == 0 and out.strip():
            return str(python_path), f"reused venv at {PINNED_VENV} (chromadb {out.strip().splitlines()[-1]})"
        # Half-built venv from an interrupted install: rebuild it rather than
        # reporting a misleading import error from a broken interpreter.
        shutil.rmtree(PINNED_VENV, ignore_errors=True)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    code, out = run(
        [sys.executable, "-m", "venv", str(PINNED_VENV)],
        timeout=300,
    )
    log_lines.append(f"--- create pinned venv (exit {code})\n{out}")
    if code != 0 or not python_path.is_file():
        reason = f"could not create the pinned venv: {out.strip()[-400:]}"
        PINNED_VENV_BLOCKER.write_text(reason, encoding="utf-8")
        return None, reason

    code, out = run(
        [str(python_path), "-m", "pip", "install", "--quiet", PINNED_CHROMA_REQUIREMENT],
        timeout=1800,
    )
    log_lines.append(f"--- pip install '{PINNED_CHROMA_REQUIREMENT}' (exit {code})\n{out}")
    if code != 0:
        tail = " | ".join(line.strip() for line in out.strip().splitlines()[-12:] if line.strip())
        reason = f"BLOCKED: could not install {PINNED_CHROMA_REQUIREMENT} -> {tail[-600:]}"
        PINNED_VENV_BLOCKER.write_text(reason, encoding="utf-8")
        return None, reason

    code, out = run(
        [str(python_path), "-c", "import chromadb; print(chromadb.__version__)"],
        timeout=120,
    )
    version = out.strip().splitlines()[-1] if out.strip() else "unknown"
    return str(python_path), f"{PINNED_CHROMA_REQUIREMENT} -> chromadb {version}"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_artifact(name: str, payload: dict[str, Any]) -> pathlib.Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_log(name: str, text: str) -> pathlib.Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / name
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 1. PostgreSQL
# --------------------------------------------------------------------------- #


def check_postgres() -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    log_lines: list[str] = []
    host = ENV.get("POSTGRES_HOST", "127.0.0.1")
    port = ENV.get("POSTGRES_PORT", "5432")
    user = ENV.get("POSTGRES_USER", "postgres")
    password = ENV.get("POSTGRES_PASSWORD", "")
    admin_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/postgres"
    drill_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{VERIFY_DB}"

    result: dict[str, Any] = {
        "service": "postgresql",
        "target": f"{host}:{port}",
        "live_app_database_untouched": ENV.get("DATABASE_URL", ""),
        "isolated_database": VERIFY_DB,
        "checks": {},
        "steps": steps,
        "ok": False,
    }

    if not VERIFY_DB.startswith(VERIFY_DB_PREFIX):
        raise SystemExit(f"ABORT: refusing to operate on {VERIFY_DB!r}")

    # -- 0. server reachability + version ------------------------------------
    probe = textwrap.dedent(
        f"""
        import sqlalchemy as sa
        engine = sa.create_engine({admin_url!r}, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            print("server_version:", conn.execute(sa.text("show server_version")).scalar())
            print("current_database:", conn.execute(sa.text("select current_database()")).scalar())
        """
    )
    code, out = run_child(probe, timeout=60, name="pg_admin_probe")
    steps.append(record("connect to postgres admin database", "python -c <probe>", code, out))
    log_lines.append(f"--- admin probe (exit {code})\n{out}")
    result["checks"]["server_reachable"] = code == 0
    if code != 0:
        result["blocked_reason"] = "PostgreSQL is not reachable with the configured credentials"
        return result

    # -- 1. isolated database -------------------------------------------------
    reset = textwrap.dedent(
        f"""
        import sqlalchemy as sa
        engine = sa.create_engine({admin_url!r}, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            conn.execute(sa.text('DROP DATABASE IF EXISTS "{VERIFY_DB}"'))
            conn.execute(sa.text('CREATE DATABASE "{VERIFY_DB}"'))
            print("created", "{VERIFY_DB}")
        """
    )
    code, out = run_child(reset, timeout=120, name="pg_create_isolated_db")
    steps.append(record(f"recreate isolated database {VERIFY_DB}", "python -c <ddl>", code, out))
    log_lines.append(f"--- recreate isolated db (exit {code})\n{out}")
    result["checks"]["isolated_database_created"] = code == 0
    if code != 0:
        return result

    # -- 2. alembic upgrade head using the project's own configuration --------
    code, out = run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={"DATABASE_URL": drill_url},
        timeout=300,
        label="alembic upgrade head",
    )
    steps.append(record("alembic upgrade head (empty -> head)", "alembic upgrade head", code, out))
    log_lines.append(f"--- alembic upgrade head (exit {code})\n{out}")
    result["checks"]["alembic_upgrade_head"] = code == 0

    code, out = run(
        [sys.executable, "-m", "alembic", "current"],
        env={"DATABASE_URL": drill_url},
        timeout=120,
    )
    steps.append(record("alembic current", "alembic current", code, out))
    revision_lines = [
        line.strip()
        for line in out.strip().splitlines()
        if line.strip() and not line.strip().startswith(("INFO", "WARN", "DEBUG"))
    ]
    revision = revision_lines[-1] if revision_lines else ""
    result["checks"]["alembic_revision"] = revision
    log_lines.append(f"--- alembic current (exit {code})\n{out}")

    # -- 3. core tables created + write + read --------------------------------
    rw = textwrap.dedent(
        f"""
        import json
        import sqlalchemy as sa
        from sqlalchemy import text
        engine = sa.create_engine({drill_url!r})
        core = ("users", "user_profiles", "resources", "knowledge_points", "learning_paths", "alembic_version")
        with engine.connect() as conn:
            present = {{
                name: bool(conn.execute(text(
                    "select 1 from information_schema.tables where table_schema='public' and table_name=:n"
                ), {{"n": name}}).scalar())
                for name in core
            }}
            total = conn.execute(text(
                "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'"
            )).scalar()
        print("core_tables:", json.dumps(present, ensure_ascii=False))
        print("total_tables:", total)
        if not all(present.values()):
            raise SystemExit("core tables missing: " + json.dumps(present))
        """
    )
    code, out = run_child(rw, timeout=120, name="pg_core_tables")
    steps.append(record("core tables present after migration", "python -c <inspect>", code, out))
    log_lines.append(f"--- core table inspection (exit {code})\n{out}")
    result["checks"]["core_tables_present"] = code == 0

    roundtrip = textwrap.dedent(
        """
        import json
        from uuid import uuid4
        from common.db.session import SessionLocal
        from common.models.learning import KnowledgePoint, Resource, User
        from common.security.auth import hash_password, verify_password

        suffix = uuid4().hex[:8]
        db = SessionLocal()
        try:
            user = User(username=f"verify_pg_{suffix}", password_hash=hash_password("verify"),
                        role="student", email=f"verify_pg_{suffix}@example.com")
            db.add(user)
            db.flush()
            point = KnowledgePoint(name=f"verify-{suffix}", description="pg round trip", difficulty=1, importance=1)
            db.add(point)
            db.flush()
            resource = Resource(title="verify-resource", type="mind_map",
                                content="# verify", format="json",
                                knowledge_point_id=point.id, generated_for_user_id=user.id,
                                audit_status="passed", structured_json=json.dumps({"ok": True}))
            db.add(resource)
            db.commit()
            resource_id, point_id, user_id = resource.id, point.id, user.id

            # read back through fresh queries (not the identity map)
            db.expire_all()
            read_user = db.query(User).filter(User.id == user_id).one()
            read_resource = db.query(Resource).filter(Resource.id == resource_id).one()
            print("user_id:", read_user.id, "role:", read_user.role)
            print("resource_id:", read_resource.id, "type:", read_resource.type,
                  "structured_json:", read_resource.structured_json)
            print("password_verified:", verify_password("verify", read_user.password_hash))

            # delete in dependency order; knowledge_points is referenced by resources
            db.query(Resource).filter(Resource.id == resource_id).delete(synchronize_session=False)
            db.flush()
            db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).delete(synchronize_session=False)
            db.flush()
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()

            db.expire_all()
            print("rows_after_cleanup:", db.query(Resource).filter(Resource.id == resource_id).count())
        finally:
            db.close()
        """
    )
    code, out = run_child(roundtrip, env={"DATABASE_URL": drill_url}, timeout=180, name="pg_round_trip")
    steps.append(record("write + read core rows (users/resources)", "python -c <roundtrip>", code, out))
    log_lines.append(f"--- core read/write round trip (exit {code})\n{out}")
    result["checks"]["core_read_write"] = code == 0

    # -- 4. a real service starts against the migrated database ---------------
    service_port = free_port()
    service_log = ARTIFACT_DIR / "postgres-service-startup.log"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    service_env = {
        **os.environ,
        "DATABASE_URL": drill_url,
        "USER_SERVICE_PORT": str(service_port),
    }
    startup_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "services.user_service.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(service_port),
    ]
    handle = subprocess.Popen(
        startup_command,
        cwd=PROJECT_ROOT,
        env=service_env,
        stdout=service_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    healthy = False
    health_body = ""
    deadline = time.time() + 60
    try:
        import urllib.error
        import urllib.request

        while time.time() < deadline:
            if handle.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{service_port}/health", timeout=2
                ) as response:
                    health_body = response.read().decode("utf-8")
                    healthy = response.status == 200
                    if healthy:
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
    finally:
        handle.terminate()
        try:
            handle.wait(timeout=20)
        except subprocess.TimeoutExpired:
            handle.kill()

    service_output = service_log.read_text(encoding="utf-8") if service_log.is_file() else ""
    steps.append(
        record(
            "uvicorn user-service against the migrated database",
            " ".join(startup_command),
            0 if healthy else 1,
            service_output,
            health_body=health_body,
        )
    )
    log_lines.append(f"--- service startup health={healthy} body={health_body}\n{service_output[-2000:]}")
    result["checks"]["service_starts_after_migration"] = healthy

    result["ok"] = all(
        bool(result["checks"].get(key))
        for key in (
            "server_reachable",
            "isolated_database_created",
            "alembic_upgrade_head",
            "core_tables_present",
            "core_read_write",
            "service_starts_after_migration",
        )
    )
    write_log("postgres.log", "\n".join(log_lines))
    return result


# --------------------------------------------------------------------------- #
# 2. Neo4j
# --------------------------------------------------------------------------- #


def check_neo4j() -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    log_lines: list[str] = []
    uri = ENV.get("NEO4J_URI", "bolt://localhost:7687")
    user = ENV.get("NEO4J_USERNAME", "neo4j")
    password = ENV.get("NEO4J_PASSWORD", "")

    result: dict[str, Any] = {
        "service": "neo4j",
        "target": uri,
        "checks": {},
        "steps": steps,
        "ok": False,
    }

    # -- 1. connect + authenticate + real Cypher write/read/delete -------------
    cypher = textwrap.dedent(
        f"""
        import json
        import time
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver({uri!r}, auth=({user!r}, {password!r}), connection_timeout=5)
        started = time.perf_counter()
        driver.verify_connectivity()
        print("verify_connectivity_ok seconds:", round(time.perf_counter() - started, 3))

        marker = "verify-upstream-integration"
        with driver.session() as session:
            row = session.run("RETURN 1 AS ok").single()
            print("basic_cypher:", row["ok"])
            session.run(
                "MERGE (n:VerifyProbe {{marker: $marker}}) SET n.at = timestamp() RETURN n",
                marker=marker,
            ).consume()
            read = session.run(
                "MATCH (n:VerifyProbe {{marker: $marker}}) RETURN n.marker AS marker, n.at AS at",
                marker=marker,
            ).single()
            print("write_read:", read["marker"], bool(read["at"]))
            session.run("MATCH (n:VerifyProbe {{marker: $marker}}) DELETE n", marker=marker).consume()
            remaining = session.run(
                "MATCH (n:VerifyProbe {{marker: $marker}}) RETURN count(n) AS c", marker=marker
            ).single()["c"]
            print("cleanup_remaining:", remaining)
        driver.close()
        """
    )
    code, out = run_child(cypher, timeout=120, name="neo4j_connectivity")
    steps.append(record("connect / auth / Cypher write-read-delete", "python -c <neo4j probe>", code, out))
    log_lines.append(f"--- neo4j connectivity (exit {code})\n{out}")
    result["checks"]["connect_auth_cypher"] = code == 0

    # -- 2. a dead endpoint must degrade, not raise a driver error ------------
    dead_env = {
        "NEO4J_URI": "bolt://127.0.0.1:7699",
        "NEO4J_ENABLED": "true",
        "NEO4J_CONNECTION_TIMEOUT_SECONDS": "0.5",
        "NEO4J_QUERY_TIMEOUT_SECONDS": "0.5",
        "NEO4J_FAILURE_THRESHOLD": "1",
        "NEO4J_COOLDOWN_SECONDS": "60",
        "GRAPH_LLM_ENRICH_ENABLED": "false",
        "DATABASE_URL": ENV.get("DATABASE_URL", "sqlite+pysqlite:///./learning_system.db"),
    }
    graph_degradation = textwrap.dedent(
        """
        import json
        import time

        from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
        from services.agent_service.app.connectors.neo4j_connector import (
            KnowledgeGraphRepository as Repo,
        )

        repo = Repo()
        print(json.dumps({"driver_created_for_dead_endpoint": repo._driver is not None}))

        # A closed local port must be reported unreachable within the bound.
        started = time.perf_counter()
        reachable = Repo._neo4j_reachable(type("S", (), {
            "neo4j_uri": "bolt://127.0.0.1:7699",
            "neo4j_connection_timeout_seconds": 0.5,
        })())
        preflight_seconds = round(time.perf_counter() - started, 3)
        print(json.dumps({
            "preflight_reachable_for_closed_port": reachable,
            "preflight_seconds": preflight_seconds,
        }))
        if reachable:
            raise SystemExit("a closed port must not be reported reachable")
        if preflight_seconds > 5:
            raise SystemExit(f"preflight exceeded its bound: {preflight_seconds}s")

        # After the configured failure threshold the breaker must be open, so a
        # request path does not even attempt a connection.
        Repo._record_neo4j_failure()
        print(json.dumps({"breaker_open_after_failures": not Repo._neo4j_available()}))
        if Repo._neo4j_available():
            raise SystemExit("breaker did not open after the configured threshold")
        """
    )
    code, out = run_child(graph_degradation, env=dead_env, timeout=180, name="neo4j_dead_endpoint")
    steps.append(
        record(
            "closed endpoint (bolt://127.0.0.1:7699) -> preflight + breaker",
            "NEO4J_URI=bolt://127.0.0.1:7699 python -c <degradation probe>",
            code,
            out,
        )
    )
    log_lines.append(f"--- neo4j dead-endpoint degradation (exit {code})\n{out}")
    result["checks"]["degrades_when_unavailable"] = code == 0

    # -- 3. a server that accepts but never answers must stay bounded ---------
    silent_server = textwrap.dedent(
        """
        import json
        import os
        import socket
        import threading
        import time

        # A purely local "silent" Bolt endpoint: the TCP handshake completes and
        # then nothing is ever written, which is exactly what an overloaded or
        # firewalled Neo4j looks like to the client.
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(8)
        port = server.getsockname()[1]
        stop = threading.Event()

        def _accept_forever():
            while not stop.is_set():
                try:
                    conn, _ = server.accept()
                except OSError:
                    return

                def _hold(connection):
                    try:
                        time.sleep(60)
                    finally:
                        connection.close()

                threading.Thread(target=_hold, args=(conn,), daemon=True).start()

        threading.Thread(target=_accept_forever, daemon=True).start()

        # Settings are read when common.config is first imported, so the override
        # must be in place before the connector (and therefore the settings) load.
        os.environ["NEO4J_URI"] = f"bolt://127.0.0.1:{port}"

        from common.config import get_settings
        from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository

        settings = get_settings()
        print(json.dumps({
            "uri": settings.neo4j_uri,
            "connection_timeout": settings.neo4j_connection_timeout_seconds,
            "query_timeout": settings.neo4j_query_timeout_seconds,
        }))

        repo = KnowledgeGraphRepository()
        try:
            started = time.perf_counter()
            error = None
            try:
                repo._neo4j_run("RETURN 1 AS ok")
            except Exception as exc:  # noqa: BLE001 - boundedness is the assertion
                error = type(exc).__name__
            elapsed = round(time.perf_counter() - started, 3)
            print(json.dumps({"silent_endpoint_error": error, "seconds": elapsed}))
            if error is None:
                raise SystemExit("a silent endpoint must not be treated as a successful query")
            if elapsed > 8:
                raise SystemExit(f"a silent Neo4j blocked the caller for {elapsed}s")
        finally:
            stop.set()
            try:
                server.close()
            except OSError:
                pass
            repo.close()
        """
    )
    silent_env = {
        **dead_env,
        "DATABASE_URL": ENV.get("DATABASE_URL", "sqlite+pysqlite:///./learning_system.db"),
    }
    code, out = run_child(silent_server, env=silent_env, timeout=180, name="neo4j_silent_endpoint")
    steps.append(
        record(
            "silent endpoint (accepts, never replies) -> bounded query timeout",
            "NEO4J_URI=bolt://127.0.0.1:<ephemeral> python -c <silent server probe>",
            code,
            out,
        )
    )
    log_lines.append(f"--- neo4j silent-endpoint timeout (exit {code})\n{out}")
    result["checks"]["timeout_bounded"] = code == 0

    # -- 4. the documented fallback still answers with Neo4j down -------------
    fallback_db = ARTIFACT_DIR / "neo4j-degrade-scratch.db"
    if fallback_db.exists():
        fallback_db.unlink()
    fallback_url = f"sqlite+pysqlite:///{fallback_db.as_posix()}"
    fallback = textwrap.dedent(
        """
        import json

        from common.db.bootstrap import ensure_database_schema
        from common.db.session import SessionLocal
        from common.models.learning import KnowledgePoint, KnowledgeRelation
        from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository

        ensure_database_schema()
        with SessionLocal() as db:
            source = KnowledgePoint(name="验证-前置知识目标", description="", difficulty=1, importance=1)
            target = KnowledgePoint(name="验证-前置知识基础", description="", difficulty=1, importance=1)
            db.add_all([source, target])
            db.flush()
            db.add(KnowledgeRelation(from_id=source.id, to_id=target.id, relation_type="DEPENDS_ON"))
            db.commit()

        paths = KnowledgeGraphRepository().find_dependency_path("验证-前置知识目标", max_depth=2)
        print(json.dumps({"paths": paths}, ensure_ascii=False))
        flattened = [p.get("path") for p in paths]
        if ["验证-前置知识目标", "验证-前置知识基础"] not in flattened:
            raise SystemExit("SQL fallback did not produce the stored dependency")
        """
    )
    code, out = run_child(
        fallback,
        env={**dead_env, "DATABASE_URL": fallback_url},
        timeout=300,
        name="neo4j_sql_fallback",
    )
    steps.append(
        record(
            "Neo4j down -> SQL fallback still returns stored dependencies",
            "NEO4J_URI=bolt://127.0.0.1:7699 DATABASE_URL=<scratch sqlite> python -c <fallback probe>",
            code,
            out,
        )
    )
    log_lines.append(f"--- neo4j SQL fallback (exit {code})\n{out}")
    result["checks"]["sql_fallback_serves_graph_data"] = code == 0
    try:
        if fallback_db.exists():
            fallback_db.unlink()
    except OSError:
        pass

    result["ok"] = all(
        bool(result["checks"].get(key))
        for key in (
            "connect_auth_cypher",
            "degrades_when_unavailable",
            "timeout_bounded",
            "sql_fallback_serves_graph_data",
        )
    )
    write_log("neo4j.log", "\n".join(log_lines))
    return result


# --------------------------------------------------------------------------- #
# 3. Chroma
# --------------------------------------------------------------------------- #


def check_chroma() -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    log_lines: list[str] = []
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "service": "chroma",
        "checks": {},
        "steps": steps,
        "ok": False,
    }

    # -- 1. configured mode matches the client that is actually built ---------
    mode_probe = textwrap.dedent(
        """
        import json
        from common.config import get_settings
        from services.agent_service.app.services.rag import ChromaRetriever

        settings = get_settings()
        retriever = ChromaRetriever()
        client = retriever.client
        client_ok = client is not None
        module = type(client).__module__ if client_ok else ""
        print(json.dumps({
            "configured_mode": settings.chroma_mode,
            "configured_host": settings.chroma_host,
            "configured_port": settings.chroma_port,
            "persist_directory": settings.chroma_persist_directory,
            "collection_name": settings.chroma_collection_name,
            "collection_version": settings.chroma_collection_version,
            "client_class": type(client).__name__ if client_ok else None,
            "client_module": module,
            "collection_available": retriever.is_available,
            "described": retriever.describe(),
        }, ensure_ascii=False, default=str))
        if settings.chroma_mode == "http" and "HttpClient" not in type(client).__name__:
            raise SystemExit("CHROMA_MODE=http but the client is not an HTTP client")
        if settings.chroma_mode == "persistent" and "HttpClient" in type(client).__name__:
            raise SystemExit("CHROMA_MODE=persistent but the client is an HTTP client")
        """
    )
    code, out = run_child(mode_probe, timeout=180, name="chroma_mode")
    steps.append(record("configured mode vs actual client", "python <chroma_mode.py>", code, out))
    log_lines.append(f"--- chroma mode (exit {code})\n{out}")
    result["checks"]["mode_matches_config"] = code == 0
    configured_mode = ""
    for line in out.strip().splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                configured_mode = json.loads(line).get("configured_mode", "")
            except json.JSONDecodeError:
                configured_mode = ""
    result["configured_mode"] = configured_mode

    # -- 2. persistent-mode collection: create / write / query / chunk return --
    scratch = SCRATCH_DIR / "persistent"
    write_query = textwrap.dedent(
        """
        import json

        from services.agent_service.app.services.rag import ChromaRetriever

        retriever = ChromaRetriever()
        collection = retriever.collection
        if collection is None:
            raise SystemExit("collection is unavailable in the configured mode")

        ids = ["verify-doc-1", "verify-doc-2"]
        documents = [
            "循环结构：for 循环用于遍历序列，while 循环按条件重复执行。",
            "二分查找必须在有序数组上进行，每次比较把区间折半。",
        ]
        metadatas = [
            {"source_id": "verify-src-1", "knowledge_point_name": "循环结构", "subject": "python"},
            {"source_id": "verify-src-2", "knowledge_point_name": "二分查找", "subject": "algorithms"},
        ]
        retriever.upsert_documents(ids=ids, documents=documents, metadatas=metadatas)
        stored = collection.get(ids=ids, include=["documents", "metadatas"])
        print("stored_ids:", json.dumps(stored.get("ids")))

        hits = retriever.retrieve_with_metadata("循环结构 for 循环", top_k=2, retrieval_mode="vector")
        print("hit_count:", len(hits))
        if hits:
            first = hits[0]
            print("first_hit_keys:", json.dumps(sorted(first.keys())))
            print("first_hit_source_id:", (first.get("metadata") or {}).get("source_id"))
            print("first_hit_content_prefix:", str(first.get("content") or "")[:40])
            if not first.get("content"):
                raise SystemExit("a retrieved chunk must carry its content")
            if not (first.get("metadata") or {}).get("source_id"):
                raise SystemExit("a retrieved chunk must carry its source metadata")
        else:
            raise SystemExit("query returned no chunks after an upsert")

        retriever.delete_documents(ids=ids)
        after = collection.get(ids=ids)
        print("ids_after_delete:", json.dumps(after.get("ids")))
        """
    )
    persistent_env = {
        "CHROMA_MODE": "persistent",
        "CHROMA_PERSIST_DIRECTORY": str(scratch),
        "CHROMA_COLLECTION_NAME": "verify_upstream_integration",
        "CHROMA_COLLECTION_VERSION": "verify",
        "RAG_LEXICAL_FAST_PATH": "false",
    }
    code, out = run_child(
        write_query,
        env=persistent_env,
        timeout=300,
        name="chroma_persistent_round_trip",
    )
    steps.append(
        record(
            "persistent mode: create / upsert / query / source chunk / delete",
            "CHROMA_MODE=persistent python <chroma_persistent_round_trip.py>",
            code,
            out,
        )
    )
    log_lines.append(f"--- chroma persistent round trip (exit {code})\n{out}")
    result["checks"]["collection_write_query_chunks"] = code == 0

    # -- 3. http mode: is the *installed* client compatible with the server? ---
    #
    # This is a genuine compatibility question, not a formality. ``pyproject.toml``
    # pins ``chromadb>=0.5.5,<1.0`` because the 1.x client speaks ``/api/v2`` while
    # the pinned server image only serves ``/api/v1``; a drifted environment that
    # installed chromadb 1.x therefore cannot use ``CHROMA_MODE=http`` at all.
    # The failure is recorded as a failure and re-tested below with the version
    # the project actually declares.
    CHROMA_HTTP_HOST = ENV.get("CHROMA_HTTP_HOST", "127.0.0.1")
    CHROMA_HTTP_PORT = ENV.get("CHROMA_HTTP_PORT", "8010")
    http_probe = textwrap.dedent(
        """
        import json
        import os
        import urllib.error
        import urllib.request

        import chromadb

        HOST = os.environ["CHROMA_HTTP_HOST"]
        PORT = os.environ["CHROMA_HTTP_PORT"]

        server_version = None
        try:
            raw = urllib.request.urlopen(
                f"http://{HOST}:{PORT}/api/v1/version", timeout=10
            ).read().decode()
            server_version = json.loads(raw)
            hb = urllib.request.urlopen(
                f"http://{HOST}:{PORT}/api/v1/heartbeat", timeout=10
            ).read().decode()
            print("server_version_payload:", raw.strip())
            print("heartbeat_payload:", hb.strip())
        except (urllib.error.URLError, OSError) as exc:
            print("server_unreachable:", exc)

        client_version = getattr(chromadb, "__version__", "unknown")
        print("client_version:", client_version)
        print(json.dumps({
            "server_version": server_version,
            "client_version": client_version,
            "client_major": client_version.split(".")[0],
        }))

        client = chromadb.HttpClient(host=HOST, port=PORT)
        collection = client.get_or_create_collection(
            name="verify_upstream_http", metadata={"collection_version": "verify"}
        )
        collection.upsert(
            ids=["http-1"],
            documents=["计算机网络：TCP 三次握手建立可靠连接。"],
            metadatas=[{"source_id": "verify-http-src"}],
        )
        got = collection.get(ids=["http-1"], include=["documents", "metadatas"])
        print("http_stored_ids:", json.dumps(got.get("ids")))
        queried = collection.query(
            query_texts=["TCP 三次握手"], n_results=1, include=["documents", "metadatas"]
        )
        print("http_query_ids:", json.dumps(queried.get("ids")))
        if not queried.get("ids") or not queried["ids"][0]:
            raise SystemExit("http-mode query returned nothing after an upsert")
        docs = queried.get("documents") or [[]]
        metas = queried.get("metadatas") or [[]]
        print("http_query_doc_prefix:", str(docs[0][0])[:40])
        print("http_query_source_id:", (metas[0][0] or {}).get("source_id"))

        client.delete_collection("verify_upstream_http")
        print("http_scratch_collection_deleted:", True)
        """
    )
    http_env = {"CHROMA_HTTP_HOST": CHROMA_HTTP_HOST, "CHROMA_HTTP_PORT": CHROMA_HTTP_PORT}
    code, out = run_child(
        http_probe, env=http_env, timeout=300, name="chroma_http_round_trip"
    )
    installed_client_version = _extract_json_line(out, "client_version") or ""
    steps.append(
        record(
            f"CHROMA_MODE=http against {CHROMA_HTTP_HOST}:{CHROMA_HTTP_PORT} "
            "with the interpreter's installed chromadb",
            "python <chroma_http_round_trip.py>",
            code,
            out,
        )
    )
    log_lines.append(f"--- chroma http round trip, installed client (exit {code})\n{out}")
    result["checks"]["http_mode_client_server_compatible"] = code == 0
    result["installed_chromadb_version"] = installed_client_version
    result["installed_client_traceback"] = [line for line in out.strip().splitlines() if line.strip()][-6:]

    # -- 3a. the running server's own v1 REST API -----------------------------
    #
    # This isolates the failure: if the server answers the v1 REST contract
    # correctly, then the incompatibility is purely the installed client's
    # protocol major, not a broken server.
    server_v1 = textwrap.dedent(
        """
        import json
        import os
        import urllib.error
        import urllib.request

        BASE = f"http://{os.environ['CHROMA_HTTP_HOST']}:{os.environ['CHROMA_HTTP_PORT']}/api/v1"
        NAME = "verify_upstream_v1_raw"

        def call(method, path, payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            request = urllib.request.Request(
                f"{BASE}{path}", data=data, method=method,
                headers={"content-type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read().decode()
                return response.status, (json.loads(body) if body.strip() else None)
            except urllib.error.HTTPError as exc:
                print(f"HTTP {exc.code} on {method} {path}: {exc.read().decode()[:400]}")
                raise

        print("version:", urllib.request.urlopen(f"{BASE}/version", timeout=10).read().decode().strip())
        try:
            call("DELETE", f"/collections/{NAME}")
        except urllib.error.HTTPError:
            pass

        status, collection = call(
            "POST", "/collections", {"name": NAME, "metadata": {"collection_version": "verify"}, "get_or_create": True}
        )
        collection_id = collection["id"]
        print("create_collection_status:", status, "id:", collection_id)

        status, _ = call(
            "POST",
            f"/collections/{collection_id}/add",
            {
                "ids": ["v1-1"],
                "documents": ["计算机网络：TCP 三次握手建立可靠连接。"],
                "metadatas": [{"source_id": "verify-v1-src"}],
            },
        )
        print("add_status:", status)

        # The 0.5.x REST layer stores the embedding for a text add, and its mirror
        # of the Python client is that /query expects *embeddings*, not texts.
        status, fetched = call(
            "POST",
            f"/collections/{collection_id}/get",
            {"include": ["documents", "metadatas"]},
        )
        print("get_status:", status, "ids:", json.dumps((fetched or {}).get("ids")))
        docs = (fetched or {}).get("documents") or []
        metas = (fetched or {}).get("metadatas") or []
        if not (fetched or {}).get("ids"):
            raise SystemExit("the v1 REST API did not return the stored document")
        print("get_doc_prefix:", str(docs[0])[:40])
        print("get_source_id:", (metas[0] or {}).get("source_id"))

        status, queried = call(
            "POST",
            f"/collections/{collection_id}/query",
            {
                "query_embeddings": [[0.05] * 384],
                "n_results": 1,
                "include": ["documents", "metadatas"],
            },
        )
        ids = (queried or {}).get("ids") or [[]]
        print("query_status:", status, "ids:", json.dumps(ids))
        # The raw REST layer mirrors the Python client and expects a *pre-computed*
        # embedding; a synthetic vector is expected to miss. This is recorded as an
        # observation (the app's own vector query path is exercised separately in
        # persistent mode), not as a server defect.
        print("query_synthetic_embedding_hits:", len(ids[0]) if ids else 0)

        status, _ = call("DELETE", f"/collections/{NAME}")
        print("delete_collection_status:", status)
        """
    )
    code, out = run_child(server_v1, env=http_env, timeout=300, name="chroma_server_v1_rest")
    steps.append(
        record(
            f"running Chroma server v1 REST API at {CHROMA_HTTP_HOST}:{CHROMA_HTTP_PORT}",
            "python <chroma_server_v1_rest.py>",
            code,
            out,
        )
    )
    log_lines.append(f"--- chroma server v1 REST API (exit {code})\n{out}")
    result["checks"]["server_v1_rest_works"] = code == 0

    # -- 3b. the same probe with the dependency version the project declares ---
    pinned_python, pinned_note = _ensure_pinned_chroma_venv(log_lines)
    if pinned_python is None:
        result["checks"]["http_mode_with_pinned_client"] = False
        result["pinned_client_note"] = pinned_note
        result["pinned_client_status"] = "blocked" if pinned_note.startswith("BLOCKED") else "failed"
        steps.append(
            record(
                "CHROMA_MODE=http with the declared chromadb constraint",
                "python -m venv + pip install 'chromadb>=0.5.5,<1.0'",
                1,
                pinned_note,
            )
        )
    else:
        code, out = run_child(
            http_probe,
            env=http_env,
            timeout=300,
            name="chroma_http_round_trip_pinned",
            python=pinned_python,
        )
        steps.append(
            record(
                "CHROMA_MODE=http with the declared chromadb constraint ('chromadb>=0.5.5,<1.0')",
                f"{pinned_python} <chroma_http_round_trip_pinned.py>",
                code,
                out,
            )
        )
        log_lines.append(f"--- chroma http round trip, pinned client (exit {code})\n{out}")
        result["checks"]["http_mode_with_pinned_client"] = code == 0
        result["pinned_client_note"] = pinned_note
        result["pinned_client_status"] = "ran" if code == 0 else "failed"

    # -- 4. no evidence must produce insufficient_evidence, not fabricated sources
    no_evidence = textwrap.dedent(
        """
        import json

        from services.agent_service.app.services.content_validation import (
            validate_generated_resource,
        )

        # Structurally valid courseware, so the ONLY stage that can fail is the
        # source stage: nothing was retrieved, so nothing may be cited.
        content = (
            "# 循环结构\\n\\n"
            "## 学习目标\\n学完后能够说明 for 与 while 的区别，并能独立写出一个累加循环。\\n\\n"
            "## 知识讲解\\n循环用于在满足条件时重复执行同一段语句，for 适合已知次数的遍历，"
            "while 适合由条件驱动的重复。\\n\\n"
            "## 示例\\n例如对 1 到 5 求和，可以先初始化累加变量，再逐项相加。\\n\\n"
            "## 小结\\nfor 与 while 都能表达重复，选择取决于次数是否已知。\\n\\n"
            "## 自测\\n请写出一个用 while 计算阶乘的函数。\\n"
        )
        report = validate_generated_resource(
            resource_type="courseware",
            content=content,
            payload=None,
            knowledge_point="",
            source_chunks=[],
            title="循环结构",
        )
        print("structure_passed:", report["structure_passed"])
        print("verdict:", report["verdict"])
        print("source_passed:", report["source_passed"])
        print("citations:", json.dumps(report["citations"], ensure_ascii=False))
        if not report["structure_passed"]:
            raise SystemExit("the probe content must pass the structural contract")
        if report["verdict"] != "insufficient_evidence":
            raise SystemExit(f"expected insufficient_evidence, got {report['verdict']}")
        if report["citations"]:
            raise SystemExit("no retrieval happened, so no citation may be produced")
        """
    )
    code, out = run_child(
        no_evidence,
        env=persistent_env,
        timeout=120,
        name="chroma_insufficient_evidence",
    )
    steps.append(
        record(
            "no retrieval hits -> insufficient_evidence (no fabricated sources)",
            "python <chroma_insufficient_evidence.py>",
            code,
            out,
        )
    )
    log_lines.append(f"--- insufficient_evidence probe (exit {code})\n{out}")
    result["checks"]["insufficient_evidence"] = code == 0

    result["ok"] = all(
        bool(result["checks"].get(key))
        for key in (
            "mode_matches_config",
            "collection_write_query_chunks",
            "server_v1_rest_works",
            "http_mode_client_server_compatible",
            "http_mode_with_pinned_client",
            "insufficient_evidence",
        )
    )
    if not result["checks"].get("http_mode_client_server_compatible"):
        notes = [
            "The installed chromadb speaks the /api/v2 protocol while the running server "
            "image only serves /api/v1, so CHROMA_MODE=http fails in this interpreter.",
            "pyproject.toml already pins 'chromadb>=0.5.5,<1.0'; this environment does not "
            "honour it.",
            "The server itself answers the v1 REST contract correctly (see "
            "'server_v1_rest_works'), so the incompatibility is client-side only.",
        ]
        if result.get("pinned_client_status") == "blocked":
            notes.append(
                "Re-running the probe with the declared constraint is BLOCKED here: "
                + str(result.get("pinned_client_note"))
            )
        result["blocked_reason"] = " ".join(notes)
    write_log("chroma.log", "\n".join(log_lines))
    return result


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

CHECKS = {
    "postgres": check_postgres,
    "neo4j": check_neo4j,
    "chroma": check_chroma,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(CHECKS),
        help="run only the named check(s); default is all three",
    )
    args = parser.parse_args()
    selected = args.only or sorted(CHECKS)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()

    for name in selected:
        print("=" * 78)
        print(f"verifying {name} ...")
        print("=" * 78)
        try:
            payload = CHECKS[name]()
        except SystemExit as exc:
            payload = {"service": name, "ok": False, "error": str(exc), "checks": {}, "steps": []}
        except Exception as exc:  # noqa: BLE001 - a verifier must record, not crash
            payload = {
                "service": name,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "checks": {},
                "steps": [],
            }
        write_artifact(f"{name}.json", payload)
        SUMMARY.append(
            {
                "service": payload.get("service", name),
                "ok": bool(payload.get("ok")),
                "checks": payload.get("checks", {}),
                "error": payload.get("error"),
            }
        )
        print(f"-> {name}: {'PASS' if payload.get('ok') else 'FAIL'}")

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_seconds": round(time.time() - started, 2),
        "artifacts": "artifacts/upstream-integration/external-services/",
        "services": SUMMARY,
        "all_passed": all(entry["ok"] for entry in SUMMARY),
    }
    path = write_artifact("summary.json", summary)
    print("=" * 78)
    for entry in SUMMARY:
        print(f"{entry['service']:<10} {'PASS' if entry['ok'] else 'FAIL'}  {entry['checks']}")
    print(f"summary written: {path.relative_to(PROJECT_ROOT)}")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

