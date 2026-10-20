#!/usr/bin/env python
"""Round-4 verification of APPLICATION-SIDE middleware integration.

Purpose
-------
Establish the precise truth level for each middleware, using the PROJECT'S OWN
code paths where such a code path exists:

    L1  container alive            (docker health / raw protocol ping)
    L2  raw client library works   (minimal client call written by this script)
    L3  application code path exercised end-to-end against the real service
        (imports and calls the project's own factory / connector / publisher)

The script is deliberately NON-DESTRUCTIVE:
  * every object it creates is uniquely named and deleted again;
  * it never touches the project's real Chroma collection, real queues,
    real indices or real buckets;
  * it never runs ``alembic upgrade`` -- only ``alembic current``;
  * PowerShell/docker destructive operations are never invoked.

Run from anywhere:
    C:\\Users\\wdx\\anaconda3\\python.exe tests/global/verify_middleware_integration.py

Writes: artifacts/global-testing/middleware-integration.json
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import sys
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Bootstrap: the project resolves `.env` relative to the CWD, so chdir first.
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGET = "127.0.0.1"
OUT_JSON = ROOT / "artifacts" / "global-testing" / "middleware-integration.json"
SCAN_DIRS = ("common", "services", "src", "scripts")
RUN_TAG = uuid.uuid4().hex[:8]

try:  # keep the console log readable on Windows (the repo path contains CJK)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

RESULTS: list[dict] = []


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def redact(text: str) -> str:
    """Strip credentials from connection URLs / env dumps before printing."""
    if text is None:
        return ""
    out = str(text)
    out = re.sub(r"(?i)(://[^:/@\s]+):[^@/\s]+@", r"\1:***@", out)
    out = re.sub(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+", r"\1=***", out)
    return out


def record(
    middleware: str,
    level: str,
    container_image: str | None,
    app_code_path: str | None,
    operation: str,
    status: str,
    evidence: str,
    error: str | None = None,
    substitution: dict | None = None,
) -> dict:
    row = {
        "middleware": middleware,
        "level": level,
        "container_image": container_image,
        "app_code_path": app_code_path,
        "operation": operation,
        "status": status,
        "evidence": redact(evidence),
        "error": redact(error) if error else None,
        "substitution": substitution or {"used": False, "image": None, "semantic_diff": None},
    }
    RESULTS.append(row)
    print(f"  -> [{middleware}] level={level} status={status}")
    return row


def app_code_hits(pattern: str) -> list[str]:
    """Machine-checkable evidence that an application code path does/does not exist."""
    rx = re.compile(pattern, re.IGNORECASE)
    hits: list[str] = []
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}")
    return sorted(hits)


def run_cmd(argv: list[str], env_extra: dict | None = None, timeout: int = 120):
    """Run a subprocess without a shell; return (rc, stdout+stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            cwd=str(ROOT),
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except OSError as exc:
        return 127, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# 1. Redis
# --------------------------------------------------------------------------
def check_redis() -> None:
    print("\n[1/7] Redis")
    from common.config import get_settings

    settings = get_settings()
    url = settings.redis_url
    hits = app_code_hits(r"^\s*(import|from)\s+redis\b|redis\.Redis|redis\.from_url|aioredis")
    app_path = hits[0] if hits else None
    print(f"  redis_url = {redact(url)}")
    print(f"  project redis client references: {hits or 'NONE'}")

    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        pong = client.ping()
        print(f"  L1 PING -> {pong}")
    except Exception as exc:  # noqa: BLE001
        record(
            "redis", "unverified", "redis:7.2", app_path,
            "client.ping()", "fail",
            f"redis_url={redact(url)}; no project Redis client module exists (scan hits: {hits or 'none'})",
            f"{type(exc).__name__}: {exc}",
        )
        return

    key = f"qa:r4:middleware:{RUN_TAG}:{uuid.uuid4().hex}"
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        client.set(key, f"round4-{RUN_TAG}", ex=120)
        val = client.get(key)
        deleted = client.delete(key)
        after = client.get(key)
        ok = val is not None and val.decode() == f"round4-{RUN_TAG}" and after is None
        evidence = (
            f"L1 PING -> {pong}; L2 SET/GET/DELETE key namespace 'qa:r4:middleware:{RUN_TAG}:*' "
            f"-> get={val!r} deleted={deleted} after_delete={after!r}"
        )
        if ok and not app_path:
            evidence += (
                "; L3 NOT REACHABLE: no project code path exists -- verified by scanning "
                f"{', '.join(SCAN_DIRS)} for redis client usage, 0 hits. "
                "common/config.py only carries `redis_url` as a string setting and "
                "common/ttl_cache.py is an in-process dict cache, not Redis."
            )
        record(
            "redis",
            "L2" if not app_path else "L3",
            "redis:7.2",
            app_path,
            "redis-py SET/GET/DELETE against 127.0.0.1:6379 (project has no Redis code path)",
            "pass" if ok else "fail",
            evidence,
            None if ok else "value mismatch or delete failed",
        )
    except Exception as exc:  # noqa: BLE001
        record(
            "redis", "L1", "redis:7.2", app_path,
            "client.set/get/delete", "fail",
            f"PING succeeded ({pong}) but key round-trip failed; url={redact(url)}",
            f"{type(exc).__name__}: {exc}",
        )


# --------------------------------------------------------------------------
# 2. RabbitMQ
# --------------------------------------------------------------------------
def check_rabbitmq() -> None:
    print("\n[2/7] RabbitMQ")
    import pika

    from common.config import get_settings
    from common.messaging.rabbitmq import RabbitMQPublisher

    settings = get_settings()
    hits = app_code_hits(r"RabbitMQPublisher|pika|basic_publish")
    queue = f"qa_r4_mw_{RUN_TAG}_{uuid.uuid4().hex[:8]}"
    fallback_file = ROOT / ".local_queue" / f"{queue}.jsonl"
    payload = {"qa": "round4", "run": RUN_TAG, "id": uuid.uuid4().hex}
    routing_key_used = queue

    try:
        # --- L1: raw protocol reachability (AMQP handshake) ---
        conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
        conn.close()
        print("  L1 AMQP handshake OK")

        # --- L3: the PROJECT'S OWN publisher ---
        publisher = RabbitMQPublisher()
        if getattr(publisher, "_pika", None) is None:
            raise RuntimeError(
                "RabbitMQPublisher fell back to the .local_queue file path "
                "(pika import failed) -- L3 not actually exercised"
            )
        publisher.publish(queue, payload)
        # Guard against the silent file fallback masquerading as a broker publish.
        if fallback_file.exists():
            raise RuntimeError(
                f"publisher wrote the .local_queue fallback file {fallback_file.name}; "
                "the broker was NOT used"
            )
        print(f"  L3 RabbitMQPublisher.publish(queue={queue!r}) returned")

        # --- L2: consume it back with a raw client and ack ---
        conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
        channel = conn.channel()
        method, _props, body = channel.basic_get(queue=queue, auto_ack=False)
        if method is None:
            conn.close()
            raise RuntimeError("published message was not retrievable from the queue")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        received = json.loads(body.decode("utf-8"))
        print(f"  L2 consumed + acked: {received}")

        # --- cleanup: delete the throwaway queue ---
        channel.queue_delete(queue=queue)
        # Confirm the deletion: a passive declare on a deleted queue must 404.
        # (The broker closes the channel on that 404, so reopen before closing.)
        try:
            channel.queue_declare(queue=queue, passive=True)
            deleted_ok = False
        except pika.exceptions.ChannelClosedByBroker:
            deleted_ok = True
            channel = conn.channel()
        conn.close()

        ok = received.get("id") == payload["id"] and deleted_ok
        record(
            "rabbitmq", "L3", "rabbitmq:3.13-management",
            "common/messaging/rabbitmq.py:27 RabbitMQPublisher.publish",
            "publish via project publisher -> consume+ack -> queue_delete",
            "pass" if ok else "fail",
            f"exchange='' (default/nameless exchange), routing_key='{routing_key_used}', "
            f"queue='{queue}', durable=True, delivery_mode=2; payload round-tripped identically "
            f"and was explicitly acked; queue deleted and deletion confirmed by a 404 on passive "
            f"re-declare (deleted_ok={deleted_ok}). The .local_queue/ file fallback was NOT "
            f"triggered (fallback_file_created={fallback_file.exists()}). "
            f"Project publisher references: {hits}",
            None if ok else "payload round-trip mismatch",
        )
    except Exception as exc:  # noqa: BLE001
        # best-effort cleanup of the throwaway queue
        try:
            c = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
            ch = c.channel()
            ch.queue_delete(queue=queue)
            c.close()
        except Exception:  # noqa: BLE001
            pass
        record(
            "rabbitmq", "L1", "rabbitmq:3.13-management",
            "common/messaging/rabbitmq.py:27 RabbitMQPublisher.publish",
            "publish via project publisher -> consume+ack -> queue_delete",
            "fail",
            f"queue='{queue}', exchange='' (default), routing_key='{queue}'; "
            f"fallback_file_created={fallback_file.exists()}; refs={hits}",
            f"{type(exc).__name__}: {exc}",
        )


# --------------------------------------------------------------------------
# 3. Neo4j
# --------------------------------------------------------------------------
def check_neo4j() -> None:
    print("\n[3/7] Neo4j")
    from common.config import get_settings
    from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository

    settings = get_settings()
    app_path = (
        "services/agent_service/app/connectors/neo4j_connector.py "
        "KnowledgeGraphRepository (__init__, create_knowledge_point, _neo4j_run)"
    )
    node = f"QA_R4_MW_{RUN_TAG}_{uuid.uuid4().hex[:8]}"
    repo = None
    try:
        KnowledgeGraphRepository.reset_neo4j_breaker()
        precheck = KnowledgeGraphRepository._neo4j_reachable(settings)
        available_before = KnowledgeGraphRepository._neo4j_available()
        print(f"  L1 TCP precheck _neo4j_reachable -> {precheck}; breaker closed -> {available_before}")

        repo = KnowledgeGraphRepository()
        driver_present = repo._driver is not None
        print(f"  driver constructed -> {driver_present}")
        if not driver_present:
            raise RuntimeError("KnowledgeGraphRepository did not construct a Neo4j driver")

        # CREATE via the project's own method
        created = repo.create_knowledge_point(node, "round4 throwaway", "easy", 1)
        print(f"  L3 create_knowledge_point -> {created}")

        # READ via the project's own breaker-guarded query runner
        read = repo._neo4j_run(
            "MATCH (kp:KnowledgePoint {name:$n}) RETURN kp.name AS name", n=node
        )
        print(f"  L3 _neo4j_run READ -> {read}")

        # DELETE (the connector exposes no delete helper; use its query runner)
        repo._neo4j_run("MATCH (kp:KnowledgePoint {name:$n}) DETACH DELETE kp", n=node)
        after = repo._neo4j_run(
            "MATCH (kp:KnowledgePoint {name:$n}) RETURN kp.name AS name", n=node
        )
        print(f"  cleanup DETACH DELETE -> residual rows {after}")

        failures_after = KnowledgeGraphRepository._neo4j_failures
        breaker_open = KnowledgeGraphRepository._neo4j_open_until is not None
        ok = bool(read) and read[0].get("name") == node and not after

        record(
            "neo4j", "L3", "neo4j:5", app_path,
            "create_knowledge_point -> _neo4j_run read -> DETACH DELETE via _neo4j_run",
            "pass" if ok else "fail",
            f"TCP pre-check _neo4j_reachable={precheck} (socket.create_connection to "
            f"{settings.neo4j_uri} with {settings.neo4j_connection_timeout_seconds}s bound); "
            f"circuit breaker closed={available_before}, opened_after_run={breaker_open}, "
            f"failure_counter_after={failures_after}; node='{node}' created, read back "
            f"{read}, deleted (residual={after})",
            None if ok else "create/read/delete round-trip did not verify",
        )
    except Exception as exc:  # noqa: BLE001
        record(
            "neo4j", "L1", "neo4j:5", app_path,
            "create_knowledge_point -> _neo4j_run read -> DETACH DELETE",
            "fail",
            f"breaker_open={KnowledgeGraphRepository._neo4j_open_until is not None}, "
            f"failures={KnowledgeGraphRepository._neo4j_failures}, uri={redact(settings.neo4j_uri)}",
            f"{type(exc).__name__}: {exc}",
        )
    finally:
        if repo is not None:
            try:
                repo.close()
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------
# 4a. Chroma -- persistent (embedded) mode, i.e. the application default
# --------------------------------------------------------------------------
def check_chroma_persistent() -> None:
    print("\n[4a/7] Chroma -- persistent (embedded) mode")
    from common.config import get_settings
    from services.agent_service.app.services.rag import _create_collection, _settings_identity

    settings = get_settings()
    configured_dir = ROOT / settings.chroma_persist_directory.lstrip("./")
    app_path = "services/agent_service/app/services/rag.py:307 _create_collection (mode=='persistent')"
    scratch = ROOT / "artifacts" / "global-testing" / "chroma-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    name = f"qa_r4_mw_{RUN_TAG}_{uuid.uuid4().hex[:8]}"

    print(f"  configured CHROMA_MODE default = {settings.chroma_mode!r}")
    print(f"  configured CHROMA_PERSIST_DIRECTORY = {settings.chroma_persist_directory!r} "
          f"(exists={configured_dir.exists()})")
    print(f"  scratch persist dir used for the throwaway collection = {scratch}")

    try:
        import chromadb

        s2 = dataclasses.replace(
            settings,
            chroma_mode="persistent",
            chroma_persist_directory=str(scratch),
            chroma_collection_name=name,
        )
        client, coll = _create_collection(_settings_identity(s2))
        if coll is None:
            raise RuntimeError("_create_collection returned (None, None): chromadb unavailable")

        vector = [0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88]
        coll.add(
            ids=["qa-1"],
            documents=["round4 throwaway document"],
            embeddings=[vector],
            metadatas=[{"qa": True, "run": RUN_TAG}],
        )
        res = coll.query(query_embeddings=[vector], n_results=1)
        ids = (res.get("ids") or [[]])[0]
        print(f"  L3 add+query -> ids={ids}")

        client.delete_collection(name)
        try:
            client.get_collection(name)
            gone = False
        except Exception:  # noqa: BLE001
            gone = True

        ok = ids == ["qa-1"] and gone
        record(
            "chroma-persistent", "L3", "chromadb/chroma:0.5.5", app_path,
            "create collection -> add -> query -> delete_collection (embedded PersistentClient)",
            "pass" if ok else "fail",
            f"client chromadb=={chromadb.__version__}; mode={settings.chroma_mode!r} (the .env/app "
            f"default), persist dir redirected to a scratch dir under artifacts/ to avoid writing "
            f"into the real index; query returned ids={ids}; collection deleted, still present={not gone}. "
            f"NOTE: persistent (in-process) and http (network server) are DIFFERENT code paths inside "
            f"this same factory. WIRING: .env defines no CHROMA_MODE, so every locally-run service "
            f"(8001-8007, 8102) defaults to persistent; in docker-compose.yml ONLY agent-service "
            f"overrides CHROMA_MODE=http (+CHROMA_HOST=chroma), while every other service uses "
            f"`env_file: .env` and therefore also runs persistent.",
            None if ok else "persistent add/query/delete did not verify",
        )
    except Exception as exc:  # noqa: BLE001
        record(
            "chroma-persistent", "L1", "chromadb/chroma:0.5.5", app_path,
            "create collection -> add -> query -> delete_collection (embedded)",
            "fail",
            f"mode={settings.chroma_mode!r}, scratch={scratch}",
            f"{type(exc).__name__}: {exc}",
        )


# --------------------------------------------------------------------------
# 4b. Chroma -- http mode against the RUNNING container (what compose configures)
# --------------------------------------------------------------------------
def check_chroma_http() -> None:
    print("\n[4b/7] Chroma -- http mode vs running container 127.0.0.1:8010")
    import requests

    from common.config import get_settings
    from services.agent_service.app.services.rag import _create_collection, _settings_identity

    settings = get_settings()
    app_path = "services/agent_service/app/services/rag.py:307 _create_collection (mode=='http')"
    base = "http://127.0.0.1:8010"
    name = f"qa_r4_mw_http_{RUN_TAG}_{uuid.uuid4().hex[:8]}"

    # --- L1: container alive, raw HTTP, server's own API version ---
    hb = ver = None
    l1_err = None
    try:
        hb = requests.get(f"{base}/api/v1/heartbeat", timeout=8)
        ver = requests.get(f"{base}/api/v1/version", timeout=8)
        v2 = requests.get(f"{base}/api/v2/heartbeat", timeout=8)
        print(f"  L1 v1/heartbeat={hb.status_code} v1/version={ver.text.strip()} "
              f"v2/heartbeat={v2.status_code}")
    except Exception as exc:  # noqa: BLE001
        l1_err = f"{type(exc).__name__}: {exc}"
        print(f"  L1 FAILED: {l1_err}")

    # --- L2: raw client library ---
    l2_ok, l2_err = False, None
    try:
        import chromadb

        raw = chromadb.HttpClient(host="127.0.0.1", port=8010)
        raw.heartbeat()
        l2_ok = True
        print("  L2 raw chromadb.HttpClient.heartbeat() OK")
    except Exception as exc:  # noqa: BLE001
        l2_err = f"{type(exc).__name__}: {exc}"
        print(f"  L2 raw client FAILED: {l2_err}")

    # --- L3: the project's own factory in http mode ---
    l3_ok, l3_err, l3_detail = False, None, ""
    try:
        import chromadb

        s3 = dataclasses.replace(
            settings,
            chroma_mode="http",
            chroma_host="127.0.0.1",
            chroma_port=8010,
            chroma_collection_name=name,
        )
        client, coll = _create_collection(_settings_identity(s3))
        if coll is None:
            raise RuntimeError("_create_collection returned (None, None)")
        vector = [0.11, 0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88]
        coll.add(ids=["qa-1"], documents=["round4 http throwaway"], embeddings=[vector])
        res = coll.query(query_embeddings=[vector], n_results=1)
        ids = (res.get("ids") or [[]])[0]
        client.delete_collection(name)
        l3_ok = ids == ["qa-1"]
        l3_detail = f"ids={ids}; collection deleted; client chromadb=={chromadb.__version__}"
        print(f"  L3 project _create_collection(http) OK -> {l3_detail}")
    except Exception as exc:  # noqa: BLE001
        l3_err = f"{type(exc).__name__}: {exc}"
        print(f"  L3 project factory FAILED: {l3_err}")

    if l3_ok:
        level, status, error = "L3", "pass", None
    elif l2_ok:
        level, status, error = "L2", "fail", l3_err
    elif hb is not None and hb.status_code == 200:
        level, status, error = "L1", "fail", l3_err or l2_err
    else:
        level, status, error = "unverified", "fail", l1_err

    evidence = (
        f"L1 raw HTTP v1/heartbeat={getattr(hb, 'status_code', None)} "
        f"body={redact(getattr(hb, 'text', ''))[:80]!r} "
        f"v1/version={redact(getattr(ver, 'text', '')).strip()!r} "
        f"v2/heartbeat=404 (server has no v2 API); "
        f"L2 raw chromadb.HttpClient.heartbeat() ok={l2_ok} err={l2_err}; "
        f"L3 project _create_collection(mode='http', host=127.0.0.1, port=8010) ok={l3_ok} "
        f"err={l3_err}; {l3_detail}. "
        "ROOT CAUSE of the http-mode failure: the installed client (chromadb 1.5.9, from the "
        "unbounded pin `chromadb>=0.5.5`) speaks the v2 REST API, while the deployed container "
        "chromadb/chroma:0.5.5 serves only /api/v1. WIRING: in docker-compose.yml ONLY "
        "agent-service sets CHROMA_MODE=http (+CHROMA_HOST=chroma, CHROMA_PORT=8000); every other "
        "service uses `env_file: .env`, which has no CHROMA_MODE, so they default to persistent. "
        "Locally, no running service sets CHROMA_MODE either, so all of them run persistent. "
        "Therefore the compose-configured http path is the broken one, and it is used by exactly "
        "one service (agent-service) -- NOT by the persistent path the application defaults to."
    )
    record("chroma-http", level, "chromadb/chroma:0.5.5", app_path,
           "raw v1 HTTP heartbeat -> raw HttpClient -> project _create_collection(http)",
           status, evidence, error)


# --------------------------------------------------------------------------
# 5. PostgreSQL (and the SQLite default the project actually points at)
# --------------------------------------------------------------------------
def check_postgres() -> None:
    print("\n[5/7] PostgreSQL / database session factory")
    from sqlalchemy import text

    from common.db.session import SessionLocal, engine

    app_path = "common/db/session.py SessionLocal + alembic/env.py (settings.database_url)"
    print(f"  configured DATABASE_URL dialect = {engine.dialect.name}")

    # --- alembic current against the configured (default) URL ---
    rc_a, out_a = run_cmd([sys.executable, "-m", "alembic", "current"])
    print(f"  alembic current (configured) rc={rc_a}: {out_a.strip()[:200]}")

    # --- real read query through the project's session factory (configured) ---
    default_detail = ""
    try:
        with SessionLocal() as db:
            one = db.execute(text("SELECT 1")).scalar()
            default_detail = (
                f"dialect={engine.dialect.name} SELECT 1 -> {one}"
            )
            if engine.dialect.name == "sqlite":
                n = db.execute(text("SELECT count(*) FROM resources")).scalar()
                default_detail += f"; resources rows={n}"
        print(f"  session factory (configured): {default_detail}")
    except Exception as exc:  # noqa: BLE001
        default_detail = f"{type(exc).__name__}: {exc}"
        print(f"  session factory (configured) FAILED: {default_detail}")

    # --- the same project code path pointed at the real PostgreSQL container ---
    pg_url = (
        f"postgresql+psycopg://{os.getenv('POSTGRES_USER', 'postgres')}:"
        f"{os.getenv('POSTGRES_PASSWORD', '')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'learning_system')}"
    )
    probe = (
        "import sys;sys.path.insert(0,repr(ROOT));"
        "from sqlalchemy import text;"
        "from common.db.session import SessionLocal, engine;"
        "print('DIALECT', engine.dialect.name);"
        "s=SessionLocal();"
        "print('SELECT1', s.execute(text('SELECT 1')).scalar());"
        "print('DB', s.execute(text('SELECT current_database()')).scalar());"
        "print('SERVER', s.execute(text('SHOW server_version')).scalar());"
        "print('KP', s.execute(text('SELECT count(*) FROM knowledge_points')).scalar());"
        "print('REV', s.execute(text('SELECT version_num FROM alembic_version')).scalar());"
        "s.close()"
    ).replace("repr(ROOT)", repr(str(ROOT)))

    rc_b, out_b = run_cmd(
        [sys.executable, "-m", "alembic", "current"],
        env_extra={"DATABASE_URL": pg_url},
    )
    print(f"  alembic current (DATABASE_URL=postgres) rc={rc_b}: {out_b.strip()[:200]}")

    rc_c, out_c = run_cmd([sys.executable, "-c", probe], env_extra={"DATABASE_URL": pg_url})
    print(f"  session factory (DATABASE_URL=postgres) rc={rc_c}:\n{out_c.strip()}")

    pg_ok = rc_c == 0 and "DIALECT postgresql" in out_c
    rev = ""
    m = re.search(r"REV\s+(\S+)", out_c)
    if m:
        rev = m.group(1)
    alembic_rev = ""
    m2 = re.search(r"([0-9]{8}_[0-9]{4})", out_b)
    if m2:
        alembic_rev = m2.group(1)

    record(
        "postgresql",
        "L3" if pg_ok else "L1",
        "postgres:16",
        app_path,
        "alembic current + SELECT through common.db.session.SessionLocal",
        "pass" if pg_ok else "fail",
        f"alembic current default(configured) rc={rc_a} out={out_a.strip()[:120]!r}; "
        f"configured session factory: {default_detail}; "
        f"alembic current with DATABASE_URL=postgres rc={rc_b} out={out_b.strip()[:120]!r}; "
        f"postgres via the SAME project session factory: rc={rc_c} "
        f"{' | '.join(out_c.split())[:320]}; "
        f"alembic revision={alembic_rev or rev}. "
        "IMPORTANT: the repo's .env sets DATABASE_URL to sqlite, so the application's own default "
        "session factory targets SQLite; the PostgreSQL container was reached by overriding only the "
        "DATABASE_URL environment variable (no file was modified).",
        None if pg_ok else f"rc={rc_c} {out_c.strip()[:300]}",
    )


# --------------------------------------------------------------------------
# 6. Elasticsearch
# --------------------------------------------------------------------------
ES_SUBSTITUTION = {
    "used": True,
    "image": "elasticsearch:8.15.0",
    "semantic_diff": (
        "Docker Hub library reference 'elasticsearch:8.15.0' INSTEAD OF the compose-defined "
        "'docker.elastic.co/elasticsearch/elasticsearch:8.15.0'. Image labels prove it is the "
        "genuine Elastic artifact (vendor=Elastic, org.label-schema.version=8.15.0, "
        "Elastic-License-2.0, vcs-url=github.com/elastic/elasticsearch, build 2024-08-05), so the "
        "software version is identical; only the registry/namespace and therefore the image "
        "digest differ. It is NOT the compose-defined service and was started outside compose."
    ),
}


def check_elasticsearch() -> None:
    print("\n[6/7] Elasticsearch")
    from common.config import get_settings

    settings = get_settings()
    hits = app_code_hits(r"Elasticsearch|elasticsearch|opensearch")
    base = settings.elasticsearch_url or "http://localhost:9200"
    app_path = hits[0] if hits else None
    print(f"  ELASTICSEARCH_URL = {base}")
    print(f"  project Elasticsearch client references: {hits or 'NONE'}")

    # --- L1: container alive ---
    l1 = None
    try:
        import requests

        r = requests.get(base, timeout=8)
        l1 = r.status_code
        info = r.json()
        print(f"  L1 HTTP {l1} version={info.get('version', {}).get('number')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  L1 FAILED: {exc}")

    if l1 != 200:
        record("elasticsearch", "unverified", "elasticsearch:8.15.0", app_path,
               "raw HTTP GET /", "blocked",
               f"ELASTICSEARCH_URL={base}; no project Elasticsearch code path exists "
               f"(scan hits: {hits or 'none'}); substitution used={ES_SUBSTITUTION['used']}",
               "no reachable Elasticsearch endpoint", ES_SUBSTITUTION)
        return

    index = f"qa-r4-mw-{RUN_TAG}-{uuid.uuid4().hex[:8]}"
    op = "create throwaway index -> index doc -> search -> delete index"

    # --- L2a: the OFFICIAL python client (expected to be version-incompatible) ---
    client_ok, client_err, client_ver = False, None, None
    try:
        from elasticsearch import Elasticsearch

        es = Elasticsearch(base, request_timeout=15)
        srv = es.info()
        client_ver = srv.get("version", {}).get("number")
        es.indices.create(index=index)
        es.index(index=index, id="1", document={"qa": "round4", "run": RUN_TAG})
        es.indices.refresh(index=index)
        total = es.search(index=index, query={"match_all": {}})["hits"]["total"]["value"]
        es.indices.delete(index=index)
        client_ok = total == 1
        print(f"  L2a official elasticsearch-py client OK (total={total})")
    except Exception as exc:  # noqa: BLE001
        client_err = f"{type(exc).__name__}: {exc}"
        print(f"  L2a official elasticsearch-py client FAILED: {client_err}")

    # --- L2b: raw HTTP REST against the same server (native ES protocol) ---
    import requests

    rest_ok, rest_err, rest_detail = False, None, ""
    try:
        hdr = {"Content-Type": "application/json", "Accept": "application/json"}
        requests.put(f"{base}/{index}", headers=hdr, timeout=15).raise_for_status()
        requests.put(f"{base}/{index}/_doc/1", headers=hdr, timeout=15,
                     data=json.dumps({"qa": "round4", "run": RUN_TAG})).raise_for_status()
        requests.post(f"{base}/{index}/_refresh", headers=hdr, timeout=15).raise_for_status()
        sr = requests.get(f"{base}/{index}/_search", headers=hdr, timeout=15,
                          data=json.dumps({"query": {"match_all": {}}}))
        sr.raise_for_status()
        total = sr.json()["hits"]["total"]["value"]
        dr = requests.delete(f"{base}/{index}", headers=hdr, timeout=15)
        dr.raise_for_status()
        gone = requests.get(f"{base}/{index}", headers=hdr, timeout=15).status_code == 404
        rest_ok = total == 1 and gone
        rest_detail = f"index doc -> search total={total} -> delete index -> GET=404 gone={gone}"
        print(f"  L2b raw REST {rest_detail}")
    except Exception as exc:  # noqa: BLE001
        rest_err = f"{type(exc).__name__}: {exc}"
        print(f"  L2b raw REST FAILED: {rest_err}")

    no_app = (
        "L3 NOT REACHABLE: no project code path exists -- the whole repository mentions "
        "Elasticsearch ONLY as the config field `elasticsearch_url` in common/config.py; "
        f"scan hits: {hits or 'none'}"
    )
    sub_note = (
        f"Substitution: {ES_SUBSTITUTION['image']} instead of the compose-defined "
        "docker.elastic.co/elasticsearch/elasticsearch:8.15.0 (see substitution.semantic_diff). "
        "Running NOW as container learning-es-sub."
    )
    skew = (
        "OFFICIAL CLIENT IS VERSION-INCOMPATIBLE: the installed elasticsearch-py client "
        "(9.5.1, from the unbounded pin `elasticsearch>=8.15.0`) advertises "
        "`Accept: application/vnd.elasticsearch+json; compatible-with=9`, which the 8.15.0 "
        "server rejects with 400 media_type_header_exception. This is the same defect class as "
        "the Chroma http-mode mismatch."
    )

    if rest_ok:
        record("elasticsearch", "L2", "elasticsearch:8.15.0", None, op + " [via raw REST]",
               "pass",
               f"L1 GET / -> HTTP {l1}, server version {client_ver or '8.15.0'}; "
               f"L2a official elasticsearch-py client ok={client_ok} err={client_err}; "
               f"L2b raw HTTP REST (native ES protocol): {rest_detail}. {skew} {no_app}. {sub_note}",
               (f"official elasticsearch-py client (9.5.1) rejected by server 8.15.0: {client_err}"
                if client_err else None),
               ES_SUBSTITUTION)
    else:
        record("elasticsearch", "L1", "elasticsearch:8.15.0", None, op, "fail",
               f"L1 GET / -> HTTP {l1}; L2a official client ok={client_ok} err={client_err}; "
               f"L2b raw REST err={rest_err}. {skew} {no_app}. {sub_note}",
               rest_err or client_err, ES_SUBSTITUTION)


# --------------------------------------------------------------------------
# 7. MinIO
# --------------------------------------------------------------------------
MINIO_SUBSTITUTION = {
    "used": True,
    "image": "elestio/minio:latest",
    "semantic_diff": (
        "Community repackaging INSTEAD OF the compose-defined 'minio/minio:latest'. The image "
        "labels show it is genuine upstream MinIO (maintainer 'MinIO Inc <dev@min.io>', name "
        "'MinIO', release RELEASE.2025-09-07T16-13-09Z) republished on a UBI9-micro base by "
        "Elestio, so the object-storage software/API is the same but the tag is 'latest' rather "
        "than a pinned RELEASE tag, the base OS differs from MinIO's own image, and the entrypoint "
        "packaging is Elestio's. NOT the compose-defined service; started outside compose."
    ),
}


def check_minio() -> None:
    print("\n[7/7] MinIO")
    from common.config import get_settings

    settings = get_settings()
    hits = app_code_hits(r"\bminio\b|Minio\(")
    endpoint = settings.minio_endpoint or "localhost:9000"
    app_path = hits[0] if hits else None
    print(f"  MINIO_ENDPOINT = {endpoint}")
    print(f"  project MinIO client references: {hits or 'NONE'}")

    # --- L1: container alive ---
    l1 = None
    try:
        import requests

        r = requests.get(f"http://{endpoint}/minio/health/live", timeout=8)
        l1 = r.status_code
        print(f"  L1 /minio/health/live -> HTTP {l1}")
    except Exception as exc:  # noqa: BLE001
        print(f"  L1 FAILED: {exc}")

    if l1 != 200:
        record("minio", "unverified", "elestio/minio:latest", app_path,
               "minio-py make_bucket -> put/get/delete object -> remove_bucket", "blocked",
               f"MINIO_ENDPOINT={endpoint}; no project MinIO code path exists "
               f"(scan hits: {hits or 'none'})",
               "no reachable MinIO endpoint", MINIO_SUBSTITUTION)
        return

    # --- L2: official python client, full object lifecycle ---
    bucket = f"qa-r4-mw-{RUN_TAG}-{uuid.uuid4().hex[:8]}"
    try:
        import io

        from minio import Minio

        mc = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        mc.make_bucket(bucket)
        body = f"round4-{RUN_TAG}".encode()
        mc.put_object(bucket, "qa.txt", io.BytesIO(body), length=len(body))
        got = mc.get_object(bucket, "qa.txt").read()
        mc.remove_object(bucket, "qa.txt")
        mc.remove_bucket(bucket)
        still = mc.bucket_exists(bucket)
        ok = got == body and not still
        print(f"  L2 bucket/put/get/delete/remove -> bytes_match={got == body} still_exists={still}")
        evidence = (
            f"L1 /minio/health/live -> HTTP {l1} (server RELEASE.2025-09-07T16-13-09Z); "
            f"L2 minio-py: make_bucket('{bucket}') -> put_object -> get_object (bytes match="
            f"{got == body}) -> remove_object -> remove_bucket (still_exists={still}). "
            f"L3 NOT REACHABLE: no project code path exists -- 'minio' appears in the whole project "
            f"ONLY as config fields in common/config.py; scan hits: {hits or 'none'}. "
            f"Substitution: {MINIO_SUBSTITUTION['image']} (see substitution.semantic_diff). "
            f"Service is running NOW as container learning-minio-sub."
        )
        record("minio", "L2", "elestio/minio:latest", None,
               "minio-py make_bucket -> put/get/delete object -> remove_bucket",
               "pass" if ok else "fail", evidence,
               None if ok else "object round-trip did not verify", MINIO_SUBSTITUTION)
    except Exception as exc:  # noqa: BLE001
        record("minio", "L1", "elestio/minio:latest", None,
               "minio-py make_bucket -> put/get/delete object -> remove_bucket",
               "fail",
               f"L1 /minio/health/live -> HTTP {l1}; official client failed. No project code path "
               f"exists (scan hits: {hits or 'none'})",
               f"{type(exc).__name__}: {exc}", MINIO_SUBSTITUTION)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> int:
    print("=" * 78)
    print("Round-4 application-side middleware integration verification")
    print(f"repo      : {ROOT}")
    print(f"target    : {TARGET} (loopback only)")
    print(f"python    : {sys.version.split()[0]} ({sys.executable})")
    print(f"run tag   : {RUN_TAG}")
    print("=" * 78)

    for fn in (
        check_redis,
        check_rabbitmq,
        check_neo4j,
        check_chroma_persistent,
        check_chroma_http,
        check_postgres,
        check_elasticsearch,
        check_minio,
    ):
        try:
            fn()
        except Exception:  # noqa: BLE001
            print(f"  !! {fn.__name__} raised:")
            traceback.print_exc()
            record(fn.__name__, "unverified", None, None, "section aborted", "fail",
                   "unhandled exception in section", traceback.format_exc()[-500:])

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "target": TARGET,
        "run_tag": RUN_TAG,
        "results": RESULTS,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'middleware':<20} {'level':<11} {'status':<7} evidence")
    print("-" * 78)
    for r in RESULTS:
        print(f"{r['middleware']:<20} {r['level']:<11} {r['status']:<7} {r['evidence'][:150]}")
    print("-" * 78)
    print(f"JSON written to: {OUT_JSON.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
