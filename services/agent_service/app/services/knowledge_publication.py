"""Fail-closed visibility and replayable reconciliation of reviewed publications.

Chroma and SQL do not share a transaction. SQL active versions authorize reads;
the existing persistent knowledge task queue retries deterministic writes.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from sqlalchemy.orm import Session

from common.db.session import SessionLocal
from common.knowledge_lock import knowledge_write_lock
from common.knowledge_paths import CORPUS_DIR, KNOWLEDGE_ROOT
from common.models.learning import KnowledgeVersion

_verification_source: ContextVar[str] = ContextVar("publication_verification_source", default="")


@contextmanager
def verifying(source: str):
    token = _verification_source.set(source)
    try:
        yield
    finally:
        _verification_source.reset(token)


def visible_chunks(rows: list[dict]) -> list[dict]:
    # Personal AI-draft chunks (P0-4) are only readable through the owner-scoped
    # ``ChromaRetriever.retrieve_personal`` path. The public gate fail-closes them
    # so a learner's private draft can never leak into public retrieval.
    rows = [
        row for row in rows
        if str((row.get("metadata") or {}).get("scope") or "") != "personal_draft"
    ]

    def source(row):
        return str((row.get("metadata") or {}).get("source") or "")

    def managed(row):
        return Path(source(row)).name.startswith("candidate_")

    if not any(managed(row) for row in rows):
        return rows
    # No result cache may bypass this current database check. If SQL is down,
    # managed rows are unavailable; unrelated legacy corpus can still be read.
    try:
        with SessionLocal() as db:
            active = {
                v.corpus_path.removeprefix("knowledge_base/corpus/")
                for v in db.query(KnowledgeVersion).filter_by(is_active=True).all()
            }
    except Exception:
        active = set()
    return [
        row
        for row in rows
        if not managed(row) or source(row) in active or source(row) == _verification_source.get()
    ]


def reconcile(db: Session, *, guard=None, lock_token: str = "") -> dict:
    """Restore SQL-authorized files and retire uncommitted candidate files.

    Repeat after interrupted publication, cancellation or DB failure. Never
    modifies uploaded originals or non-candidate legacy corpus files.
    """
    from services.agent_service.app.services.knowledge_base_admin import _run_index_command
    from services.agent_service.app.services.rag import clear_retrieval_runtime_caches

    with knowledge_write_lock(KNOWLEDGE_ROOT, inherited_token=lock_token) as token:
        db.expire_all()
        active = db.query(KnowledgeVersion).filter_by(is_active=True).all()
        expected = set()
        subjects = set()
        for version in active:
            path = (KNOWLEDGE_ROOT / version.corpus_path).resolve()
            if not path.is_relative_to(CORPUS_DIR.resolve()) or not path.name.startswith(
                "candidate_"
            ):
                raise ValueError("Invalid publication corpus path")
            expected.add(path)
            subjects.add(version.subject)
            if guard:
                guard()
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                archive = path.with_suffix(".archived")
                if archive.exists():
                    archive.replace(path)
                else:
                    path.write_text(
                        f"# {version.title}\n\n> 来源: {version.source_url}\n\n{version.content}\n",
                        encoding="utf-8",
                    )
        retired = []
        for path in CORPUS_DIR.rglob("candidate_*.md"):
            if not path.resolve().is_relative_to(CORPUS_DIR.resolve()):
                raise ValueError("Unsafe publication path")
            if path.resolve() not in expected:
                if guard:
                    guard()
                subjects.add(path.parent.name)
                path.replace(path.with_suffix(".pending"))
                retired.append(path.name)
        # Even when a prior attempt already moved files, its manifest can still
        # have orphan vectors. Reindex all known candidate subjects on replay.
        for path in CORPUS_DIR.rglob("candidate_*.pending"):
            subjects.add(path.parent.name)
        for subject in sorted(subjects):
            if guard:
                guard()
            _run_index_command(subject=subject, force=False, lock_token=token)
        clear_retrieval_runtime_caches()
        return {
            "active_versions": len(active),
            "retired_files": retired,
            "subjects": sorted(subjects),
        }
