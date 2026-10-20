from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import (
    AuditLog,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgePoint,
    SystemSubject,
)
from services.agent_service.app.main import app
from services.agent_service.app.services import knowledge_documents as service


@pytest.fixture
def context(tmp_path, db_session, test_user, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    monkeypatch.setattr(service, "CORPUS_DIR", corpus)
    monkeypatch.setattr(service, "UPLOADS", tmp_path / "originals")
    monkeypatch.setattr(service, "_read_manifest", lambda: {"documents": {}})
    subject = SystemSubject(
        name=f"数学-{tmp_path.name}",
        code=f"math_{test_user.id}",
        description="test",
        aliases_json=["线性代数"],
    )
    other = SystemSubject(
        name=f"其他-{tmp_path.name}", code=f"other_{test_user.id}", description="test"
    )
    db_session.add_all([subject, other])
    db_session.flush()
    point = KnowledgePoint(name="向量", subject_id=subject.id)
    wrong = KnowledgePoint(name="其他知识", subject_id=other.id)
    db_session.add_all([point, wrong])
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=test_user.id, role="admin"
    )
    client = TestClient(app)
    yield SimpleNamespace(
        db=db_session,
        client=client,
        corpus=corpus,
        subject=subject,
        other=other,
        point=point,
        wrong=wrong,
        user=test_user,
    )
    app.dependency_overrides.clear()
    # Leave test data confined to the unique runner database, avoiding shared
    # fixture user teardown foreign-key references.
    db_session.query(AuditLog).filter_by(actor_user_id=test_user.id).delete()
    from common.models.learning import KnowledgeBuildTask, KnowledgeDocumentPoint

    docs = db_session.query(KnowledgeDocument).filter_by(creator_user_id=test_user.id).all()
    for doc in docs:
        db_session.query(KnowledgeDocumentPoint).filter_by(document_id=doc.id).delete()
        db_session.delete(doc)
    db_session.flush()
    db_session.query(KnowledgeCandidate).filter_by(creator_user_id=test_user.id).delete()
    db_session.query(KnowledgeBuildTask).filter_by(actor_user_id=test_user.id).delete()
    db_session.query(KnowledgePoint).filter(
        KnowledgePoint.subject_id.in_([subject.id, other.id])
    ).delete()
    db_session.delete(subject)
    db_session.delete(other)
    db_session.commit()


