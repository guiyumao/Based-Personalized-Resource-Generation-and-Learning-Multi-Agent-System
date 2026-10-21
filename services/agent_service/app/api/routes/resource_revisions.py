"""Owner-only mindmap edits with immutable snapshots and optimistic concurrency."""
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user
from common.learning_context import validate_context
from common.models.learning import Resource, User
from common.models.media import ResourceRevision
from common.resource_version import resource_version

router = APIRouter(prefix="/learning/contexts", tags=["resource-revisions"])
resource_router = APIRouter(prefix="/learning/resources", tags=["resource-revisions"])


class MapNode(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    parent_id: str | None = Field(None, max_length=80)


class MindmapEdit(BaseModel):
    expected_resource_version: str = Field(min_length=64, max_length=64)
    nodes: list[MapNode] = Field(min_length=1, max_length=100)


def snapshot(db, user_id, resource):
    version = resource_version(resource)
    if db.query(ResourceRevision).filter_by(resource_id=resource.id, version=version).first() is None:
        db.add(ResourceRevision(id=str(uuid4()), resource_id=resource.id, user_id=user_id, version=version,
            title=resource.title, content=resource.content, structured_json=resource.structured_json))


@router.put("/{context_id}/mindmap")
def save_mindmap(context_id: str, payload: MindmapEdit, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, _, _, _, _, resource = validate_context(db, user.id, context_id)
    return save_owned_mindmap(resource, payload, db, user)


def save_owned_mindmap(resource, payload, db, user):
    if not resource or resource.generated_for_user_id != user.id or resource.type != "mind_map":
        raise HTTPException(404, "Owned mindmap required")
    if resource.publish_status == "archived":
        raise HTTPException(409, "Archived resource cannot be edited")
    if resource_version(resource) != payload.expected_resource_version:
        raise HTTPException(409, "Resource changed")
    nodes = {node.id: node for node in payload.nodes}
    if len(nodes) != len(payload.nodes) or sum(node.parent_id is None for node in payload.nodes) != 1:
        raise HTTPException(422, "Unique nodes and one root required")
    for node in payload.nodes:
        visited = {node.id}
        parent = node.parent_id
        while parent is not None:
            if parent not in nodes or parent in visited:
                raise HTTPException(422, "Mindmap has missing parent or cycle")
            visited.add(parent)
            parent = nodes[parent].parent_id
    snapshot(db, user.id, resource)
    try:
        stored = json.loads(resource.structured_json or "{}")
    except ValueError:
        stored = {}
    structured = stored.setdefault("structured", {})
    structured["nodes"] = [node.model_dump() for node in payload.nodes]
    structured["root_id"] = next(node.id for node in payload.nodes if node.parent_id is None)
    stored["content_validation"] = {"status": "passed", "source": "owner_edit", "checks": ["unique_nodes", "single_root", "acyclic"]}
    body = json.dumps(stored, ensure_ascii=False)
    markdown = f"# {resource.title or '思维导图'}\n\n" + "\n".join(f"- {node.label}" for node in payload.nodes)
    # Compare content and access state in the UPDATE itself; SQLite SELECT
    # FOR UPDATE alone would not prevent another tab's concurrent edit.
    conditions = [Resource.id == resource.id]
    for field in ("title", "content", "structured_json", "generated_for_user_id", "publish_status", "audit_status", "generation_status", "knowledge_point_id", "knowledge_versions_json", "knowledge_review_required"):
        conditions.append(getattr(Resource, field) == getattr(resource, field))
    changed = db.execute(update(Resource).where(*conditions).values(structured_json=body, content=markdown).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Mindmap changed during save")
    db.refresh(resource)
    snapshot(db, user.id, resource)
    db.commit()
    return {"resource_id": resource.id, "resource_version": resource_version(resource), "reopen_required": True}


@resource_router.get("/{resource_id}/mindmap")
def read_owned_mindmap(resource_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resource = db.get(Resource, resource_id)
    if not resource or resource.generated_for_user_id != user.id or resource.type != "mind_map":
        raise HTTPException(404, "Owned mindmap required")
    return {"resource_version": resource_version(resource), "structured_json": resource.structured_json}


@resource_router.put("/{resource_id}/mindmap")
def edit_owned_mindmap(resource_id: int, payload: MindmapEdit, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return save_owned_mindmap(db.get(Resource, resource_id), payload, db, user)


@resource_router.get("/{resource_id}/resource-history")
def owned_resource_history(resource_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resource = db.get(Resource, resource_id)
    if not resource or resource.generated_for_user_id != user.id:
        raise HTTPException(404, "Resource not found")
    return {"items": [{"version": row.version, "title": row.title, "created_at": row.created_at}
                      for row in db.query(ResourceRevision).filter_by(user_id=user.id, resource_id=resource_id)
                      .order_by(ResourceRevision.created_at.desc()).limit(100).all()]}


@router.get("/{context_id}/resource-history")
def resource_history(context_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Historical bindings remain useful for the owner's edit history, while
    # normal execution endpoints still reject stale resource versions.
    from common.models.learning import LearningContext
    context = db.get(LearningContext, context_id)
    if not context or context.user_id != user.id:
        raise HTTPException(404, "Context not found")
    resource = db.get(Resource, context.resource_id) if context.resource_id else None
    if not resource or resource.generated_for_user_id != user.id:
        raise HTTPException(404, "Resource not found")
    return {"items": [{"version": row.version, "title": row.title, "content": row.content,
        "structured_json": row.structured_json, "created_at": row.created_at} for row in db.query(ResourceRevision).filter_by(
            user_id=user.id, resource_id=resource.id).order_by(ResourceRevision.created_at.desc()).limit(100).all()]}
