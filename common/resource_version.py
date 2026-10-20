"""Opaque version of stored resource content and access state."""

import hashlib
import json

from common.models.learning import Resource


def resource_version(resource: Resource) -> str:
    content = [
        resource.id,
        resource.title,
        resource.content,
        resource.structured_json,
        resource.knowledge_point_id,
        resource.generated_for_user_id,
        resource.generation_status,
        resource.audit_status,
        resource.publish_status,
        resource.knowledge_versions_json,
        resource.knowledge_review_required,
    ]
    return hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
