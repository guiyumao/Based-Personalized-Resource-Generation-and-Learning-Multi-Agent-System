"""Neo4j connector and graph-building helpers for knowledge visualization.

Performance contract (DEF-012)
------------------------------
``get_visualization_graph`` never calls the LLM on the request path. It merges the
available *deterministic* sources (Neo4j relations, SQL relations, stored
public courseware content) and returns without scheduling model work. Historical
Neo4j records lack ownership/review provenance and are excluded from public reads.
Explicit enrichment uses the durable knowledge construction/review pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import queue
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import or_

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import KnowledgePoint, KnowledgeRelation, Resource
from common.ttl_cache import TTLCache
from services.agent_service.app.services.knowledge_base import (
    KnowledgeBaseService,
)
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.web_search_service import WebSearchService

logger = logging.getLogger(__name__)

_GRAPH_LLM_PROMPT = """你是知识图谱助手。给定知识点名称和课件全文，提取有意义的前置知识点和后续推荐知识点。

**提取规则：**
- 前置知识（prereqs）：课件中 ## 课程导入、## 你的当前学习情况、## 学习目标 段落暗示的"学生应已掌握"的背景知识。每个必须是 5~25 字完整名词短语，如"变量与数据类型""Python 基础语法""二叉树的定义"。
- 后续推荐（recs）：课件中 ## 拓展延伸、## 学完后自测 段落指向的下一步学习主题。每个必须是 5~25 字完整名词短语，如"面向对象编程""动态规划算法"。
- 不要输出课件标题本身。
- 不要输出"概念""函数""循环""编程"这种 1~3 个字的泛词。
- 如果确实没有，返回空列表。

输出严格 JSON：
{{"prereqs": ["完整知识点1"], "recs": ["完整知识点2"]}}

知识点名称：{kp}
课件全文（仅供提取参考）：
{courseware}"""


_CW_EXTRACT_PROMPT = """从下面课件内容提取有意义的前置知识和推荐后续知识。

当前知识点：{kp}
课件：
{courseware}

