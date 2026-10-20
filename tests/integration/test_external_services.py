"""Opt-in integration verification against the real external services.

    RUN_EXTERNAL_SERVICES=1 python -m pytest -m external_service \\
        tests/integration/test_external_services.py -q

Skipped by default, so the ordinary pytest run never needs Docker, MySQL/Postgres
or any network service. The single source of truth is
``scripts/verify_external_services.py``; this module runs it once and asserts the
invariants that must hold, so the same evidence backs both the script output and
the tests.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

pytestmark = pytest.mark.external_service

MARKER = "EXTERNAL_SERVICES_NOT_ENABLED"
_TRUTHY = {"1", "true", "yes", "on"}

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SUMMARY_PATH = (
    PROJECT_ROOT / "artifacts" / "upstream-integration" / "external-services" / "summary.json"
)


def _enabled() -> bool:
    return os.getenv("RUN_EXTERNAL_SERVICES", "").strip().lower() in _TRUTHY


if not _enabled():
    pytest.skip(
        f"{MARKER}: RUN_EXTERNAL_SERVICES is not set. "
        "Run 'RUN_EXTERNAL_SERVICES=1 pytest -m external_service' to execute these tests.",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def verification() -> dict:
    """Run the verifier once and return its summary plus per-service artifacts."""

    proc = subprocess.run(
        [sys.executable, "scripts/verify_external_services.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    assert SUMMARY_PATH.is_file(), (
        "the verifier produced no summary.json\n"
        f"stdout tail:\n{(proc.stdout or '')[-2000:]}\n"
        f"stderr tail:\n{(proc.stderr or '')[-2000:]}"
    )
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    services = {
        entry["service"]: entry
        for entry in summary["services"]
    }
    artifacts = {}
    for name in ("postgres", "neo4j", "chroma"):
        path = SUMMARY_PATH.parent / f"{name}.json"
        artifacts[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {"summary": summary, "services": services, "artifacts": artifacts, "proc": proc}


def _checks(verification: dict, service: str) -> dict:
    return verification["services"].get(service, {}).get("checks", {})


# --------------------------------------------------------------------------- #
# PostgreSQL
# --------------------------------------------------------------------------- #


def test_postgres_real_connection_migration_and_round_trip(verification) -> None:
    checks = _checks(verification, "postgresql")
    artifact = verification["artifacts"]["postgres"]

    assert checks.get("server_reachable") is True, artifact.get("blocked_reason") or checks
    assert checks.get("isolated_database_created") is True, "the isolated database was not created"
    assert checks.get("alembic_upgrade_head") is True, "alembic upgrade head failed"
    assert checks.get("core_tables_present") is True, "core tables are missing after migration"
    assert checks.get("core_read_write") is True, "writing/reading core rows failed"
    assert checks.get("service_starts_after_migration") is True, (
        "the user service did not answer /health against the migrated database"
    )
    assert artifact.get("isolated_database", "").startswith("learning_system_verify"), (
        "the verifier must never target a non-throwaway database"
    )


def test_postgres_alembic_head_matches_the_models(verification) -> None:
    """A freshly migrated database must contain every column the ORM selects."""

    checks = _checks(verification, "postgresql")
    revision = str(checks.get("alembic_revision") or "")
    assert revision, "alembic current returned no revision"
    assert "20261016_0009" in revision, (
        "the ORM-drift reconciliation revision is not applied; "
        f"head reported {revision!r}"
    )


# --------------------------------------------------------------------------- #
# Neo4j
# --------------------------------------------------------------------------- #


def test_neo4j_connect_auth_and_cypher(verification) -> None:
    checks = _checks(verification, "neo4j")
    assert checks.get("connect_auth_cypher") is True, "connect / auth / Cypher round trip failed"


def test_neo4j_degrades_and_does_not_block(verification) -> None:
    checks = _checks(verification, "neo4j")
    assert checks.get("degrades_when_unavailable") is True, "an unreachable Neo4j did not degrade"
    assert checks.get("timeout_bounded") is True, "a silent Neo4j blocked the caller"
    assert checks.get("sql_fallback_serves_graph_data") is True, (
        "the documented SQL fallback did not return stored dependencies"
    )


# --------------------------------------------------------------------------- #
# Chroma
# --------------------------------------------------------------------------- #


def test_chroma_mode_collection_and_source_chunks(verification) -> None:
    checks = _checks(verification, "chroma")
    artifact = verification["artifacts"]["chroma"]

    assert checks.get("mode_matches_config") is True, (
        f"CHROMA_MODE={artifact.get('configured_mode')!r} does not match the client that was built"
    )
    assert checks.get("collection_write_query_chunks") is True, (
        "create / upsert / query / source-chunk return failed"
    )


def test_chroma_without_evidence_is_insufficient_evidence(verification) -> None:
    checks = _checks(verification, "chroma")
    assert checks.get("insufficient_evidence") is True, (
        "an empty retrieval did not report insufficient_evidence"
    )


def test_chroma_http_mode_compatibility_is_honest_about_the_environment(verification) -> None:
    """The http-mode verdict must match the installed client's protocol major.

    This is not a rubber stamp: it fails if the http path is broken while the
    declared dependency line is satisfied, and it fails if the http path is
    reported working while the installed client cannot speak the server's
    protocol.
    """

    checks = _checks(verification, "chroma")
    artifact = verification["artifacts"]["chroma"]
    installed = str(artifact.get("installed_chromadb_version") or "")
    installed_major = installed.split(".")[0] if installed else ""

    assert checks.get("server_v1_rest_works") is True, (
        "the running Chroma server did not answer its own /api/v1 REST contract"
    )

    if installed_major.isdigit() and int(installed_major) >= 1:
        assert checks.get("http_mode_client_server_compatible") is False, (
            f"chromadb {installed} speaks /api/v2 but the pinned server serves /api/v1; "
            "http mode must not be reported as working"
        )
        assert artifact.get("blocked_reason"), (
            "an incompatible http mode must carry an explicit blocked_reason"
        )
    else:
        assert checks.get("http_mode_client_server_compatible") is True, (
            f"chromadb {installed or 'unknown'} should be compatible with the pinned server; "
            f"blocked_reason={artifact.get('blocked_reason')!r}"
        )
