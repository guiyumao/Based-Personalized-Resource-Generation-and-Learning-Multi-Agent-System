"""No model can precede catalog/publication/current-chunk validation."""

import hashlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import (
    KnowledgeBuildTask,
    KnowledgeCandidate,
    KnowledgePoint,
    KnowledgeVersion,
    LearningKnowledgeGap,
    LearningPath,
    SystemSubject,
)
from common.schemas.agent import CoordinationRequest, LearningPathRequest
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.main import app
from services.agent_service.app.services import plan_knowledge as service
from services.agent_service.app.services.learning_path import LearningPathService


@pytest.fixture
def coverage(db_session, test_user, tmp_path, monkeypatch):
    subject = SystemSubject(
        name=f"网络-{test_user.id}",
        code=f"network_{test_user.id}",
        description="fixture",
        aliases_json=[f"network-alias-{test_user.id}"],
    )
    db_session.add(subject)
    db_session.flush()
    point = KnowledgePoint(name=f"TCP-{test_user.id}", subject_id=subject.id)
    db_session.add(point)
    db_session.commit()
    monkeypatch.setattr(service, "KNOWLEDGE_ROOT", tmp_path)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=test_user.id, role="student"
    )
    yield SimpleNamespace(
        db=db_session,
        user=test_user,
        subject=subject,
        point=point,
        root=tmp_path,
        monkeypatch=monkeypatch,
    )
    app.dependency_overrides.clear()
    db_session.query(LearningKnowledgeGap).filter_by(user_id=test_user.id).delete()
    db_session.query(KnowledgeVersion).filter_by(subject=subject.code).delete()
    db_session.query(KnowledgeCandidate).filter_by(subject=subject.code).delete()
    db_session.query(KnowledgeBuildTask).filter_by(actor_user_id=test_user.id).delete()
    db_session.query(LearningPath).filter_by(user_id=test_user.id).delete()
    db_session.delete(point)
    db_session.delete(subject)
    db_session.commit()


def publish_fixture(ctx):
    # Existing publication records are an explicit fixture; the retriever below
    # is a protocol stub, not evidence of a running Chroma deployment.
    corpus = ctx.root / "knowledge_base/corpus" / ctx.subject.code
    corpus.mkdir(parents=True)
    path = corpus / "approved.md"
    path.write_text("# TCP\nApproved fixture publication", encoding="utf-8")
    task = KnowledgeBuildTask(
        actor_user_id=ctx.user.id,
        client_request_id="publication-fixture",
        request_hash="f" * 64,
        trigger_source="manual",
        operation_type="BUILD_POINT",
        subject=ctx.subject.code,
    )
    ctx.db.add(task)
    ctx.db.flush()
    candidate = KnowledgeCandidate(
        creator_user_id=ctx.user.id,
        source_task_id=task.id,
        subject=ctx.subject.code,
        knowledge_point=ctx.point.name,
        title="Approved",
        content="fixture",
        source_url="upload:fixture",
        source_hash="f" * 64,
        content_hash="f" * 64,
        status="PUBLISHED",
    )
    ctx.db.add(candidate)
    ctx.db.flush()
    ctx.db.add(
        KnowledgeVersion(
            candidate_id=candidate.id,
            version_number=1,
            subject=ctx.subject.code,
            knowledge_point=ctx.point.name,
            title="Approved",
            content="fixture",
            source_url="upload:fixture",
            content_hash="f" * 64,
            corpus_path=path.relative_to(ctx.root).as_posix(),
            published_by=ctx.user.id,
            is_active=True,
        )
    )
    ctx.db.commit()
    metadata = {
        "source": f"{ctx.subject.code}/approved.md",
        "document_version": hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest(),
        "subject": ctx.subject.code,
        "teacher_scope": "public",
    }
    return {"content": "Approved fixture publication", "metadata": metadata}


def retriever(ctx, chunks, available=True):
    class Retriever:
        is_available = available

        def retrieve_with_metadata(self, query, **kwargs):
            assert query == ctx.point.name
            assert kwargs["filters"] == {"subject": ctx.subject.code}
            return chunks

    ctx.monkeypatch.setattr(service, "ChromaRetriever", Retriever)


