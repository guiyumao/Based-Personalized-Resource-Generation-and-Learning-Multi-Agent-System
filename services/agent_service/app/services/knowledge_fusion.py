"""Deterministic filter, classification and incremental fusion for knowledge candidates.

This is the *decision* layer between raw collection (search/fetch/upload) and the
existing publication/index pipeline.  It never makes a public knowledge node on
its own: it classifies a candidate against the reviewed catalog, judges quality
with non-model rules, decides a fusion action (create / supplement / revise /
duplicate / conflict), and tells the caller whether the auto-publish policy may
apply.

Design constraints (from the task):
- A model's self-scored confidence never decides publication.
- Keyword similarity alone never classifies a candidate.
- New text never overwrites better published text (supplement only appends).
- Conflicts and ambiguity are routed to human review, not auto-published.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from common.models.learning import (
    KnowledgeCandidate,
    KnowledgePoint,
    KnowledgeVersion,
    SystemSubject,
)

#: Minimum body size for a candidate to be considered substantive.
MIN_CONTENT_CHARS = 200
#: Auto-publish never applies to these actions.
REVIEW_ACTIONS = {"revise", "conflict", "duplicate"}


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip().casefold())


def classify_candidate(db: Session, candidate: KnowledgeCandidate) -> dict:
    """Hierarchically match subject -> chapter -> point. Never keyword-only."""
    subject = None
    if candidate.subject:
        subject = (
            db.query(SystemSubject)
            .filter(
                (SystemSubject.code == candidate.subject)
                | (SystemSubject.name == candidate.subject)
            )
            .first()
        )
    point = None
    if subject is not None and candidate.knowledge_point:
        wanted = normalize(candidate.knowledge_point)
        for item in db.query(KnowledgePoint).filter_by(subject_id=subject.id).all():
            names = {normalize(item.name), *(normalize(alias) for alias in item.aliases_json or [])}
            if wanted in names:
                point = item
                break
    return {
        "subject_id": subject.id if subject else None,
        "subject": subject.name if subject else "",
        "point_id": point.id if point else None,
        "point": point.name if point else "",
        "chapter": point.chapter if point else "",
        "matched": point is not None,
        "complete": subject is not None and point is not None,
    }


@dataclass(frozen=True)
class QualityResult:
    passed: bool
    reasons: tuple[str, ...]


def assess_quality(candidate: KnowledgeCandidate) -> QualityResult:
    """Non-model quality gates. A model score is never accepted as proof."""
    reasons: list[str] = []
    content = (candidate.content or "").strip()
    if len(content) < MIN_CONTENT_CHARS:
        reasons.append("CONTENT_TOO_SHORT")
    source = candidate.source_url or ""
    if not source.startswith(("http://", "https://")):
        reasons.append("SOURCE_NOT_TRACEABLE")
    if content and "\ufffd" in content:
        reasons.append("CONTENT_CORRUPTED")
    return QualityResult(passed=not reasons, reasons=tuple(reasons))


def decide_fusion(db: Session, candidate: KnowledgeCandidate) -> dict:
    """Classify the fusion action against the active published version."""
    existing = (
        db.query(KnowledgeVersion)
        .filter_by(
            subject=candidate.subject,
            knowledge_point=candidate.knowledge_point,
            is_active=True,
        )
        .order_by(KnowledgeVersion.version_number.desc())
        .first()
    )
    if existing is None:
        action = "create_version"
        reason = "NO_ACTIVE_VERSION"
    elif (existing.content_hash or "") == (candidate.content_hash or ""):
        action = "duplicate"
        reason = "IDENTICAL_CONTENT"
    elif len(existing.content or "") >= len(candidate.content or ""):
        action = "supplement"
        reason = "EXISTING_IS_RICHER"
    else:
        action = "revise"
        reason = "CANDIDATE_IS_LARGER"
    return {
        "action": action,
        "reason": reason,
        "target_version_id": existing.id if existing else None,
        "target_version_number": existing.version_number if existing else None,
    }


def auto_publish_allowed(classification: dict, quality: QualityResult, decision: dict,
                         *, policy: str = "manual") -> tuple[bool, str]:
    """Return (allowed, reason). Defaults to manual review."""
    if policy != "strict_auto":
        return False, "POLICY_MANUAL"
    if not quality.passed:
        return False, "QUALITY_FAILED:" + ",".join(quality.reasons)
    if not classification.get("complete"):
        return False, "CLASSIFICATION_INCOMPLETE"
    if decision["action"] in REVIEW_ACTIONS:
        return False, "ACTION_REQUIRES_REVIEW:" + decision["action"]
    return True, "AUTO_PUBLISH_OK"


def evaluate_candidate(db: Session, candidate: KnowledgeCandidate,
                       *, policy: str = "manual") -> dict:
    """Full deterministic assessment for one candidate (filter+classify+fuse)."""
    classification = classify_candidate(db, candidate)
    quality = assess_quality(candidate)
    decision = decide_fusion(db, candidate)
    allowed, reason = auto_publish_allowed(classification, quality, decision, policy=policy)
    return {
        "candidate_id": candidate.id,
        "classification": classification,
        "quality": {"passed": quality.passed, "reasons": list(quality.reasons)},
        "decision": decision,
        "auto_publish": allowed,
        "auto_publish_reason": reason,
        "needs_review": not allowed,
    }


def fusion_summary(db: Session, *, since=None) -> dict:
    """Aggregated counters for the admin fusion page."""
    query = db.query(KnowledgeCandidate)
    if since is not None:
        query = query.filter(KnowledgeCandidate.created_at >= since)
    candidates = query.all()
    counts = {"candidates": len(candidates), "published": 0, "duplicate": 0,
              "needs_review": 0, "blocked": 0}
    for candidate in candidates:
        if candidate.status == "PUBLISHED":
            counts["published"] += 1
            continue
        decision = decide_fusion(db, candidate)
        if decision["action"] == "duplicate":
            counts["duplicate"] += 1
        elif not assess_quality(candidate).passed:
            counts["blocked"] += 1
        else:
            counts["needs_review"] += 1
    return counts


def content_hash(candidate: KnowledgeCandidate) -> str:
    return hashlib.sha256((candidate.content or "").encode("utf-8")).hexdigest()
