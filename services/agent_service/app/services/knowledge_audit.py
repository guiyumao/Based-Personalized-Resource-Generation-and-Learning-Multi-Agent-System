"""Read-only operations insight for automatic knowledge-base backfill.

Two things an operator needs and nothing else dares to guess:

* how much knowledge the system published on its own, and how often it failed;
* whether the three stores (SQL rows, corpus files, vector index) still agree.

Every function here is strictly read-only.  Repair stays an explicit,
audited action through the existing reconcile endpoint.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from common.knowledge_paths import CORPUS_DIR, KNOWLEDGE_ROOT
from common.models.learning import AuditLog, KnowledgeCandidate, KnowledgeVersion

PUBLISHED_EVENT = "knowledge.auto_backfill.published"
FAILED_EVENT = "knowledge.auto_backfill.failed"
COMPENSATION_EVENT = "knowledge.auto_backfill.compensation_incomplete"
ALL_EVENTS = (PUBLISHED_EVENT, FAILED_EVENT, COMPENSATION_EVENT)

AI_LICENSE_NAME = "AI_GENERATED"
AUTO_APPROVED_STATUS = "AUTO_APPROVED"

_REASON = re.compile(r"reason=(?P<reason>[A-Za-z0-9_.]+)")
_MAX_SAMPLES = 50


def _reason_of(message: str) -> str:
    match = _REASON.search(message or "")
    return match.group("reason") if match else "UNSPECIFIED"


def auto_backfill_stats(db: Session, *, days: int = 7) -> dict:
    """Count what the automatic backfill produced and how often it failed."""
    since = datetime.utcnow() - timedelta(days=max(days, 1))

    statuses: Counter[str] = Counter()
    for (status,) in db.query(KnowledgeCandidate.status).all():
        statuses[status or "UNKNOWN"] += 1

    active = db.query(KnowledgeVersion).filter_by(is_active=True).all()
    auto_published = [item for item in active if (item.license_name or "") == AI_LICENSE_NAME]

    events: Counter[str] = Counter()
    for event, created in db.query(AuditLog.event, AuditLog.created_at).filter(
        AuditLog.event.in_(ALL_EVENTS)
    ).all():
        if created is None or created >= since:
            events[event] += 1

    failures = (
        db.query(AuditLog)
        .filter(AuditLog.event == FAILED_EVENT)
        .order_by(AuditLog.id.desc())
        .limit(200)
        .all()
    )
    reasons: Counter[str] = Counter()
    recent: list[dict] = []
    for row in failures:
        reasons[_reason_of(row.message)] += 1
        if len(recent) < 10:
            recent.append(
                {
                    "id": row.id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "actor_user_id": row.actor_user_id,
                    "reason": _reason_of(row.message),
                    "message": (row.message or "")[:400],
                }
            )

    return {
        "window_days": days,
        "candidates": {
            "total": sum(statuses.values()),
            "by_status": dict(statuses),
            "auto_approved": statuses.get(AUTO_APPROVED_STATUS, 0),
        },
        "versions": {
            "active": len(active),
            "auto_published": len(auto_published),
            "human_published": len(active) - len(auto_published),
        },
        "events_in_window": dict(events),
        "failure_reasons": dict(reasons),
        "recent_failures": recent,
    }


def orphan_inspection(db: Session) -> dict:
    """Report disagreements between SQL rows, corpus files and the index."""
    active = db.query(KnowledgeVersion).filter_by(is_active=True).all()
    expected: dict[str, int] = {}
    missing_corpus_files: list[dict] = []
    for version in active:
        source = version.corpus_path.removeprefix("knowledge_base/corpus/")
        expected[source] = version.id
        if not (KNOWLEDGE_ROOT / version.corpus_path).exists():
            missing_corpus_files.append(
                {"version_id": version.id, "subject": version.subject, "source": source}
            )

    orphan_corpus_files: list[str] = []
    if CORPUS_DIR.is_dir():
        for path in CORPUS_DIR.rglob("candidate_*.md"):
            relative = path.relative_to(CORPUS_DIR).as_posix()
            if relative not in expected:
                orphan_corpus_files.append(relative)

    pending_files: list[str] = []
    if CORPUS_DIR.is_dir():
        for path in CORPUS_DIR.rglob("candidate_*.pending"):
            pending_files.append(path.relative_to(CORPUS_DIR).as_posix())

    orphan_vectors: list[str] = []
    index_available = False
    try:
        from services.agent_service.app.services.rag import ChromaRetriever

        retriever = ChromaRetriever()
        index_available = bool(retriever.is_available)
        if index_available:
            stored = retriever.collection.get(include=["metadatas"])
            for row_id, metadata in zip(
                stored.get("ids") or [], stored.get("metadatas") or []
            ):
                source = str((metadata or {}).get("source") or "")
                if not source.startswith("candidate_") and "/candidate_" not in source:
                    continue
                if source not in expected:
                    orphan_vectors.append(str(row_id))
    except Exception:  # pragma: no cover - index outage must not break the report
        index_available = False

    return {
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "index_available": index_available,
        "active_versions": len(active),
        "missing_corpus_files": missing_corpus_files,
        "orphan_corpus_files": sorted(orphan_corpus_files)[:_MAX_SAMPLES],
        "orphan_corpus_file_count": len(orphan_corpus_files),
        "pending_files": sorted(pending_files)[:_MAX_SAMPLES],
        "pending_file_count": len(pending_files),
        "orphan_vectors": sorted(orphan_vectors)[:_MAX_SAMPLES],
        "orphan_vector_count": len(orphan_vectors),
        "healthy": not (
            missing_corpus_files or orphan_corpus_files or pending_files or orphan_vectors
        ),
    }