def test_unknown_subject_gap_deduplicates_and_backfills_knowledge_base(coverage, monkeypatch):
    ctx = coverage
    monkeypatch.setattr(
        LearningPathService,
        "_generate_path_with_llm",
        lambda self, request, teacher_scope: {
            "user_id": request.user_id,
            "subject": request.subject,
            "knowledge_point": request.knowledge_point,
            "overview": "从零学习",
            "estimated_days": 42,
            "stages": [{"stage_id": "s1", "title": "基础", "description": "", "tasks": [
                {"task_id": "t1", "title": "入门", "task_type": "courseware",
                 "knowledge_point": request.knowledge_point, "objective": "理解",
                 "estimated_minutes": 30, "difficulty": "foundation", "completed": False,
                 "status": "pending", "depends_on": []},
            ]}],
        },
    )
    body = {"subject": "未知物理学科", "knowledge_point": "陌生知识点"}
    client = TestClient(app)
    first = client.post("/paths/preflight", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["reason"] == "SUBJECT_MISSING"
    assert first.json()["mode"] == "personal_draft"
    assert client.post("/paths/preflight", json=body).json()["gap_id"] == first.json()["gap_id"]
    assert ctx.db.query(LearningKnowledgeGap).filter_by(user_id=ctx.user.id, subject=body["subject"], knowledge_point=body["knowledge_point"]).count() == 1
    # The coverage fixture isolates preflight's corpus root to tmp_path, but
    # the backfill publishes through the normal pipeline rooted at the
    # runtime knowledge root; point preflight back at it so the end-to-end
    # "published then retrievable" check is consistent.
    from common.knowledge_paths import KNOWLEDGE_ROOT as RUNTIME_ROOT

    monkeypatch.setattr(service, "KNOWLEDGE_ROOT", RUNTIME_ROOT)
    workflow = CoordinatorWorkflow(db=ctx.db)
    workflow.run(
        CoordinationRequest(
            user_id=ctx.user.id,
            intent="生成计划",
            knowledge_point="陌生知识点",
            payload={
                "execute": True,
                "force_agents": ["path_planning_agent"],
                "subject": "未知物理学科",
            },
        )
    )
    # The unknown discipline is auto-built and published into the knowledge base,
    # so the next request for it is served directly from public knowledge.
    subject = ctx.db.query(SystemSubject).filter_by(name="未知物理学科").one()
    path = (ctx.db.query(LearningPath)
            .filter_by(user_id=ctx.user.id, status="active")
            .order_by(LearningPath.id.desc()).first())
    assert path is not None
    assert path.path_data_json["knowledge_scope"] == "public"
    assert path.path_data_json["subject_id"] == subject.id
    assert "knowledge_gap_reason" not in path.path_data_json
    # The recorded gap is resolved by the successful backfill.
    gap = ctx.db.query(LearningKnowledgeGap).filter_by(
        user_id=ctx.user.id, subject=body["subject"], knowledge_point=body["knowledge_point"]).one()
    assert gap.status == "RESOLVED"
    # Clean up the auto-backfilled catalog/publication rows: they use the
    # generated auto_* subject code, outside the fixture's teardown scope.
    ctx.db.query(KnowledgeVersion).filter_by(subject=subject.code).delete()
    ctx.db.query(KnowledgeCandidate).filter_by(subject=subject.code).delete()
    ctx.db.query(KnowledgePoint).filter_by(subject_id=subject.id).delete()
    ctx.db.delete(subject)
    ctx.db.commit()


@pytest.mark.parametrize(
    "state",
    [
        "missing_publication",
        "unavailable",
        "stale",
        "private",
        "wrong_subject",
        "inactive",
        "valid",
    ],
)
def test_publication_and_live_index_version_must_both_match(coverage, state):
    ctx = coverage
    chunks = [] if state == "missing_publication" else [publish_fixture(ctx)]
    if state == "stale":
        chunks[0]["metadata"]["document_version"] = "0" * 64
    if state == "private":
        chunks[0]["metadata"]["teacher_scope"] = "teacher:99"
    if state == "wrong_subject":
        chunks[0]["metadata"]["subject"] = "other"
    if state == "inactive":
        ctx.db.query(KnowledgeVersion).filter_by(subject=ctx.subject.code).update(
            {"is_active": False}
        )
        ctx.db.commit()
    retriever(ctx, chunks, state != "unavailable")
    result = service.plan_preflight(ctx.db, ctx.user.id, ctx.subject.name, ctx.point.name)
    assert result["ready"] is (state == "valid")
    if state != "valid":
        assert result["gap_id"]
        with pytest.raises(HTTPException):
            service.require_plan_knowledge(ctx.db, ctx.user.id, ctx.subject.name, ctx.point.name)
    else:
        assert result["usable_chunks"] == chunks
        path_service = LearningPathService(ctx.db)

        def generate(request, _):
            assert request.retrieval_context["retrieved_chunks"] == chunks
            return {
                "user_id": ctx.user.id,
                "subject": ctx.subject.name,
                "knowledge_point": ctx.point.name,
                "overview": "fixture",
                "estimated_days": 1,
                "stages": [
                    {
                        "stage_id": "s1",
                        "title": "fixture",
                        "tasks": [
                            {
                                "task_id": "t1",
                                "title": "阅读",
                                "knowledge_point": "model invented point",
                                "task_type": "courseware",
                                "depends_on": [],
                            }
                        ],
                    }
                ],
            }

        ctx.monkeypatch.setattr(path_service, "_generate_path_with_llm", generate)
        payload = path_service.generate_path(
            LearningPathRequest(
                user_id=ctx.user.id, subject=ctx.subject.name, knowledge_point=ctx.point.name
            ),
            persist=False,
        )
        assert payload["stages"][0]["tasks"][0]["knowledge_point_id"] == ctx.point.id
        assert payload["stages"][0]["tasks"][0]["knowledge_point"] == ctx.point.name
        assert payload["knowledge_versions"]


def test_gap_admin_boundary_and_queued_construction(coverage):
    ctx = coverage
    gap = service.plan_preflight(ctx.db, ctx.user.id, ctx.subject.name, ctx.point.name)["gap_id"]
    client = TestClient(app)
    assert client.get("/knowledge-base/admin/learning-gaps").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=ctx.user.id, role="admin"
    )
    assert client.get("/knowledge-base/admin/learning-gaps").status_code == 200
    body = {"client_request_id": "gap-construction-fixture"}
    first = client.post(f"/knowledge-base/admin/learning-gaps/{gap}/construction", json=body)
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "QUEUED"
    assert (
        client.post(f"/knowledge-base/admin/learning-gaps/{gap}/construction", json=body).json()[
            "id"
        ]
        == first.json()["id"]
    )
    # Leave fixture's FK target intact, but disconnect it for user teardown.
    ctx.db.get(LearningKnowledgeGap, gap).knowledge_task_id = None
    ctx.db.commit()
    from common.models.learning import AuditLog, KnowledgeBuildTask

    ctx.db.query(AuditLog).filter_by(actor_user_id=ctx.user.id).delete()
    ctx.db.query(KnowledgeBuildTask).filter_by(actor_user_id=ctx.user.id).delete()
    ctx.db.commit()


def test_publication_withdrawn_during_generation_prevents_plan_write(coverage):
    ctx = coverage
    retriever(ctx, [publish_fixture(ctx)])
    path_service = LearningPathService(ctx.db)

    def generate(*_):
        ctx.db.query(KnowledgeVersion).filter_by(subject=ctx.subject.code).update(
            {"is_active": False}
        )
        ctx.db.commit()
        return {"stages": []}

    ctx.monkeypatch.setattr(path_service, "_generate_path_with_llm", generate)
    with pytest.raises(HTTPException) as caught:
        path_service.generate_path(
            LearningPathRequest(
                user_id=ctx.user.id, subject=ctx.subject.name, knowledge_point=ctx.point.name
            )
        )
    assert caught.value.status_code == 409
    assert ctx.db.query(LearningPath).filter_by(user_id=ctx.user.id).count() == 0
