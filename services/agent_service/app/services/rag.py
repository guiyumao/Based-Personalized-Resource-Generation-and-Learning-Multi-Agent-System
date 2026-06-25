"""Simple RAG retriever service backed by Chroma."""

from __future__ import annotations

import json

from typing import Any

from common.config import Settings, get_settings


class ChromaRetriever:
    """Retrieve related educational snippets from Chroma."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=self.settings.chroma_persist_directory)
            self.collection = self.client.get_or_create_collection(name="education_resources")
        except ImportError:
            self.client = None
            self.collection = None

    @property
    def is_available(self) -> bool:
        return self.collection is not None

    def upsert_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert or update retriever documents."""

        if self.collection is None:
            return
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Fetch the most relevant snippets for a query."""

        if self.collection is None:
            _ = query, top_k
            return []
        results = self.collection.query(query_texts=[query], n_results=top_k)
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        return [
            {"id": doc_id, "content": content, "metadata": metadata}
            for doc_id, content, metadata in zip(ids, documents, metadatas, strict=False)
        ]

    def retrieve_with_metadata(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Retrieve snippets with full metadata including distance scores."""
        if self.collection is None:
            return []
        results = self.collection.query(query_texts=[query], n_results=top_k)
        ids_list = results.get("ids", [[]])[0]
        docs_list = results.get("documents", [[]])[0]
        metas_list = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if "distances" in results else [None] * len(ids_list)

        output: list[dict[str, Any]] = []
        for i in range(len(ids_list)):
            meta = metas_list[i] if i < len(metas_list) else {}
            tags_raw = meta.get("tags", "[]") if isinstance(meta, dict) else "[]"
            try:
                tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
            except (json.JSONDecodeError, TypeError):
                tags = []
            output.append({
                "id": ids_list[i],
                "content": docs_list[i] if i < len(docs_list) else "",
                "metadata": meta,
                "tags": tags if isinstance(tags, list) else [],
                "distance": distances[i] if i < len(distances) else None,
            })
        return output

    def retrieve_by_tags(self, tags: list[str], query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Retrieve snippets matching at least one of the given tags, then rank by query similarity."""
        all_results = self.retrieve_with_metadata(query, top_k=max(top_k * 3, 15))
        if not tags:
            return all_results[:top_k]

        filtered = [
            r for r in all_results
            if any(t in r.get("tags", []) for t in tags)
        ]
        return filtered[:top_k] if filtered else all_results[:top_k]

    def retrieve_context_text(self, query: str, tags: list[str] | None = None, top_k: int = 3) -> str:
        """Convenience: return retrieved content as a single formatted string for LLM prompt injection."""
        if tags:
            results = self.retrieve_by_tags(tags, query, top_k=top_k)
        else:
            results = self.retrieve_with_metadata(query, top_k=top_k)

        if not results:
            return ""

        lines = ["【参考学习资料】"]
        for i, r in enumerate(results, 1):
            src = r.get("metadata", {}).get("title", "未知来源") if isinstance(r.get("metadata"), dict) else "未知来源"
            content = r.get("content", "")[:600]
            lines.append(f"\n--- 参考 {i}: {src} ---\n{content}")
        return "\n".join(lines)
