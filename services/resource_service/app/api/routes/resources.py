"""Resource management routes."""

from fastapi import APIRouter, HTTPException

from common.schemas.response import ApiResponse
from services.resource_service.app.schemas.resource import (
    ResourceExportRequest,
    ResourceItem,
    ResourceStatusUpdate,
)
from services.resource_service.app.services.resource_manager import ResourceManager

router = APIRouter()
manager = ResourceManager()


@router.get("", response_model=ApiResponse[list[ResourceItem]])
def list_resources() -> ApiResponse[list[ResourceItem]]:
    """List managed learning resources."""

    return ApiResponse(data=manager.list_resources(), message="Resources fetched successfully.")


@router.get("/{resource_id}", response_model=ApiResponse[ResourceItem])
def get_resource(resource_id: int) -> ApiResponse[ResourceItem]:
    """Get one resource by ID."""

    resource = manager.get_resource(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data=resource, message="Resource fetched successfully.")


@router.post("/{resource_id}/export", response_model=ApiResponse[dict[str, str]])
def export_resource(resource_id: int, payload: ResourceExportRequest) -> ApiResponse[dict[str, str]]:
    """Export a resource to PDF or Word."""

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


@router.patch("/{resource_id}/status", response_model=ApiResponse[ResourceItem])
def update_resource_status(
    resource_id: int,
    payload: ResourceStatusUpdate,
) -> ApiResponse[ResourceItem]:
    """Update the status of a managed resource."""

    updated = manager.update_status(resource_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ApiResponse(data=updated, message="Resource status updated successfully.")
