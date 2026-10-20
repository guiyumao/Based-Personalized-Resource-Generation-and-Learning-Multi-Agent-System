from __future__ import annotations

import json
from dataclasses import replace

import pytest

from common.config import get_settings
from common.performance import PerformanceTrace
from services.agent_service.app.services.rag import (
    ChromaRetriever,
    _build_where,
    clear_retrieval_runtime_caches,
)


class FakeCollection:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "ids": [["chunk-1"]],
            "documents": [["极限的定义与计算"]],
            "metadatas": [[{"subject": "math", "chapter": "第二章", "tags": json.dumps(["极限"])}]],
            "distances": [[0.1]],
        }


class FakeHybridCollection(FakeCollection):
    def get(self, **kwargs):
        return {
            "ids": ["python-list-1"],
            "documents": ["列表推导式可以用一行表达式创建列表。"],
            "metadatas": [{"subject": "python", "title": "Python 列表推导式", "tags": "[]"}],
        }


class FakeTitleNoiseCollection(FakeCollection):
    def get(self, **kwargs):
        return {
            "ids": ["noise", "relevant"],
            "documents": ["异常捕获使用 try 和 except。", "装饰器可以包装函数并增强行为。"],
            "metadatas": [
                {"subject": "python", "title": "Python 装饰器与异步函数", "tags": "[]"},
                {"subject": "python", "title": "Python 装饰器与异步函数", "tags": "[]"},
            ],
        }


def build_retriever() -> tuple[ChromaRetriever, FakeCollection]:
    settings = replace(
        get_settings(),
        rag_cache_ttl_seconds=60,
        rag_cache_max_entries=10,
        rag_lexical_fast_path=False,
    )
    retriever = ChromaRetriever.__new__(ChromaRetriever)
    retriever.settings = settings
    retriever.client = object()
    collection = FakeCollection()
    retriever.collection = collection
    return retriever, collection


def test_metadata_filter_is_applied_before_vector_search() -> None:
    clear_retrieval_runtime_caches()
    retriever, collection = build_retriever()
    retriever.retrieve_with_metadata(
        "极限", filters={"subject": "math", "chapter": "第二章", "ignored": "x"}
    )
    assert collection.calls[0]["where"] == {
        "$and": [
            {"chapter": {"$eq": "第二章"}},
            {"subject": {"$eq": "math"}},
        ]
    }


def test_private_retrieval_cache_is_isolated_by_user() -> None:
    clear_retrieval_runtime_caches()
    retriever, collection = build_retriever()
    retriever.retrieve_with_metadata("极限", cache_scope="private", user_id=1)
    retriever.retrieve_with_metadata("极限", cache_scope="private", user_id=1)
    retriever.retrieve_with_metadata("极限", cache_scope="private", user_id=2)
    assert len(collection.calls) == 2


def test_normalized_query_and_larger_result_cache_are_reused() -> None:
    clear_retrieval_runtime_caches()
    retriever, collection = build_retriever()
    retriever.retrieve_with_metadata("Python   LIST", top_k=10)
    retriever.retrieve_with_metadata("python list", top_k=3)
    assert len(collection.calls) == 1


def test_lexical_fast_path_skips_expensive_vector_embedding() -> None:
    clear_retrieval_runtime_caches()
    settings = replace(
        get_settings(),
        rag_lexical_fast_path=True,
        rag_lexical_min_score=0.58,
    )
    retriever = ChromaRetriever.__new__(ChromaRetriever)
    retriever.settings = settings
    retriever.client = object()
    collection = FakeHybridCollection()
    retriever.collection = collection
    results = retriever.retrieve_with_metadata(
        "列表推导式", top_k=5, filters={"subject": "python"}
    )
    assert results[0]["retrieval_strategy"] == "lexical_fast_path"
    assert collection.calls == []


def test_lexical_fast_path_prefers_chunk_content_over_document_title() -> None:
    clear_retrieval_runtime_caches()
    settings = replace(
        get_settings(),
        rag_lexical_fast_path=True,
        rag_lexical_min_score=0.58,
    )
    retriever = ChromaRetriever.__new__(ChromaRetriever)
    retriever.settings = settings
    retriever.client = object()
    retriever.collection = FakeTitleNoiseCollection()

    results = retriever.retrieve_with_metadata(
        "装饰器的作用", top_k=5, filters={"subject": "python"}
    )

    assert results[0]["id"] == "relevant"
    assert all(item["id"] != "noise" for item in results)


def test_vector_mode_bypasses_lexical_fast_path() -> None:
    clear_retrieval_runtime_caches()
    settings = replace(
        get_settings(),
        rag_lexical_fast_path=True,
        rag_lexical_min_score=0.58,
    )
    retriever = ChromaRetriever.__new__(ChromaRetriever)
    retriever.settings = settings
    retriever.client = object()
    collection = FakeHybridCollection()
    retriever.collection = collection

    results = retriever.retrieve_with_metadata(
        "列表推导式",
        top_k=5,
        filters={"subject": "python"},
        retrieval_mode="vector",
    )

    assert len(collection.calls) == 1
    assert results[0]["retrieval_strategy"] == "vector"


def test_private_cache_requires_user_id() -> None:
    retriever, _ = build_retriever()
    with pytest.raises(ValueError, match="requires user_id"):
        retriever.retrieve_with_metadata("极限", cache_scope="private")


def test_explicit_query_does_not_trigger_rewrite() -> None:
    retriever, _ = build_retriever()
    assert retriever.should_rewrite_query("生成函数单调性的课件") is False
    assert retriever.should_rewrite_query("解释二元关系传递性") is False
    assert retriever.should_rewrite_query("这个") is True


def test_trace_keeps_no_deadline_distinct_from_zero() -> None:
    trace = PerformanceTrace()
    payload = trace.to_dict()
    assert payload["remaining_ms"] is None
    trace.set_context(deadline_seconds=10)
    assert float(trace.to_dict()["remaining_ms"]) > 0


def test_build_where_ignores_empty_and_unknown_fields() -> None:
    assert _build_where({"subject": "math", "grade": "", "token": "secret"}) == {
        "subject": {"$eq": "math"}
    }
    assert _build_where({"university": "MIT", "course": "6.006"}) == {
        "$and": [
            {"course": {"$eq": "6.006"}},
            {"university": {"$eq": "MIT"}},
        ]
    }
