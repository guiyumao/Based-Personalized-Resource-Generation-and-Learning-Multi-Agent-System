"""Schemas for resource management APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Every resource kind this system can store.  The list is deliberately open at
# the type level (``str``) while these constants document the registered kinds:
# archived rows written before a kind existed must still deserialize, because
# reading history must never fail just because the generator changed.
KNOWN_RESOURCE_TYPES = (
    "courseware",
    "exercise",
    "notes",
    "exam",
    "mind_map",
    "code_case",
    "video_script",
)
ResourceTypeName = str


class ResourceItem(BaseModel):
    """A managed learning resource item."""

    id: int
    title: str
    type: ResourceTypeName
    format: str
    status: Literal["draft", "ready", "archived"]
    knowledge_point: str
    knowledge_point_id: int | None = None
    owner_user_id: int | None = None
    source_type: Literal["generated", "external_import"] = "generated"
    provider: str | None = None
    source_kind: str | None = None
    external_url: str | None = None
    download_url: str | None = None
    notes: str | None = None
    file_name: str | None = None
    is_downloadable: bool = False
    generation_status: Literal["queued", "generating", "generated", "failed"] = "generated"
    audit_status: Literal["pending", "passed", "rejected", "unavailable"] = "pending"
    publish_status: Literal["draft", "published", "archived"] = "draft"
    audit_reason: str = ""
    # Payload fields are only populated by the single-resource detail endpoint;
    # the list endpoint leaves them null so browsing stays light.
    version: str | None = None
    teaching_json: str | None = None
    content: str | None = None
    structured: dict[str, Any] | None = None
    content_validation: dict[str, Any] | None = None


class ResourceRecommendationItem(ResourceItem):
    """A resource ranked for the current learner with explainable signals."""

    recommendation_score: float = 0
    recommendation_reason: str
    recommendation_strategy: Literal[
        "hybrid_collaborative", "personalized_heuristic", "cold_start_popularity"
    ] = "personalized_heuristic"
    collaborative_score: float = 0
    user_cf_score: float = 0
    item_cf_score: float = 0
    view_count: int = 0
    download_count: int = 0


class ResourceInteractionCreate(BaseModel):
    """A learner action that contributes to future recommendations."""

    action: Literal["view", "download", "open_source"]


class ResourceInteractionSummary(BaseModel):
    """Updated aggregate counters after an interaction is recorded."""

    resource_id: int
    recorded: bool
    view_count: int = 0
    download_count: int = 0


class ResourceStatusUpdate(BaseModel):
    """Payload for updating resource status."""

    status: Literal["draft", "ready", "archived"]


class ResourceExportRequest(BaseModel):
    """Payload for requesting a resource export."""

    export_format: Literal["pdf", "word"] = Field(description="Target export format.")


class ExternalResourceImportRequest(BaseModel):
    """Payload for importing an official external learning asset into managed resources."""

    title: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1000)
    kind: str = Field(default="courseware", min_length=1, max_length=100)
    license: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=1000)
    knowledge_point: str = Field(min_length=1, max_length=255)
    owner_user_id: int | None = None
