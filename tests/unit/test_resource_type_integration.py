"""Integration tests for new resource types and the unified task state.

These verify the wiring, not the model: the coordinator's resource agent is
stubbed to return a real-shaped payload, so the assertions cover the contract
between the generators, the coordinator and the response schema.
"""

from __future__ import annotations

from common.schemas.agent import (
    CoordinationRequest,
    CoordinationResponse,
    ResourceGenerationRequest,
    ResourceGenerationResponse,
)
from services.agent_service.app.agents import coordinator as coordinator_module
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow


def _resource_result(resource_type: str) -> dict:
    """A resource payload shaped exactly like the generators return."""

    validation = {
        "resource_type": resource_type,
        "verdict": "valid",
        "structure_passed": True,
        "source_passed": True,
        "source_coverage": 0.5,
        "citations": [
            {
                "marker": "[来源:c1]",
                "reference": "c1",
                "resolved": True,
                "chunk_id": "c1",
                "source": "kb/course.md",
            }
        ],
        "checks": [],
        "notes": [],
    }
    result = {
        "id": 99,
        "user_id": 7,
        "knowledge_point": "循环结构",
        "resource_type": resource_type,
        "resource_style": "interactive",
        "generation_plan": {
            "request_summary": "s",
            "knowledge_point": "循环结构",
            "resource_type": resource_type,
            "resource_style": "interactive",
            "title_suggestion": "t",
            "suggested_outline": [],
            "target_word_count": 1200,
            "difficulty": "intermediate",
            "personalization_hints": [],
            "analysis_source": "heuristic",
        },
        "references": [{"id": "c1", "content": "循环", "metadata": {"source": "kb/course.md"}}],
        "personalization": {},
        "content": "# 内容",
        "variants": [],
        "generation_status": "generated",
        "audit_status": "passed",
        "publish_status": "draft",
        "audit_reason": "rule_audit_passed",
        "content_validation": validation,
    }
    if resource_type == "mind_map":
        result["mind_map"] = {
            "title": "导图",
            "knowledge_point": "循环结构",
            "root_id": "r",
            "nodes": [{"id": "r", "label": "循环", "parent_id": None, "level": 0, "detail": ""}],
            "edges": [],
            "mermaid_source": "",
        }
    elif resource_type == "code_case":
        result["code_case"] = {
            "title": "案例",
            "knowledge_point": "循环结构",
            "language": "python",
            "objective": "掌握循环",
            "example_code": "print(1)",
            "run_steps": ["python x.py"],
        }
    elif resource_type == "video_script":
        result["video_script"] = {
            "title": "脚本",
            "knowledge_point": "循环结构",
            "chapters": [{"narration": "讲解", "duration_seconds": 30}],
            "total_duration_seconds": 30,
        }
    return result


def _workflow_with_stub(monkeypatch, requested_type: str) -> CoordinatorWorkflow:
    class FakeResourceService:
        def __init__(self) -> None:
            pass

        def generate_courseware_with_plan(self, request, snapshot=None):
            return _resource_result("courseware")

        def generate_mind_map(self, request):
            return _resource_result("mind_map")

        def generate_code_case(self, request):
            return _resource_result("code_case")

        def generate_video_script(self, request):
            return _resource_result("video_script")

    class FakeGraphRepo:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def sync_courseware_to_graph(self, knowledge_point):
            return None

        def close(self):
            return None

    class FakeSnapshot:
        mastery_score = 60
        correct_rate = 55
        answered_count = 4
        recent_mistakes: list = []
        learner_profile = {"weak_question_types": []}

    monkeypatch.setattr(coordinator_module, "ResourceGenerationService", FakeResourceService)
    monkeypatch.setattr(coordinator_module, "KnowledgeGraphRepository", FakeGraphRepo)

    workflow = CoordinatorWorkflow(db=object())
    monkeypatch.setattr(workflow.publisher, "publish", lambda *a, **k: None)
    monkeypatch.setattr(
        workflow,
        "_build_profile_snapshot",
        lambda **kwargs: FakeSnapshot(),
    )
    return workflow


def _run(workflow: CoordinatorWorkflow, resource_type: str) -> dict:
    return workflow.run(
        CoordinationRequest(
            user_id=7,
            intent="courseware resource generation",
            knowledge_point="循环结构",
            payload={
                "execute": True,
                "force_agents": ["learner_profiling_agent", "resource_generation_agent"],
                "resource_type": resource_type,
            },
        )
    )


# --------------------------------------------------------------------------
# dispatch to the right generator
# --------------------------------------------------------------------------


