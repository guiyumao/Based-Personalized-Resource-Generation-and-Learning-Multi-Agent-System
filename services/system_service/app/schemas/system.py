"""Schemas for system administration APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoleAssignment(BaseModel):
    """User role assignment payload."""

    user_id: int
    role: str = Field(min_length=2, max_length=50)


class SubjectCreate(BaseModel):
    """Payload for creating a managed subject."""

    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=200)


class SubjectItem(BaseModel):
    """Subject entry."""

    id: int
    name: str
    description: str


class SystemConfigUpdate(BaseModel):
    """Payload for updating a system configuration item."""

    value: str = Field(min_length=1, max_length=200)


class SystemConfigItem(BaseModel):
    """System configuration entry."""

    key: str
    value: str


class AuditLogItem(BaseModel):
    """Audit log entry returned to the admin workspace."""

    level: str
    event: str
    message: str
