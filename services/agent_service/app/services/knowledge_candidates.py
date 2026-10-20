"""Review and publish fetched knowledge with explicit provenance and versions."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from common.knowledge_paths import KNOWLEDGE_ROOT
from common.knowledge_lock import knowledge_write_lock

from common.models.learning import AuditLog, KnowledgeBuildTask, KnowledgeCandidate, KnowledgePoint, KnowledgeVersion, SystemSubject
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.knowledge_base_admin import publish_document_and_reindex

ROOT_DIR = KNOWLEDGE_ROOT


class KnowledgeCandidateConflict(ValueError):
    pass


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _subject(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not re.fullmatch(r"[a-z0-9_]{1,100}", normalized):
        raise ValueError("Subject must use letters, digits, or underscores")
    return normalized


def serialize_candidate(item: KnowledgeCandidate) -> dict[str, Any]:
    return {
        "id": item.id, "source_task_id": item.source_task_id, "subject": item.subject,
        "knowledge_point": item.knowledge_point, "title": item.title, "content": item.content,
        "source_url": item.source_url, "source_hash": item.source_hash,
        "content_hash": item.content_hash, "status": item.status,
        "review_notes": item.review_notes, "reviewed_by": item.reviewed_by,
        "published_version_id": item.published_version_id,
        "license_name": item.license_name, "license_evidence_url": item.license_evidence_url,
        "publication_allowed": item.publication_allowed,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def create_from_fetch(
    db: Session, *, actor_user_id: int, source_task_id: int, subject: str,
    knowledge_point: str,
) -> KnowledgeCandidate:
    existing = db.query(KnowledgeCandidate).filter_by(source_task_id=source_task_id).first()
    if existing:
        return existing
    task = db.get(KnowledgeBuildTask, source_task_id)
    if task is None or task.operation_type != "FETCH_SOURCE" or task.status != "COMPLETED":
        raise ValueError("Completed fetch task not found")
    source = (task.result_json or {}).get("source")
    if not isinstance(source, dict):
        raise ValueError("Fetch task has no source content")
    content = str(source.get("content") or "").strip()
    source_url = str(source.get("url") or "").strip()
    title = str(source.get("title") or knowledge_point).strip()
    if len(content) < 20 or not source_url.startswith(("http://", "https://")):
        raise ValueError("Fetched source is incomplete")
    point = knowledge_point.strip()
    if not point:
        raise ValueError("Knowledge point is required")
    item = KnowledgeCandidate(
        creator_user_id=actor_user_id, source_task_id=source_task_id,
        subject=_subject(subject or task.subject), knowledge_point=point[:160], title=title[:240],
        content=content, source_url=source_url, source_hash=_hash(source_url),
        content_hash=_hash(content), status="DRAFT", review_notes="",
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(KnowledgeCandidate).filter_by(source_task_id=source_task_id).one()
    db.refresh(item)
    return item


def edit_candidate(db: Session, item: KnowledgeCandidate, **changes: str) -> KnowledgeCandidate:
    if item.status not in {"DRAFT", "REJECTED", "APPROVED"}:
        raise KnowledgeCandidateConflict("Candidate cannot be edited from its current state")
    for field in ("title", "knowledge_point", "content"):
        if field in changes:
            value = changes[field].strip()
            if not value:
                raise ValueError(f"{field} is required")
            setattr(item, field, value[:240] if field == "title" else value[:160] if field == "knowledge_point" else value)
    if "subject" in changes:
        item.subject = _subject(changes["subject"])
    for field in ("license_name", "license_evidence_url"):
        if field in changes:
            setattr(item, field, str(changes[field]).strip())
    if "publication_allowed" in changes:
        item.publication_allowed = changes["publication_allowed"] is True
    if len(item.content) < 20:
        raise ValueError("Candidate content must contain at least 20 characters")
    item.content_hash = _hash(item.content)
    item.status = "DRAFT"
    item.reviewed_at = None; item.reviewed_by = None; item.review_notes = ""
    db.commit()
    db.refresh(item)
    return item


def submit_candidate(db: Session, item: KnowledgeCandidate) -> KnowledgeCandidate:
    if item.status not in {"DRAFT", "REJECTED"}:
        raise KnowledgeCandidateConflict("Candidate cannot be submitted from its current state")
    item.status = "PENDING_REVIEW"
    item.review_notes = ""
    db.commit(); db.refresh(item)
    return item


def review_candidate(
    db: Session, item: KnowledgeCandidate, *, reviewer_user_id: int, approved: bool, notes: str,
) -> KnowledgeCandidate:
    if item.status != "PENDING_REVIEW":
        raise KnowledgeCandidateConflict("Only pending candidates can be reviewed")
    if not approved and not notes.strip():
        raise ValueError("Rejection notes are required")
    item.status = "APPROVED" if approved else "REJECTED"
    item.review_notes = notes.strip()
    item.reviewed_by = reviewer_user_id
    item.reviewed_at = datetime.utcnow()
    db.add(AuditLog(level="INFO", event="knowledge.reviewed", actor_user_id=reviewer_user_id,
                    message=f"candidate={item.id} decision={'APPROVE' if approved else 'REJECT'}"))
    db.commit(); db.refresh(item)
    return item


def _document(item: KnowledgeCandidate) -> str:
    return (
        f"# {item.title}\n\n"
        f"> 文档ID: candidate-{item.id}-{item.content_hash[:12]}\n"
        f"> 来源: {item.source_url}\n"
        f"> 来源类型: administrator_reviewed_candidate\n"
        f"> 授权: {item.license_name}\n"
        f"> 学科: {item.subject} | 难度: 未标注\n"
        f"> 内容哈希: {item.content_hash}\n"
        f"> 更新时间: {datetime.utcnow().isoformat()}Z\n\n"
        f"## 知识点\n\n{item.knowledge_point}\n\n## 正文\n\n{item.content.strip()}\n"
    )


def publish_candidate(db: Session, item: KnowledgeCandidate, *, publisher_user_id: int, guard=None) -> tuple[KnowledgeVersion, list[dict[str, object]]]:
    with knowledge_write_lock(ROOT_DIR) as token:
        db.refresh(item)
        if guard:
            guard()
        return _publish_candidate(db, item, publisher_user_id=publisher_user_id, lock_token=token, guard=guard)


def _publish_candidate(db: Session, item: KnowledgeCandidate, *, publisher_user_id: int, lock_token: str, guard=None) -> tuple[KnowledgeVersion, list[dict[str, object]]]:
    if item.status == "PUBLISHED" and item.published_version_id:
        version = db.get(KnowledgeVersion, item.published_version_id)
        if version and version.is_active:
            matches = KnowledgeBaseService().search_indexed(version.knowledge_point, top_k=10,
                filters={"subject": version.subject, "source": version.corpus_path.removeprefix("knowledge_base/corpus/")})
            if not matches:
                raise RuntimeError("Published version is not currently retrievable; run publication reconciliation")
            return version, matches
    if item.status != "APPROVED":
        raise KnowledgeCandidateConflict("Candidate must be approved before publication")
    from common.knowledge_paths import PROJECT_ROOT
    from services.agent_service.app.services.deepseek_search import _public_url
    if not item.publication_allowed or not item.license_name or not _public_url(item.license_evidence_url):
        raise KnowledgeCandidateConflict("Verified publication permission and a license evidence URL are required")
    if item.license_name == "INTERNAL_TEST_ONLY" and ROOT_DIR == PROJECT_ROOT:
        raise KnowledgeCandidateConflict("Internal test permissions cannot publish to the shared corpus")
    existing = db.query(KnowledgeVersion).filter_by(candidate_id=item.id, content_hash=item.content_hash).first()
    if existing:
        if existing.subject != item.subject:
            raise KnowledgeCandidateConflict("Changing subject requires a new content revision")
        from services.agent_service.app.services.knowledge_versions import rollback_version
        result = rollback_version(db, existing, actor_user_id=publisher_user_id, lock_token=lock_token, guard=guard)
        return existing, result.get("retrieval_results", [])
    relative = Path("knowledge_base") / "corpus" / item.subject / f"candidate_{item.id}_{item.content_hash[:12]}.md"
    target = ROOT_DIR / relative
    previous = db.query(KnowledgeVersion).filter_by(candidate_id=item.id, is_active=True).all()
    expected = relative.relative_to("knowledge_base/corpus").as_posix()
    verified = []
    def verify() -> None:
        from services.agent_service.app.services.knowledge_publication import verifying
        if guard:
            guard()
        with verifying(expected):
            matches = KnowledgeBaseService().search_indexed(item.knowledge_point, top_k=10, filters={"subject": item.subject, "source": expected})
        verified[:] = [row for row in matches if row.get("source") == expected]
        if not verified:
            raise RuntimeError("Published document was not returned by indexed retrieval")
    try:
        publish_document_and_reindex(target=target, content=_document(item), subject=item.subject, lock_token=lock_token,
                                     retire_paths=[ROOT_DIR / version.corpus_path for version in previous], verify=verify)
        if not verified:
            verify()
    except Exception:
        # Keep the reviewed source and candidate; a retry reuses the same deterministic file.
        raise
    version_number = db.query(KnowledgeVersion).filter_by(candidate_id=item.id).count() + 1
    for old in previous:
        old.is_active = False
    version = KnowledgeVersion(
        candidate_id=item.id, version_number=version_number, subject=item.subject,
        knowledge_point=item.knowledge_point, title=item.title, content=item.content,
        source_url=item.source_url, content_hash=item.content_hash,
        corpus_path=relative.as_posix(), published_by=publisher_user_id,
        published_at=datetime.utcnow(),
        license_name=item.license_name, license_evidence_url=item.license_evidence_url,
    )
    try:
        db.add(version)
        db.flush()
    except Exception:
        db.rollback()
        from services.agent_service.app.services.knowledge_publication import reconcile
        reconcile(db, lock_token=lock_token)
        raise
    item.status = "PUBLISHED"; item.published_version_id = version.id
    subject = db.query(SystemSubject).filter_by(code=item.subject).first()
    if subject:
        point = db.query(KnowledgePoint).filter_by(subject_id=subject.id, name=item.knowledge_point).first()
        if point:
            point.construction_status = "PUBLISHED"
    old_ids = {old.id for old in previous}
    from services.agent_service.app.services.knowledge_versions import mark_impact
    mark_impact(db, old_ids)
    db.add(AuditLog(level="INFO", event="knowledge.published", actor_user_id=publisher_user_id,
                    message=f"candidate={item.id} version={version.id} content_hash={item.content_hash}"))
    try:
        if guard:
            guard(db)
        db.commit()
    except Exception:
        db.rollback()
        from services.agent_service.app.services.knowledge_publication import reconcile
        reconcile(db, lock_token=lock_token)
        raise
    db.refresh(version)
    return version, verified


def start_revision(db: Session, item: KnowledgeCandidate) -> KnowledgeCandidate:
    if item.status not in {"PUBLISHED", "WITHDRAWN"} or not item.published_version_id:
        raise KnowledgeCandidateConflict("A published candidate is required for revision")
    item.status = "DRAFT"
    item.reviewed_at = None; item.reviewed_by = None; item.review_notes = ""
    db.commit(); db.refresh(item)
    return item
