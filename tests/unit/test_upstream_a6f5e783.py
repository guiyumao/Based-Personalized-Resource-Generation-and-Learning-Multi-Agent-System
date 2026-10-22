"""Remote a6f5e783 contracts across UI payloads, model batching and graph metadata."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from common.db.session import SessionLocal
from common.models.learning import Exercise
from common.schemas.agent import ExerciseGenerationRequest, GraphVisualizationResponse
from services.agent_service.app.api.routes.assistant import AssistantChatInput
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.agent_service.app.services import assistant_tasks
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.qa_service import QAService


@pytest.mark.parametrize("count", [1, 2, 7, 10, 25])
def test_requested_count_persists_exactly_for_current_learner(test_user, monkeypatch, count):
    service = ExerciseGenerationService()

    def generate(request, *args):
        return {
            "summary": "受控模型输出，真实持久化验证",
            "exercises": [
                {
                    "exercise_id": i,
                    "knowledge_point": "TCP",
                    "question_type": "choice",
                    "difficulty": "foundation",
                    "prompt": f"TCP 报文段初始序号为 {1000 + i * 100}，携带 {i} 字节数据，接收方确认号是多少？",
                    "options": [f"A. {1000 + i * 100 + i}", f"B. {1000 + i * 100}", "C. 0", "D. 1"],
                    "answer": "A",
                    "analysis": "TCP 确认号等于下一个期望接收的字节序号，即当前序号加有效数据长度。",
                }
                for i in range(1, count + 1)
            ],
        }

    monkeypatch.setattr(service, "_try_generate_with_llm", generate)
    result = service.generate_exercises(
        ExerciseGenerationRequest(
            user_id=test_user.id,
            knowledge_point="TCP",
            exercise_count=count,
            question_type_counts={"choice": count},
        )
    )
    assert len(result["exercises"]) == count
    ids = [row["exercise_id"] for row in result["exercises"]]
    assert len(set(ids)) == count
    with SessionLocal() as db:
        rows = db.query(Exercise).filter(Exercise.id.in_(ids)).all()
        assert len(rows) == count
        assert all(json.loads(row.content)["generated_for_user_id"] == test_user.id for row in rows)


@pytest.mark.parametrize("count", range(1, 26))
def test_default_question_mix_covers_requested_count(count):
    request = ExerciseGenerationRequest(user_id=1, knowledge_point="TCP", exercise_count=count)
    service = ExerciseGenerationService()
    counts = service._question_type_counts(request)
    assert sum(counts.values()) == count
    assert all(value > 0 for value in counts.values())
    assert len(service._question_type_sequence_for_request(request)) == count


@pytest.mark.parametrize("count", [0, 26, -1])
def test_all_public_generation_inputs_reject_out_of_range_count(count):
    with pytest.raises(ValidationError):
        ExerciseGenerationRequest(user_id=1, knowledge_point="TCP", exercise_count=count)
    with pytest.raises(ValidationError):
        AssistantChatInput(client_request_id="range-test", message="生成题目", exercise_count=count)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, [1]), (2, [2]), (11, [10, 1]), (20, [10, 10]), (21, [10, 10, 1]), (25, [10, 10, 5])],
)
def test_assistant_count_batches_keep_stable_distinct_receipts(monkeypatch, count, expected):
    batches = []
    indices = []

    class Coordinator:
        def __init__(self, db):
            pass

        def run(self, request):
            n = request.payload["exercise_count"]
            start = sum(batches)
            batches.append(n)
            indices.append(request.payload.get("assistant_exercise_batch", 0))
            return {
                "status": "success",
                "agent_calls": [],
                "citations": [],
                "outputs": {
                    "exercise_generation_agent": {
                        "exercise_set": {
                            "exercises": [
                                {"exercise_id": i} for i in range(start + 1, start + n + 1)
                            ]
                        }
                    }
                },
            }

    monkeypatch.setattr(assistant_tasks, "CoordinatorWorkflow", Coordinator)
    task = SimpleNamespace(
        user_id=1,
        task_type="exercise",
        current_step="",
        request_json={
            "message": f"生成{count}道 TCP 练习题",
            "knowledge_point": "TCP",
            "exercise_count": count,
        },
    )
    result, _ = assistant_tasks._coordinated_result(SimpleNamespace(commit=lambda: None), task)
    assert batches == expected
    assert indices == list(range(len(expected)))
    assert [row["exercise_id"] for row in result["exercise_set"]["exercises"]] == list(
        range(1, count + 1)
    )


@pytest.mark.parametrize(
    ("question", "expected"), [("生成1道练习", 1), ("生成25道练习", 25), ("生成26道练习", 25)]
)
def test_qa_count_uses_same_supported_range(question, expected):
    assert QAService._extract_exercise_count(None, question) == expected


def test_graph_references_survive_build_merge_and_response_schema(monkeypatch):
    repo = object.__new__(KnowledgeGraphRepository)
    repo.knowledge_base = SimpleNamespace(
        article_to_dict=lambda _: {
            "external_resources": [
                {
                    "title": "TCP RFC 9293",
                    "url": "https://www.rfc-editor.org/rfc/rfc9293",
                    "provider": "RFC Editor",
                    "kind": "reference",
                },
                {"title": "不安全脚本", "url": "javascript:alert(1)"},
                {"title": "缺少主机", "url": "https://"},
            ]
        }
    )
    monkeypatch.setattr(repo, "_get_article_for_graph", lambda _: object())
    monkeypatch.setattr(repo, "_derive_prerequisites", lambda *a, **kw: [])
    monkeypatch.setattr(repo, "_derive_recommendations", lambda *a, **kw: [])
    monkeypatch.setattr(repo, "_derive_resource_nodes", lambda *a: ["TCP RFC 9293"])
    graph = repo._build_visualization_graph_from_content("TCP", allow_llm=False)
    graph = repo._merge_graphs(
        [
            graph,
            {
                "nodes": [{"id": "TCP RFC 9293", "label": "TCP RFC 9293", "category": "resource"}],
                "edges": [],
            },
        ]
    )
    response = GraphVisualizationResponse(knowledge_point="TCP", **graph)
    node = next(row for row in response.nodes if row.category == "resource")
    assert node.url == "https://www.rfc-editor.org/rfc/rfc9293"
    assert node.provider == "RFC Editor"
    assert node.kind == "reference"
    assert len(repo._resource_links(object())) == 1


def test_graph_exact_reference_match_beats_earlier_fuzzy_label():
    repo = object.__new__(KnowledgeGraphRepository)
    links = [
        {
            "title": "TCP RFC 9293 扩展阅读",
            "url": "https://example.org/long",
            "provider": "扩展",
            "kind": "article",
        },
        {
            "title": "TCP RFC 9293",
            "url": "https://www.rfc-editor.org/rfc/rfc9293",
            "provider": "RFC",
            "kind": "standard",
        },
    ]
    assert repo._match_resource_link("TCP RFC 9293", links)["url"] == links[1]["url"]


def test_audit_retry_formats_current_count_plan_and_deduplication(monkeypatch):
    from langchain_core.runnables import RunnableLambda

    from services.agent_service.app.services import exercise_generation as module
    from services.agent_service.app.services.audit_service import AuditService
    from services.agent_service.app.services.llm_factory import LLMFactory
    from services.agent_service.app.services.personalization import LearnerPersonalizationSnapshot

    captured = []
    decisions = iter(
        [
            SimpleNamespace(passed=False, reason="需要重试", status="rejected"),
            SimpleNamespace(passed=True, reason="通过", status="passed"),
        ]
    )
    monkeypatch.setattr(AuditService, "audit_exercises", lambda *args, **kwargs: next(decisions))
    monkeypatch.setattr(
        LLMFactory, "build_chat_model", lambda *args, **kwargs: RunnableLambda(lambda _: "")
    )

    def invoke(chain, variables, **kwargs):
        messages = chain.first.format_messages(**variables)
        captured.append((variables, messages))
        return json.dumps(
            {
                "summary": "重试结果",
                "exercises": [
                    {
                        "prompt": "TCP",
                        "answer": "A",
                        "analysis": "TCP",
                        "question_type": "choice",
                        "difficulty": "foundation",
                    }
                ],
            }
        )

    monkeypatch.setattr(module, "traced_invoke", invoke)
    service = ExerciseGenerationService()
    monkeypatch.setattr(service.knowledge_base, "get_article", lambda *args: None)
    snapshot = LearnerPersonalizationSnapshot({}, None, [], 0, None)
    plan = {"question_type_targets": ["choice"]}
    result = service._audit_and_retry_exercises(
        ExerciseGenerationRequest(user_id=1, knowledge_point="TCP", exercise_count=1),
        snapshot,
        {"exercises": []},
        plan,
        {"already-used-question"},
    )
    assert result["_audit_status"] == "passed"
    variables, messages = captured[0]
    assert variables["exercise_count"] == 1
    assert json.loads(variables["agent_plan"]) == plan
    assert json.loads(variables["previous_question_signatures"]) == ["already-used-question"]
    assert "本次请求题量为 1 道" in messages[0].content


@pytest.mark.parametrize(
    ("message", "count"),
    [
        ("生成一道TCP练习题", 1),
        ("生成两道TCP练习题", 2),
        ("生成二十五道TCP练习题", 25),
        ("生成125道TCP练习题", 125),
    ],
)
def test_assistant_natural_count_respects_new_lower_bound_and_full_number(message, count):
    assert assistant_tasks.infer_exercise_count(message) == count


def test_teacher_detail_forwards_original_bearer_header(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from common.dependencies import get_current_user
    from common.models.learning import User
    from services.teacher_service.app.api.routes import classes

    api = FastAPI()
    api.include_router(classes.router, prefix="/teacher")
    api.dependency_overrides[get_current_user] = lambda: User(
        id=7, username="teacher", role="teacher", password_hash="x"
    )
    permissions = []
    forwarded = []
    monkeypatch.setattr(
        classes.manager, "ensure_teacher_class_access", lambda *args: permissions.append(args)
    )

    async def get_detail(class_id, user_id, auth_header=None):
        forwarded.append((class_id, user_id, auth_header))
        raise ValueError("No report in isolated test")

    monkeypatch.setattr(classes.manager, "get_student_learning_detail", get_detail)
    response = TestClient(api).get(
        "/teacher/classes/9/students/11", headers={"Authorization": "Bearer original-test-token"}
    )
    assert response.status_code == 404
    assert permissions == [(9, 7, "teacher")]
    assert forwarded == [(9, 11, "Bearer original-test-token")]
