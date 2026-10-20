"""Version comparisons, recoverable rollback and conservative resource impact."""

import difflib
import json

from sqlalchemy.orm import Session

from common.knowledge_lock import knowledge_write_lock
from common.knowledge_paths import KNOWLEDGE_ROOT
from common.models.learning import AuditLog, Exercise, KnowledgeCandidate, KnowledgeVersion, Resource
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.knowledge_base_admin import publish_document_and_reindex


def serialize_version(version: KnowledgeVersion) -> dict:
    return {"id": version.id, "candidate_id": version.candidate_id, "number": version.version_number,
            "title": version.title, "content": version.content, "source_url": version.source_url,
            "subject": version.subject, "knowledge_point": version.knowledge_point,
            "content_hash": version.content_hash, "corpus_path": version.corpus_path,
            "published_by": version.published_by, "published_at": version.published_at.isoformat() + "Z",
            "is_active": version.is_active}


def referenced_versions(db: Session, context: dict) -> list[int]:
    sources = {str((row.get("metadata") or {}).get("source") or "")
               for row in context.get("retrieved_chunks", []) if isinstance(row, dict)}
    return [version.id for version in db.query(KnowledgeVersion).filter_by(is_active=True).all()
            if version.corpus_path.removeprefix("knowledge_base/corpus/") in sources]


def mark_impact(db: Session, old_ids: set[int]) -> dict:
    resources, exercises = [], []
    if not old_ids:
        return {"resource_ids": resources, "exercise_ids": exercises}
    for resource in db.query(Resource).all():
        if old_ids.intersection(resource.knowledge_versions_json or []):
            resource.knowledge_review_required = True
            resources.append(resource.id)
    for exercise in db.query(Exercise).all():
        try:
            body = json.loads(exercise.content)
        except (ValueError, TypeError):
            continue
        if isinstance(body, dict) and old_ids.intersection(body.get("knowledge_version_ids", [])):
            body["knowledge_review_required"] = True
            exercise.content = json.dumps(body, ensure_ascii=False)
            exercises.append(exercise.id)
    return {"resource_ids": resources, "exercise_ids": exercises}


def compare_versions(old: KnowledgeVersion, new: KnowledgeVersion) -> dict:
    if old.candidate_id != new.candidate_id:
        raise ValueError("Compare versions of the same knowledge candidate")
    return {"old": serialize_version(old), "new": serialize_version(new), "source_changed": old.source_url != new.source_url,
            "diff": "\n".join(difflib.unified_diff(old.content.splitlines(), new.content.splitlines(), fromfile=f"version-{old.id}", tofile=f"version-{new.id}", lineterm=""))}


def rollback_version(db: Session, version: KnowledgeVersion, *, actor_user_id: int, lock_token: str = "", guard=None) -> dict:
    with knowledge_write_lock(KNOWLEDGE_ROOT, inherited_token=lock_token) as token:
        db.refresh(version)
        candidate = db.get(KnowledgeCandidate, version.candidate_id)
        active = db.query(KnowledgeVersion).filter_by(candidate_id=version.candidate_id, is_active=True).all()
        target = KNOWLEDGE_ROOT / version.corpus_path
        archive = target.with_suffix(".archived")
        if archive.exists():
            content = archive.read_text(encoding="utf-8")
        else:
            content = f"# {version.title}\n\n> 来源: {version.source_url}\n> 内容哈希: {version.content_hash}\n\n{version.content}\n"
        expected = target.relative_to(KNOWLEDGE_ROOT / "knowledge_base" / "corpus").as_posix()
        matches = []
        def verify():
            from services.agent_service.app.services.knowledge_publication import verifying
            if guard:
                guard()
            with verifying(expected):
                matches[:] = KnowledgeBaseService().search_indexed(version.knowledge_point, top_k=5,
                                                                  filters={"subject": version.subject, "source": expected})
            if not any(item.get("source") == expected for item in matches):
                raise RuntimeError("Rollback retrieval verification failed")
        publish_document_and_reindex(target=target, content=content, subject=version.subject, lock_token=token,
                                     retire_paths=[KNOWLEDGE_ROOT / item.corpus_path for item in active], verify=verify)
        old_ids = {item.id for item in active}
        for item in active:
            item.is_active = False
        version.is_active = True
        candidate.published_version_id = version.id
        candidate.status = "PUBLISHED"
        candidate.title = version.title; candidate.content = version.content
        candidate.subject = version.subject; candidate.knowledge_point = version.knowledge_point
        candidate.content_hash = version.content_hash; candidate.source_url = version.source_url
        affected = mark_impact(db, old_ids)
        db.add(AuditLog(level="INFO", event="knowledge.rollback", actor_user_id=actor_user_id,
                        message=f"candidate={candidate.id} version={version.id} previous={sorted(old_ids)}"))
        try:
            if guard:
                guard(db)
            db.commit()
        except Exception:
            db.rollback()
            from services.agent_service.app.services.knowledge_publication import reconcile
            reconcile(db, lock_token=token)
            raise
        return {"version_id": version.id, "is_active": True, "retrieval_matches": len(matches), "retrieval_results": matches, "affected": affected}
