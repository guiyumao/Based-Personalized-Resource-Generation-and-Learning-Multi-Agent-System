"""Public-source and owner-only graph boundaries using real SQLite/API routes."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import KnowledgePoint, KnowledgeRelation, Resource, SystemSubject, User
from common.resource_version import resource_version
from services.agent_service.app.connectors import neo4j_connector as graph_module
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.agent_service.app.main import app


@pytest.fixture
def graph_db(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all(
            [
                User(id=1, username="one", password_hash="unused"),
                User(id=2, username="two", password_hash="unused"),
                User(id=3, username="admin", role="admin", password_hash="unused"),
            ]
        )
        subject = SystemSubject(name="计算机网络", code="network", description="test")
        db.add(subject)
        db.flush()
        point = KnowledgePoint(name="TCP", subject_id=subject.id)
        db.add(point)
        db.flush()
        db.add_all(
            [
                Resource(
                    id=1,
                    title="私人标题",
                    type="article",
                    content="# 私人协议细节",
                    knowledge_point_id=point.id,
                    generated_for_user_id=1,
                ),
                Resource(
                    id=2,
                    title="公开标题",
                    type="article",
                    content="# TCP公开课件",
                    knowledge_point_id=point.id,
                    publish_status="published",
                    audit_status="passed",
                ),
                Resource(
                    id=3,
                    title="未审核标题",
                    type="article",
                    content="# TCP待审",
                    knowledge_point_id=point.id,
                    publish_status="published",
                    audit_status="pending",
                ),
            ]
        )
        db.commit()
        monkeypatch.setattr(graph_module, "SessionLocal", factory)
        monkeypatch.setattr(
            KnowledgeGraphRepository, "_neo4j_reachable", staticmethod(lambda _: False)
        )
        monkeypatch.setattr(KnowledgeGraphRepository, "_get_article_for_graph", lambda *_: None)
        KnowledgeGraphRepository.clear_visualization_cache()
        app.dependency_overrides[get_db] = lambda: db
        yield db, factory
        app.dependency_overrides.clear()
        KnowledgeGraphRepository.clear_visualization_cache()
    engine.dispose()


def test_anonymous_cannot_reach_graph_or_enrichment(graph_db, monkeypatch):
    monkeypatch.setattr(
        KnowledgeGraphRepository,
        "acquire_shared",
        classmethod(lambda _: pytest.fail("unauthenticated repository acquisition")),
    )
    client = TestClient(app)
    assert client.post("/graph/visualization", json={"knowledge_point": "TCP"}).status_code == 401
    assert client.post("/graph/dependencies", json={"knowledge_point": "TCP"}).status_code == 401
    assert client.get("/graph/related-resources/TCP").status_code == 401
    assert (
        client.post(
            "/graph/enrichment", json={"point_id": 1, "client_request_id": "graph-test-one"}
        ).status_code
        == 401
    )


def test_public_graph_filters_private_drafts_and_revalidates_versions(graph_db, monkeypatch):
    db, _ = graph_db
    monkeypatch.setattr(
        KnowledgeGraphRepository,
        "_schedule_enrichment",
        lambda *_: pytest.fail("paid scheduling from a read"),
    )
    monkeypatch.setattr(
        KnowledgeGraphRepository,
        "_extract_kp_labels_via_llm",
        lambda *_: pytest.fail("model on graph read"),
    )
    repo = KnowledgeGraphRepository()
    assert [row.id for row, _ in repo._matching_resource_rows("TCP", 10)] == [2]
    first = repo.get_visualization_graph("TCP", allow_enrichment=True)
    assert "私人协议" not in str(first)
    assert "TCP公开课件" in str(first)
    resource = db.get(Resource, 2)
    resource.content = "# TCP更新课件"
    db.commit()
    second = repo.get_visualization_graph("TCP")
    assert "更新课件" in str(second) and "TCP公开课件" not in str(second)
    resource.publish_status = "archived"
    db.commit()
    with pytest.raises(ValueError):
        repo.get_visualization_graph("TCP")
    assert db.query(KnowledgeRelation).count() == 0


def test_private_owner_cross_user_admin_version_and_no_shared_cache(graph_db):
    db, _ = graph_db
    client = TestClient(app)
    request = {
        "knowledge_point": "TCP",
        "resource_id": 1,
        "resource_version": resource_version(db.get(Resource, 1)),
    }
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    own = client.post("/graph/visualization", json=request)
    assert own.status_code == 200 and "私人协议细节" in own.text
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 2)
    cross = client.post("/graph/visualization", json=request)
    assert cross.status_code == 404 and "私人" not in cross.text
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 3)
    assert client.post("/graph/visualization", json=request).status_code == 200
    resource = db.get(Resource, 1)
    resource.content = "# 另一版本"
    db.commit()
    assert client.post("/graph/visualization", json=request).status_code == 409
    assert KnowledgeGraphRepository.visualization_cache_stats().entries == 0


def test_explicit_enrichment_reuses_durable_budgeted_queue(graph_db, monkeypatch):
    from services.agent_service.app.services import knowledge_tasks

    db, factory = graph_db
    monkeypatch.setattr(knowledge_tasks, "SessionLocal", factory)
    client = TestClient(app)
    body = {"point_id": 1, "client_request_id": "graph-build-test"}
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 1)
    assert client.post("/graph/enrichment", json=body).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 3)
    first = client.post("/graph/enrichment", json=body)
    assert first.status_code == 202
    assert client.post("/graph/enrichment", json=body).json()["id"] == first.json()["id"]
    assert first.json()["operation_type"] == "BUILD_POINT"
    assert first.json()["status"] == "QUEUED"


def test_unclassified_historical_labels_do_not_enter_public_graph(graph_db, monkeypatch):
    db, _ = graph_db
    private_point = KnowledgePoint(name="PRIVATE_INFERRED_LABEL")
    db.add(private_point)
    db.flush()
    db.add(KnowledgeRelation(from_id=1, to_id=private_point.id, relation_type="DEPENDS_ON"))
    db.commit()
    repo = KnowledgeGraphRepository()
    repo._driver = object()
    monkeypatch.setattr(
        repo,
        "_get_visualization_graph_from_neo4j",
        lambda *_: pytest.fail("unclassified Neo4j labels read"),
    )
    monkeypatch.setattr(
        repo,
        "_find_dependency_path_from_neo4j",
        lambda *_: pytest.fail("unclassified Neo4j dependencies read"),
    )
    assert "PRIVATE_INFERRED_LABEL" not in str(repo.get_visualization_graph("TCP"))
    assert repo._find_dependency_path_from_sql("TCP", 2) == []
    assert not db.get(KnowledgePoint, private_point.id).subject_id
    repo._driver = None


@pytest.mark.parametrize("stop", ["budget_zero", "cancelled"])
def test_graph_construction_budget_or_cancel_prevents_provider(graph_db, monkeypatch, stop):
    from common.models.learning import KnowledgeBuildTask
    from services.agent_service.app.services import (
        knowledge_budget,
        knowledge_construction,
        knowledge_tasks,
    )

    db, factory = graph_db
    monkeypatch.setattr(knowledge_tasks, "SessionLocal", factory)
    monkeypatch.setattr(knowledge_budget, "SessionLocal", factory)
    monkeypatch.setenv("KNOWLEDGE_MODEL_DAY_LIMIT", "0")

    def construction(task, guard):
        knowledge_budget.reserve_usage("model", input_tokens=100, output_tokens=100)
        pytest.fail("provider reached after zero budget or cancellation")

    monkeypatch.setattr(knowledge_construction, "build_point", construction)
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 3)
    response = TestClient(app).post(
        "/graph/enrichment", json={"point_id": 1, "client_request_id": f"graph-stop-{stop}"}
    )
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    if stop == "cancelled":
        knowledge_tasks.cancel_task(db, db.get(KnowledgeBuildTask, task_id))
    if stop == "budget_zero":
        with pytest.raises(knowledge_budget.KnowledgeBudgetExceeded):
            knowledge_tasks.execute_task(task_id)
    else:
        knowledge_tasks.execute_task(task_id)
    db.expire_all()
    task = db.get(KnowledgeBuildTask, task_id)
    assert task.status == ("CANCELLED" if stop == "cancelled" else "FAILED")
    assert db.query(KnowledgeRelation).count() == 0
    assert KnowledgeGraphRepository.visualization_cache_stats().entries == 0
