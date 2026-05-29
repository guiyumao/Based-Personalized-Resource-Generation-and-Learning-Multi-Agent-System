"""Unit tests for graph visualization and remedial exercise generation."""

from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


def test_graph_visualization_fallback_contains_nodes_and_edges() -> None:
    """Fallback graph visualization should provide nodes and edges."""

    repository = KnowledgeGraphRepository()
    result = repository.get_visualization_graph("Python 循环", 2)

    assert result["nodes"]
    assert result["edges"]


def test_remedial_exercises_generated_from_mistakes() -> None:
    """Wrong answers should produce variant remedial exercises."""

    service = ReportService()
    service.evaluate_practice(
        PracticeSubmission(
            user_id=1,
            exercise_id=3,
            knowledge_point="Python 循环",
            question_type="choice",
            user_answer="A",
            correct_answer="B",
            analysis="要关注循环的核心用途。",
            time_spent=10,
        )
    )

    remedial = service.generate_remedial_exercises(1)

    assert remedial.generated_from_mistakes == 1
    assert remedial.exercises[0].source_exercise_id == 3