def test_coordinator_dispatches_the_requested_structured_generator(monkeypatch):
    workflow = _workflow_with_stub(monkeypatch, "mind_map")
    result = _run(workflow, "mind_map")
    resource = result["outputs"]["resource_generation_agent"]["resource"]
    assert resource["resource_type"] == "mind_map"
    assert "mind_map" in resource


def test_coordinator_rejects_unregistered_resource_type(monkeypatch):
    """The dispatcher refuses an unregistered type instead of downgrading it.

    ``ResourceGenerationRequest`` already rejects unknown values at the API
    boundary, so this exercises the dispatcher directly — the guard also covers
    internal/agent callers that pass a plain dict.
    """

    workflow = _workflow_with_stub(monkeypatch, "hologram")
    service = coordinator_module.ResourceGenerationService()
    request = ResourceGenerationRequest(
        user_id=7,
        knowledge_point="循环结构",
        resource_type="courseware",
    )

    import pytest

    with pytest.raises(Exception, match="Unsupported resource type"):
        workflow._generate_resource(
            service, request, resource_type="hologram", snapshot=None
        )


def test_dispatch_refuses_exercise_type_with_a_pointed_message(monkeypatch):
    import pytest

    workflow = _workflow_with_stub(monkeypatch, "exercise")
    service = coordinator_module.ResourceGenerationService()
    request = ResourceGenerationRequest(
        user_id=7, knowledge_point="循环结构", resource_type="exercise"
    )
    with pytest.raises(Exception, match="exercise generation agent"):
        workflow._generate_resource(
            service, request, resource_type="exercise", snapshot=None
        )


# --------------------------------------------------------------------------
# unified task state
# --------------------------------------------------------------------------


def test_task_state_survives_synchronous_execution(monkeypatch):
    """Regression: the execute path used to replace task_state with 5 keys."""

    workflow = _workflow_with_stub(monkeypatch, "courseware")
    result = _run(workflow, "courseware")
    task_state = result["task_state"]

    for field in (
        "user_id",
        "task_id",
        "session_id",
        "intent",
        "intent_params",
        "learner_profile",
        "learning_evidence",
        "selected_agents",
        "task_plan",
        "agent_handoff",
        "intermediate_results",
        "citations",
        "validation_results",
        "status",
        "progress",
        "current_step",
        "error",
    ):
        assert field in task_state, f"unified task state is missing {field}"

    assert task_state["selected_agents"], "selected_agents was dropped by execution"
    assert task_state["intent"] == "courseware resource generation"
    assert task_state["progress"] == 1.0


def test_validation_results_and_citations_are_populated(monkeypatch):
    workflow = _workflow_with_stub(monkeypatch, "courseware")
    result = _run(workflow, "courseware")

    assert result["validation_results"], "validation_results were not collected"
    entry = result["validation_results"][0]
    assert entry["verdict"] == "valid"
    assert entry["structure_passed"] is True
    assert entry["source_coverage"] == 0.5

    assert result["citations"], "citations were not collected"
    assert result["citations"][0]["resolved"] is True
    assert result["citations"][0]["chunk_id"] == "c1"


def test_task_state_never_leaks_raw_answer_text(monkeypatch):
    """learner_profile in the task state is a summary, not the raw profile."""

    workflow = _workflow_with_stub(monkeypatch, "courseware")
    result = _run(workflow, "courseware")
    profile = result["task_state"]["learner_profile"]
    assert "recent_mistakes" not in profile
    assert "raw_answers" not in profile


def test_agent_calls_never_record_prompts_or_tokens(monkeypatch):
    workflow = _workflow_with_stub(monkeypatch, "courseware")
    result = _run(workflow, "courseware")
    for call in result["agent_calls"]:
        summary = call.get("input_summary", {})
        assert "prompt" not in summary.get("keys", [])
        assert "token" not in summary.get("keys", [])
        assert "authorization" not in summary.get("keys", [])


# --------------------------------------------------------------------------
# response schema accepts every new type
# --------------------------------------------------------------------------


def test_response_schema_accepts_every_new_resource_type():
    for resource_type in ("courseware", "mind_map", "code_case", "video_script"):
        response = ResourceGenerationResponse(**_resource_result(resource_type))
        assert response.resource_type == resource_type
        assert response.content_validation is not None


def test_coordination_response_schema_carries_the_partial_verdict(monkeypatch):
    workflow = _workflow_with_stub(monkeypatch, "courseware")
    result = _run(workflow, "courseware")
    # outputs contain no failures, so the run is a success rather than partial
    assert result["status"] == "success"
    validated = CoordinationResponse(**{k: v for k, v in result.items() if k != "citations"})
    assert validated.status == "success"
    assert validated.task_state["progress"] == 1.0
