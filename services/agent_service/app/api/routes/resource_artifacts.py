"""Authenticated artifacts bound to a server learning context and source version."""
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user
from common.learning_context import validate_context
from common.models.learning import ChatSession, User
from common.models.media import ResourceArtifact
from services.agent_service.app.services.assistant_tasks import (
    AssistantTaskRequestConflict,
    create_task,
    execute_task,
    task_execution_mode,
    task_to_dict,
)
from services.agent_service.app.services.resource_artifacts import FORMATS, verified_path

router = APIRouter(prefix="/learning", tags=["learning-artifacts"])


class ArtifactRequest(BaseModel):
    kind: Literal["pptx", "animation", "audio", "video"]
    client_request_id: str = Field(min_length=8, max_length=80)


@router.post("/contexts/{context_id}/artifacts", status_code=202)
def generate_artifact(context_id: str, payload: ArtifactRequest, background: BackgroundTasks,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, _, _, _, point, resource = validate_context(db, user.id, context_id)
    if resource is None:
        raise HTTPException(409, "Select a learning resource first")
    session = ChatSession(user_id=user.id, title=f"{payload.kind}学习产物", subject=f"ctx:{context_id}")
    db.add(session)
    db.flush()
    try:
        task, created = create_task(db, user_id=user.id, session=session, client_request_id=payload.client_request_id,
            action="artifact", message=f"生成{payload.kind}学习产物", knowledge_point=point.name, exercise_count=3,
            allow_session_reuse=True, learning_context_id=context_id, artifact_kind=payload.kind)
    except AssistantTaskRequestConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if created and task_execution_mode() == "background":
        background.add_task(execute_task, task.id)
    return task_to_dict(task)


@router.get("/contexts/{context_id}/artifacts")
def list_artifacts(context_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    validate_context(db, user.id, context_id)
    return {"items": [{"id": row.id, "kind": row.kind, "resource_id": row.resource_id, "resource_version": row.resource_version,
        "size": row.size, "sha256": row.sha256} for row in db.query(ResourceArtifact).filter_by(user_id=user.id, context_id=context_id).all()]}


@router.get("/artifacts/{artifact_id}/file")
def artifact_file(artifact_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(ResourceArtifact, artifact_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Artifact not found")
    validate_context(db, user.id, row.context_id)
    path = verified_path(row)
    return FileResponse(path, media_type=FORMATS[row.kind][0], filename=f"learning-{row.resource_id}.{FORMATS[row.kind][1]}",
        content_disposition_type="inline" if row.kind in {"animation", "audio", "video"} else "attachment",
        headers={"Cache-Control": "private, no-store", "Content-Security-Policy": "sandbox; default-src 'none'", "X-Content-Type-Options": "nosniff"})
