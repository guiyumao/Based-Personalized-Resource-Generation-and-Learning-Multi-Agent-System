"""Unit tests for graph visualization and remedial exercise generation."""

from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


class _FailingSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, *args, **kwargs):
        raise RuntimeError("neo4j unavailable")


class _FailingDriver:
    def session(self):
        return _FailingSession()


def test_graph_visualization_fallback_contains_nodes_and_edges() -> None:
    """Fallback graph visualization should provide nodes and edges."""

    repository = KnowledgeGraphRepository()
    result = repository.get_visualization_graph("Python 循环", 2)

    assert result["nodes"]
    assert result["edges"]


def test_graph_dependencies_fallback_when_driver_errors() -> None:
    """Dependency queries should still return fallback paths when Neo4j errors."""

    repository = KnowledgeGraphRepository()
    repository._driver = _FailingDriver()

    result = repository.find_dependency_path("Python 循环", 2)

    assert result
    assert all("path" in item for item in result)
    assert any("顺序结构" in item["path"] or "条件判断" in item["path"] for item in result)


def test_remedial_exercises_generated_from_mistakes(db_session, test_user) -> None:
    """Wrong answers should produce variant remedial exercises."""

    service = ReportService(db_session)
    service.evaluate_practice(
        PracticeSubmission(
            user_id=test_user.id,
            exercise_id=130000 + test_user.id,
            knowledge_point="Python 循环",
            question_type="choice",
            user_answer="A",
            correct_answer="B",
            analysis="需要关注循环的核心用法。",
            time_spent=10,
        )
    )

    remedial = service.generate_remedial_exercises(test_user.id)

    assert remedial.generated_from_mistakes == 1
    assert remedial.exercises[0].source_exercise_id == 130000 + test_user.id
