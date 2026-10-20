from common.schemas.agent import CoordinationRequest
from services.agent_service.app.agents import coordinator as coordinator_module
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.services.profile_mapping import build_zhishu_profile_view


def test_zhishu_profile_view_keeps_unknown_dimensions_unscored() -> None:
    result = build_zhishu_profile_view(
        learner_profile={
            "mastery": 72,
            "profile_dimensions": {"goalOrientation": "项目实践"},
            "goal_orientation": "项目实践",
        },
        mastery_score=72,
        answered_count=4,
        correct_rate=75,
        recent_mistakes=[{"question_type": "short_answer"}],
    )

    assert result["algorithm_version"] == "zhishu-scoring-v3"
    assert result["dimensions"]["knowledge_base"]["score"] == 72
    assert result["dimensions"]["knowledge_base"]["source"] == "behavior_inference"
    assert result["dimensions"]["learning_goal"]["value"] == "项目实践"
    assert result["dimensions"]["learning_goal"]["score"] is not None
    assert result["dimensions"]["memory"]["source"] == "insufficient_evidence"
    assert result["dimensions"]["memory"]["score"] is None


def test_zhishu_profile_scores_behavior_proxies_with_evidence_metadata() -> None:
    records = [
        {
            "answer_record_id": index,
            "exercise_id": index,
            "question_type": "short_answer" if index % 2 else "choice",
            "difficulty": 2,
            "is_correct": index != 2,
            "time_spent": 20 + index,
            "created_at": f"2026-10-1{index}T10:00:00",
            "evaluation": {"ratio": 1.0 if index != 2 else 0.0},
        }
        for index in range(1, 7)
    ]
    result = build_zhishu_profile_view(
        learner_profile={},
        mastery_score=0,
        answered_count=len(records),
        correct_rate=83,
        recent_mistakes=[],
        records=records,
    )

    assert 80 <= result["dimensions"]["knowledge_base"]["score"] <= 90
    assert result["dimensions"]["knowledge_base"]["status"] == "sufficient"
    assert result["dimensions"]["knowledge_base"]["sample_size"] == 6
    assert result["dimensions"]["knowledge_base"]["evidence_ids"] == [1, 2, 3, 4, 5, 6]
    assert result["dimensions"]["attention"]["score"] is not None
    assert result["dimensions"]["imagination"]["score"] is None


def test_memory_requires_repeated_attempts_and_scores_later_retention() -> None:
    records = [
        {
            "answer_record_id": index,
            "exercise_id": 7 if index < 5 else index,
            "question_type": "choice",
            "difficulty": 1,
            "is_correct": index >= 2,
            "time_spent": 15,
            "created_at": f"2026-10-1{index}T10:00:00",
            "evaluation": {},
        }
        for index in range(1, 7)
    ]
    result = build_zhishu_profile_view(
        learner_profile={},
        mastery_score=0,
        answered_count=6,
        correct_rate=67,
        recent_mistakes=[],
        records=records,
    )

    assert result["dimensions"]["memory"]["score"] == 100
    assert result["dimensions"]["memory"]["sample_size"] == 3
    assert result["dimensions"]["memory"]["status"] == "limited"
    assert result["dimensions"]["memory"]["confidence"] > 0


def test_imagination_stays_unscored_without_persisted_open_ended_rubric() -> None:
    records = [
        {
            "answer_record_id": index,
            "exercise_id": index,
            "question_type": "short_answer",
            "difficulty": 2,
            "is_correct": True,
            "time_spent": 30,
            "evaluation": {"score": 8, "max_score": 10},
        }
        for index in range(1, 4)
    ]
    result = build_zhishu_profile_view(
        learner_profile={},
        mastery_score=0,
        answered_count=3,
        correct_rate=100,
        recent_mistakes=[],
        records=records,
    )

    assert result["dimensions"]["imagination"]["score"] is None
    assert result["dimensions"]["imagination"]["source"] == "insufficient_evidence"


def test_scoring_exposes_calculation_policy_and_next_evidence() -> None:
    result = build_zhishu_profile_view(
        learner_profile={},
        mastery_score=0,
        answered_count=0,
        correct_rate=0,
        recent_mistakes=[],
        records=[],
    )

    assert result["algorithm_version"] == "zhishu-scoring-v3"
    assert result["calculation"]["recency_half_life_days"] == 45
    assert result["calculation"]["confidence_semantics"] == "evidence_coverage_heuristic_not_calibrated_probability"
    assert "memory" in result["next_evidence"]
    assert "imagination" in result["next_evidence"]
    assert result["dimensions"]["imagination"]["next_evidence"]


def test_zhishu_profile_view_marks_cold_start_as_insufficient() -> None:
    result = build_zhishu_profile_view(
        learner_profile={},
        mastery_score=0,
        answered_count=0,
        correct_rate=0,
        recent_mistakes=[],
    )

    assert result["dimensions"]["knowledge_base"]["source"] == "insufficient_evidence"
    assert result["dimensions"]["knowledge_base"]["confidence"] == 0.0


def test_coordinator_exposes_task_state_and_queued_call_summary() -> None:
    workflow = CoordinatorWorkflow(db=object())
    workflow.publisher.publish = lambda queue_name, message: None

    result = workflow.run(
        CoordinationRequest(
            user_id=8,
            intent="qa question",
            knowledge_point="Python loops",
            payload={},
        )
    )

    assert result["task_id"]
    assert result["task_state"]["status"] == "success"
    assert result["task_state"]["task_plan"][0]["agent"] == result["selected_agents"][0]
    assert result["agent_calls"][0]["output_status"] == "queued"
    assert "prompt" not in result["agent_calls"][0]["input_summary"]["keys"]


def test_coordinator_isolates_agent_failure_and_keeps_sibling_result(monkeypatch) -> None:
    class FailingGraphRepository:
        def __init__(self):
            raise RuntimeError("graph service unavailable")

    workflow = CoordinatorWorkflow(db=object())
    monkeypatch.setattr(coordinator_module, "KnowledgeGraphRepository", FailingGraphRepository)
    monkeypatch.setattr(
        workflow,
        "_run_qa_agent",
        lambda **kwargs: {"status": "completed", "qa": {"student_response": "ok"}},
    )

    result = workflow.run(
        CoordinationRequest(
            user_id=8,
            intent="qa question",
            knowledge_point="Python loops",
            payload={
                "execute": True,
                "force_agents": ["knowledge_graph_agent", "qa_agent"],
                "question": "Why?",
            },
        )
    )

    assert result["status"] == "partial"
    assert result["outputs"]["knowledge_graph_agent"]["error_code"] == "AGENT_EXECUTION_FAILED"
    assert result["outputs"]["qa_agent"]["status"] == "completed"
    calls = {item["agent"]: item for item in result["agent_calls"]}
    assert calls["knowledge_graph_agent"]["output_status"] == "failed"
    assert calls["qa_agent"]["output_status"] == "completed"
