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


@router.get("/{resource_id}", response_model=ApiResponse[ResourceItem])
def get_resource(resource_id: int, db: Session = Depends(get_db)) -> ApiResponse[ResourceItem]:
    """Get one resource by ID."""

    manager = ResourceManager(db)
    resource = manager.get_resource(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data=resource, message="Resource fetched successfully.")


@router.post("/import-external", response_model=ApiResponse[ResourceItem])
def import_external_resource(
    payload: ExternalResourceImportRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[ResourceItem]:
    """Download an official external asset and register it as a managed learning resource."""

    manager = ResourceManager(db)
    resource = manager.import_external_resource(payload)
    return ApiResponse(data=resource, message="External resource imported successfully.")


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
