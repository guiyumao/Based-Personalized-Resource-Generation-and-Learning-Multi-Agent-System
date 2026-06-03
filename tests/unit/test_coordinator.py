"""Unit tests for the coordinator workflow."""

from common.schemas.agent import CoordinationRequest
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow


def test_coordinator_selects_resource_generation_agents(monkeypatch):
    """Coordinator should route resource requests to profiling + generation agents."""

    published_messages: list[tuple[str, dict]] = []

    def fake_publish(queue_name: str, message: dict) -> None:
        published_messages.append((queue_name, message))

    workflow = CoordinatorWorkflow()
    monkeypatch.setattr(workflow.publisher, "publish", fake_publish)

    result = workflow.run(
        CoordinationRequest(
            user_id=1,
            intent="请生成 Python 循环的个性化课件和习题",
            knowledge_point="Python 循环",
            payload={"grade": "freshman"},
        )
    )

    assert result["status"] == "success"
    assert "resource_generation_agent" in result["selected_agents"]
    assert len(published_messages) == 2
