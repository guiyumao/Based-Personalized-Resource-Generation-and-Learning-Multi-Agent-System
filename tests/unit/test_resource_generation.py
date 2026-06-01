"""Unit tests for the resource generation service."""

from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.resource_generation import ResourceGenerationService


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
            learner_profile={"style": "visual"},
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
