"""Versioned Chroma retrieval with metadata filtering and safe reuse."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
import uuid
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from common.config import Settings, get_settings
from common.performance import get_current_trace, traced_invoke

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalContext:
    """Reusable retrieval result scoped to one knowledge and teaching context."""

    context_id: str
    query: str
    knowledge_point_id: str
    scope_id: str
    knowledge_base_version: str
    retrieved_chunks: list[dict[str, Any]]
    source_ids: list[str]
    created_at: str
    expire_at: str
    filters: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class _RetrievalCache:
    """Small process-local TTL cache; entries never mix public and private scopes."""

    def __init__(self) -> None:
        self._entries: OrderedDict[
            str, tuple[float, int, list[dict[str, Any]]]
        ] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str, *, min_results: int) -> list[dict[str, Any]] | None:
        now = time.monotonic()
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                return None
            expire_at, fetched_count, value = item
            if expire_at <= now:
                self._entries.pop(key, None)
                return None
            if fetched_count < min_results:
                return None
            self._entries.move_to_end(key)
            return deepcopy(value[:min_results])

    def put(
        self,
        key: str,
        value: list[dict[str, Any]],
        *,
        fetched_count: int,
        ttl_seconds: int,
        max_entries: int,
    ) -> None:
        with self._lock:
            self._entries[key] = (
                time.monotonic() + max(1, ttl_seconds),
                max(0, fetched_count),
                deepcopy(value),
            )
            self._entries.move_to_end(key)
            while len(self._entries) > max(1, max_entries):
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_RETRIEVAL_CACHE = _RetrievalCache()


def _normalize_query(query: str) -> str:
    """Normalize equivalent user queries so they share embeddings and cache entries."""

    normalized = unicodedata.normalize("NFKC", query)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


def _lexical_tokens(query: str) -> set[str]:
    stop_words = {
        "什么", "怎么", "如何", "为什么", "解释", "生成", "课件", "作用",
        "区别", "关系", "适合", "问题", "这个", "那个", "刚才", "例子",
        "不同", "怎样", "用来", "干什么",
    }
    tokens: set[str] = set()
    for raw in re.findall(r"[a-z0-9_+#.]{2,}|[\u4e00-\u9fff]{2,}", query.casefold()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", raw):
            meaningful = raw
            for stop_word in sorted(stop_words, key=len, reverse=True):
                meaningful = meaningful.replace(stop_word, " ")
            for part in re.split(r"[的了呢吗和与及是有在为]", meaningful):
                if len(part) > 4:
                    tokens.update(part[index:index + 2] for index in range(len(part) - 1))
                elif len(part) >= 2:
                    tokens.add(part)
        elif raw not in stop_words:
            tokens.add(raw)
    return {token for token in tokens if token and token not in stop_words}


class _LexicalIndex:
    """Small in-process exact-match index used before expensive query embedding."""

    def __init__(self) -> None:
        self._collection_id = 0
        self._generation = ""
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._collection_id = 0
            self._entries = []

    def _ensure(self, collection: Any, generation: str = "") -> None:
        collection_id = id(collection)
        with self._lock:
            if self._collection_id == collection_id and self._generation == generation and self._entries:
                return
            # Chroma caps ``get`` at 100 rows by default. Without pagination the
            # index only ever saw the oldest chunks, so every document published
            # later was invisible to the fast path even though it was indexed
            # correctly -- planning then reported it as missing.
            payload: dict[str, Any] = {"ids": [], "documents": [], "metadatas": []}
            page_size = 500
            offset = 0
            while True:
                page = collection.get(
                    include=["documents", "metadatas"], limit=page_size, offset=offset
                )
                page_ids = page.get("ids", []) or []
                if not page_ids:
                    break
                payload["ids"].extend(page_ids)
                payload["documents"].extend(page.get("documents", []) or [])
                payload["metadatas"].extend(page.get("metadatas", []) or [])
                if len(page_ids) < page_size:
                    break
                offset += page_size
            ids = payload.get("ids", []) or []
            documents = payload.get("documents", []) or []
            metadatas = payload.get("metadatas", []) or []
            entries: list[dict[str, Any]] = []
            for index, doc_id in enumerate(ids):
                content = str(documents[index] if index < len(documents) else "")
                metadata = metadatas[index] if index < len(metadatas) else {}
                metadata = metadata if isinstance(metadata, dict) else {}
                metadata_text = " ".join(
                    str(metadata.get(key) or "")
                    for key in ("title", "subject", "chapter", "knowledge_point_name", "tags")
                )
                entries.append({
                    "id": str(doc_id),
                    "content": content,
                    "metadata": metadata,
                    "content_text": _normalize_query(content),
                    "metadata_text": _normalize_query(metadata_text),
                })
            self._collection_id = collection_id
            self._generation = generation
            self._entries = entries

    def search(
        self,
        collection: Any,
        query: str,
        *,
        top_k: int,
        filters: dict[str, Any] | None,
        min_score: float,
        generation: str = "",
    ) -> list[dict[str, Any]]:
        self._ensure(collection, generation)
        tokens = _lexical_tokens(query)
        if not tokens:
            return []
        normalized_filters = _normalize_filters(filters)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for entry in self._entries:
            metadata = entry["metadata"]
            if any(metadata.get(key) != value for key, value in normalized_filters.items()):
                continue
            content_text = entry["content_text"]
            metadata_text = entry["metadata_text"]
            content_matched = sum(1 for token in tokens if token in content_text)
            metadata_matched = sum(1 for token in tokens if token in metadata_text)
            if not content_matched and not metadata_matched:
                continue
            content_coverage = content_matched / len(tokens)
            metadata_coverage = metadata_matched / len(tokens)
            phrase_bonus = 0.15 if _normalize_query(query) in content_text else 0.0
            # Metadata identifies the right document but must not make every
            # chunk in that document appear equally relevant.
            score = min(1.0, content_coverage + phrase_bonus + 0.1 * metadata_coverage)
            if not content_matched:
                score = 0.45 * metadata_coverage
            if score < min_score:
                continue
            ranked.append((score, entry))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked:
            return []
        best_score = ranked[0][0]
        if best_score < max(min_score, 0.8) and len(ranked) < 2:
            return []
        output: list[dict[str, Any]] = []
        for score, entry in ranked[:top_k]:
            tags_raw = entry["metadata"].get("tags", "[]")
            try:
                tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
            except (json.JSONDecodeError, TypeError):
                tags = []
            output.append({
                "id": entry["id"],
                "content": entry["content"],
                "metadata": entry["metadata"],
                "tags": tags if isinstance(tags, list) else [],
                "distance": round(1.0 - score, 6),
                "retrieval_strategy": "lexical_fast_path",
            })
        return output


_LEXICAL_INDEX = _LexicalIndex()


def _assert_chroma_host_is_trusted(host: str) -> None:
    """Refuse to talk to a Chroma server outside the trusted internal network.

    Chroma 0.5.x exposes its API — including collection administration — without
    authentication, so pointing this service at a remote/public Chroma instance
    would let anyone who can reach that port create, read or drop collections.
    The host must therefore be a loopback address, a private-network address, or
    a bare service name on the compose network.

    Set ``CHROMA_ALLOW_REMOTE_HOST=true`` only when the remote endpoint has its own
    authentication layer in front of it.
    """

    settings = get_settings()
    if getattr(settings, "chroma_allow_remote_host", False):
        return

    candidate = (host or "").strip().lower()
    if not candidate:
        raise ValueError("CHROMA_HOST must not be empty when CHROMA_MODE=http")

    # Service names on a container network (e.g. "chroma") and loopback aliases.
    if candidate in {"localhost", "127.0.0.1", "::1", "chroma"}:
        return
    # Bare name without a dot: resolved inside the compose network only.
    if "." not in candidate and not candidate.replace(".", "").isdigit():
        return

    try:
        import ipaddress

        address = ipaddress.ip_address(candidate)
    except ValueError:
        # A dotted hostname (e.g. chroma.internal or an external FQDN). Only bare
        # service names are trusted, since those resolve inside the compose network.
        raise ValueError(
            f"CHROMA_HOST '{host}' is not a loopback or internal service name. "
            "Chroma has no built-in authentication; set CHROMA_ALLOW_REMOTE_HOST=true "
            "only behind an authenticated proxy."
        ) from None

    if address.is_loopback or address.is_link_local:
        return

    # Explicit RFC1918 / CGNAT allow-list. ``ipaddress.is_private`` is not used
    # because it also classifies documentation ranges such as 203.0.113.0/24 as
    # private, which would let a non-routable-looking but untrusted address pass.
    trusted_networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("fc00::/7"),
    )
    if any(address in network for network in trusted_networks):
        return

    raise ValueError(
        f"CHROMA_HOST '{host}' is not a loopback, private-network, or internal service "
        "address. Refusing to connect to an unauthenticated Chroma instance; set "
        "CHROMA_ALLOW_REMOTE_HOST=true only behind an authenticated proxy."
    )


def _settings_identity(settings: Settings) -> tuple[Any, ...]:
    return (
        settings.chroma_mode,
        settings.chroma_persist_directory,
        settings.chroma_host,
        settings.chroma_port,
        settings.chroma_ssl,
        settings.chroma_collection_name,
        settings.chroma_collection_version,
    )


def _manifest_revision(settings: Settings) -> str:
    from common.knowledge_paths import KNOWLEDGE_ROOT
    path = (Path(settings.chroma_persist_directory) / "index_manifest.json" if settings.chroma_mode == "persistent"
            else KNOWLEDGE_ROOT / ".cache" / f"chroma-index-{settings.chroma_collection_name}.json")
    try:
        stat = path.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return ""


@lru_cache(maxsize=8)
def _create_collection(identity: tuple[Any, ...]) -> tuple[Any | None, Any | None]:
    mode, persist_directory, host, port, ssl, collection_name, collection_version = identity
    try:
        import chromadb
    except ImportError:
        LOGGER.warning("Chroma is unavailable because chromadb is not installed")
        return None, None

    if mode == "http":
        _assert_chroma_host_is_trusted(host)
        client = chromadb.HttpClient(host=host, port=int(port), ssl=bool(ssl))
    elif mode == "persistent":
        client = chromadb.PersistentClient(path=persist_directory)
    else:
        raise ValueError("CHROMA_MODE must be either 'persistent' or 'http'")

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"collection_version": collection_version},
    )
    LOGGER.info(
        "knowledge_base_config mode=%s collection=%s collection_version=%s location=%s",
        mode,
        collection_name,
        collection_version,
        f"{host}:{port}" if mode == "http" else persist_directory,
    )
    return client, collection


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, str | int | float | bool]:
    if not filters:
        return {}
    allowed = {
        "source_id", "document_id", "subject", "grade", "chapter", "section",
        "knowledge_point_id", "knowledge_point_name", "teacher_scope", "version",
        "source", "source_site", "source_type", "university", "course", "difficulty",
        "language", "license",
        # Personal AI-draft namespace (P0-4). Public retrieval never sends these,
        # and ``visible_chunks`` drops ``scope=personal_draft`` fail-closed.
        "owner_user_id", "scope",
    }
    return {
        key: value
        for key, value in filters.items()
        if key in allowed and value not in (None, "", []) and isinstance(value, (str, int, float, bool))
    }


def _build_where(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized = _normalize_filters(filters)
    if not normalized:
        return None
    expressions = [{key: {"$eq": value}} for key, value in sorted(normalized.items())]
    return expressions[0] if len(expressions) == 1 else {"$and": expressions}


class ChromaRetriever:
    """Retrieve educational snippets from one explicitly configured Chroma store."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client, self.collection = _create_collection(_settings_identity(self.settings))

    @property
    def is_available(self) -> bool:
        return self.collection is not None

    def describe(self) -> dict[str, Any]:
        return {
            "mode": self.settings.chroma_mode,
            "collection": self.settings.chroma_collection_name,
            "collection_version": self.settings.chroma_collection_version,
            "embedding_model_version": self.settings.embedding_model_version,
            "knowledge_base_version": self.settings.knowledge_base_version,
            "corpus_version": self.settings.corpus_version,
        }

    def should_rewrite_query(self, query: str) -> bool:
        """Detect genuinely ambiguous queries without an extra model call."""

        compact = re.sub(r"\s+", "", query)
        if len(compact) < 4:
            return True
        pronouns = ("这个", "它", "那个", "上面", "刚才", "这部分")
        has_pronoun = any(item in compact for item in pronouns)
        concrete_tokens = re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}", compact)
        return has_pronoun and len(concrete_tokens) <= 1

    def rewrite_query(self, query: str, *, context_hint: str = "") -> str:
        """Rewrite only ambiguous queries, using the configured auxiliary model."""

        if not self.should_rewrite_query(query):
            return query
        try:
            from services.agent_service.app.services.llm_factory import LLMFactory

            llm = LLMFactory(self.settings).build_for_task("rewrite", temperature=0.0)
            result = traced_invoke(
                llm,
                [
                    {
                        "role": "system",
                        "content": "将模糊问题改写为不超过 40 字的知识库检索词，只输出检索词。",
                    },
                    {
                        "role": "user",
                        "content": f"原问题：{query}\n上下文：{context_hint[:300]}",
                    },
                ],
                stage="query_rewrite",
            )
            rewritten = str(getattr(result, "content", result)).strip().splitlines()[0][:80]
            return rewritten or query
        except Exception:
            return query

    def should_rerank(self, results: list[dict[str, Any]], *, mode: str) -> bool:
        if len(results) < 2 or mode == "fast":
            return False
        if mode == "quality":
            return True
        first = results[0].get("distance")
        second = results[1].get("distance")
        if not isinstance(first, (int, float)) or not isinstance(second, (int, float)):
            return False
        return abs(float(second) - float(first)) <= self.settings.rag_score_ambiguity_threshold

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        *,
        limit: int,
        mode: str,
    ) -> list[dict[str, Any]]:
        """Apply a cheap lexical/metadata rerank only when scores are ambiguous."""

        if not self.should_rerank(results, mode=mode):
            return results[:limit]
        started = time.perf_counter()
        query_tokens = {
            token.casefold()
            for token in re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query)
        }

        def score(item: dict[str, Any]) -> float:
            content = str(item.get("content") or "").casefold()
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            metadata_text = " ".join(
                str(metadata.get(key) or "")
                for key in ("title", "subject", "chapter", "knowledge_point_name", "tags")
            ).casefold()
            matches = sum(1 for token in query_tokens if token in content or token in metadata_text)
            lexical = matches / max(1, len(query_tokens))
            distance = item.get("distance")
            vector = 1.0 / (1.0 + max(0.0, float(distance))) if isinstance(distance, (int, float)) else 0.0
            return (vector * 0.75) + (lexical * 0.25)

        ranked = sorted(results, key=score, reverse=True)[:limit]
        trace = get_current_trace()
        if trace is not None:
            trace.add_stage("rerank", (time.perf_counter() - started) * 1000)
        return ranked

    def upsert_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if self.collection is None:
            return
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        _RETRIEVAL_CACHE.clear()
        _LEXICAL_INDEX.clear()

    def delete_documents(self, ids: list[str]) -> None:
        if self.collection is None or not ids:
            return
        self.collection.delete(ids=ids)
        _RETRIEVAL_CACHE.clear()
        _LEXICAL_INDEX.clear()

    def _cache_key(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None,
        cache_scope: str,
        user_id: int | str | None,
        retrieval_mode: str,
    ) -> str:
        if cache_scope not in {"public", "private"}:
            raise ValueError("cache_scope must be 'public' or 'private'")
        if cache_scope == "private" and user_id is None:
            raise ValueError("private retrieval cache requires user_id")
        payload = {
            "store_identity": _settings_identity(self.settings),
            "manifest_revision": _manifest_revision(self.settings),
            "query_hash": hashlib.sha256(_normalize_query(query).encode("utf-8")).hexdigest(),
            "filters": _normalize_filters(filters),
            "scope": cache_scope,
            "user_id": str(user_id) if cache_scope == "private" else "",
            "collection": self.settings.chroma_collection_name,
            "collection_version": self.settings.chroma_collection_version,
            "corpus_version": self.settings.corpus_version,
            "embedding_model_version": self.settings.embedding_model_version,
            "retrieval_config_version": self.settings.retrieval_config_version,
            "retrieval_mode": retrieval_mode,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def retrieve_with_metadata(
        self, query: str, top_k: int | None = None, **kwargs,
    ) -> list[dict[str, Any]]:
        from services.agent_service.app.services.knowledge_publication import visible_chunks
        return visible_chunks(self._retrieve_with_metadata_unchecked(query, top_k, **kwargs))

    def _retrieve_with_metadata_unchecked(
        self,
        query: str,
        top_k: int | None = None,
        *,
        filters: dict[str, Any] | None = None,
        cache_scope: str = "public",
        user_id: int | str | None = None,
        retrieval_mode: str = "hybrid",
    ) -> list[dict[str, Any]]:
        """Retrieve snippets using a metadata pre-filter and a versioned cache."""

        normalized_query = _normalize_query(query)
        if self.collection is None or not normalized_query:
            return []
        if retrieval_mode not in {"hybrid", "lexical", "vector"}:
            raise ValueError("retrieval_mode must be 'hybrid', 'lexical', or 'vector'")
        candidate_count = max(1, top_k or self.settings.rag_retrieval_top_k)
        cache_key = self._cache_key(
            query=normalized_query, top_k=candidate_count, filters=filters,
            cache_scope=cache_scope, user_id=user_id, retrieval_mode=retrieval_mode,
        )
        trace = get_current_trace()
        cached = _RETRIEVAL_CACHE.get(cache_key, min_results=candidate_count)
        if cached is not None:
            if trace is not None:
                trace.record_retrieval(len(cached), cache_hit=True, cache_type=f"retrieval_{cache_scope}")
            return cached

        if retrieval_mode != "vector" and self.settings.rag_lexical_fast_path:
            lexical_started = time.perf_counter()
            lexical_results = _LEXICAL_INDEX.search(
                self.collection,
                normalized_query,
                top_k=candidate_count,
                filters=filters,
                min_score=self.settings.rag_lexical_min_score,
                generation=_manifest_revision(self.settings),
            )
            if lexical_results:
                elapsed_ms = (time.perf_counter() - lexical_started) * 1000
                _RETRIEVAL_CACHE.put(
                    cache_key,
                    lexical_results,
                    fetched_count=candidate_count,
                    ttl_seconds=self.settings.rag_cache_ttl_seconds,
                    max_entries=self.settings.rag_cache_max_entries,
                )
                if trace is not None:
                    trace.add_stage("lexical_search", elapsed_ms)
                    trace.attributes["retrieval_strategy"] = "lexical_fast_path"
                    trace.record_retrieval(len(lexical_results))
                return lexical_results
            if retrieval_mode == "lexical":
                return []

        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "query_texts": [normalized_query],
            "n_results": candidate_count,
            "include": ["documents", "metadatas", "distances"],
        }
        where = _build_where(filters)
        if where is not None:
            kwargs["where"] = where
        results = self.collection.query(**kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if trace is not None:
            trace.add_stage("vector_search", elapsed_ms)
            trace.attributes["embedding_measurement"] = "included_in_vector_search"

        ids_list = results.get("ids", [[]])[0]
        docs_list = results.get("documents", [[]])[0]
        metas_list = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        output: list[dict[str, Any]] = []
        for index, doc_id in enumerate(ids_list):
            meta = metas_list[index] if index < len(metas_list) and metas_list[index] else {}
            tags_raw = meta.get("tags", "[]") if isinstance(meta, dict) else "[]"
            try:
                tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
            except (json.JSONDecodeError, TypeError):
                tags = []
            output.append({
                "id": doc_id,
                "content": docs_list[index] if index < len(docs_list) else "",
                "metadata": meta,
                "tags": tags if isinstance(tags, list) else [],
                "distance": distances[index] if index < len(distances) else None,
                "retrieval_strategy": "vector",
            })

        _RETRIEVAL_CACHE.put(
            cache_key, output,
            fetched_count=candidate_count,
            ttl_seconds=self.settings.rag_cache_ttl_seconds,
            max_entries=self.settings.rag_cache_max_entries,
        )
        if trace is not None:
            trace.record_retrieval(len(output))
            trace.attributes["retrieval_strategy"] = "vector"
        return output

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        *,
        filters: dict[str, Any] | None = None,
        cache_scope: str = "public",
        user_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return self.retrieve_with_metadata(
            query, top_k, filters=filters, cache_scope=cache_scope, user_id=user_id,
        )

    def retrieve_personal(
        self,
        user_id: int | str,
        query: str,
        *,
        subject: str = "",
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        """Retrieve only this learner's own personal AI-draft chunks (P0-4).

        Owner-scoped at the store layer and intentionally bypasses the public
        ``visible_chunks`` gate (which fail-closes ``scope=personal_draft``), so a
        personal draft is reusable by its owner but never leaks into public
        retrieval.
        """
        filters: dict[str, Any] = {"owner_user_id": str(user_id), "scope": "personal_draft"}
        if subject:
            filters["subject"] = subject
        return self._retrieve_with_metadata_unchecked(
            query, top_k, filters=filters, cache_scope="private", user_id=user_id,
        )

    def retrieve_by_tags(
        self,
        tags: list[str],
        query: str,
        top_k: int = 5,
        *,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        all_results = self.retrieve_with_metadata(query, top_k=max(top_k * 3, 15), filters=filters)
        if not tags:
            return all_results[:top_k]
        filtered = [result for result in all_results if any(tag in result.get("tags", []) for tag in tags)]
        return filtered[:top_k] if filtered else all_results[:top_k]

    def build_context(
        self,
        query: str,
        *,
        knowledge_point_id: str = "",
        scope_id: str = "public",
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
        user_id: int | str | None = None,
        private: bool = False,
    ) -> RetrievalContext:
        normalized_filters = _normalize_filters(filters)
        chunks = self.retrieve_with_metadata(
            query, top_k=top_k, filters=normalized_filters,
            cache_scope="private" if private else "public", user_id=user_id,
        )
        now = datetime.now(UTC)
        return RetrievalContext(
            context_id=uuid.uuid4().hex,
            query=query,
            knowledge_point_id=knowledge_point_id,
            scope_id=scope_id,
            knowledge_base_version=self.settings.knowledge_base_version,
            retrieved_chunks=chunks,
            source_ids=[str(item.get("id", "")) for item in chunks if item.get("id")],
            created_at=now.isoformat(),
            expire_at=(now + timedelta(seconds=self.settings.rag_cache_ttl_seconds)).isoformat(),
            filters=normalized_filters,
        )

    def retrieve_context_text(
        self,
        query: str,
        tags: list[str] | None = None,
        top_k: int = 3,
        *,
        filters: dict[str, Any] | None = None,
    ) -> str:
        if tags:
            results = self.retrieve_by_tags(tags, query, top_k=top_k, filters=filters)
        else:
            results = self.retrieve_with_metadata(query, top_k=top_k, filters=filters)
        if not results:
            return ""
        lines = ["【参考学习资料】"]
        for index, result in enumerate(results, 1):
            metadata = result.get("metadata", {})
            source = metadata.get("title", "未知来源") if isinstance(metadata, dict) else "未知来源"
            lines.append(f"\n--- 参考 {index}: {source} ---\n{result.get('content', '')[:600]}")
        text = "\n".join(lines)
        trace = get_current_trace()
        if trace is not None:
            trace.record_context(text)
        return text


def clear_retrieval_runtime_caches() -> None:
    """Test/maintenance hook for clearing in-process clients and retrieval data."""

    _RETRIEVAL_CACHE.clear()
    _LEXICAL_INDEX.clear()
    _create_collection.cache_clear()
