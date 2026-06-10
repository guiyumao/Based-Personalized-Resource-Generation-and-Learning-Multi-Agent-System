"""Simple RAG retriever service backed by Chroma."""

from __future__ import annotations

from typing import Any

from common.config import get_settings


class ChromaRetriever:
    """Retrieve related educational snippets from Chroma."""

    def __init__(self) -> None:
        settings = get_settings()
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
            self.collection = self.client.get_or_create_collection(name="education_resources")
        except ImportError:
            self.client = None
            self.collection = None

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
