from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import Exercise, KnowledgeVersion, Resource, User
from services.agent_service.app.services.knowledge_versions import compare_versions, rollback_version, serialize_version

router = APIRouter(prefix="/knowledge-base/versions", tags=["knowledge-versions"])


def _get(db: Session, version_id: int):
    row = db.get(KnowledgeVersion, version_id)
    if row is None:
        raise HTTPException(404, "Knowledge version not found")
    return row


@router.get("")
def versions(candidate_id: int | None = None, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    query = db.query(KnowledgeVersion)
    if candidate_id:
        query = query.filter_by(candidate_id=candidate_id)
    return {"items": [serialize_version(row) for row in query.order_by(KnowledgeVersion.id.desc()).limit(100).all()]}


@router.get("/{version_id}/compare/{other_id}")
def compare(version_id: int, other_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    try:
        return compare_versions(_get(db, version_id), _get(db, other_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{version_id}/impact")
def impact(version_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    import json
    _get(db, version_id)
    exercises = []
    for row in db.query(Exercise).all():
        try:
            body = json.loads(row.content)
        except (ValueError, TypeError):
            continue
        if isinstance(body, dict) and version_id in body.get("knowledge_version_ids", []):
            exercises.append({"id": row.id, "review_required": body.get("knowledge_review_required", False)})
    return {"items": [{"id": row.id, "title": row.title, "review_required": row.knowledge_review_required}
                       for row in db.query(Resource).all() if version_id in (row.knowledge_versions_json or [])], "exercises": exercises}


@router.post("/{version_id}/rollback")
def rollback(version_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    try:
        return rollback_version(db, _get(db, version_id), actor_user_id=user.id)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from exc
