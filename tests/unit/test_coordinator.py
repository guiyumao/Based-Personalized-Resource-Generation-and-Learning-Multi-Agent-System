"""Unit tests for the coordinator workflow."""

from types import SimpleNamespace

from common.schemas.agent import CoordinationRequest
from services.agent_service.app.agents import coordinator as coordinator_module
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.evaluation_service.app.schemas.report import AnalyticsSuggestion


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


def test_coordinator_executes_agents_as_one_workflow(monkeypatch):
    """Coordinator should compose profiling, graph, path, resource and exercise outputs."""

    published_messages: list[tuple[str, dict]] = []

    class FakePersonalizationService:
        def __init__(self, db):
            self.db = db

        def build_snapshot(self, user_id: int, knowledge_point: str, fallback_profile: dict):
            return SimpleNamespace(
                learner_profile={
                    **fallback_profile,
                    "mastery": 72,
                    "weak_question_types": ["short_answer"],
                    "profile_dimensions": {"cognitiveStyle": "视觉型"},
                    "profile_analysis_summaries": {
                        "knowledgeBase": "基础不错但迁移偏弱",
                        "goalOrientation": "求职导向较明确",
                    },
                    "preferred_resource_modes": ["diagram"],
                    "agent_handoff": {
                        "path_planning_agent": ["use visual path"],
                        "resource_generation_agent": ["use diagrams"],
                        "exercise_generation_agent": ["practice graph mistakes"],
                    },
                },
                mastery_score=72,
                correct_rate=80,
                answered_count=5,
                recent_mistakes=[{"question_type": "short_answer", "difficulty": "intermediate"}],
            )

    class FakeKnowledgeGraphRepository:
        def find_dependency_path(self, knowledge_point: str, max_depth: int):
            return [{"name": "变量", "relation": "prerequisite"}]

        def get_visualization_graph(self, knowledge_point: str, max_depth: int):
            return {"nodes": [{"id": knowledge_point, "label": knowledge_point}], "edges": []}

        def close(self):
            return None

    class FakeLearningPathService:
        def __init__(self, db):
            self.db = db

        def generate_path(self, request):
            return {
                "user_id": request.user_id,
                "subject": request.subject,
                "knowledge_point": request.knowledge_point,
                "overview": "协同路径",
                "estimated_days": 3,
                "stages": [],
            }

    class FakeResourceGenerationService:
        def generate_courseware_with_plan(self, request):
            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "resource_type": request.resource_type,
                "resource_style": request.resource_style,
                "content": "课件正文",
                "variants": [{"variant_id": "interactive-1", "is_recommended": True, "content": "课件正文"}],
            }

    class FakeExerciseGenerationService:
        def generate_exercises(self, request):
            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "summary": request.courseware_content,
                "exercises": [],
            }

    workflow = CoordinatorWorkflow(db=object())
    monkeypatch.setattr(workflow.publisher, "publish", lambda queue_name, message: published_messages.append((queue_name, message)))
    monkeypatch.setattr(coordinator_module, "PersonalizationService", FakePersonalizationService)
    monkeypatch.setattr(coordinator_module, "KnowledgeGraphRepository", FakeKnowledgeGraphRepository)
    monkeypatch.setattr(coordinator_module, "LearningPathService", FakeLearningPathService)
    monkeypatch.setattr(coordinator_module, "ResourceGenerationService", FakeResourceGenerationService)
    monkeypatch.setattr(coordinator_module, "ExerciseGenerationService", FakeExerciseGenerationService)

    result = workflow.run(
        CoordinationRequest(
            user_id=7,
            intent="生成个性化学习路径、课件和练习",
            knowledge_point="Python 循环",
            payload={
                "execute": True,
                "include_exercises": True,
                "subject": "Python 程序设计",
                "daily_minutes": 45,
                "learner_profile": {"learning_style": "visual"},
            },
        )
    )

    assert result["status"] == "success"
    assert result["selected_agents"] == [
        "learner_profiling_agent",
        "resource_generation_agent",
        "knowledge_graph_agent",
        "path_planning_agent",
        "exercise_generation_agent",
    ]
    assert len(published_messages) == 5
    assert result["outputs"]["learner_profiling_agent"]["learner_profile"]["mastery"] == 72
    assert result["outputs"]["learner_profiling_agent"]["agent_handoff"]["resource_generation_agent"] == ["use diagrams"]
    assert result["outputs"]["learner_profiling_agent"]["profile_analysis_summaries"]["knowledgeBase"] == "基础不错但迁移偏弱"
    assert result["outputs"]["knowledge_graph_agent"]["dependencies"][0]["name"] == "变量"
    assert result["outputs"]["path_planning_agent"]["learning_path"]["overview"] == "协同路径"
    assert result["outputs"]["path_planning_agent"]["profile_handoff"] == ["use visual path"]
    assert result["outputs"]["resource_generation_agent"]["resource"]["content"] == "课件正文"
    assert result["outputs"]["resource_generation_agent"]["profile_handoff"] == ["use diagrams"]
    assert result["outputs"]["exercise_generation_agent"]["exercise_set"]["summary"] == "课件正文"
    assert result["outputs"]["exercise_generation_agent"]["profile_handoff"] == ["practice graph mistakes"]
    summary = result["outputs"]["coordinator_summary"]
    assert summary["completed_agents"] == result["selected_agents"]
    assert summary["shared_context"]["profile_analysis_summaries"]["knowledgeBase"] == "基础不错但迁移偏弱"
    assert summary["handoff_map"]["resource_generation_agent"] == ["use diagrams"]


def test_coordinator_full_collaboration_intent_selects_all_agents():
    """Full-collaboration intent should schedule every local agent capability."""

    workflow = CoordinatorWorkflow(db=object())
    workflow.publisher.publish = lambda queue_name, message: None

    result = workflow.run(
        CoordinationRequest(
            user_id=3,
            intent="智能体全部联合实现系统配合",
            knowledge_point="Python 循环",
            payload={},
        )
    )

    assert result["status"] == "success"
    assert result["selected_agents"] == [
        "learner_profiling_agent",
        "knowledge_graph_agent",
        "knowledge_base_agent",
        "path_planning_agent",
        "resource_generation_agent",
        "exercise_generation_agent",
        "qa_agent",
        "evaluation_feedback_agent",
    ]


def test_coordinator_force_agents_override_intent_routing():
    """Forced agents should bypass automatic intent-based agent expansion."""

    workflow = CoordinatorWorkflow(db=object())
    workflow.publisher.publish = lambda queue_name, message: None

    result = workflow.run(
        CoordinationRequest(
            user_id=3,
            intent="qa question analysis",
            knowledge_point="",
            payload={
                "force_agents": ["qa_agent"],
            },
        )
    )

    assert result["selected_agents"] == ["qa_agent"]
    assert "used forced agents" in result["route_reason"]
