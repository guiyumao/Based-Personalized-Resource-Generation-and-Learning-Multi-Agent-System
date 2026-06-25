"""In-memory system administration manager."""

from __future__ import annotations

from services.system_service.app.schemas.system import (
    AuditLogItem,
    RoleAssignment,
    SubjectCreate,
    SubjectItem,
    SystemConfigItem,
)


class SystemManager:
    """Provide admin-side management data for the system service."""

    def __init__(self) -> None:
        self._subjects: list[SubjectItem] = []
        self._configs: list[SystemConfigItem] = []
        self._logs: list[AuditLogItem] = []

    def assign_role(self, payload: RoleAssignment) -> dict[str, object]:
        """Return one role assignment result."""

        self._logs.insert(
            0,
            AuditLogItem(
                level="INFO",
                event="role_assigned",
                message=f"Assigned role `{payload.role}` to user {payload.user_id}.",
            ),
        )
        return {
            "user_id": payload.user_id,
            "role": payload.role,
            "status": "updated",
        }

    def list_subjects(self) -> list[SubjectItem]:
        """Return configured subjects."""

        return self._subjects

    def create_subject(self, payload: SubjectCreate) -> SubjectItem:
        """Create a subject entry."""

        next_id = max((item.id for item in self._subjects), default=0) + 1
        item = SubjectItem(id=next_id, name=payload.name, description=payload.description)
        self._subjects.append(item)
        self._logs.insert(
            0,
            AuditLogItem(
                level="INFO",
                event="subject_created",
                message=f"Created subject `{payload.name}`.",
            ),
        )
        return item

    def list_configs(self) -> list[SystemConfigItem]:
        """Return system configuration items."""

        return self._configs

    def update_config(self, key: str, value: str) -> SystemConfigItem:
        """Update one config entry, creating it when absent."""

        for item in self._configs:
            if item.key == key:
                item.value = value
                self._logs.insert(
                    0,
                    AuditLogItem(
                        level="WARN",
                        event="config_updated",
                        message=f"Updated config `{key}` to `{value}`.",
                    ),
                )
                return item

        item = SystemConfigItem(key=key, value=value)
        self._configs.append(item)
        self._logs.insert(
            0,
            AuditLogItem(
                level="WARN",
                event="config_created",
                message=f"Created config `{key}` with value `{value}`.",
            ),
        )
        return item

    def list_logs(self, level: str | None = None) -> list[AuditLogItem]:
        """Return audit logs, optionally filtered by log level."""

        if not level:
            return self._logs
        normalized = level.strip().upper()
        return [item for item in self._logs if item.level.upper() == normalized]
