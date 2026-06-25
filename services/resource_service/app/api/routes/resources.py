"""Resource management routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.response import ApiResponse
from services.resource_service.app.schemas.resource import (
    ExternalResourceImportRequest,
    ResourceExportRequest,
    ResourceItem,
    ResourceStatusUpdate,
)
from services.resource_service.app.services.resource_manager import ResourceManager

router = APIRouter()


@router.get("", response_model=ApiResponse[list[ResourceItem]])
def list_resources(db: Session = Depends(get_db)) -> ApiResponse[list[ResourceItem]]:
    """List managed learning resources."""

    manager = ResourceManager(db)
    return ApiResponse(data=manager.list_resources(), message="Resources fetched successfully.")


@router.post("/import-external", response_model=ApiResponse[ResourceItem])
def import_external_resource(
    payload: ExternalResourceImportRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[ResourceItem]:
    """Download an official external asset and register it as a managed learning resource."""

    manager = ResourceManager(db)
    resource = manager.import_external_resource(payload)
    return ApiResponse(data=resource, message="External resource imported successfully.")


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
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Export a resource to PDF or Word."""

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
def download_resource(resource_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Download the locally stored asset for an imported external resource."""

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
    db: Session = Depends(get_db),
) -> ApiResponse[ResourceItem]:
    """Update the status of a managed resource."""

    manager = ResourceManager(db)
    updated = manager.update_status(resource_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data=updated, message="Resource status updated successfully.")


@router.delete("/{resource_id}", response_model=ApiResponse[dict[str, int]])
def delete_resource(resource_id: int, db: Session = Depends(get_db)) -> ApiResponse[dict[str, int]]:
    """Delete a managed resource."""

    manager = ResourceManager(db)
    deleted = manager.delete_resource(resource_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data={"resource_id": resource_id}, message="Resource deleted successfully.")


@router.delete("", response_model=ApiResponse[dict[str, int]])
def delete_all_resources(
    source_type: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Delete all managed resources, optionally filtered by source type."""

    manager = ResourceManager(db)
    if source_type not in {None, "generated", "external_import"}:
        raise HTTPException(status_code=400, detail="Invalid source_type")

    deleted_count = manager.delete_all_resources(source_type=source_type)
    return ApiResponse(
        data={"deleted_count": deleted_count},
        message="Filtered resources deleted successfully." if source_type else "All resources deleted successfully.",
    )
