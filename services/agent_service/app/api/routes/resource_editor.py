"""Administrator resource editing routes (P1-07): rewrite and image composition."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import User
from services.agent_service.app.services.resource_editor import (
    REWRITE_STYLES,
    apply_resource_content,
    illustrate_resource,
    image_provider_status,
    insert_illustration,
    list_illustrations,
    resource_sections,
    review_illustration,
    rewrite_resource,
    set_image_provider,
)

router = APIRouter(prefix="/admin", tags=["resource-editor"], dependencies=[Depends(require_role("admin"))])


class RewriteRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    style: str = Field(default="plain", max_length=40)


class ApplyContentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500_000)
    expected_version: str = Field(default="", max_length=64)


class ImageProviderUpdate(BaseModel):
    provider: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=120)
    enabled: bool | None = None


class IllustrateRequest(BaseModel):
    section_title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(default="", max_length=1000)


@router.get("/image-provider")
def get_image_provider(db: Session = Depends(get_db)) -> dict:
    return image_provider_status(db)


@router.put("/image-provider")
def put_image_provider(
    payload: ImageProviderUpdate,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    return set_image_provider(db, admin.id, payload.provider, payload.model, payload.enabled)


@router.post("/resources/{resource_id}/rewrite")
def rewrite(
    resource_id: int,
    payload: RewriteRequest,
    db: Session = Depends(get_db),
) -> dict:
    if payload.style and payload.style not in REWRITE_STYLES:
        raise HTTPException(status_code=422, detail=f"style must be one of: {', '.join(REWRITE_STYLES)}")
    try:
        return rewrite_resource(db, resource_id, payload.instruction, payload.style)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/resources/{resource_id}/content")
def apply_content(
    resource_id: int,
    payload: ApplyContentRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return apply_resource_content(
            db, admin.id, resource_id, payload.content, payload.expected_version
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/resources/{resource_id}/sections")
def list_sections(resource_id: int, db: Session = Depends(get_db)) -> dict:
    from common.models.learning import Resource

    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return {
        "resource_id": resource_id,
        "title": resource.title,
        "sections": resource_sections(resource.content),
        "image_provider": image_provider_status(db),
    }


@router.post("/resources/{resource_id}/illustrations")
def illustrate(
    resource_id: int,
    payload: IllustrateRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return illustrate_resource(db, resource_id, payload.section_title, payload.prompt, admin.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/resources/{resource_id}/illustrations")
def get_illustrations(resource_id: int, db: Session = Depends(get_db)) -> dict:
    return {"resource_id": resource_id, "illustrations": list_illustrations(db, resource_id)}


@router.post("/resources/{resource_id}/illustrations/{illustration_id}/approve")
def approve_illustration(
    resource_id: int,
    illustration_id: str,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return review_illustration(db, illustration_id, approve=True, admin_id=admin.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/resources/{resource_id}/illustrations/{illustration_id}/reject")
def reject_illustration(
    resource_id: int,
    illustration_id: str,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return review_illustration(db, illustration_id, approve=False, admin_id=admin.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/resources/{resource_id}/illustrations/{illustration_id}/insert")
def insert_illustration_route(
    resource_id: int,
    illustration_id: str,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return insert_illustration(db, illustration_id, admin.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
