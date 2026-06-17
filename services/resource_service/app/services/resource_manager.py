"""Database-backed resource manager for generated learning assets."""

from __future__ import annotations

from sqlalchemy.orm import Session

from common.models.learning import KnowledgePoint, Resource
from services.resource_service.app.schemas.resource import ResourceItem


class ResourceManager:
    """Read generated resources stored in the shared database."""

    _status_overrides: dict[int, str] = {}

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_resources(self) -> list[ResourceItem]:
        """Return all managed resources ordered by newest first."""

        rows = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .order_by(Resource.id.desc())
            .all()
        )
        return [self._to_item(resource, knowledge_point) for resource, knowledge_point in rows]

    def get_resource(self, resource_id: int) -> ResourceItem | None:
        """Return one resource by ID."""

        row = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .filter(Resource.id == resource_id)
            .first()
        )
        if row is None:
            return None
        resource, knowledge_point = row
        return self._to_item(resource, knowledge_point)

    def update_status(self, resource_id: int, status: str) -> ResourceItem | None:
        """Update the lightweight in-service status for a resource."""

        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()
        if resource is None:
            return None

        self._status_overrides[resource_id] = status
        return self.get_resource(resource_id)

    def _to_item(self, resource: Resource, knowledge_point: KnowledgePoint | None) -> ResourceItem:
        return ResourceItem(
            id=resource.id,
            title=self._build_title(resource, knowledge_point),
            type=resource.type,  # type: ignore[arg-type]
            format=resource.format,  # type: ignore[arg-type]
            status=self._status_overrides.get(resource.id, "ready"),  # type: ignore[arg-type]
            knowledge_point=knowledge_point.name if knowledge_point is not None else "未关联知识点",
            owner_user_id=resource.generated_for_user_id,
        )

    def _build_title(self, resource: Resource, knowledge_point: KnowledgePoint | None) -> str:
        lines = (resource.content or "").strip().splitlines()
        if lines:
            heading = lines[0].strip()
            if heading.startswith("# "):
                return heading[2:].strip()

        point_name = knowledge_point.name if knowledge_point is not None else "学习资源"
        suffix_map = {
            "courseware": "课件",
            "exercise": "练习",
            "notes": "笔记",
            "exam": "试卷",
        }
        return f"{point_name}{suffix_map.get(resource.type, '资源')}"

