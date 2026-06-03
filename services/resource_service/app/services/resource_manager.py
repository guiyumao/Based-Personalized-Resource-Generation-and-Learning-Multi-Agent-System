"""In-memory resource manager for the resource service skeleton."""

from __future__ import annotations

from services.resource_service.app.schemas.resource import ResourceItem


class ResourceManager:
    """Simple in-memory resource manager used for the phase-2 service skeleton."""

    def __init__(self) -> None:
        self._resources = [
            ResourceItem(
                id=1,
                title="Python 循环交互课件",
                type="courseware",
                format="markdown",
                status="ready",
                knowledge_point="Python 循环",
                owner_user_id=1,
            ),
            ResourceItem(
                id=2,
                title="Python 条件判断习题集",
                type="exercise",
                format="markdown",
                status="draft",
                knowledge_point="条件判断",
                owner_user_id=1,
            ),
        ]

    def list_resources(self) -> list[ResourceItem]:
        """Return all managed resources."""

        return self._resources

    def get_resource(self, resource_id: int) -> ResourceItem | None:
        """Return one resource by ID."""

        return next((item for item in self._resources if item.id == resource_id), None)

    def update_status(self, resource_id: int, status: str) -> ResourceItem | None:
        """Update the resource status."""

        resource = self.get_resource(resource_id)
        if resource is None:
            return None
        updated = resource.model_copy(update={"status": status})
        self._resources = [updated if item.id == resource_id else item for item in self._resources]
        return updated
