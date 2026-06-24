"""Unit tests for the resource generation service."""

import pytest

from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.resource_generation import (
    ResourceGenerationError,
    ResourceGenerationService,
)


def test_generate_courseware_with_stubbed_llm(monkeypatch):
    """Generation service should return resource metadata and content."""

    service = ResourceGenerationService()

    monkeypatch.setattr(
        service.retriever,
        "retrieve",
        lambda query, top_k=3: [
            {
                "id": "1",
                "content": "Loops can be implemented with for and while in Python.",
                "metadata": {"source": "seed"},
            }
        ],
    )

    monkeypatch.setattr(service, "_invoke_llm", lambda _: "# Python loops\n\n- for\n- while")

    response = service.generate_courseware_with_plan(
        ResourceGenerationRequest(
            user_id=1,
            knowledge_point="Python loops",
            resource_style="interactive",
            resource_type="courseware",
            learner_profile={
                "style": "visual",
                "profile_analysis_summaries": {
                    "knowledgeBase": "基础可以但抽象迁移偏弱",
                    "goalOrientation": "项目导向明确",
                },
            },
            request_text="Please generate a beginner-friendly Python loop lesson for review.",
        )
    )

    assert response["knowledge_point"]
    assert response["references"]
    assert response["content"].startswith("# Python loops")
    assert response["generation_plan"]["difficulty"] == "foundation"
    assert response["generation_plan"]["analysis_source"] == "profile_enriched"
    assert response["generation_plan"]["suggested_outline"]
    assert response["generation_plan"]["knowledge_point"] == response["knowledge_point"]
    assert "profile_analysis_summaries" in response["personalization"]
    assert len(response["variants"]) == 1
    assert response["variants"][0]["resource_style"] == "interactive"


def test_generate_courseware_raises_when_model_generation_fails(monkeypatch):
    """The service should not silently fall back to a local quick courseware."""

    service = ResourceGenerationService()

    monkeypatch.setattr(
        service.retriever,
        "retrieve",
        lambda query, top_k=3: [
            {
                "id": "1",
                "content": "Loops can be implemented with for and while in Python.",
                "metadata": {"source": "seed"},
            }
        ],
    )

    def _raise(_: object) -> str:
        raise ResourceGenerationError("Model-based courseware generation failed.")

    monkeypatch.setattr(service, "_invoke_llm", _raise)

    with pytest.raises(ResourceGenerationError):
        service.generate_courseware_with_plan(
            ResourceGenerationRequest(
                user_id=1,
                knowledge_point="Python loops",
                resource_style="interactive",
                resource_type="courseware",
                learner_profile={"style": "visual"},
                request_text="Please generate a beginner-friendly Python loop lesson for review.",
            )
        )


def test_infer_resource_type_prefers_courseware_when_request_mentions_courseware_and_exercises():
    """Mixed requests should keep the current courseware generation intent."""

    service = ResourceGenerationService()

    resource_type = service._infer_resource_type(
        ResourceGenerationRequest(
            user_id=1,
            knowledge_point="Python loops",
            resource_style="interactive",
            resource_type="courseware",
            learner_profile={},
            request_text="请生成 Python 循环的课件和习题",
        ),
        "请生成 Python 循环的课件和习题",
    )

    assert resource_type == "courseware"


def test_normalize_knowledge_point_keeps_user_requested_topic():
    """Courseware generation should honor the user's topic instead of replacing it from the KB."""

    service = ResourceGenerationService()
    request = ResourceGenerationRequest(
        user_id=1,
        knowledge_point="物理",
        resource_style="interactive",
        resource_type="courseware",
        learner_profile={},
        request_text="围绕物理生成可独立阅读的正式课件",
    )

    assert service._normalize_knowledge_point(request, request.request_text) == "物理"