严格 JSON：{{"prereqs": ["前置知识点", ...], "recs": ["推荐知识点", ...]}}
每个知识点 5~25 字完整名词，没有则空列表。"""


class KnowledgeGraphRepository:
    _SECTION_ALIASES = {
        "prerequisite": ("前置知识", "前置基础", "基础知识", "预备知识"),
        "recommended": ("后续模块", "进阶内容", "拓展学习", "拓展延伸", "延伸学习", "相关知识"),
        "resource": ("学习资源", "关联资源", "推荐资源", "练习建议"),
    }
    _STOP_LABELS = {
        "以",
        "它",
        "概念",
        "主题",
        "摘要",
        "再看例子",
        "最后完成自测",
        "阅读方式",
        "学习顺序",
        "理解",
        "运用",
        "区分",
        "准确说出",
        "准确区分",
        "独立推导",
        "识别并避免",
        "分析",
        "核心概念",
        "学习目标",
        "知识讲解",
        "课程导入",
        "你的当前学习情况",
        "重点难点突破",
        "典型例题",
        "课堂小结",
    }
    _EXTENSION_HEADINGS = ("拓展延伸", "拓展学习", "延伸学习", "扩展阅读")

    #: Process-wide cache for the visualization payload. The key contains only the
    #: normalized knowledge point and max_depth — never a user id or any private
    #: data — so sharing it across callers cannot leak per-user information.
    _VIS_CACHE_LOCK = threading.RLock()
    _vis_cache: TTLCache | None = None
    _enrich_inflight: set[tuple[str, int]] = set()
    _enrich_executor: ThreadPoolExecutor | None = None
    #: Neo4j circuit-breaker state (shared by all repository instances).
    _neo4j_failures: int = 0
    _neo4j_open_until: float | None = None
    #: One shared repository per process. Rebuilding it per request used to cost
    #: ~2s of lazy third-party imports (langchain / web-search deps), which showed
    #: up as graph-request latency (DEF-012).
    _shared_instance: KnowledgeGraphRepository | None = None
    _shared_refs: int = 0
    #: Serialized, delayed enrichment dispatch (never started inside a request).
    _enrich_queue: queue.Queue = queue.Queue(maxsize=256)
    _enrich_dispatcher: threading.Thread | None = None

    @classmethod
    def acquire_shared(cls) -> KnowledgeGraphRepository:
        """Return the process-wide repository, creating it on first use."""

        with cls._VIS_CACHE_LOCK:
            if cls._shared_instance is None:
                cls._shared_instance = cls()
            cls._shared_refs += 1
            return cls._shared_instance

    @classmethod
    def release_shared(cls) -> None:
        """Drop one reference; the connection closes when the last one goes."""

        with cls._VIS_CACHE_LOCK:
            if cls._shared_refs > 0:
                cls._shared_refs -= 1
            if cls._shared_refs == 0 and cls._shared_instance is not None:
                try:
                    cls._shared_instance.close()
                except Exception:  # pragma: no cover - defensive
                    pass
                cls._shared_instance = None

    @classmethod
    def prewarm(cls) -> None:
        """Eagerly import the heavy collaborators so request threads do not pay for it."""

        try:
            get_settings()
            from services.agent_service.app.services.knowledge_base import (
                KnowledgeBaseService as _KB,  # noqa: F401
            )
            from services.agent_service.app.services.llm_factory import LLMFactory as _F  # noqa: F401
            from services.agent_service.app.services.web_search_service import (
                WebSearchService as _W,  # noqa: F401
            )

            logger.info("Knowledge graph repository prewarmed.")
        except Exception as exc:  # pragma: no cover - prewarm must never break startup
            logger.warning("Knowledge graph prewarm skipped: %s", exc)

    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self.knowledge_base = KnowledgeBaseService()
        self.llm_factory = LLMFactory(settings)
        self.web_search = WebSearchService(settings)
        self._driver = None
        if not settings.neo4j_enabled:
            logger.info("Neo4j disabled.")
            return
        if not self._neo4j_available():
            # Breaker is open: do not even construct a driver this request.
            logger.debug("Neo4j circuit breaker open; skipping driver creation.")
            return
        if not self._neo4j_reachable(settings):
            # A configured-but-dead server must not cost the driver's connection
            # attempt on every cold start. Tripping here keeps request latency low.
            logger.info("Neo4j endpoint is not reachable; skipping driver creation.")
            self._record_neo4j_failure()
            return
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
                connection_timeout=settings.neo4j_connection_timeout_seconds,
                max_connection_lifetime=300,
            )
        except Exception:
            logger.warning("Neo4j driver unavailable.")
            self._record_neo4j_failure()

    # ------------------------------------------------------- Neo4j availability
    @staticmethod
    def _neo4j_reachable(settings) -> bool:
        """Cheap TCP preflight so a dead endpoint never builds a driver.

        Bounded by ``neo4j_connection_timeout_seconds``; any parsing or socket
        error is treated as "not reachable".
        """

        uri = (settings.neo4j_uri or "").strip()
        if not uri:
            return False
        try:
            from urllib.parse import urlparse

            parsed = urlparse(uri if "://" in uri else f"bolt://{uri}")
            host = parsed.hostname
            port = parsed.port or 7687
            if not host:
                return False
            import socket

            with socket.create_connection(
                (host, port), timeout=max(0.1, float(settings.neo4j_connection_timeout_seconds))
            ):
                return True
        except Exception:
            return False

    @classmethod
    def _neo4j_available(cls) -> bool:
        """Return False while the breaker is open after repeated failures."""

        with cls._VIS_CACHE_LOCK:
            open_until = cls._neo4j_open_until
        if open_until is None:
            return True
        if time.monotonic() >= open_until:
            with cls._VIS_CACHE_LOCK:
                cls._neo4j_open_until = None
                cls._neo4j_failures = 0
            logger.info("Neo4j circuit breaker reset; retrying connections.")
            return True
        return False

    @classmethod
    def _record_neo4j_failure(cls) -> None:
        """Count one failure and open the breaker past the configured threshold."""

        settings = get_settings()
        with cls._VIS_CACHE_LOCK:
            cls._neo4j_failures += 1
            if cls._neo4j_failures >= max(1, settings.neo4j_failure_threshold):
                cls._neo4j_open_until = time.monotonic() + max(1, settings.neo4j_cooldown_seconds)
                logger.warning(
                    "Neo4j circuit breaker opened for %ss after %d failures.",
                    settings.neo4j_cooldown_seconds,
                    cls._neo4j_failures,
                )

    @classmethod
    def _record_neo4j_success(cls) -> None:
        with cls._VIS_CACHE_LOCK:
            cls._neo4j_failures = 0
            cls._neo4j_open_until = None

    @classmethod
    def reset_neo4j_breaker(cls) -> None:
        """Reset breaker state (tests / admin tooling)."""

        with cls._VIS_CACHE_LOCK:
            cls._neo4j_failures = 0
            cls._neo4j_open_until = None

    # ------------------------------------------------------------ visualization
    @classmethod
    def _get_vis_cache(cls) -> TTLCache:
        """Return the shared visualization cache, creating it on first use."""

        with cls._VIS_CACHE_LOCK:
            if cls._vis_cache is None:
                settings = get_settings()
                cls._vis_cache = TTLCache(
                    ttl_seconds=settings.graph_cache_ttl_seconds,
                    max_entries=settings.graph_cache_max_entries,
                )
            return cls._vis_cache

    @classmethod
    def clear_visualization_cache(cls) -> None:
        """Drop every cached visualization (used by tests and admin tooling)."""

        with cls._VIS_CACHE_LOCK:
            if cls._vis_cache is not None:
                cls._vis_cache.clear()
            cls._enrich_inflight.clear()

    @classmethod
    def visualization_cache_stats(cls):
        """Expose cache counters for tests and diagnostics."""

        return cls._get_vis_cache().stats()

    @staticmethod
    def _normalize_knowledge_point(knowledge_point: str) -> str:
        """Normalize a knowledge point so equivalent spellings share one entry."""

        return " ".join(str(knowledge_point or "").split()).strip().casefold()

    @classmethod
    def _cache_key(cls, knowledge_point: str, max_depth: int) -> tuple[str, int]:
        """Cache key: normalized knowledge point + depth (nothing user specific)."""

        try:
            depth = max(1, min(int(max_depth), 5))
        except (TypeError, ValueError):
            depth = 2
        return cls._normalize_knowledge_point(knowledge_point), depth

    def get_visualization_graph(self, kp, max_depth=2, *, allow_enrichment=False):
        """Return a visualization graph without blocking on the LLM.

        Order: versioned cache → deterministic public sources.
        Raises ``ValueError`` unchanged when no source produced edges,
        so existing 404 semantics are preserved.
        """

        key = (*self._cache_key(kp, max_depth), "public", self._public_source_version(kp))
        cache = self._get_vis_cache()
        cached = cache.get(key)
        if cached is not None:
            return cached

        merged = self._build_deterministic_visualization(kp, key[1])
        has_edges = bool(merged.get("nodes")) and bool(merged.get("edges"))

        if has_edges:
            # Only complete, non-empty results are cached.
            cache.set(key, merged)
            return merged

        # Even an old caller passing allow_enrichment=True cannot bypass the
        # persistent construction queue, budget reservations and review process.
        raise ValueError("知识点没有图谱数据")

    def _public_source_version(self, kp: str) -> str:
        """Revoke shared snapshots after source edits, publication or withdrawal."""
        resources = [(row.id, row.title, row.content, row.structured_json)
                     for row, _ in self._matching_resource_rows(kp, 8)]
        with SessionLocal() as db:
            relations = db.query(KnowledgeRelation.from_id, KnowledgeRelation.to_id,
                                 KnowledgeRelation.relation_type).order_by(KnowledgeRelation.id).all()
            points = db.query(KnowledgePoint.id, KnowledgePoint.name).order_by(KnowledgePoint.id).all()
        article = self._get_article_for_graph(kp)
        corpus = self.knowledge_base.article_to_dict(article) if article else None
        body = json.dumps([resources, [tuple(row) for row in relations], [tuple(row) for row in points], corpus],
                          sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(body.encode()).hexdigest()

    def _build_deterministic_visualization(self, kp, max_depth: int) -> dict[str, Any]:
        """Merge Neo4j / SQL / stored-courseware relations. Never calls the LLM."""

        graphs = []
        # A historical graph node is not proof of public ownership/review.
        # Preserve the connector for explicit synchronization, but do not merge
        # unclassified Neo4j labels into shared student snapshots.
        sg = self._get_visualization_graph_from_sql(kp, max_depth)
        if sg["nodes"]:
            graphs.append(sg)
        cg = self._build_visualization_graph_from_content(kp, allow_llm=False)
        if cg["nodes"]:
            graphs.append(cg)
        return self._merge_graphs(graphs)

    def _schedule_enrichment(self, kp: str, max_depth: int) -> None:
        """Queue one background LLM enrichment per cache key.

        The request thread never waits: enrichment is handed to a single delayed
        dispatcher rather than started inline, and consecutive jobs are spaced by
        a minimum interval. Starting the LLM work *during* the request made the
        caller intermittently stall for ~2.2 s (measured 1 run in 3), which broke
        the graph latency SLO; deferring it keeps the request path clean.
        """

        settings = self._settings
        if not settings.graph_llm_enrich_enabled:
            return

        key = (self._normalize_knowledge_point(kp), max_depth)
        with self._VIS_CACHE_LOCK:
            if key in self._enrich_inflight:
                return
            self._enrich_inflight.add(key)
            if self._enrich_dispatcher is None:
                self._enrich_dispatcher = threading.Thread(
                    target=self._enrichment_dispatch_loop,
                    name="graph-enrich-dispatch",
                    daemon=True,
                )
                self._enrich_dispatcher.start()

        try:
            self._enrich_queue.put((kp, max_depth, key), timeout=1.0)
        except Exception as exc:  # queue full / unavailable
            logger.warning("Graph enrichment enqueue failed for %s: %s", kp, exc)
            with self._VIS_CACHE_LOCK:
                self._enrich_inflight.discard(key)

    @classmethod
    def _enrichment_dispatch_loop(cls) -> None:
        """Single background dispatcher: one enrichment at a time, spaced out.

        Settings are re-read every iteration so the grace period and spacing stay
        configurable at runtime (and observable in tests) rather than frozen when
        the thread happens to start.
        """

        while True:
            settings = get_settings()
            # Let the service finish warming up before competing with real traffic.
            delay = max(0.0, float(settings.graph_enrich_startup_delay_seconds))
            if delay:
                time.sleep(delay)

            try:
                kp, max_depth, key = cls._enrich_queue.get()
            except Exception:  # pragma: no cover - queue shut down
                return
            try:
                executor = cls._get_enrich_executor(settings.graph_enrich_max_workers)
                executor.submit(cls._enrichment_worker_entry, kp, max_depth, key).result()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Graph enrichment run failed for %s: %s", kp, exc)
                with cls._VIS_CACHE_LOCK:
                    cls._enrich_inflight.discard(key)
            time.sleep(max(0.0, float(get_settings().graph_enrich_min_interval_seconds)))

    @classmethod
    def _enrichment_worker_entry(cls, kp: str, max_depth: int, key: tuple[str, int]) -> None:
        """Build a repository and run one enrichment job."""

        repository = None
        try:
            repository = cls()
            repository._run_enrichment(kp, max_depth, key)
        except Exception as exc:
            logger.warning("graph enrichment failed for %s: %s", kp, exc)
            with cls._VIS_CACHE_LOCK:
                cls._enrich_inflight.discard(key)
        finally:
            if repository is not None:
                try:
                    repository.close()
                except Exception:  # pragma: no cover - defensive
                    pass

    @classmethod
    def _get_enrich_executor(cls, max_workers: int) -> ThreadPoolExecutor:
        """Lazily create the shared enrichment pool."""

        with cls._VIS_CACHE_LOCK:
            if cls._enrich_executor is None:
                cls._enrich_executor = ThreadPoolExecutor(
                    max_workers=max(1, int(max_workers)),
                    thread_name_prefix="graph-enrich",
                )
            return cls._enrich_executor

    def _run_enrichment(self, kp: str, max_depth: int, key: tuple[str, int]) -> None:
        """Background worker: build the LLM-enriched graph and cache it.

        The worker deliberately does **not** write to SQLite. Persisting relations
        from a background thread competed with request-path writes for SQLite's
        single writer lock and produced multi-second stalls inside the request
        (measured ~2.2 s p95). Enrichment is therefore cache-only: LLM-derived
        nodes improve this process's answers, while relation persistence stays an
        explicit operation (``sync_courseware_to_graph``).
        """

        started = time.monotonic()
        repository = None
        try:
            repository = KnowledgeGraphRepository()
            enriched = repository._enrich_visualization_graph(kp, max_depth)
            nodes = enriched.get("nodes") or []
            edges = enriched.get("edges") or []
            if nodes and edges:
                self._get_vis_cache().set(key, enriched)
                logger.info(
                    "graph enrichment cached: kp=%s depth=%d nodes=%d elapsed=%.2fs",
                    kp,
                    max_depth,
                    len(nodes),
                    time.monotonic() - started,
                )
            else:
                # Empty / partial results are deliberately not cached.
                logger.info(
                    "graph enrichment produced no edges: kp=%s depth=%d elapsed=%.2fs",
                    kp,
                    max_depth,
                    time.monotonic() - started,
                )
        except Exception as exc:
            logger.warning("graph enrichment failed for %s: %s", kp, exc)
        finally:
            if repository is not None:
                try:
                    repository.close()
                except Exception:  # pragma: no cover - defensive
                    pass
            with KnowledgeGraphRepository._VIS_CACHE_LOCK:
                KnowledgeGraphRepository._enrich_inflight.discard(key)

    def _persist_llm_relations(self, kp: str) -> None:
        """Run the LLM extraction once and store the resulting relations.

        Kept for explicit/manual graph building. The request-triggered enrichment
        worker intentionally does not call this: see ``_run_enrichment`` for why
        background SQLite writes were removed.
        """

        deadline = time.monotonic() + max(1, int(self._settings.graph_llm_enrich_timeout_seconds))
        prerequisites = self._derive_prerequisites(kp, None, allow_llm=True)
        if time.monotonic() > deadline:
            logger.warning(
                "graph enrichment deadline exceeded after prerequisite extraction: kp=%s", kp
            )
            return
        recommendations = self._derive_recommendations(kp, None, allow_llm=True)
        if not prerequisites and not recommendations:
            return
        self._apply_relations(kp, prerequisites, recommendations)

    def _enrich_visualization_graph(self, kp, max_depth: int) -> dict[str, Any]:
        """Build the LLM-assisted graph. Runs only inside the enrichment worker."""

        deadline = time.monotonic() + max(1, int(self._settings.graph_llm_enrich_timeout_seconds))
        merged = self._build_deterministic_visualization(kp, max_depth)
        if time.monotonic() > deadline:
            logger.warning("graph enrichment deadline exceeded before LLM step: kp=%s", kp)
            return merged

        graphs = [merged] if merged.get("nodes") else []
        content_graph = self._build_visualization_graph_from_content(kp, allow_llm=True)
        if content_graph.get("nodes"):
            graphs.append(content_graph)

        if time.monotonic() > deadline:
            # Over budget: keep only what the deterministic sources produced.
            logger.warning("graph enrichment deadline exceeded after content step: kp=%s", kp)
            return merged

        return self._merge_graphs(graphs)

    def _neo4j_run(self, query: str, **params):
        """Run one Neo4j query with a hard timeout and breaker accounting.

        A configured-but-unreachable server must not cost every request the
        driver's default connection timeout (~4 s observed), so the query runs
        under an explicit deadline and repeated failures open the breaker.
        """

        driver = self._require_driver()
        timeout = max(0.1, float(self._settings.neo4j_query_timeout_seconds))

        def _execute():
            with driver.session() as session:
                return session.run(query, **params).data()

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="neo4j-query")
        future = pool.submit(_execute)
        try:
            records = future.result(timeout=timeout)
        except Exception:
            self._record_neo4j_failure()
            raise
        else:
            self._record_neo4j_success()
            return records
        finally:
            pool.shutdown(wait=False)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()

    def _require_driver(self):
        if self._driver is None:
            raise RuntimeError("Neo4j is not available.")
        return self._driver

    def create_knowledge_point(self, name, desc, diff, imp):
        q = """MERGE (kp:KnowledgePoint {name:$n}) SET kp.description=$d,kp.difficulty=$f,kp.importance=$i RETURN kp"""
        with self._require_driver().session() as s:
            return dict(s.run(q, n=name, d=desc, f=diff, i=imp).single()["kp"])

    def find_dependency_path(self, kp, max_depth=3):
        results = []
        results.extend(self._find_dependency_path_from_sql(kp, max_depth))
        results.extend(self._build_dependency_paths_from_content(kp))
        u = self._unique_paths(results)
        if u:
            return u
        raise ValueError("知识点没有依赖数据")

    def find_related_resources(self, kp):
        resources = []
        # Historical graph Resource nodes have no authoritative ownership or
        # review state. Resolve resource visibility against SQL on every read.
        resources.extend(self._find_related_resources_from_sql(kp))
        resources.extend(self._build_related_resources_from_content(kp))
        u = self._unique_resources(resources)
        if u:
            return u
        raise ValueError("知识点没有关联资源")

    def _find_dependency_path_from_neo4j(self, kp, md):
        q = """MATCH path=(kp:KnowledgePoint {name:$kp})-[:DEPENDS_ON*1..$md]->(d) RETURN [n IN nodes(path)|n.name] AS dp"""
        return [{"path": r["dp"]} for r in self._neo4j_run(q, kp=kp, md=md) if r.get("dp")]

    def _find_related_resources_from_neo4j(self, kp):
        q = """MATCH (kp:KnowledgePoint {name:$kp})-[:ASSOCIATED_WITH]-(r:Resource) RETURN r.name AS name,r.type AS type,r.uri AS uri"""
        return [dict(r) for r in self._neo4j_run(q, kp=kp)]

    def _get_visualization_graph_from_neo4j(self, kp, md):
        q = """MATCH (kp:KnowledgePoint {name:$kp}) OPTIONAL MATCH (kp)-[:DEPENDS_ON*1..$md]->(d) OPTIONAL MATCH (kp)-[:RECOMMENDS]->(n) RETURN kp.name AS cur, collect(DISTINCT d.name) AS deps, collect(DISTINCT n.name) AS nexts"""
        rows = self._neo4j_run(q, kp=kp, md=md)
        if not rows:
            return {"nodes": [], "edges": []}
        r = rows[0]
        nodes = [{"id": r["cur"], "label": r["cur"], "category": "current"}]
        edges = []
        for d in r.get("deps") or []:
            if d:
                nodes.append({"id": d, "label": d, "category": "prerequisite"})
                edges.append({"source": r["cur"], "target": d, "label": "DEPENDS_ON"})
        for n in r.get("nexts") or []:
            if n:
                nodes.append({"id": n, "label": n, "category": "recommended"})
                edges.append({"source": r["cur"], "target": n, "label": "RECOMMENDS"})
        return {"nodes": nodes, "edges": edges}

    def _find_dependency_path_from_sql(self, kp, md):
        with SessionLocal() as db:
            cur = db.query(KnowledgePoint).filter(KnowledgePoint.name == kp).first()
            if not cur or cur.subject_id is None:
                return []
            out = (
                db.query(KnowledgeRelation, KnowledgePoint)
                .join(KnowledgePoint, KnowledgeRelation.to_id == KnowledgePoint.id)
                .filter(
                    KnowledgeRelation.from_id == cur.id,
                    KnowledgePoint.subject_id.is_not(None),
                    or_(
                        KnowledgeRelation.relation_type == "DEPENDS_ON",
                        KnowledgeRelation.relation_type == "前置基础",
                    ),
                )
                .all()
            )
            return [{"path": [kp, t.name]} for _, t in out]

    def _get_visualization_graph_from_sql(self, kp, md):
        with SessionLocal() as db:
            cur = db.query(KnowledgePoint).filter(KnowledgePoint.name == kp).first()
            if not cur or cur.subject_id is None:
                return {"nodes": [], "edges": []}
            nodes = [{"id": kp, "label": kp, "category": "current"}]
            edges = []
            out = (
                db.query(KnowledgeRelation, KnowledgePoint)
                .join(KnowledgePoint, KnowledgeRelation.to_id == KnowledgePoint.id)
                .filter(KnowledgeRelation.from_id == cur.id)
                .all()
            )
            inc = (
                db.query(KnowledgeRelation, KnowledgePoint)
                .join(KnowledgePoint, KnowledgeRelation.from_id == KnowledgePoint.id)
                .filter(KnowledgeRelation.to_id == cur.id)
                .all()
            )
            for r, t in out:
                if t.subject_id is None or r.relation_type not in {"DEPENDS_ON", "前置基础", "RECOMMENDS", "后续模块"}:
                    continue
                cat = (
                    "recommended"
                    if r.relation_type in {"RECOMMENDS", "后续模块"}
                    else "prerequisite"
                )
                nodes.append({"id": t.name, "label": t.name, "category": cat})
                edges.append({"source": cur.name, "target": t.name, "label": r.relation_type})
            for r, s in inc:
                if s.subject_id is None or r.relation_type not in {"DEPENDS_ON", "前置基础", "RECOMMENDS", "后续模块"}:
                    continue
                cat = (
                    "prerequisite"
                    if r.relation_type in {"DEPENDS_ON", "前置基础"}
                    else "recommended"
                )
                nodes.append({"id": s.name, "label": s.name, "category": cat})
                edges.append({"source": cur.name, "target": s.name, "label": r.relation_type})
            return self._merge_graphs([{"nodes": nodes, "edges": edges}])

    def _build_visualization_graph_from_content(self, kp, allow_llm: bool = True):
        article = self._get_article_for_graph(kp)
        nodes = [{"id": kp, "label": kp, "category": "current"}]
        edges = []
        for p in self._derive_prerequisites(kp, article, allow_llm=allow_llm):
            nodes.append({"id": p, "label": p, "category": "prerequisite"})
            edges.append({"source": kp, "target": p, "label": "前置基础"})
        for r in self._derive_recommendations(kp, article, allow_llm=allow_llm):
            nodes.append({"id": r, "label": r, "category": "recommended"})
            edges.append({"source": kp, "target": r, "label": "后续模块"})
        resource_links = self._resource_links(article)
        for r in self._derive_resource_nodes(kp, article):
            node = {"id": r, "label": r, "category": "resource"}
            node.update(self._match_resource_link(r, resource_links))
            nodes.append(node)
            edges.append({"source": kp, "target": r, "label": "关联资源"})
        g = self._merge_graphs([{"nodes": nodes, "edges": edges}])
        return {"nodes": [], "edges": []} if len(g["nodes"]) <= 1 or not g["edges"] else g

    def _build_dependency_paths_from_content(self, kp):
        a = self._get_article_for_graph(kp)
        return [{"path": [i, kp]} for i in self._derive_prerequisites(kp, a, allow_llm=False)]

    def _build_related_resources_from_content(self, kp):
        r = []
        a = self._get_article_for_graph(kp)
        if a:
            for i in self.knowledge_base.article_to_dict(a).get("external_resources", [])[:6]:
                if isinstance(i, dict):
                    r.append(
                        {
                            "name": str(i.get("title") or "res"),
                            "type": str(i.get("kind") or "resource"),
                            "uri": str(i.get("url") or ""),
                        }
                    )
        return r

    def _build_recommendations_from_content(self, kp):
        a = self._get_article_for_graph(kp)
        return [
            {"name": t, "difficulty": 1, "importance": 1}
            for t in self._derive_recommendations(kp, a, allow_llm=False)
        ]

    def _find_related_resources_from_sql(self, kp):
        r = []
        for res, k in self._matching_resource_rows(kp, 8):
            t = self._extract_title_from_content(res.content) or f"{(k.name if k else kp)}资源"
            r.append({"name": t, "type": res.type, "uri": f"/resources/{res.id}"})
        return r

    def _get_article_for_graph(self, kp):
        return self.knowledge_base.get_article(kp)

    # ------------------------------------------------------------------
    # NEW: LLM-based courseware extraction — the primary extraction path.
    # Replaces brittle regex heuristics with LLM reading the actual
    # generated courseware Markdown content.
    # ------------------------------------------------------------------

    def _llm_call_with_timeout(self, callable_, *args, **kwargs):
        """Run one LLM call under an explicit timeout.

        Enrichment already runs off the request path, but a runaway model call
        must still be bounded so the worker thread is released and the dead-line
        checks in ``_enrich_visualization_graph`` stay meaningful.
        """

        from concurrent.futures import ThreadPoolExecutor as _Pool

        timeout = max(1, int(self._settings.graph_llm_enrich_timeout_seconds))
        pool = _Pool(max_workers=1, thread_name_prefix="graph-llm")
        future = pool.submit(callable_, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        finally:
            # Do not wait for a stuck model call; the daemon-ish pool thread is
            # abandoned and the timeout surfaces to the caller.
            pool.shutdown(wait=False)

    def _extract_kp_labels_via_llm(self, kp: str) -> dict[str, list[str]]:
        """Ask the LLM to read the stored courseware content and extract
        meaningful knowledge-point labels for prerequisites and recommendations."""
        cw_text = self._combined_resource_text(kp)
        if not cw_text or len(cw_text.strip()) < 80:
            return {"prereqs": [], "recs": []}

        # Keep a reasonable window for the LLM
        truncated = cw_text[:2400]

        def _invoke() -> str:
            from langchain_core.messages import HumanMessage
            from langchain_core.output_parsers import StrOutputParser

            llm = self.llm_factory.build_chat_model(temperature=0.1)
            prompt = _GRAPH_LLM_PROMPT.replace("{kp}", kp).replace("{courseware}", truncated)
            chain = llm | StrOutputParser()
            return chain.invoke([HumanMessage(content=prompt)])

        try:
            raw = self._llm_call_with_timeout(_invoke)
            if not isinstance(raw, str) or not raw.strip():
                return {"prereqs": [], "recs": []}
            parsed = self._parse_json_safely(raw)
            if not isinstance(parsed, dict):
                return {"prereqs": [], "recs": []}
            prereqs = parsed.get("prereqs", [])
            recs = parsed.get("recs", [])
            return {
                "prereqs": [str(x).strip() for x in prereqs if str(x).strip()],
                "recs": [str(x).strip() for x in recs if str(x).strip()],
            }
        except Exception as exc:
            logger.warning("LLM-based KP label extraction failed for '%s': %s", kp, exc)
            return {"prereqs": [], "recs": []}

    def _parse_json_safely(self, raw: str) -> dict[str, Any] | None:
        cleaned = raw.strip()
        # strip markdown fences
        for prefix in ("```json", "```"):
            if cleaned.startswith(prefix):
                cleaned = cleaned.removeprefix(prefix).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned.removesuffix("```").strip()
        # try direct parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # balanced brace extraction
        start = cleaned.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(cleaned)):
                ch = cleaned[i]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(cleaned[start : i + 1])
                            except json.JSONDecodeError:
                                break
        return None

    # ------------------------------------------------------------------
    # Derivation methods — now prefer LLM extraction, fall back to
    # regex heuristics only when the LLM returns nothing.
    # ------------------------------------------------------------------

    def _derive_prerequisites(self, kp, article, allow_llm: bool = True):
        # Step 1: try LLM on courseware content (skipped on the request path)
        if allow_llm:
            llm_result = self._extract_kp_labels_via_llm(kp)
            if llm_result["prereqs"]:
                chosen = [label for label in llm_result["prereqs"] if self._is_meaningful_label(label, kp)]
                if chosen:
                    return self._finalize_labels(kp, chosen)

        # Step 2: fall back to regex + heuristic extraction
        labels = []
        if article:
            labels.extend([self._short_concept_label(c) for c in article.concepts[:4]])
        labels.extend(self._extract_section_items(kp, "prerequisite"))
        labels.extend(self._extract_introductory_concepts(kp))
        labels.extend(self._match_existing_points(kp, "prerequisite"))
        labels = [label for label in labels if self._is_meaningful_label(label, kp)]
        if not labels and allow_llm:
            labels = self._derive_topics_from_title(kp)
        return self._finalize_labels(kp, list(dict.fromkeys(labels)))

    def _derive_recommendations(self, kp, article, allow_llm: bool = True):
        if allow_llm:
            llm_result = self._extract_kp_labels_via_llm(kp)
            if llm_result["recs"]:
                chosen = [label for label in llm_result["recs"] if self._is_meaningful_label(label, kp)]
                if chosen:
                    return self._finalize_labels(kp, chosen)

        labels = []
        if article:
            labels.extend([self._clean_text_label(c, 20) for c in article.checks[:2]])
            labels.extend([self._clean_text_label(a, 18) for a in article.applications[:2]])
        labels.extend(self._extract_section_items(kp, "recommended"))
        labels.extend(self._extract_extension_targets(kp))
        labels.extend(self._extract_learning_objective_targets(kp))
        labels.extend(self._match_existing_points(kp, "recommended"))
        labels = [label for label in labels if self._is_meaningful_label(label, kp)]
        if not labels and allow_llm:
            labels = self._derive_topics_from_title(kp)
        return self._finalize_labels(kp, labels)

    def _derive_resource_nodes(self, kp, article):
        labels = []
        if article:
            labels.extend(
                str(i.get("title") or "")
                for i in self.knowledge_base.article_to_dict(article).get("external_resources", [])[
                    :4
                ]
                if isinstance(i, dict)
            )
        labels.extend(self._extract_section_items(kp, "resource"))
        labels.extend(self._resource_titles_from_sql(kp))
        return self._finalize_labels(kp, labels, limit=6)

    def _resource_links(self, article) -> list[dict[str, str]]:
        """Return public reference links that can be attached to resource nodes."""

        if article is None:
            return []
        links: list[dict[str, str]] = []
        try:
            payload = self.knowledge_base.article_to_dict(article)
        except Exception:
            return []
        references = payload.get("external_resources")
        if not isinstance(references, list):
            return []
        for item in references[:8]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            try:
                parsed = urlsplit(url)
                if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or any(ord(char) < 33 for char in url):
                    continue
            except ValueError:
                continue
            links.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "url": url,
                    "provider": str(item.get("provider") or "").strip(),
                    "kind": str(item.get("kind") or "").strip(),
                }
            )
        return links

    def _match_resource_link(self, label, links) -> dict[str, str]:
        """Match a finalized node label back to a reference link, tolerating cleanup."""

        key = " ".join(str(label or "").split()).casefold()
        if not key:
            return {}
        exact = next((link for link in links if " ".join(link["title"].split()).casefold() == key), None)
        if exact is None:
            exact = next((link for link in links if (title := " ".join(link["title"].split()).casefold())
                and min(len(key), len(title)) >= 4 and (key in title or title in key)), None)
        return {name: exact[name] for name in ("url", "provider", "kind")} if exact else {}

    def _is_meaningful_label(self, label: str, kp: str) -> bool:
        """Reject labels that are too short, too generic, or identical to the current KP."""
        if not label or len(label) < 3:
            return False
        clean = self._clean_text_label(label, 30)
        if len(clean) < 3:
            return False
        if clean == self._clean_text_label(kp, 30):
            return False
        generic_tokens = {
            "概念",
            "函数",
            "循环",
            "方法",
            "变量",
            "类型",
            "对象",
            "模块",
            "语句",
            "表达式",
            "算法",
            "数据",
            "基础",
            "编程",
            "语法",
            "入门",
            "概述",
        }
        if clean in generic_tokens:
            return False
        # also reject labels that are just 1-2 character CJK tokens
        if len(clean) <= 2 and all("一" <= c <= "鿿" for c in clean):
            return False
        return True

    # ------------------------------------------------------------------
    # Legacy regex-based helpers — kept as fallback
    # ------------------------------------------------------------------

    def _extract_section_items(self, kp, kind):
        content = self._combined_resource_text(kp)
        if not content:
            return []
        items = []
        for alias in self._SECTION_ALIASES[kind]:
            m = re.search(rf"##+\s*{re.escape(alias)}\s*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
            if m:
                items.extend(self._extract_bullets_from_text(m.group("body")))
        return items

    def _extract_introductory_concepts(self, kp):
        content = self._combined_resource_text(kp)
        if not content:
            return []
        concepts = []
        for h in ("学习目标", "知识讲解", "核心概念"):
            m = re.search(rf"##+\s*{re.escape(h)}\s*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
            if m:
                for line in m.group("body").splitlines():
                    concepts.extend(self._extract_phrases_from_line(line))
        return concepts[:8]

    def _extract_learning_objective_targets(self, kp):
        content = self._combined_resource_text(kp)
        if not content:
            return []
        m = re.search(r"##+\s*学习目标\s*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
        if not m:
            return []
        labels = []
        for line in m.group("body").splitlines():
            if any(t in line for t in ("运用", "解释", "推导", "识别", "区分", "分析")):
                labels.extend(self._extract_phrases_from_line(line))
        return labels

    def _extract_extension_targets(self, kp):
        content = self._combined_resource_text(kp)
        if not content:
            return []
        items = []
        for h in self._EXTENSION_HEADINGS:
            m = re.search(rf"##+\s*{re.escape(h)}[^\n]*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
            if m:
                items.extend(self._extract_bullets_from_text(m.group("body")))
        return items

    def _match_existing_points(self, kp, relation):
        ct = set(self._tokenize(kp))
        if not ct:
            return []
        with SessionLocal() as db:
            names = [str(r[0]) for r in db.query(KnowledgePoint.name).all() if str(r[0]).strip()]
        scored = []
        kl = kp.lower()
        for c in names:
            if c == kp:
                continue
            ot = len(ct & set(self._tokenize(c)))
            if ot <= 0:
                continue
            s = ot * 10
            if relation == "recommended" and c.lower() > kl:
                s += 1
            scored.append((s, c))
        scored.sort(key=lambda x: (-x[0], len(x[1]), x[1]))
        return [x[1] for x in scored[:4]]

    def _resource_titles_from_sql(self, kp):
        return [
            t
            for r, _ in self._matching_resource_rows(kp, 4)
            if (t := self._extract_title_from_content(r.content))
        ]

    def _combined_resource_text(self, kp):
        return "\n".join(r.content or "" for r, _ in self._matching_resource_rows(kp, 4))

    def _matching_resource_rows(self, kp, limit):
        with SessionLocal() as db:
            er = (
                db.query(Resource, KnowledgePoint)
                .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
                .filter(Resource.generated_for_user_id.is_(None), Resource.publish_status == "published", Resource.audit_status == "passed")
                .filter(KnowledgePoint.name == kp)
                .order_by(Resource.id.desc())
                .limit(limit)
                .all()
            )
            if er:
                return er
            return (
                db.query(Resource, KnowledgePoint)
                .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
                .filter(Resource.generated_for_user_id.is_(None), Resource.publish_status == "published", Resource.audit_status == "passed")
                .filter(Resource.content.contains(kp))
                .order_by(Resource.id.desc())
                .limit(limit)
                .all()
            )

    def _extract_bullets_from_text(self, text):
        return [
            p
            for line in text.splitlines()
            if line.strip() and line.strip()[0] in "-*12"
            for p in self._extract_phrases_from_line(line.strip())
        ]

    def _merge_graphs(self, graphs):
        nb = {}
        edges = []
        ek = set()
        for g in graphs:
            for n in g.get("nodes", []):
                nid = str(n.get("id") or "").strip()
                if nid:
                    merged_node = {
                        "id": nid,
                        "label": str(n.get("label") or nid),
                        "category": str(n.get("category") or "resource"),
                    }
                    previous = nb.get(nid) or {}
                    for key in ("url", "provider", "kind"):
                        value = str(n.get(key) or previous.get(key) or "").strip()
                        if value:
                            merged_node[key] = value
                    nb[nid] = merged_node
            for e in g.get("edges", []):
                src = str(e.get("source") or "").strip()
                tgt = str(e.get("target") or "").strip()
                lbl = str(e.get("label") or "").strip()
                if src and tgt:
                    key = (src, tgt, lbl)
                    if key not in ek:
                        ek.add(key)
                        edges.append({"source": src, "target": tgt, "label": lbl})
        return {"nodes": list(nb.values()), "edges": edges}

    def _unique_paths(self, paths):
        u = []
        seen = set()
        for p in paths:
            rp = p.get("path")
            if not isinstance(rp, list):
                continue
            n = tuple(str(x).strip() for x in rp if str(x).strip())
            if len(n) >= 2 and n not in seen:
                seen.add(n)
                u.append({"path": list(n)})
        return u

    def _unique_resources(self, rs):
        u = []
        seen = set()
        for r in rs:
            name = str(r.get("name") or r.get("title") or "").strip()
            uri = str(r.get("uri") or "").strip()
            if name and (name, uri) not in seen:
                seen.add((name, uri))
                u.append(
                    {
                        "name": name,
                        "type": str(r.get("type") or r.get("kind") or "resource"),
                        "uri": uri,
                    }
                )
        return u

    def _unique_recommendations(self, items):
        u = []
        seen = set()
        for r in items:
            name = str(r.get("name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                u.append(
                    {
                        "name": name,
                        "difficulty": int(r.get("difficulty") or 1),
                        "importance": int(r.get("importance") or 1),
                    }
                )
        return u

    def _normalize_labels(self, labels, limit=5):
        cleaned = [self._clean_text_label(i) for i in labels if isinstance(i, str) and i.strip()]
        cleaned = [i for i in cleaned if i]
        counts = Counter(cleaned)
        return sorted(counts, key=lambda i: (-counts[i], len(i), i))[:limit]

    def _finalize_labels(self, kp, labels, limit=5):
        filtr = [label for label in labels if self._is_meaningful_label(label, kp)]
        n = self._normalize_labels(filtr, limit * 3)
        res = []
        nkp = self._clean_text_label(kp, 40)
        for label in n:
            if not label or label == nkp:
                continue
            res.append(label)
            if len(res) >= limit:
                break
        return res

    def _clean_text_label(self, value, max_len=18):
        cleaned = re.sub(r"^[\-\*\d\.\s]+", "", value).strip()
        cleaned = re.sub(r"[`#>\[\]\(\)（）]", " ", cleaned)
        cleaned = re.sub(r"[" "\"''']", "", cleaned)
        cleaned = re.sub(r"\*\*|__|[:：；;，,。！？!?]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for t in (
            "你应该能够",
            "学完这节课后",
            "根据系统记录",
            "重点提醒",
            "这节课围绕",
            "当前掌握度约",
        ):
            cleaned = cleaned.replace(t, "").strip()
        for p in ("主题 ", "摘要 ", "阅读方式 ", "学习顺序 ", "核心主题 "):
            if cleaned.startswith(p):
                cleaned = cleaned[len(p) :].strip()
        cleaned = re.sub(r"^(以及|以及它和|以及它|以及|关于|其中|一个|一种)\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s*(是什么|的内容|的关系|时运动状态的区别)$", "", cleaned).strip()
        cleaned = re.sub(r"\s+[（(][^)）]*[）)]$", "", cleaned).strip()
        if cleaned in self._STOP_LABELS or len(cleaned) < 2:
            return ""
        return cleaned[:max_len].strip() if len(cleaned) > max_len else cleaned

    def _short_concept_label(self, concept):
        text = re.sub(r"`([^`]+)`", r"\1", concept)
        text = text.split("：", 1)[0].split(":", 1)[0]
        for d in ("，", ",", "。", ".", "、", "；", ";", "——"):
            b = text.split(d, 1)[0]
            if len(b.strip()) >= 2:
                text = b
        text = text.strip("` ").strip()
        if len(text) > 6:
            for n in (2, 3):
                if n <= len(text):
                    s = text[:n]
                    if not any(c in s for c in "，、。的了一在是") and any(
                        "一" <= c <= "鿿" for c in s
                    ):
                        return s
        return self._clean_text_label(text)

    def _line_to_label(self, line):
        return self._clean_text_label(re.sub(r"^\d+\.\s*", "", line.strip()))

    def _extract_phrases_from_line(self, line):
        s = line.strip()
        if not s:
            return []
        c = []
        c.extend(re.findall(r"\*\*(.+?)\*\*", s))
        c.extend(re.findall(r"[「“]([^」”]{2,20})[」”]", s))
        for t in (
            "理解",
            "掌握",
            "区分",
            "运用",
            "解释",
            "推导",
            "识别",
            "分析",
            "准确说出",
            "准确区分",
            "独立推导",
            "识别并避免",
        ):
            if t in s:
                c.extend(self._split_labels(s.split(t, 1)[1]))
        if not c:
            c.append(s)
        cl = [self._line_to_label(i) for i in c]
        return [i for i in cl if i and i not in self._STOP_LABELS]

    def _extract_title_from_content(self, content):
        for line in (content or "").splitlines():
            if line.strip().startswith("# "):
                return line.strip()[2:].strip()
            if line.strip().startswith("## "):
                return line.strip()[3:].strip()
        return ""

    def _tokenize(self, text):
        if not text.strip():
            return []
        cc = re.findall(r"[一-鿿]{2,}", text)
        lc = re.findall(r"[A-Za-z]{3,}", text.lower())
        tokens = list(lc)
        for chunk in cc:
            tokens.append(chunk)
            for size in range(2, min(4, len(chunk)) + 1):
                for start in range(len(chunk) - size + 1):
                    tokens.append(chunk[start : start + size])
        return tokens

    def _split_labels(self, text):
        return [
            self._clean_text_label(i)
            for i in re.split(r"(?:、|，|,|；|;|和|与|以及|及其|及|/)\s*", text)
            if self._clean_text_label(i)
        ]

    def _derive_topics_from_title(self, knowledge_point: str) -> list[str]:
        """Use LLM + web search to suggest graph nodes for an unknown topic.

        Only used as a last resort when NO courseware content exists.
        """
        return self._llm_suggest_nodes(knowledge_point)

    def _llm_suggest_nodes(self, knowledge_point: str) -> list[str]:
        """Use LLM to suggest graph nodes. No web search — just LLM reasoning."""
        try:
            from langchain_core.messages import HumanMessage
            from langchain_core.output_parsers import StrOutputParser

            prompt = (
                "你是知识图谱助手。给定知识点名称，请列出它的前置依赖和后续进阶知识点。\n\n"
                "输出 JSON (键必须双引号):\n"
                '{{"prereqs": ["前置知识点1", ...], "recs": ["进阶知识点1", ...]}}\n\n'
                f"知识点: {knowledge_point}\n\n"
                "注意：每个知识点必须是完整有意义的名词短语（5-25字），不可是1-3字的泛词。没有则返回空列表。"
            )

            def _invoke() -> str:
                llm = self.llm_factory.build_chat_model(temperature=0.2)
                chain = llm | StrOutputParser()
                return chain.invoke([HumanMessage(content=prompt)])

            raw = self._llm_call_with_timeout(_invoke)
            if not isinstance(raw, str):
                return []
            parsed = self._parse_json_safely(raw)
            if not isinstance(parsed, dict):
                return []
            topics = list(parsed.get("prereqs", [])) + list(parsed.get("recs", []))
            return [str(t) for t in topics if str(t).strip()]
        except Exception as exc:
            logger.warning("LLM graph nodes suggestion failed for %s: %s", knowledge_point, exc)
            return []

    # ------------------------------------------------------------------
    # Courseware -> graph synchronization
    # ------------------------------------------------------------------

    def sync_courseware_to_graph(
        self, knowledge_point: str, allow_llm: bool = False
    ) -> dict[str, Any]:
        """Extract relations from available sources and persist them.

        The request path passes ``allow_llm=False`` so this never blocks on the
        model (DEF-012); the background enrichment worker calls it again with
        ``allow_llm=True`` and persists whatever the LLM added.
        """

        prerequisites = self._derive_prerequisites(knowledge_point, None, allow_llm=allow_llm)
        recommendations = self._derive_recommendations(knowledge_point, None, allow_llm=allow_llm)
        return self._apply_relations(knowledge_point, prerequisites, recommendations)

    def _apply_relations(
        self,
        knowledge_point: str,
        prerequisites: list[str],
        recommendations: list[str],
    ) -> dict[str, Any]:
        """Persist prerequisites/recommendations into SQL (and Neo4j when enabled)."""

        result = {
            "knowledge_point": knowledge_point,
            "prerequisites_extracted": prerequisites,
            "recommendations_extracted": recommendations,
            "sql_knowledge_points_created": 0,
            "sql_relations_created": 0,
            "neo4j_relations_created": 0,
        }
        if not prerequisites and not recommendations:
            return result

        with SessionLocal() as db:
            current_kp = self._get_or_create_sql_knowledge_point(db, knowledge_point)
            for pn in prerequisites:
                pk = self._get_or_create_sql_knowledge_point(db, pn)
                if self._create_sql_relation_if_absent(db, pk.id, current_kp.id, "DEPENDS_ON"):
                    result["sql_relations_created"] += 1
            for rn in recommendations:
                rk = self._get_or_create_sql_knowledge_point(db, rn)
                if self._create_sql_relation_if_absent(db, current_kp.id, rk.id, "RECOMMENDS"):
                    result["sql_relations_created"] += 1
            db.commit()

        nc = self._sync_relations_to_neo4j(
            knowledge_point, prerequisites, "DEPENDS_ON"
        ) + self._sync_relations_to_neo4j(knowledge_point, recommendations, "RECOMMENDS")
        result["neo4j_relations_created"] = nc
        logger.info(
            "sync_courseware_to_graph: kp=%s prereq=%d rec=%d sql=%d neo4j=%d",
            knowledge_point,
            len(prerequisites),
            len(recommendations),
            result["sql_relations_created"],
            nc,
        )
        return result

    def _get_or_create_sql_knowledge_point(self, db, name):
        existing = db.query(KnowledgePoint).filter(KnowledgePoint.name == name).first()
        if existing is not None:
            return existing
        kp = KnowledgePoint(name=name, description="", difficulty=2, importance=2)
        db.add(kp)
        db.flush()
        return kp

    def _create_sql_relation_if_absent(self, db, from_id, to_id, relation_type):
        existing = (
            db.query(KnowledgeRelation)
            .filter(
                KnowledgeRelation.from_id == from_id,
                KnowledgeRelation.to_id == to_id,
                KnowledgeRelation.relation_type == relation_type,
            )
            .first()
        )
        if existing is not None:
            return False
        db.add(KnowledgeRelation(from_id=from_id, to_id=to_id, relation_type=relation_type))
        return True

    def _sync_relations_to_neo4j(self, kp, targets, rtype):
        if self._driver is None:
            return 0
        count = 0
        try:
            with self._require_driver().session() as s:
                for t in targets:
                    q = """MERGE (kp:KnowledgePoint {name:$kp}) MERGE (target:KnowledgePoint {name:$t}) MERGE (kp)-[r:RELATION {type:$rtype}]->(target) SET r.label=$rtype"""
                    s.run(q, kp=kp, t=t, rtype=rtype)
                    count += 1
        except Exception as exc:
            logger.warning("Neo4j sync failed for %s (%s): %s", kp, rtype, exc)
        return count
