"""Resource management routes.

Authorization matrix (DEF-007):

======================  ==========================================  ==============================
Endpoint                Requirement                                 Rationale
======================  ==========================================  ==============================
GET  /resources         public (read-only catalog)                  exposes metadata only, no file bytes
GET  /resources/{id}    public (read-only catalog)                  same payload shape as the list
GET  /recommendations   authenticated learner                       per-user personalized data
POST /{id}/interactions authenticated learner                       writes user-scoped feedback
GET  /{id}/download     authenticated (any role)                    serves local file bytes to learners
POST /import-external   teacher | admin                             mutates the managed catalog
POST /{id}/export       teacher | admin                             generates downloadable artifacts
PATCH /{id}/status      teacher | admin                             publishes/archives content
DELETE /{id}            teacher | admin                             destructive
DELETE /resources       admin + explicit confirmation header         bulk destruction
======================  ==========================================  ==============================

Every write path resolves authentication/authorization **before** touching
``ResourceManager``, so unauthenticated callers never reach business logic.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user, require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.resource_service.app.schemas.resource import (
    ExternalResourceImportRequest,
    ResourceExportRequest,
    ResourceInteractionCreate,
    ResourceInteractionSummary,
    ResourceItem,
    ResourceRecommendationItem,
    ResourceStatusUpdate,
)
from services.resource_service.app.services.resource_manager import ResourceManager

router = APIRouter()

#: Header that must accompany the bulk-delete call so a bare URL visit can never
#: destroy the whole catalog.
BULK_DELETE_CONFIRMATION_HEADER = "X-Confirm-Delete-All"
BULK_DELETE_CONFIRMATION_VALUE = "true"

_STAFF_ROLES = ("teacher", "admin")


@router.get("", response_model=ApiResponse[list[ResourceItem]])
def list_resources(db: Session = Depends(get_db)) -> ApiResponse[list[ResourceItem]]:
    """List managed learning resources."""

    manager = ResourceManager(db)
    return ApiResponse(data=manager.list_resources(), message="Resources fetched successfully.")


@router.post("/import-external", response_model=ApiResponse[ResourceItem])
def import_external_resource(
    payload: ExternalResourceImportRequest,
    _user: User = Depends(require_role(*_STAFF_ROLES)),
    db: Session = Depends(get_db),
) -> ApiResponse[ResourceItem]:
    """Download an official external asset and register it as a managed learning resource.

    (teacher or admin only)
    """

    manager = ResourceManager(db)
    resource = manager.import_external_resource(payload)
    return ApiResponse(data=resource, message="External resource imported successfully.")


@router.get("/recommendations", response_model=ApiResponse[list[ResourceRecommendationItem]])
def recommend_resources(
    limit: int = Query(default=6, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[ResourceRecommendationItem]]:
    """Return explainable recommendations for the authenticated learner."""

    manager = ResourceManager(db)
    return ApiResponse(
        data=manager.recommend_resources(current_user.id, limit=limit),
        message="Personalized resources fetched successfully.",
    )


@router.post("/{resource_id}/interactions", response_model=ApiResponse[ResourceInteractionSummary])
def record_resource_interaction(
    resource_id: int,
    payload: ResourceInteractionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ResourceInteractionSummary]:
    """Record an authenticated view, download, or source-open event."""

    manager = ResourceManager(db)
    summary = manager.record_interaction(current_user.id, resource_id, payload.action)
    if summary is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data=summary, message="Resource interaction recorded.")


@router.get("/{resource_id}", response_model=ApiResponse[ResourceItem])
def get_resource(resource_id: int, db: Session = Depends(get_db)) -> ApiResponse[ResourceItem]:
    """Get one resource by ID."""

    manager = ResourceManager(db)
    resource = manager.get_resource(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data=resource, message="Resource fetched successfully.")


@router.post("/{resource_id}/export", response_model=ApiResponse[dict[str, str]])
def export_resource(
    resource_id: int,
    payload: ResourceExportRequest,
    _user: User = Depends(require_role(*_STAFF_ROLES)),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Export a resource to PDF or Word. (teacher or admin only)"""

    manager = ResourceManager(db)
    resource = manager.get_resource(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(
        data={
            "resource_id": str(resource_id),
            "export_format": payload.export_format,
            "download_url": f"/resources/{resource_id}/downloads/{payload.export_format}",
        },
        message="Export task created successfully.",
    )


@router.get("/{resource_id}/download")
def download_resource(
    resource_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the locally stored asset for an imported external resource.

    Requires an authenticated caller: this endpoint streams local file bytes, so
    it must not stay anonymously reachable. Any authenticated role may download,
    preserving the existing learner download flow.
    """

    manager = ResourceManager(db)
    download = manager.get_download_info(resource_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Downloadable file not found")

    file_path = Path(download["absolute_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Downloaded file is missing from storage")

    return FileResponse(
        path=file_path,
        media_type=download["media_type"],
        filename=download["file_name"],
    )


@router.patch("/{resource_id}/status", response_model=ApiResponse[ResourceItem])
def update_resource_status(
    resource_id: int,
    payload: ResourceStatusUpdate,
    _user: User = Depends(require_role(*_STAFF_ROLES)),
    db: Session = Depends(get_db),
) -> ApiResponse[ResourceItem]:
    """Update the status of a managed resource. (teacher or admin only)"""

    manager = ResourceManager(db)
    try:
        updated = manager.update_status(resource_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data=updated, message="Resource status updated successfully.")


@router.delete("/{resource_id}", response_model=ApiResponse[dict[str, int]])
def delete_resource(
    resource_id: int,
    _user: User = Depends(require_role(*_STAFF_ROLES)),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Delete a managed resource. (teacher or admin only)"""

    manager = ResourceManager(db)
    deleted = manager.delete_resource(resource_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data={"resource_id": resource_id}, message="Resource deleted successfully.")


@router.delete("", response_model=ApiResponse[dict[str, int]])
def delete_all_resources(
    source_type: str | None = None,
    confirmation: str | None = Header(
        default=None,
        alias=BULK_DELETE_CONFIRMATION_HEADER,
        description=(
            "Must be exactly 'true'. Prevents a bare URL/API visit from wiping the catalog."
        ),
    ),
    _user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Delete all managed resources, optionally filtered by source type.

    (admin only, plus an explicit confirmation header)
    """

    if (confirmation or "").strip().lower() != BULK_DELETE_CONFIRMATION_VALUE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Bulk deletion requires an explicit confirmation: send header "
                f"'{BULK_DELETE_CONFIRMATION_HEADER}: {BULK_DELETE_CONFIRMATION_VALUE}'."
            ),
        )

    manager = ResourceManager(db)
    if source_type not in {None, "generated", "external_import"}:
        raise HTTPException(status_code=400, detail="Invalid source_type")

    deleted_count = manager.delete_all_resources(source_type=source_type)
    return ApiResponse(
        data={"deleted_count": deleted_count},
        message="Filtered resources deleted successfully."
        if source_type
        else "All resources deleted successfully.",
    )
