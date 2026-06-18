"""Tests for coordinator synchronous QA and evaluation execution."""

from common.schemas.agent import CoordinationRequest
from services.agent_service.app.agents import coordinator as coordinator_module
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.evaluation_service.app.schemas.report import AnalyticsSuggestion


def test_coordinator_executes_qa_and_evaluation_agents(monkeypatch):
    """Coordinator should synchronously run QA and evaluation agents when selected."""

    published_messages: list[tuple[str, dict]] = []

    class FakeKnowledgeGraphRepository:
        def find_dependency_path(self, knowledge_point: str, max_depth: int):
            return [{"name": knowledge_point, "relation": "current"}]

        def get_visualization_graph(self, knowledge_point: str, max_depth: int):
            return {"nodes": [{"id": knowledge_point, "label": knowledge_point}], "edges": []}

        def close(self):
            return None

    class FakeQAService:
        def __init__(self, db):
            self.db = db

        def analyze_question(self, request):
            return {
                "student_id": request.student_id,
                "subject": request.subject,
                "grade": request.grade,
                "student_response": f"answer: {request.question}",
                "structured_analysis": {
                    "identified_knowledge_gaps": request.current_knowledge_points,
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
                "message_history": [],
                "context_snippets": [],
                "confidence": 0.8,
            }

    class FakeReportService:
        async def generate_learning_suggestions(self, user_id: int):
            return AnalyticsSuggestion(
                user_id=user_id,
                suggestions=["review loops"],
                focus_areas=["Python loops"],
                recommended_action="practice next",
            )

        async def generate_profile_snapshot(self, user_id: int):
            return {"user_id": user_id, "mastery": 70}

        async def get_mistake_statistics(self, user_id: int):
            return {"user_id": user_id, "mistake_count": 1}

    workflow = CoordinatorWorkflow(db=object())
    monkeypatch.setattr(
        workflow.publisher,
        "publish",
        lambda queue_name, message: published_messages.append((queue_name, message)),
    )
    monkeypatch.setattr(coordinator_module, "KnowledgeGraphRepository", FakeKnowledgeGraphRepository)
    monkeypatch.setattr(coordinator_module, "QAService", FakeQAService)
    monkeypatch.setattr(coordinator_module, "ReportService", FakeReportService)

    result = workflow.run(
        CoordinationRequest(
            user_id=9,
            intent="qa question evaluation feedback",
            knowledge_point="Python loops",
            payload={
                "execute": True,
                "question": "Why does my loop never stop?",
                "subject": "Python",
                "grade": "freshman",
            },
        )
    )

    assert result["status"] == "success"
    assert result["selected_agents"] == [
        "evaluation_feedback_agent",
        "knowledge_graph_agent",
        "qa_agent",
    ]
    assert len(published_messages) == 3
    assert result["outputs"]["qa_agent"]["qa"]["student_response"] == "answer: Why does my loop never stop?"
    assert result["outputs"]["qa_agent"]["qa"]["structured_analysis"]["identified_knowledge_gaps"] == ["Python loops"]
    evaluation = result["outputs"]["evaluation_feedback_agent"]["evaluation"]
    assert evaluation["suggestions"]["recommended_action"] == "practice next"
    assert evaluation["profile_snapshot"]["mastery"] == 70