def upload(ctx, name="vectors.md", data=None):
    response = ctx.client.post(
        "/knowledge-base/admin/documents/upload",
        files={
            "file": (
                name,
                data or ("# 向量\n\n" + "向量是具有大小和方向的数学对象。" * 10).encode(),
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def classify(ctx, doc_id, **changes):
    return ctx.client.post(
        "/knowledge-base/admin/documents/classify",
        json={
            "document_ids": [doc_id],
            "subject_id": ctx.subject.id,
            "point_ids": [ctx.point.id],
            "chapter": "线性空间",
            "tags": ["数学"],
            **changes,
        },
    )


def test_legacy_full_preview_no_implicit_import(context):
    path = context.corpus / "math" / "vectors.md"
    path.parent.mkdir()
    text = "# 线性代数\n\n> 来源: https://example.org/course\n\n" + "完整正文" * 600
    path.write_text(text, encoding="utf-8")
    response = context.client.get("/knowledge-base/admin/documents").json()
    assert response["inventory"]["physical_corpus_files"] == 1
    assert response["inventory"]["source_websites"] == 1
    assert response["inventory"]["metadata_records"] == 0
    doc = response["items"][0]
    assert "text" not in doc
    assert doc["subject_id"] is None
    assert context.client.get(f"/knowledge-base/admin/documents/{doc['id']}").json()["text"] == text
    assert (
        context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/original").content
        == path.read_bytes()
    )
    assert context.db.query(KnowledgeDocument).count() == 0


@pytest.mark.parametrize("role,status", [("student", 403), ("teacher", 403), (None, 401)])
def test_all_document_routes_require_admin(context, role, status):
    if role is None:
        app.dependency_overrides.pop(get_current_user)
    else:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            role=role, id=context.user.id
        )
    routes = [
        ("get", "/documents"),
        ("get", "/documents/missing"),
        ("get", "/documents/missing/original"),
        ("get", "/documents/missing/chunks"),
        ("get", "/subjects/preflight?name=数学"),
        ("get", f"/subjects/{context.subject.id}/coverage"),
        ("post", "/documents/missing/archive"),
        ("post", "/documents/missing/candidate"),
    ]
    for method, path in routes:
        assert getattr(context.client, method)("/knowledge-base/admin" + path).status_code == status


@pytest.mark.parametrize("name", ["vectors.md", "vectors.txt", "../../vectors.md"])
def test_upload_classify_persist_stage_and_audit(context, name):
    doc = upload(context, name)
    assert doc["status"] == "DRAFT"
    assert list(context.corpus.rglob("*.md")) == []
    assert classify(context, doc["id"]).status_code == 200
    context.db.expire_all()
    detail = context.client.get(f"/knowledge-base/admin/documents/{doc['id']}").json()
    assert detail["subject_id"] == context.subject.id and detail["point_ids"] == [context.point.id]
    assert detail["chapter"] == "线性空间"
    assert (
        context.client.get(f"/knowledge-base/admin/subjects/{context.subject.id}/coverage").json()[
            "covered_points"
        ]
        == 0
    )
    first = context.client.post(f"/knowledge-base/admin/documents/{doc['id']}/candidate")
    assert first.status_code == 201, first.text
    assert first.json()["source_url"].startswith("upload://")
    assert first.json()["publication_allowed"] is False
    assert (
        context.client.post(f"/knowledge-base/admin/documents/{doc['id']}/candidate").json()["id"]
        == first.json()["id"]
    )
    assert (
        context.client.post(f"/knowledge-base/candidates/{first.json()['id']}/publish").status_code
        == 409
    )
    assert (
        context.db.query(AuditLog)
        .filter_by(event="knowledge.document.classified", actor_user_id=context.user.id)
        .count()
        == 1
    )
    assert (
        context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/original").status_code
        == 200
    )


def test_bulk_classification_rejects_wrong_subject_and_rolls_back(context):
    doc = upload(context)
    assert classify(context, doc["id"], point_ids=[context.wrong.id]).status_code == 422
    assert classify(context, doc["id"], document_ids=[doc["id"], "not-found"]).status_code == 404
    assert context.db.get(KnowledgeDocument, doc["id"]).subject_id is None


def test_preflight_alias_no_writes_and_no_automatic_merge(context):
    path = context.corpus / "math" / "linear.md"
    path.parent.mkdir()
    path.write_text("# 线性代数资料\n\n正文", encoding="utf-8")
    result = context.client.get(
        "/knowledge-base/admin/subjects/preflight", params={"name": "线性代数"}
    ).json()
    assert result["subjects"][0]["match"] == "EXACT"
    assert result["unlinked_documents"][0]["subject_id"] is None
    assert result["requires_confirmation"]
    assert context.db.query(KnowledgeDocument).count() == 0


def test_invalid_files_and_oversized_upload_leave_no_records(context):
    for name, data, status in [
        ("a.pdf", b"not PDF", 422),
        ("a.exe", b"123", 422),
        ("a.docx", b"invalid", 422),
        ("a.txt", b"x" * (5 * 1024 * 1024 + 1), 413),
    ]:
        response = context.client.post(
            "/knowledge-base/admin/documents/upload", files={"file": (name, data)}
        )
        assert response.status_code == status
    assert context.db.query(KnowledgeDocument).count() == 0


@pytest.mark.parametrize("format", ["pdf", "docx"])
def test_real_pdf_docx_parser_and_original_roundtrip(context, format):
    stream = io.BytesIO()
    if format == "pdf":
        from reportlab.pdfgen.canvas import Canvas

        canvas = Canvas(stream)
        canvas.drawString(40, 800, "Vectors have magnitude and direction in linear algebra.")
        canvas.save()
    else:
        from docx import Document

        document = Document()
        document.add_paragraph("Vectors have magnitude and direction in linear algebra.")
        document.save(stream)
    data = stream.getvalue()
    doc = upload(context, f"vectors.{format}", data)
    assert "magnitude" in doc["text"]
    response = context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/original")
    assert response.content == data
    assert response.headers["x-content-type-options"] == "nosniff"


def test_missing_original_still_has_text_archive_and_stage_guards(context):
    doc = upload(context)
    row = context.db.get(KnowledgeDocument, doc["id"])
    service.contained(service.UPLOADS, row.original_path).unlink()
    assert context.client.get(f"/knowledge-base/admin/documents/{doc['id']}").json()["text"]
    assert (
        context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/original").status_code
        == 404
    )
    assert (
        context.client.post(f"/knowledge-base/admin/documents/{doc['id']}/archive").status_code
        == 200
    )
    assert (
        context.client.post(f"/knowledge-base/admin/documents/{doc['id']}/candidate").status_code
        == 409
    )


def test_unsafe_metadata_paths_fail_closed(context):
    doc = upload(context)
    row = context.db.get(KnowledgeDocument, doc["id"])
    row.original_path = "../../outside.txt"
    context.db.commit()
    assert (
        context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/original").status_code
        == 422
    )


def test_live_chunks_use_exact_source_and_unavailable_is_503(context, monkeypatch):
    from services.agent_service.app.services import rag

    path = context.corpus / "math" / "vectors.md"
    path.parent.mkdir()
    path.write_text("# Vectors\n\nActual corpus text", encoding="utf-8")
    doc = context.client.get("/knowledge-base/admin/documents").json()["items"][0]

    def get(**kwargs):
        assert kwargs["where"] == {"source": "math/vectors.md"}
        return {
            "ids": ["chunk-1"],
            "documents": ["real vector text"],
            "metadatas": [{"chunk_index": 0}],
        }

    monkeypatch.setattr(
        rag, "ChromaRetriever", lambda: SimpleNamespace(collection=SimpleNamespace(get=get))
    )
    response = context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/chunks")
    assert response.json()["items"][0]["text"] == "real vector text"
    monkeypatch.setattr(rag, "ChromaRetriever", lambda: SimpleNamespace(collection=None))
    assert (
        context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/chunks").status_code == 503
    )


def test_manifest_does_not_imply_review_coverage(context, monkeypatch):
    path = context.corpus / "math" / "vectors.md"
    path.parent.mkdir()
    text = "# Vectors\n\nActual corpus text"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(
        service,
        "_read_manifest",
        lambda: {"documents": {"math/vectors.md": {"document_version": service.digest(text)}}},
    )
    doc = context.client.get("/knowledge-base/admin/documents").json()["items"][0]
    assert doc["index_status"] == "INDEXED"
    assert classify(context, doc["id"]).status_code == 200
    assert service.coverage(context.db, context.subject.id)["covered_points"] == 0
    path.write_text(text + " changed", encoding="utf-8")
    assert service.get_document(context.db, doc["id"])["index_status"] == "STALE"


def test_document_source_filter_and_history_preserve_origin(context):
    doc = upload(context)
    assert classify(context, doc["id"]).status_code == 200
    candidate = context.client.post(f"/knowledge-base/admin/documents/{doc['id']}/candidate").json()
    listed = context.client.get(
        "/knowledge-base/admin/documents", params={"source": "upload://" + doc["id"]}
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["parse_status"] == "EXTRACTED"
    assert listed["items"][0]["created_at"]
    history = context.client.get(f"/knowledge-base/admin/documents/{doc['id']}/history").json()
    assert history["origin"]["operation"] == "IMPORT_DOCUMENT"
    assert history["review"]["status"] == "DRAFT"
    assert any(event["event"] == "knowledge.document.staged" for event in history["events"])
    assert history["versions"] == []
    assert candidate["id"]
