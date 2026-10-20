"""Private snapshots never enter public relation tables or shared graph caches."""

import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from common.models.learning import KnowledgePoint, Resource, User
from common.resource_version import resource_version


def private_resource_graph(
    db: Session, user: User, resource_id: int, topic: str, expected_version: str | None
) -> dict:
    resource = db.get(Resource, resource_id)
    if not resource or (resource.generated_for_user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Resource not found")
    if resource.publish_status == "archived":
        raise HTTPException(409, "Resource is archived")
    point = (
        db.get(KnowledgePoint, resource.knowledge_point_id) if resource.knowledge_point_id else None
    )
    if not point or point.name != topic:
        raise HTTPException(409, "Resource knowledge point does not match")
    if not expected_version or resource_version(resource) != expected_version:
        raise HTTPException(409, "Resource version changed")
    nodes = [{"id": topic, "label": topic, "category": "current"}]
    edges = []
    headings = list(
        dict.fromkeys(re.findall(r"^#{1,6}\s+(.{1,100})$", resource.content or "", re.MULTILINE))
    )[:24]
    for index, heading in enumerate(headings):
        node_id = f"resource-{resource.id}-section-{index}"
        nodes.append({"id": node_id, "label": heading.strip(), "category": "resource"})
        edges.append({"source": topic, "target": node_id, "label": "资源章节"})
    return {"nodes": nodes, "edges": edges}
