"""System administration routes.

Auth classification:
- GET  /subjects      : PUBLIC (read-only catalog)
- GET  /configs       : PUBLIC (read-only, used by other services)
- POST /roles/assign  : PROTECTED (admin only)
- POST /subjects      : PROTECTED (admin only)
- PUT  /configs/{key} : PROTECTED (admin only)
- GET  /logs          : PROTECTED (admin only)
"""

from fastapi import APIRouter, Depends, Query

from common.dependencies import require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.system_service.app.schemas.system import (
    AuditLogItem,
    RoleAssignment,
    SubjectCreate,
    SubjectItem,
    SystemConfigItem,
    SystemConfigUpdate,
)
from services.system_service.app.services.system_manager import SystemManager

router = APIRouter()
manager = SystemManager()


@router.post("/roles/assign", response_model=ApiResponse[dict[str, object]])
def assign_role(
    payload: RoleAssignment,
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[dict[str, object]]:
    """Assign a role to a user. (admin only)"""

    return ApiResponse(data=manager.assign_role(payload), message="Role assigned successfully.")


@router.get("/subjects", response_model=ApiResponse[list[SubjectItem]])
def list_subjects() -> ApiResponse[list[SubjectItem]]:
    """List all managed subjects. (public)"""

    return ApiResponse(data=manager.list_subjects(), message="Subjects fetched successfully.")


@router.post("/subjects", response_model=ApiResponse[SubjectItem])
def create_subject(
    payload: SubjectCreate,
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[SubjectItem]:
    """Create a new managed subject. (admin only)"""

    return ApiResponse(data=manager.create_subject(payload), message="Subject created successfully.")


@router.get("/configs", response_model=ApiResponse[list[SystemConfigItem]])
def list_configs() -> ApiResponse[list[SystemConfigItem]]:
    """List system configuration entries. (public, read-only)"""

    return ApiResponse(data=manager.list_configs(), message="Configs fetched successfully.")


@router.put("/configs/{key}", response_model=ApiResponse[SystemConfigItem])
def update_config(
    key: str,
    payload: SystemConfigUpdate,
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[SystemConfigItem]:
    """Update one system configuration entry. (admin only)"""

    return ApiResponse(
        data=manager.update_config(key, payload.value),
        message="Config updated successfully.",
    )


@router.get("/logs", response_model=ApiResponse[list[AuditLogItem]])
def list_logs(
    level: str | None = Query(default=None),
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[list[AuditLogItem]]:
    """List system operation logs. (admin only)"""

    return ApiResponse(data=manager.list_logs(level), message="Logs fetched successfully.")
