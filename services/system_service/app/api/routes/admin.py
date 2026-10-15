"""System administration routes.

Auth classification:
- GET  /subjects      : PUBLIC (read-only catalog)
- GET  /configs       : PROTECTED (admin only) — values are free-form strings and
                        may hold credentials, so anonymous read was closed (DEF-006)
- POST /roles/assign  : PROTECTED (admin only)
- POST /subjects      : PROTECTED (admin only)
- PUT  /configs/{key} : PROTECTED (admin only)
- GET  /logs          : PROTECTED (admin only)
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query

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
from services.system_service.app.services.system_persistence import SystemManager

LOGGER = logging.getLogger(__name__)

router = APIRouter()
manager = SystemManager()

#: Config keys matching any of these are never returned, even to an administrator.
#: Keys are free-form, so a defence-in-depth filter is required on top of RBAC.
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(secret|password|passwd|pwd|token|credential|private[_-]?key|api[_-]?key|"
    r"access[_-]?key|salt|dsn|connection[_-]?string|database[_-]?url|"
    r"jwt|session[_-]?key|smtp|webhook)",
    re.IGNORECASE,
)


def _is_sensitive_key(key: str) -> bool:
    """Return True when a config key looks like it holds a secret."""

    return bool(_SENSITIVE_KEY_PATTERN.search(str(key or "")))


def _filter_configs(items: list[SystemConfigItem]) -> list[SystemConfigItem]:
    """Drop sensitive-looking entries from a config listing."""

    kept, dropped = [], []
    for item in items:
        (dropped if _is_sensitive_key(item.key) else kept).append(item)
    if dropped:
        LOGGER.warning(
            "system_configs_sensitive_keys_suppressed count=%d keys=%s",
            len(dropped),
            ", ".join(sorted(i.key for i in dropped))[:200],
        )
    return kept


@router.post("/roles/assign", response_model=ApiResponse[dict[str, object]])
def assign_role(
    payload: RoleAssignment,
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[dict[str, object]]:
    """Assign a role to a user. (admin only)"""

    try:
        result = manager.assign_role(payload, _user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiResponse(data=result, message="Role assigned successfully.")


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

    try:
        item = manager.create_subject(payload, _user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(data=item, message="Subject created successfully.")


@router.get("/configs", response_model=ApiResponse[list[SystemConfigItem]])
def list_configs(
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[list[SystemConfigItem]]:
    """List system configuration entries. (admin only; sensitive keys filtered)

    Values are free-form strings, so this listing is limited to administrators and
    additionally drops any entry whose key looks like a credential.
    """

    return ApiResponse(
        data=_filter_configs(manager.list_configs()),
        message="Configs fetched successfully.",
    )


@router.put("/configs/{key}", response_model=ApiResponse[SystemConfigItem])
def update_config(
    key: str,
    payload: SystemConfigUpdate,
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[SystemConfigItem]:
    """Update one system configuration entry. (admin only)"""

    return ApiResponse(
        data=manager.update_config(key, payload.value, _user.id),
        message="Config updated successfully.",
    )


@router.get("/logs", response_model=ApiResponse[list[AuditLogItem]])
def list_logs(
    level: str | None = Query(default=None),
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[list[AuditLogItem]]:
    """List system operation logs. (admin only)"""

    return ApiResponse(data=manager.list_logs(level), message="Logs fetched successfully.")
