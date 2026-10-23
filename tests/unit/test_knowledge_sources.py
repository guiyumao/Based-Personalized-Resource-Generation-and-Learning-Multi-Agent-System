"""Real external source ingestion and the bounded enrichment marker."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.models.learning import KnowledgeBuildTask, User
from services.agent_service.app.services import knowledge_sources


@pytest.fixture
def session(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(User(id=6, username="learner", password_hash="unused", role="student"))
        db.commit()
        yield db
    engine.dispose()


def test_indexer_reads_explicit_knowledge_point_header(tmp_path):
    from scripts.index_resources import _extract_source_metadata

    header = "\n".join([
        "# UDP 用户数据报协议",
        "> 来源: https://example.com/udp",
        "> 来源类型: web_reference",
        "> 授权: external-reference",
        "> 内容哈希: " + "a" * 64,
        "> 学科: computer_networks | 难度: 未标注",
        "> 知识点: UDP",
        "> 知识点ID: 478",
        "",
        "正文",
    ])
    metadata = _extract_source_metadata(header)
    assert metadata["knowledge_point_name"] == "UDP"
    assert metadata["knowledge_point_id"] == "478"
    assert metadata["source_type"] == "web_reference"


def test_store_public_sources_writes_provenance_and_indexes(tmp_path, monkeypatch):
    corpus = tmp_path / "knowledge_base" / "corpus"
    monkeypatch.setattr(knowledge_sources, "CORPUS_DIR", corpus)
    monkeypatch.setattr(knowledge_sources, "KNOWLEDGE_ROOT", tmp_path)
    calls = []
    import services.agent_service.app.services.knowledge_base_admin as admin

    monkeypatch.setattr(admin, "_run_index_command", lambda **kwargs: calls.append(kwargs) or {})

    sources = [{
        "url": "https://example.com/udp-guide",
        "title": "UDP 协议详解",
        "content": "UDP 是无连接传输层协议。" * 40,
    }]
    stored = knowledge_sources.store_public_sources(
        subject_code="computer_networks",
        knowledge_point="UDP",
        knowledge_point_id="478",
        sources=sources,
    )
    assert len(stored) == 1
    path = tmp_path / stored[0]["path"]
    text = path.read_text(encoding="utf-8")
    assert "> 知识点: UDP" in text
    assert "> 知识点ID: 478" in text
    assert "> 来源: https://example.com/udp-guide" in text
    assert calls and calls[0]["subject"] == "computer_networks"

    # The same source is idempotent and does not rewrite or re-index.
    assert knowledge_sources.store_public_sources(
        subject_code="computer_networks",
        knowledge_point="UDP",
        knowledge_point_id="478",
        sources=sources,
    ) == []
    assert len(calls) == 1


def test_ensure_external_sources_is_bounded_by_a_marker(session, monkeypatch):
    monkeypatch.setattr(knowledge_sources, "has_external_sources", lambda *args: False)
    calls = []

    def fake_search(query, *, count, need_content):
        calls.append((query, count, need_content))
        return [{"url": "https://example.com/udp", "title": "UDP", "content": "内容" * 200}]

    import services.agent_service.app.services.deepseek_search as search_module

    monkeypatch.setattr(search_module, "search_sources", fake_search)
    monkeypatch.setattr(
        knowledge_sources,
        "store_public_sources",
        lambda **kwargs: [{"path": "computer_networks/source_x.md", "url": "https://example.com/udp", "title": "UDP"}],
    )

    first = knowledge_sources.ensure_external_sources(
        session,
        actor_user_id=6,
        subject_label="计算机网络",
        subject_code="computer_networks",
        knowledge_point="UDP",
        knowledge_point_id="478",
        allow_web=True,
    )
    assert len(first) == 1 and len(calls) == 1
    assert session.query(KnowledgeBuildTask).filter_by(operation_type="PUBLIC_SOURCE_ENRICH").count() == 1

    # Fresh marker: no second search for the same point.
    second = knowledge_sources.ensure_external_sources(
        session,
        actor_user_id=6,
        subject_label="计算机网络",
        subject_code="computer_networks",
        knowledge_point="UDP",
        knowledge_point_id="478",
        allow_web=True,
    )
    assert second == []
    assert len(calls) == 1


def test_ensure_external_sources_marks_index_failure(session, monkeypatch):
    monkeypatch.setattr(knowledge_sources, "has_external_sources", lambda *args: False)
    calls = []

    def fake_search(query, *, count, need_content):
        calls.append(query)
        return [{"url": "https://example.com/udp", "title": "UDP", "content": "内容" * 200}]

    import services.agent_service.app.services.deepseek_search as search_module

    monkeypatch.setattr(search_module, "search_sources", fake_search)
    def fail_store(**kwargs):
        raise RuntimeError("index down")

    monkeypatch.setattr(knowledge_sources, "store_public_sources", fail_store)

    assert knowledge_sources.ensure_external_sources(
        session,
        actor_user_id=6,
        subject_label="计算机网络",
        subject_code="computer_networks",
        knowledge_point="UDP",
        allow_web=True,
    ) == []
    assert len(calls) == 1
    marker = session.query(KnowledgeBuildTask).filter_by(operation_type="PUBLIC_SOURCE_ENRICH").one()
    assert marker.result_json["stored_count"] == 0
    assert marker.result_json["error"] == "RuntimeError"

    # The failure marker bounds retries just like a successful import.
    assert knowledge_sources.ensure_external_sources(
        session,
        actor_user_id=6,
        subject_label="计算机网络",
        subject_code="computer_networks",
        knowledge_point="UDP",
        allow_web=True,
    ) == []
    assert len(calls) == 1


def test_ensure_external_sources_respects_web_flag_and_existing_index(session, monkeypatch):
    monkeypatch.setattr(knowledge_sources, "has_external_sources", lambda *args: False)
    assert knowledge_sources.ensure_external_sources(
        session,
        actor_user_id=6,
        subject_label="计算机网络",
        subject_code="computer_networks",
        knowledge_point="UDP",
        allow_web=False,
    ) == []

    monkeypatch.setattr(knowledge_sources, "has_external_sources", lambda *args: True)
    assert knowledge_sources.ensure_external_sources(
        session,
        actor_user_id=6,
        subject_label="计算机网络",
        subject_code="computer_networks",
        knowledge_point="UDP",
        allow_web=True,
    ) == []
