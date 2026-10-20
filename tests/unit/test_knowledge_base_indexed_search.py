from __future__ import annotations

import json

from services.agent_service.app.services import rag
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService


class FakeRetriever:
    is_available = True

    def retrieve_with_metadata(
        self,
        query: str,
        *,
        top_k: int,
        filters=None,
        retrieval_mode: str = "hybrid",
    ):
        assert query == "装饰器的作用"
        assert top_k >= 5
        assert filters is None
        assert retrieval_mode == "hybrid"
        return [
            {
                "id": "chunk-1",
                "content": (
                    "# Python 装饰器\n\n"
                    "> 来源: https://docs.python.org/zh-cn/3/reference/compound_stmts.html\n\n"
                    "装饰器可以包装函数并增强行为。"
                ),
                "metadata": {
                    "source_id": "doc-1",
                    "source": "python/Python装饰器与异步函数.md",
                    "title": "Python装饰器与异步函数",
                    "subject": "python",
                    "tags": json.dumps(["Python", "装饰器", "进阶"], ensure_ascii=False),
                },
                "retrieval_strategy": "lexical_fast_path",
            }
        ]


def test_indexed_search_adapts_rag_result_for_existing_ui(monkeypatch) -> None:
    monkeypatch.setattr(rag, "ChromaRetriever", FakeRetriever)

    items = KnowledgeBaseService().search_indexed("装饰器的作用", top_k=5)

    assert items[0]["id"] == "indexed-doc-1"
    assert items[0]["title"] == "Python装饰器与异步函数"
    assert items[0]["subject"] == "Python"
    assert items[0]["retrieval_strategy"] == "lexical_fast_path"
    assert items[0]["external_resources"][0]["url"].startswith("https://docs.python.org/")


def test_core_subject_filter_does_not_leak_related_curated_articles() -> None:
    service = KnowledgeBaseService()

    operating_system_items = service.search(
        "操作系统",
        subject="operating_systems",
        top_k=10,
    )
    architecture_items = service.search(
        "计算机组成原理",
        subject="computer_architecture",
        top_k=10,
    )

    assert operating_system_items == []
    assert [item.title for item in architecture_items] == ["计算机组成原理"]
