"""Runtime end-to-end verification for automatic knowledge-base backfill.

The pytest suite proves the logic.  This script proves the logic still holds
under a REAL runtime: a real directory tree on disk, a real SQLite file shared
by several OS processes, and a real persistent Chroma collection.

Everything happens under an explicit runtime root that the caller supplies and
deletes afterwards, so the project's own public corpus is never touched.

Sub-commands (each one is a separate OS process)::

    prepare --root DIR                create runtime root, schema and learners
    worker  --root DIR --slot N       one concurrent backfill attempt
    damage  --root DIR --mode M       destroy a committed artifact on purpose
    repair  --root DIR                run reconcile() and report what it fixed
    verify  --root DIR                assert invariants over real state
    report  --root DIR                dump the observed real state

Exit code is 0 only when every assertion holds.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap_runtime(root: Path) -> None:
    """Point every runtime setting at ``root`` before project modules import."""
    root = root.resolve()
    (root / "chroma").mkdir(parents=True, exist_ok=True)
    os.environ.update(
        KNOWLEDGE_RUNTIME_ROOT=str(root),
        CHROMA_PERSIST_DIRECTORY=str(root / "chroma"),
        CHROMA_MODE="persistent",
        DATABASE_URL="sqlite+pysqlite:///" + (root / "runtime.sqlite").as_posix(),
        RUN_LIVE_LLM="0",
        APP_LOAD_DOTENV="false",
        ENVIRONMENT="test",
        JWT_SECRET_KEY="runtime-verification-secret",
        JWT_ALGORITHM="HS256",
        NEO4J_ENABLED="false",
        GRAPH_LLM_ENRICH_ENABLED="false",
        RUN_EXTERNAL_SERVICES="0",
        LLM_PREWARM_ENABLED="false",
        AI_PERFORMANCE_LOG_PATH=str(root / "ai-performance.jsonl"),
    )


def _plan(root: Path) -> dict:
    return json.loads((root / "plan.json").read_text(encoding="utf-8"))


def _session(root: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        os.environ["DATABASE_URL"],
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    return engine, sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def cmd_prepare(args) -> int:
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _bootstrap_runtime(root)
    from common.db.base import Base  # noqa: F401  (registers every mapped class)
    from common.models.learning import User

    engine, db = _session(root)
    Base.metadata.create_all(engine)
    plan = {
        "subject": args.subject,
        "point": args.point,
        "slots": args.slots,
    }
    (root / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    for slot in range(args.slots):
        db.add(User(id=slot + 1, username=f"learner-{slot + 1}", password_hash="unused"))
    db.commit()
    db.close()
    engine.dispose()
    print(json.dumps({"prepared": str(root), "plan": plan}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------


def cmd_worker(args) -> int:
    root = Path(args.root).resolve()
    _bootstrap_runtime(root)
    plan = _plan(root)
    from services.agent_service.app.services import knowledge_bootstrap as kb

    engine, db = _session(root)
    try:
        outline = kb._deterministic_outline(plan["subject"], plan["point"])
        result = kb.promote_draft_to_knowledge_base(
            db, args.slot + 1, plan["subject"], plan["point"], outline, []
        )
        db.commit()
        payload = {"slot": args.slot, "pid": os.getpid(), "result": result}
    except Exception as exc:  # pragma: no cover - diagnostic path
        payload = {"slot": args.slot, "pid": os.getpid(), "error": f"{type(exc).__name__}: {exc}"}
    finally:
        db.close()
        engine.dispose()
    print("RESULT " + json.dumps(payload, ensure_ascii=False, default=str))
    return 0


# ---------------------------------------------------------------------------
# damage / repair
# ---------------------------------------------------------------------------


def cmd_damage(args) -> int:
    """Deliberately break one committed artifact to prove recovery works."""
    root = Path(args.root).resolve()
    _bootstrap_runtime(root)
    from common.knowledge_paths import KNOWLEDGE_ROOT
    from common.models.learning import KnowledgeVersion

    engine, db = _session(root)
    version = db.query(KnowledgeVersion).filter_by(is_active=True).first()
    if version is None:
        print("damage: no active version to damage")
        return 1
    path = KNOWLEDGE_ROOT / version.corpus_path
    source = version.corpus_path.removeprefix("knowledge_base/corpus/")
    removed = {}
    if args.mode == "file":
        path.unlink(missing_ok=True)
        removed["corpus_file"] = version.corpus_path
    elif args.mode == "index":
        from services.agent_service.app.services import knowledge_bootstrap as kb

        kb._delete_index_records(version.subject, {source})
        removed["index_records"] = source
    else:
        raise SystemExit(f"unknown damage mode: {args.mode}")
    db.commit()
    db.close()
    engine.dispose()
    print(json.dumps({"damaged": removed}, ensure_ascii=False))
    return 0


def cmd_repair(args) -> int:
    root = Path(args.root).resolve()
    _bootstrap_runtime(root)
    from services.agent_service.app.services import knowledge_publication

    engine, db = _session(root)
    try:
        outcome = knowledge_publication.reconcile(db)
        db.commit()
        print(json.dumps({"reconcile": outcome}, ensure_ascii=False))
        return 0
    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# verify / report
# ---------------------------------------------------------------------------


def _collect(root: Path) -> dict:
    from common.knowledge_paths import CORPUS_DIR, KNOWLEDGE_ROOT
    from common.models.learning import (
        AuditLog,
        KnowledgeCandidate,
        KnowledgePoint,
        KnowledgeVersion,
        SystemSubject,
    )
    from services.agent_service.app.services.rag import ChromaRetriever

    engine, db = _session(root)
    versions = db.query(KnowledgeVersion).filter_by(is_active=True).all()
    index_rows = {}
    retriever = ChromaRetriever()
    for version in versions:
        source = version.corpus_path.removeprefix("knowledge_base/corpus/")
        if retriever.is_available:
            stored = retriever.collection.get(
                where={"$and": [{"subject": version.subject}, {"source": source}]},
                include=[],
            )
            index_rows[source] = len(list(stored.get("ids") or []))
        else:
            index_rows[source] = -1
        index_rows[source + "::exists"] = (KNOWLEDGE_ROOT / version.corpus_path).exists()
    state = {
        "subjects": db.query(SystemSubject).count(),
        "points": db.query(KnowledgePoint).count(),
        "candidates": db.query(KnowledgeCandidate).count(),
        "active_versions": len(versions),
        "total_versions": db.query(KnowledgeVersion).count(),
        "corpus_files": sorted(str(p.relative_to(CORPUS_DIR)) for p in CORPUS_DIR.rglob("candidate_*.md")),
        "pending_files": sorted(str(p.relative_to(CORPUS_DIR)) for p in CORPUS_DIR.rglob("candidate_*.pending")),
        "index_rows": index_rows,
        "audit_errors": db.query(AuditLog).filter_by(level="ERROR").count(),
        "chroma_available": retriever.is_available,
    }
    db.close()
    engine.dispose()
    return state


def cmd_report(args) -> int:
    root = Path(args.root).resolve()
    _bootstrap_runtime(root)
    print(json.dumps(_collect(root), ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args) -> int:
    root = Path(args.root).resolve()
    _bootstrap_runtime(root)
    state = _collect(root)
    failures: list[str] = []

    if state["active_versions"] != 1:
        failures.append(f"expected exactly 1 active version, found {state['active_versions']}")
    if state["total_versions"] != 1:
        failures.append(f"expected exactly 1 version row total, found {state['total_versions']}")
    if state["candidates"] != 1:
        failures.append(f"expected exactly 1 candidate, found {state['candidates']}")
    if state["subjects"] != 1:
        failures.append(f"expected exactly 1 subject, found {state['subjects']}")
    if len(state["corpus_files"]) != 1:
        failures.append(f"expected exactly 1 committed corpus file, found {state['corpus_files']}")
    if state["pending_files"]:
        failures.append(f"uncommitted .pending files left behind: {state['pending_files']}")
    if not state["chroma_available"]:
        failures.append("Chroma persistent collection is unavailable")
    for source, count in state["index_rows"].items():
        if source.endswith("::exists"):
            if count is not True:
                failures.append(f"corpus file missing on disk: {source}")
        elif count <= 0:
            failures.append(f"no index rows for {source}")

    print(json.dumps({"state": state, "failures": failures}, ensure_ascii=False, indent=2))
    if failures:
        print("VERIFY FAILED", file=sys.stderr)
        return 1
    print("VERIFY OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--root", required=True)
    p.add_argument("--slots", type=int, default=5)
    p.add_argument("--subject", default=f"运行时验证学科-{uuid.uuid4().hex[:6]}")
    p.add_argument("--point", default=f"运行时验证知识点-{uuid.uuid4().hex[:6]}")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("worker")
    p.add_argument("--root", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.set_defaults(func=cmd_worker)

    p = sub.add_parser("damage")
    p.add_argument("--root", required=True)
    p.add_argument("--mode", choices=["file", "index"], required=True)
    p.set_defaults(func=cmd_damage)

    p = sub.add_parser("repair")
    p.add_argument("--root", required=True)
    p.set_defaults(func=cmd_repair)

    p = sub.add_parser("report")
    p.add_argument("--root", required=True)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("verify")
    p.add_argument("--root", required=True)
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
