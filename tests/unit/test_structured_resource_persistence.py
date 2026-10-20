"""Persistence + read-back contract for the structured resource payload.

`mind_map` / `code_case` / `video_script` keep both a Markdown rendering
(`Resource.content`) and the typed payload plus its deterministic validation
report (`Resource.structured_json`).  The resource detail API must return the
typed payload; the list API must not (browsing stays light).

These are unit tests: the database is the local project database via the shared
`db_session` fixture, and no external service is contacted.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

from common.models.learning import KnowledgePoint, Resource
from common.schemas.agent import ResourceGenerationRequest
from services.resource_service.app.services.resource_manager import ResourceManager

STRUCTURED_ENVELOPE = {
    "resource_type": "mind_map",
    "structured": {
        "title": "循环结构导图",
        "knowledge_point": "循环结构-持久化用例",
        "root_id": "root",
        "nodes": [
            {"id": "root", "label": "循环结构", "parent_id": None, "level": 0, "detail": ""},
            {"id": "for", "label": "for 循环", "parent_id": "root", "level": 1, "detail": ""},
        ],
        "edges": [{"source": "root", "target": "for", "label": "包含"}],
        "mermaid_source": "",
    },
    "content_validation": {
        "resource_type": "mind_map",
        "verdict": "insufficient_evidence",
        "structure_passed": True,
        "source_passed": False,
        "source_coverage": 0.0,
        "citations": [],
        "checks": [
            {
                "check_id": "mindmap_nodes_present",
                "stage": "structure",
                "status": "passed",
                "passed": True,
                "detail": "2 nodes",
            }
        ],
        "notes": [],
    },
}


def _make_knowledge_point(db_session, suffix: str) -> KnowledgePoint:
    point = KnowledgePoint(name=f"循环结构-持久化用例-{suffix}", description="", difficulty=1, importance=1)
    db_session.add(point)
    db_session.commit()
    db_session.refresh(point)
    return point


def _make_resource(db_session, point: KnowledgePoint, **overrides) -> Resource:
    resource = Resource(
        title=overrides.pop("title", "循环结构导图"),
        type=overrides.pop("type", "mind_map"),
        content=overrides.pop("content", "# 循环结构导图\n\n- 循环结构\n  - for 循环\n"),
        format=overrides.pop("format", "json"),
        knowledge_point_id=point.id,
        generation_status="generated",
        audit_status="passed",
        publish_status="draft",
        audit_reason="rule_audit_passed",
        structured_json=overrides.pop("structured_json", json.dumps(STRUCTURED_ENVELOPE, ensure_ascii=False)),
    )
    for key, value in overrides.items():
        setattr(resource, key, value)
    db_session.add(resource)
    db_session.commit()
    db_session.refresh(resource)
    return resource


def _cleanup(db_session, point: KnowledgePoint) -> None:
    db_session.query(Resource).filter(Resource.knowledge_point_id == point.id).delete()
    db_session.query(KnowledgePoint).filter(KnowledgePoint.id == point.id).delete()
    db_session.commit()


def test_detail_endpoint_returns_payload_and_validation(db_session) -> None:
    suffix = uuid4().hex[:8]
    point = _make_knowledge_point(db_session, suffix)
    try:
        resource = _make_resource(db_session, point)
        item = ResourceManager(db_session).get_resource(resource.id)

        assert item is not None
        assert item.content and "循环结构导图" in item.content
        assert item.structured is not None
        assert [node["id"] for node in item.structured["nodes"]] == ["root", "for"]
        assert item.content_validation is not None
        assert item.content_validation["verdict"] == "insufficient_evidence"
        assert item.audit_status == "passed"
    finally:
        _cleanup(db_session, point)


def test_list_endpoint_does_not_carry_the_payload(db_session) -> None:
    suffix = uuid4().hex[:8]
    point = _make_knowledge_point(db_session, suffix)
    try:
        resource = _make_resource(db_session, point)
        items = [item for item in ResourceManager(db_session).list_resources() if item.id == resource.id]

        assert items, "the created resource must appear in the list"
        listed = items[0]
        assert listed.content is None
        assert listed.structured is None
        assert listed.content_validation is None
    finally:
        _cleanup(db_session, point)


def test_malformed_payload_degrades_instead_of_failing(db_session) -> None:
    suffix = uuid4().hex[:8]
    point = _make_knowledge_point(db_session, suffix)
    try:
        resource = _make_resource(db_session, point, structured_json="{not json at all")
        item = ResourceManager(db_session).get_resource(resource.id)

        assert item is not None
        # The row is still readable; only the structured view is unavailable.
        assert item.content and item.content.startswith("# 循环结构导图")
        assert item.structured is None
        assert item.content_validation is None
    finally:
        _cleanup(db_session, point)


def test_non_structured_payload_is_null(db_session) -> None:
    suffix = uuid4().hex[:8]
    point = _make_knowledge_point(db_session, suffix)
    try:
        resource = _make_resource(
            db_session,
            point,
            type="courseware",
            format="markdown",
            structured_json=None,
        )
        item = ResourceManager(db_session).get_resource(resource.id)

        assert item is not None
        assert item.structured is None
        assert item.content_validation is None
        # Content is still returned for plain Markdown courseware.
        assert item.content
    finally:
        _cleanup(db_session, point)


# --------------------------------------------------------------------------
# generation-side persistence
# --------------------------------------------------------------------------


def test_persist_generated_resource_writes_the_structured_envelope(
    db_session, test_user, monkeypatch
) -> None:
    """The generator must store the typed payload, not just the Markdown."""

    from services.agent_service.app.services import resource_generation as module
    from services.agent_service.app.services.resource_generation import (
        ResourceGenerationService,
    )

    suffix = uuid4().hex[:8]
    point = _make_knowledge_point(db_session, suffix)

    class _SessionContext:
        def __enter__(self):
            return db_session

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(module, "SessionLocal", lambda: _SessionContext())
    service = ResourceGenerationService.__new__(ResourceGenerationService)
    request = ResourceGenerationRequest(
        user_id=test_user.id,
        knowledge_point=point.name,
        resource_type="mind_map",
        subject="Python",
        learner_profile={},
    )
    generation_plan = {
        "request_summary": "x",
        "knowledge_point": point.name,
        "resource_type": "mind_map",
        "resource_style": "concise",
        "title_suggestion": "t",
        "suggested_outline": [],
        "target_word_count": 1,
        "difficulty": "intermediate",
        "personalization_hints": [],
        "analysis_source": "heuristic",
    }
    try:
        resource_id = service._persist_generated_resource(
            db_session,
            request,
            generation_plan,
            {"title": "循环结构导图", "content": "# 循环结构导图\n", "format": "json"},
            audit_status="passed",
            audit_reason="rule_audit_passed",
            structured_payload=STRUCTURED_ENVELOPE,
        )
        db_session.expire_all()
        stored = db_session.get(Resource, resource_id)

        assert stored is not None
        assert stored.format == "json"
        assert stored.audit_status == "passed"
        decoded = json.loads(stored.structured_json)
        assert decoded["resource_type"] == "mind_map"
        assert decoded["content_validation"]["verdict"] == "insufficient_evidence"
        assert decoded["structured"]["nodes"][1]["id"] == "for"
    finally:
        db_session.query(Resource).filter(Resource.knowledge_point_id == point.id).delete()
        db_session.query(KnowledgePoint).filter(KnowledgePoint.id == point.id).delete()
        db_session.commit()


def test_persist_generated_resource_without_payload_writes_null(db_session, test_user) -> None:
    from services.agent_service.app.services.resource_generation import (
        ResourceGenerationService,
    )

    suffix = uuid4().hex[:8]
    point = _make_knowledge_point(db_session, suffix)
    service = ResourceGenerationService.__new__(ResourceGenerationService)
    request = ResourceGenerationRequest(
        user_id=test_user.id,
        knowledge_point=point.name,
        resource_type="courseware",
        subject="Python",
        learner_profile={},
    )
    generation_plan = {
        "request_summary": "x",
        "knowledge_point": point.name,
        "resource_type": "courseware",
        "resource_style": "concise",
        "title_suggestion": "t",
        "suggested_outline": [],
        "target_word_count": 1,
        "difficulty": "intermediate",
        "personalization_hints": [],
        "analysis_source": "heuristic",
    }
    try:
        resource_id = service._persist_generated_resource(
            db_session,
            request,
            generation_plan,
            {"title": "普通课件", "content": "# 普通课件\n", "format": "markdown"},
        )
        db_session.expire_all()
        stored = db_session.get(Resource, resource_id)

        assert stored is not None
        assert stored.structured_json is None
    finally:
        db_session.query(Resource).filter(Resource.knowledge_point_id == point.id).delete()
        db_session.query(KnowledgePoint).filter(KnowledgePoint.id == point.id).delete()
        db_session.commit()


def test_finalize_structured_resource_passes_payload_to_persistence(monkeypatch) -> None:
    """`_finalize_structured_resource` must forward the typed payload + report."""

    from services.agent_service.app.services.resource_generation import (
        ResourceGenerationService,
    )

    captured: dict[str, object] = {}

    def fake_persist(db, request, generation_plan, primary, **kwargs):
        captured.update(kwargs)
        captured["resource_type"] = generation_plan["resource_type"]
        return 777

    service = ResourceGenerationService.__new__(ResourceGenerationService)
    service.settings = SimpleNamespace()
    monkeypatch.setattr(service, "_persist_generated_resource", fake_persist)

    class _NullSessionContext:
        def __enter__(self):
            return None

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(
        "services.agent_service.app.services.resource_generation.SessionLocal",
        _NullSessionContext,
    )
    monkeypatch.setattr(
        "services.agent_service.app.services.resource_generation.validate_generated_resource",
        lambda **kwargs: {"resource_type": "mind_map", "verdict": "valid", "checks": []},
    )
    monkeypatch.setattr(
        "services.agent_service.app.services.resource_generation.AuditService",
        lambda *a, **k: SimpleNamespace(
            audit_structured_resource=lambda *a, **k: SimpleNamespace(status="passed", reason="ok")
        ),
    )
    monkeypatch.setattr(service, "_build_personalization_payload", lambda *a, **k: {})

    structured = SimpleNamespace(model_dump=lambda: {"title": "t", "nodes": []})
    request = ResourceGenerationRequest(
        user_id=1,
        knowledge_point="循环结构",
        resource_type="mind_map",
        subject="Python",
        learner_profile={},
    )
    response = service._finalize_structured_resource(
        request,
        resource_type="mind_map",
        knowledge_point="循环结构",
        title="t",
        content="# t",
        structured=structured,
        raw_payload={"title": "t", "nodes": []},
        retrieved_context=[],
        snapshot=SimpleNamespace(),
    )

    payload = captured.get("structured_payload")
    assert isinstance(payload, dict)
    assert payload["resource_type"] == "mind_map"
    assert payload["structured"] == {"title": "t", "nodes": []}
    assert payload["content_validation"]["verdict"] == "valid"
    assert response["id"] == 777
