"""Unit tests for the resource generation service."""

from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.resource_generation import ResourceGenerationService


def test_generate_courseware_with_stubbed_llm(monkeypatch):
    """Generation service should return resource metadata and content."""

    service = ResourceGenerationService()

    monkeypatch.setattr(
        service.retriever,
        "retrieve",
        lambda query, top_k=3: [{"id": "1", "content": "循环可用 for 和 while。", "metadata": {"source": "seed"}}],
    )

    monkeypatch.setattr(service, "_invoke_llm", lambda _: "# Python 循环\n\n- for\n- while")

    response = service.generate_courseware(
        ResourceGenerationRequest(
            user_id=1,
            knowledge_point="Python 循环",
            resource_style="interactive",
            resource_type="courseware",
            learner_profile={"style": "visual"},
        )
    )

    assert response["knowledge_point"] == "Python 循环"
    assert response["references"]
    assert response["content"].startswith("# Python 循环")
