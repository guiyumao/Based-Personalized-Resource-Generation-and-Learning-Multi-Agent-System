"""Administrator candidate review and publication API."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import AuditLog, KnowledgeCandidate, KnowledgeVersion, User
from services.agent_service.app.services.knowledge_candidates import (
    KnowledgeCandidateConflict, create_from_fetch, edit_candidate, publish_candidate,
    review_candidate, serialize_candidate, submit_candidate,
    start_revision,
)

router = APIRouter(prefix="/knowledge-base/candidates", tags=["knowledge-candidates"])


class CandidateCreate(BaseModel):
    source_task_id: int
    subject: str = Field(min_length=1, max_length=100)
    knowledge_point: str = Field(min_length=1, max_length=160)


class CandidateEdit(BaseModel):
    subject: str | None = Field(default=None, max_length=100)
    knowledge_point: str | None = Field(default=None, max_length=160)
    title: str | None = Field(default=None, max_length=240)
    content: str | None = None
    license_name: str | None = Field(default=None, max_length=100)
    license_evidence_url: str | None = Field(default=None, max_length=8192)
    publication_allowed: bool | None = None


class CandidateReview(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    notes: str = Field(default="", max_length=2000)


class PublishTaskRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=80)


@router.post("/{candidate_id}/publish-task", status_code=202)
def publish_task(candidate_id: int, payload: PublishTaskRequest, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    from services.agent_service.app.services.knowledge_tasks import create_task, serialize_task
    try:
        candidate = _get(db, candidate_id)
        return serialize_task(create_task(db, actor_user_id=user.id, client_request_id=payload.client_request_id,
                                         operation_type="PUBLISH_CANDIDATE", subject=candidate.subject,
                                         requirements={"candidate_id": candidate.id}))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{candidate_id}/withdraw")
def withdraw(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    from common.models.learning import AuditLog
    from common.knowledge_lock import knowledge_write_lock
    from common.knowledge_paths import KNOWLEDGE_ROOT
    from services.agent_service.app.services.knowledge_tasks import create_task, serialize_task
    with knowledge_write_lock(KNOWLEDGE_ROOT):
        candidate = _get(db, candidate_id)
        db.query(KnowledgeVersion).filter_by(candidate_id=candidate.id).update({"is_active": False})
        candidate.status = "WITHDRAWN"
        db.add(AuditLog(level="INFO", actor_user_id=user.id, event="knowledge.withdrawn", message=f"candidate={candidate.id}"))
        # Remove public read authorization first, even if subsequent cleanup is
        # interrupted. Persistent reconciliation can safely be retried.
        from uuid import uuid4
        task = create_task(db, actor_user_id=user.id, client_request_id=f"withdraw-{uuid4().hex}", operation_type="RECONCILE_PUBLICATIONS")
        return {"candidate_id": candidate.id, "status": candidate.status, "cleanup_task": serialize_task(task)}


def _get(db: Session, candidate_id: int) -> KnowledgeCandidate:
    item = db.get(KnowledgeCandidate, candidate_id)
    if item is None:
        raise HTTPException(404, "Knowledge candidate not found")
    return item


@router.get("")
def list_candidates(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    items = db.query(KnowledgeCandidate).order_by(KnowledgeCandidate.id.desc()).limit(limit).all()
    return {"items": [serialize_candidate(item) for item in items]}


@router.get("/{candidate_id}/diff")
def candidate_diff(candidate_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    import difflib
    item = _get(db, candidate_id)
    old = db.get(KnowledgeVersion, item.published_version_id) if item.published_version_id else None
    return {"candidate_id": item.id, "old_version_id": old.id if old else None,
            "source_changed": bool(old and old.source_url != item.source_url),
            "diff": "\n".join(difflib.unified_diff((old.content if old else "").splitlines(), item.content.splitlines(),
                                                   fromfile=f"version-{old.id}" if old else "empty", tofile="candidate-draft", lineterm=""))}


@router.post("", status_code=201)
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    try:
        return serialize_candidate(create_from_fetch(db, actor_user_id=user.id, **payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/{candidate_id}")
def update_candidate(candidate_id: int, payload: CandidateEdit, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    try:
        db.add(AuditLog(level="INFO", event="knowledge.candidate.edited", actor_user_id=getattr(_user, "id", None), message=f"candidate={candidate_id}"))
        return serialize_candidate(edit_candidate(db, _get(db, candidate_id), **payload.model_dump(exclude_none=True)))
    except KnowledgeCandidateConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{candidate_id}/submit")
def submit(candidate_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    try:
        db.add(AuditLog(level="INFO", event="knowledge.candidate.submitted", actor_user_id=getattr(_user, "id", None), message=f"candidate={candidate_id}"))
        return serialize_candidate(submit_candidate(db, _get(db, candidate_id)))
    except KnowledgeCandidateConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{candidate_id}/revision")
def revision(candidate_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    try:
        db.add(AuditLog(level="INFO", event="knowledge.candidate.revision", actor_user_id=getattr(_user, "id", None), message=f"candidate={candidate_id}"))
        return serialize_candidate(start_revision(db, _get(db, candidate_id)))
    except KnowledgeCandidateConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{candidate_id}/review")
def review(candidate_id: int, payload: CandidateReview, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    try:
        item = review_candidate(db, _get(db, candidate_id), reviewer_user_id=user.id, approved=payload.decision == "APPROVE", notes=payload.notes)
        return serialize_candidate(item)
    except KnowledgeCandidateConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{candidate_id}/publish")
def publish(candidate_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    try:
        version, matches = publish_candidate(db, _get(db, candidate_id), publisher_user_id=user.id)
        return {"candidate": serialize_candidate(_get(db, candidate_id)), "version_id": version.id, "corpus_path": version.corpus_path, "retrieval_matches": len(matches)}
    except KnowledgeCandidateConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
