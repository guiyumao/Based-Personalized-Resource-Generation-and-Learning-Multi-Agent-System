"""Route-level tests that public feature endpoints execute through agents."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from common.schemas.agent import CoordinationRequest
from services.agent_service.app.api.routes import agents as agent_routes
from services.agent_service.app.api.routes import learning, qa, resources
from services.agent_service.app.services import coordination_runner

_learner = SimpleNamespace(id=1, role="student")


def test_resource_route_uses_coordinator(monkeypatch):
    """Resource generation endpoint should delegate to the coordinator workflow."""

    captured: list[CoordinationRequest] = []

    class FakeCoordinatorWorkflow:
        def run(self, request: CoordinationRequest):
            captured.append(request)
            return {
                "status": "success",
                "selected_agents": request.payload["force_agents"],
                "route_reason": "test",
                "outputs": {
                    "resource_generation_agent": {
                        "status": "completed",
                        "resource": {
                            "user_id": request.user_id,
                            "knowledge_point": request.knowledge_point,
                            "resource_type": "courseware",
                            "resource_style": "interactive",
                            "generation_plan": {
                                "request_summary": "test",
                                "knowledge_point": request.knowledge_point,
                                "resource_type": "courseware",
                                "resource_style": "interactive",
                                "title_suggestion": "test",
                                "suggested_outline": [],
                                "target_word_count": 1200,
                                "difficulty": "intermediate",
                                "personalization_hints": [],
                                "analysis_source": "request",
                            },
                            "content": "agent-generated content",
                            "variants": [],
                        },
                    }
                },
            }

    monkeypatch.setattr(resources, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    response = resources.generate_resource(
        resources.ResourceGenerationRequest(
            user_id=1,
            knowledge_point="Python loops",
            request_text="generate courseware",
        ),
        current_user=_learner,
    )

    assert response.content == "agent-generated content"
    assert captured[0].payload["force_agents"] == ["learner_profiling_agent", "resource_generation_agent"]
    assert captured[0].payload["execute"] is True


def test_learning_and_exercise_routes_use_coordinator(monkeypatch):
    from services.agent_service.app.services import plan_knowledge
    monkeypatch.setattr(plan_knowledge, "require_plan_knowledge", lambda *_: {})
    monkeypatch.setattr(plan_knowledge, "assess_plan_knowledge", lambda *_: {})
    """Learning path and exercise endpoints should delegate to specific agents."""

    captured: list[CoordinationRequest] = []

    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            self.db = db

        def run(self, request: CoordinationRequest):
            captured.append(request)
            if "path_planning_agent" in request.payload["force_agents"]:
                return {
                    "status": "success",
                    "selected_agents": request.payload["force_agents"],
                    "route_reason": "test",
                    "outputs": {
                        "path_planning_agent": {
                            "status": "completed",
                            "learning_path": {
                                "user_id": request.user_id,
                                "subject": request.payload["subject"],
                                "knowledge_point": request.knowledge_point,
                                "overview": "agent-planned path",
                                "estimated_days": 3,
                                "stages": [],
                            },
                        }
                    },
                }
            return {
                "status": "success",
                "selected_agents": request.payload["force_agents"],
                "route_reason": "test",
                "outputs": {
                    "exercise_generation_agent": {
                        "status": "completed",
                        "exercise_set": {
                            "user_id": request.user_id,
                            "knowledge_point": request.knowledge_point,
                            "summary": "agent-generated exercises",
                            "personalization": {},
                            "exercises": [],
                        },
                    }
                },
            }

    monkeypatch.setattr(learning, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    path = learning.generate_learning_path(
        learning.LearningPathRequest(
            user_id=1,
            subject="Python",
            knowledge_point="loops",
        ),
        db=object(),
        current_user=_learner,
    )
    exercises = learning.generate_exercises(
        learning.ExerciseGenerationRequest(
            user_id=1,
            knowledge_point="loops",
        ),
        current_user=_learner,
    )

    assert path.overview == "agent-planned path"
    assert exercises.summary == "agent-generated exercises"
    assert captured[0].payload["force_agents"] == [
        "learner_profiling_agent",
        "knowledge_graph_agent",
        "path_planning_agent",
    ]
    assert captured[1].payload["force_agents"] == ["learner_profiling_agent", "exercise_generation_agent"]


def test_learning_path_route_returns_typed_model_initialization_error(monkeypatch):
    from services.agent_service.app.services import plan_knowledge
    monkeypatch.setattr(plan_knowledge, "require_plan_knowledge", lambda *_: {})
    monkeypatch.setattr(plan_knowledge, "assess_plan_knowledge", lambda *_: {})
    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            pass

        def run(self, request):
            return {
                "outputs": {
                    "path_planning_agent": {
                        "status": "failed",
                        "error_code": "AI_MODEL_INITIALIZATION_TIMEOUT",
                        "user_message": "AI助教正在加载中，请稍后重试",
                    }
                }
            }

    monkeypatch.setattr(learning, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    with pytest.raises(HTTPException) as raised:
        learning.generate_learning_path(
            learning.LearningPathRequest(user_id=1, subject="数学", knowledge_point="定积分"),
            db=object(),
            current_user=_learner,
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "AI_MODEL_INITIALIZATION_TIMEOUT",
        "message": "AI助教正在加载中，请稍后重试",
    }


def test_coordinator_route_derives_deadline_from_selected_agent_budgets(monkeypatch):
    trace_context = []
    monkeypatch.setattr(
        coordination_runner,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "qa_deadline_seconds": 41,
                "learning_path_deadline_seconds": 23,
                "courseware_deadline_seconds": 67,
                "exercise_deadline_seconds": 19,
                "report_deadline_seconds": 31,
                "max_total_retries": 4,
            },
        )(),
    )
    monkeypatch.setattr(coordination_runner, "set_trace_context", lambda **kwargs: trace_context.append(kwargs))

    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            pass

        def run(self, request):
            return {
                "status": "success",
                "selected_agents": request.payload["force_agents"],
                "route_reason": "test",
                "outputs": {},
            }

    monkeypatch.setattr(coordination_runner, "CoordinatorWorkflow", FakeCoordinatorWorkflow)
    response = agent_routes.coordinate(
        CoordinationRequest(
            user_id=1,
            intent="learning path with companion resources",
            payload={
                "force_agents": ["learner_profiling_agent", "path_planning_agent", "resource_generation_agent", "exercise_generation_agent"],
            },
        ),
        db=object(),
        current_user=_learner,
    )

    assert response.status == "success"
    assert trace_context[0]["deadline_seconds"] == 23 + 67 + 19
    assert trace_context[0]["retry_budget"] == 4


def test_qa_route_uses_coordinator(monkeypatch):
    """QA endpoint should delegate only the required profile + QA agents."""

    captured: list[CoordinationRequest] = []

    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            self.db = db

        def run(self, request: CoordinationRequest):
            captured.append(request)
            return {
                "status": "success",
                "selected_agents": request.payload["force_agents"],
                "route_reason": "test",
                "outputs": {
                    "qa_agent": {
                        "status": "completed",
                        "qa": {
                            "student_id": "1",
                            "subject": "Python",
                            "grade": "freshman",
                            "student_response": "agent answer",
                            "structured_analysis": {
                                "identified_knowledge_gaps": [],
                                "misconceptions": [],
                                "difficulty_level": "foundation",
                                "learning_state": "",
                                "recommended_next_knowledge_points": [],
                                "learning_route_updates": [],
                                "resource_recommendations": [],
                                "study_suggestions": [],
                                "mistake_book_update": {
                                    "should_add": False,
                                    "question_summary": "",
                                    "wrong_reason": "",
                                    "correct_approach": "",
                                },
                            },
                        },
                    }
                },
            }

    monkeypatch.setattr(qa, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    response = qa.analyze_question(
        qa.QARequest(
            student_id="1",
            subject="Python",
            grade="freshman",
            question="Why?",
            current_knowledge_points=["loops"],
        ),
        db=object(),
        current_user=_learner,
    )

    assert response.student_response == "agent answer"
    assert captured[0].knowledge_point == "loops"
    assert captured[0].payload["force_agents"] == [
        "learner_profiling_agent",
        "qa_agent",
    ]


def test_qa_route_falls_back_to_direct_qa_without_knowledge_point(monkeypatch):
    """QA endpoint should still execute when subject and knowledge points are empty."""

    captured: list[CoordinationRequest] = []

    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            self.db = db

        def run(self, request: CoordinationRequest):
            captured.append(request)
            return {
                "status": "success",
                "selected_agents": request.payload["force_agents"],
                "route_reason": "test",
                "outputs": {
                    "qa_agent": {
                        "status": "completed",
                        "qa": {
                            "student_id": "1",
                            "subject": "",
                            "grade": "freshman",
                            "student_response": "general answer",
                            "structured_analysis": {
                                "identified_knowledge_gaps": [],
                                "misconceptions": [],
                                "difficulty_level": "foundation",
                                "learning_state": "",
                                "recommended_next_knowledge_points": [],
                                "learning_route_updates": [],
                                "resource_recommendations": [],
                                "study_suggestions": [],
                                "mistake_book_update": {
                                    "should_add": False,
                                    "question_summary": "",
                                    "wrong_reason": "",
                                    "correct_approach": "",
                                },
                            },
                        },
                    }
                },
            }

    monkeypatch.setattr(qa, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    response = qa.analyze_question(
        qa.QARequest(
            student_id="1",
            subject="",
            grade="freshman",
            question="阿达是谁？",
            current_knowledge_points=[],
        ),
        db=object(),
        current_user=_learner,
    )

    assert response.student_response == "general answer"
    assert captured[0].knowledge_point == ""
    assert captured[0].payload["force_agents"] == ["qa_agent"]


def test_qa_route_uses_general_mode_for_realtime_questions(monkeypatch):
    """Realtime/open-domain questions should stay in general QA mode."""

    captured: list[CoordinationRequest] = []

    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            self.db = db

        def run(self, request: CoordinationRequest):
            captured.append(request)
            return {
                "status": "success",
                "selected_agents": request.payload["force_agents"],
                "route_reason": "test",
                "outputs": {
                    "qa_agent": {
                        "status": "completed",
                        "qa": {
                            "student_id": "1",
                            "subject": "",
                            "grade": "freshman",
                            "student_response": "今天是星期三。",
                            "structured_analysis": {
                                "identified_knowledge_gaps": [],
                                "misconceptions": [],
                                "difficulty_level": "foundation",
                                "learning_state": "已完成通用问答",
                                "recommended_next_knowledge_points": [],
                                "learning_route_updates": [],
                                "resource_recommendations": [],
                                "study_suggestions": [],
                                "mistake_book_update": {
                                    "should_add": False,
                                    "question_summary": "",
                                    "wrong_reason": "",
                                    "correct_approach": "",
                                },
                            },
                        },
                    }
                },
            }

    monkeypatch.setattr(qa, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    response = qa.analyze_question(
        qa.QARequest(
            student_id="1",
            subject="",
            grade="freshman",
            question="今天星期几？",
            current_knowledge_points=[],
        ),
        db=object(),
        current_user=_learner,
    )

    assert response.student_response == "今天是星期三。"
    assert captured[0].knowledge_point == ""
    assert captured[0].payload["intent_mode"] == "general"
    assert captured[0].payload["force_agents"] == ["qa_agent"]


def test_qa_route_infers_learning_mode_from_question_text(monkeypatch):
    """Learning tasks without an explicit subject should still route through learning agents."""

    captured: list[CoordinationRequest] = []

    class FakeCoordinatorWorkflow:
        def __init__(self, db=None):
            self.db = db

        def run(self, request: CoordinationRequest):
            captured.append(request)
            return {
                "status": "success",
                "selected_agents": request.payload["force_agents"],
                "route_reason": "test",
                "outputs": {
                    "qa_agent": {
                        "status": "completed",
                        "qa": {
                            "student_id": "1",
                            "subject": "大学物理",
                            "grade": "freshman",
                            "student_response": "已生成大学物理习题。",
                            "structured_analysis": {
                                "identified_knowledge_gaps": ["大学物理"],
                                "misconceptions": [],
                                "difficulty_level": "foundation",
                                "learning_state": "已生成习题",
                                "recommended_next_knowledge_points": [],
                                "learning_route_updates": [],
                                "resource_recommendations": [],
                                "study_suggestions": [],
                                "mistake_book_update": {
                                    "should_add": False,
                                    "question_summary": "",
                                    "wrong_reason": "",
                                    "correct_approach": "",
                                },
                            },
                        },
                    }
                },
            }

    monkeypatch.setattr(qa, "CoordinatorWorkflow", FakeCoordinatorWorkflow)

    response = qa.analyze_question(
        qa.QARequest(
            student_id="1",
            subject="",
            grade="freshman",
            question="大学物理的练习题",
            current_knowledge_points=[],
        ),
        db=object(),
        current_user=_learner,
    )

    assert response.student_response == "已生成大学物理习题。"
    assert captured[0].knowledge_point == "大学物理"
    assert captured[0].payload["intent_mode"] == "learning"
    assert captured[0].payload["force_agents"] == [
        "learner_profiling_agent",
        "qa_agent",
    ]
