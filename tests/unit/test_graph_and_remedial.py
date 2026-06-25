"""Unit tests for graph visualization and remedial exercise generation."""

import asyncio

from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService


class FakeLLMClient:
    """Deterministic async LLM stub for evaluation tests."""

    async def score_subjective(self, **_: object) -> dict[str, object]:
        return {
            "score": 7.0,
            "comment": "关键点基本完整。",
            "suggestion": "补充边界条件说明",
        }


class FakePublisher:
    """No-op publisher for isolated unit tests."""

    def publish(self, queue_name: str, message: dict[str, object]) -> None:
        return None


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


class _SparseRecord:
    def __getitem__(self, key):
        if key in {"deps", "nexts"}:
            return []
        return {"name": "高数"}


class _SparseSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, *args, **kwargs):
        return self

    def single(self):
        return _SparseRecord()


class _SparseDriver:
    def session(self):
        return _SparseSession()


def test_graph_visualization_contains_nodes_and_edges() -> None:
    """Knowledge graph should provide nodes and edges from available content."""

    repository = KnowledgeGraphRepository()
    result = repository.get_visualization_graph("Python 循环", 2)

    assert result["nodes"]
    assert result["edges"]


def test_graph_dependencies_still_work_when_driver_errors() -> None:
    """Dependency queries should still return content-derived paths when Neo4j errors."""

    repository = KnowledgeGraphRepository()
    repository._driver = _FailingDriver()

    result = repository.find_dependency_path("Python 循环", 2)

    assert result
    assert all("path" in item for item in result)


def test_math_topic_graph_comes_from_available_courseware_and_knowledge() -> None:
    """Math graph generation should work from generated courseware or known articles."""

    repository = KnowledgeGraphRepository()
    repository._driver = None

    topic = "高等数学：极限、导数与积分"
    graph = repository.get_visualization_graph(topic, 3)
    dependencies = repository.find_dependency_path(topic, 3)
    resources = repository.find_related_resources(topic)

    assert len(graph["nodes"]) >= 3
    assert dependencies
    assert isinstance(resources, list)


def test_sparse_neo4j_result_is_enriched_by_content_graph() -> None:
    """Sparse Neo4j results should still be enriched by content-derived graph nodes."""

    repository = KnowledgeGraphRepository()
    repository._driver = _SparseDriver()

    graph = repository.get_visualization_graph("高数", 3)

    # After removing hardcoded data, we still expect some nodes from existing courseware
    assert len(graph["nodes"]) >= 1


def test_remedial_exercises_generated_from_mistakes(db_session, test_user) -> None:
    """Wrong answers should produce variant remedial exercises."""

    async def run() -> None:
        service = ReportService(
            llm_client=FakeLLMClient(),
            publisher=FakePublisher(),
        )
        await service.evaluate_practice(
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

        remedial = await service.generate_remedial_exercises(test_user.id)

        assert remedial.generated_from_mistakes == 1
        assert remedial.exercises[0].source_exercise_id == 130000 + test_user.id

    asyncio.run(run())
