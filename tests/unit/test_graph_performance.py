"""Regression tests for the knowledge-graph visualization hot path (DEF-012).

Original defect: ``POST /graph/visualization`` took ~12.5 s because the request
path performed synchronous LLM calls (one in ``sync_courseware_to_graph`` and two
more in the content builder), nothing was cached, and each request rebuilt the
repository — paying ~2 s of lazy third-party imports plus a ~4 s Neo4j connection
attempt against an unreachable server.

Contract locked in by these tests:

* the request path never blocks on the LLM — it merges Neo4j / SQL / stored
  courseware data only (``sync_courseware_to_graph(..., allow_llm=False)``);
* LLM completion runs in a bounded background worker, is time-boxed, persists the
  relations it found, and may only *enrich* the cached graph;
* an unreachable Neo4j degrades fast (TCP preflight + circuit breaker) instead of
  costing seconds per request;
* the cache key is exactly ``(normalized knowledge_point, max_depth)`` — no user
  scope — and a different ``max_depth`` never reuses another depth's entry;
* TTL and capacity limits are honoured;
* exceptions, empty and partial results are never cached;
* concurrent identical requests trigger at most one enrichment;
* nothing is fabricated: without real source data the original ``ValueError`` /
  404 semantics survive.

Isolation: the request path legitimately writes relations for real knowledge
points, so tests patch the content builder (their only data source) and the suite
removes the knowledge points it creates.
"""

from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.learning import KnowledgePoint, KnowledgeRelation
from common.ttl_cache import TTLCache
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.agent_service.app.main import app

CLIENT = TestClient(app)

_ASYNC_WAIT = 0.6
_MARKER = "pytestgraph"


def _graph(*labels: str) -> dict:
    """Build a minimal visualization payload with real node/edge objects."""

    return {
        "nodes": [{"id": label, "label": label, "category": "prerequisite"} for label in labels],
        "edges": [{"source": "current", "target": label, "label": "前置基础"} for label in labels],
    }


@pytest.fixture(autouse=True)
def _isolated_graph_state():
    """Empty cache, reset breakers and knowledge-point cleanup around every test.

    The enrichment queue and dispatcher are process-wide, so they are drained as
    well; otherwise a job queued by one test would be executed during the next.
    """

    KnowledgeGraphRepository.clear_visualization_cache()
    KnowledgeGraphRepository.reset_neo4j_breaker()
    _drain_enrichment_queue()
    yield
    KnowledgeGraphRepository.clear_visualization_cache()
    KnowledgeGraphRepository.reset_neo4j_breaker()
    _drain_enrichment_queue()
    with SessionLocal() as db:
        ids = [
            pid
            for (pid,) in db.query(KnowledgePoint.id)
            .filter(KnowledgePoint.name.like(f"%{_MARKER}%"))
            .all()
        ]
        if ids:
            db.query(KnowledgeRelation).filter(
                (KnowledgeRelation.from_id.in_(ids)) | (KnowledgeRelation.to_id.in_(ids))
            ).delete(synchronize_session=False)
            db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(ids)).delete(
                synchronize_session=False
            )
            db.commit()


@pytest.fixture
def content_graph(monkeypatch):
    """Control the single deterministic data source and count its invocations."""

    state: dict = {"payload": None, "calls": []}

    def fake_build(self, kp, allow_llm: bool = True):
        state["calls"].append((kp, allow_llm))
        payload = state["payload"]
        return {"nodes": [], "edges": []} if payload is None else payload

    monkeypatch.setattr(
        KnowledgeGraphRepository, "_build_visualization_graph_from_content", fake_build
    )
    return state


@pytest.fixture
def no_sql_graph(monkeypatch):
    """Force the SQL source empty so each test has exactly one data source."""

    monkeypatch.setattr(
        KnowledgeGraphRepository,
        "_get_visualization_graph_from_sql",
        lambda self, kp, md: {"nodes": [], "edges": []},
    )


@pytest.fixture
def no_relations(monkeypatch):
    """Keep the request-path relation write from touching the shared test database."""

    monkeypatch.setattr(KnowledgeGraphRepository, "_apply_relations", lambda self, *a, **k: {})


@pytest.fixture
def no_neo4j(monkeypatch):
    """Pretend the Neo4j endpoint is unreachable (the real local situation)."""

    monkeypatch.setattr(
        KnowledgeGraphRepository, "_neo4j_reachable", staticmethod(lambda settings: False)
    )


@pytest.fixture
def count_llm(monkeypatch):
    """Count LLM extractions without performing network calls."""

    calls: list[str] = []
    lock = threading.Lock()

    def fake_extract(self, kp: str):
        with lock:
            calls.append(kp)
        return {"prereqs": [], "recs": []}

    monkeypatch.setattr(KnowledgeGraphRepository, "_extract_kp_labels_via_llm", fake_extract)
    return calls


def _kp(name: str) -> str:
    return f"{name}-{_MARKER}-{uuid4().hex[:6]}"


def _use_cache(monkeypatch, cache: TTLCache) -> None:
    monkeypatch.setattr(KnowledgeGraphRepository, "_get_vis_cache", classmethod(lambda cls: cache))


def _drain_enrichment_queue() -> None:
    """Drop any queued/pending enrichment jobs and stop the previous dispatcher.

    The dispatcher is a process-wide singleton that sleeps for the grace period,
    so tests must retire it; otherwise a thread started under another test's
    settings would keep applying the old delay.
    """

    import queue as _queue

    while True:
        try:
            KnowledgeGraphRepository._enrich_queue.get_nowait()
        except _queue.Empty:
            break
    with KnowledgeGraphRepository._VIS_CACHE_LOCK:
        KnowledgeGraphRepository._enrich_inflight.clear()
        KnowledgeGraphRepository._enrich_dispatcher = None


def _assert_not_cached(knowledge_point: str, depth: int = 2) -> None:
    """Assert that *this* knowledge point was not cached.

    The dispatcher thread is process-wide and ``_drain_enrichment_queue`` can only
    drop the reference to it — a thread that already woke up may still finish an
    earlier job and add an entry for a *different* knowledge point. A global
    ``entries == 0`` check therefore reports another test's leftover as a failure.
    The contract under test is "this outcome cached nothing", so it is asserted for
    the key this test actually exercised.
    """

    key = KnowledgeGraphRepository._cache_key(knowledge_point, depth)
    cached = KnowledgeGraphRepository._get_vis_cache().get(key)
    assert cached is None, f"{knowledge_point!r} was cached despite the expected outcome"


def _remove_enrichment_delay(monkeypatch) -> None:
    """Make the background dispatcher start immediately.

    Production defers enrichment past a startup grace period so LLM work never
    overlaps early request traffic; tests must not wait 20s for that.
    """

    from common.config import get_settings

    settings_type = type(get_settings())
    monkeypatch.setattr(
        settings_type,
        "graph_enrich_startup_delay_seconds",
        property(lambda self: 0.0),
        raising=False,
    )
    monkeypatch.setattr(
        settings_type,
        "graph_enrich_min_interval_seconds",
        property(lambda self: 0.05),
        raising=False,
    )


# ---------------------------------------------------------------- connectivity
def test_unreachable_neo4j_does_not_create_a_driver(no_neo4j):
    """A dead endpoint must not even build a Neo4j driver."""

    repo = KnowledgeGraphRepository()
    assert repo._driver is None


def test_unreachable_neo4j_does_not_add_seconds_to_a_request(
    no_neo4j, content_graph, no_sql_graph, no_relations
):
    """The whole request stays fast even though Neo4j is configured but dead."""

    content_graph["payload"] = _graph("变量与数据类型")
    repo = KnowledgeGraphRepository()
    started = time.monotonic()
    repo.get_visualization_graph(_kp("快路径"), 2)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, f"request took {elapsed:.2f}s with Neo4j unreachable"


def test_codegrade_breaker_opens_after_repeated_failures():
    """Repeated failures open the breaker, and it can be reset."""

    KnowledgeGraphRepository.reset_neo4j_breaker()
    assert KnowledgeGraphRepository._neo4j_available() is True
    for _ in range(KnowledgeGraphRepository()._settings.neo4j_failure_threshold):
        KnowledgeGraphRepository._record_neo4j_failure()
    assert KnowledgeGraphRepository._neo4j_available() is False
    KnowledgeGraphRepository.reset_neo4j_breaker()
    assert KnowledgeGraphRepository._neo4j_available() is True


# ------------------------------------------------------------------ cache basics
def test_same_key_hits_cache_and_skips_rebuild(content_graph, no_sql_graph, no_relations, no_neo4j):
    """Identical (knowledge_point, max_depth) must be served from cache."""

    content_graph["payload"] = _graph("变量与数据类型")
    repo = KnowledgeGraphRepository()
    name = _kp("缓存命中")

    first = repo.get_visualization_graph(name, 2)
    second = repo.get_visualization_graph(name, 2)

    assert first == second
    assert len(content_graph["calls"]) == 1, "cache was bypassed on the second call"
    assert KnowledgeGraphRepository.visualization_cache_stats().hits >= 1


def test_different_max_depth_does_not_reuse_cache(
    content_graph, no_sql_graph, no_relations, no_neo4j
):
    """max_depth is part of the key."""

    content_graph["payload"] = _graph("变量与数据类型")
    repo = KnowledgeGraphRepository()
    name = _kp("深度区分")

    repo.get_visualization_graph(name, 2)
    repo.get_visualization_graph(name, 3)

    # `_build_visualization_graph_from_content` is only ever called with allow_llm=False.
    assert all(allow is False for (_name, allow) in content_graph["calls"])
    assert len(content_graph["calls"]) == 2, "depth 3 wrongly reused the depth 2 entry"
    assert KnowledgeGraphRepository._cache_key(name, 2) != KnowledgeGraphRepository._cache_key(
        name, 3
    )


def test_cache_key_contains_no_user_scope():
    """The key is (normalized knowledge point, depth) and nothing else."""

    assert KnowledgeGraphRepository._cache_key("  Python   循环 ", 2) == ("python 循环", 2)
    assert KnowledgeGraphRepository._cache_key("Python 循环", 99)[1] == 5  # clamped
    assert KnowledgeGraphRepository._cache_key("Python 循环", None)[1] == 2  # default


def test_equivalent_spellings_share_cache_entry(
    content_graph, no_sql_graph, no_relations, no_neo4j
):
    """Whitespace/case differences normalize to one entry."""

    content_graph["payload"] = _graph("变量与数据类型")
    repo = KnowledgeGraphRepository()
    name = _kp("归一化")

    repo.get_visualization_graph(name, 2)
    repo.get_visualization_graph(f"  {name.upper()}  ", 2)

    assert len(content_graph["calls"]) == 1


def test_ttl_expiry_recomputes(monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j):
    """An expired entry must be rebuilt, not served stale."""

    clock = {"now": 1000.0}
    _use_cache(monkeypatch, _fresh_cache(clock))
    content_graph["payload"] = _graph("变量与数据类型")
    repo = KnowledgeGraphRepository()
    name = _kp("过期")

    repo.get_visualization_graph(name, 2)
    repo.get_visualization_graph(name, 2)
    assert len(content_graph["calls"]) == 1

    clock["now"] += 10_000
    repo.get_visualization_graph(name, 2)
    assert len(content_graph["calls"]) == 2, "expired entry was served from cache"


def _fresh_cache(clock: dict) -> TTLCache:
    from common.config import get_settings

    settings = get_settings()
    return TTLCache(
        ttl_seconds=settings.graph_cache_ttl_seconds,
        max_entries=settings.graph_cache_max_entries,
        clock=lambda: clock["now"],
    )


def test_cache_is_bounded_by_max_entries(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """Capacity limit evicts instead of growing without bound."""

    content_graph["payload"] = _graph("变量与数据类型")
    _use_cache(monkeypatch, TTLCache(ttl_seconds=600, max_entries=2))

    repo = KnowledgeGraphRepository()
    for index in range(5):
        repo.get_visualization_graph(_kp(f"容量{index}"), 2)

    stats = KnowledgeGraphRepository.visualization_cache_stats()
    assert stats.entries == 2
    assert stats.evictions == 3


# ------------------------------------------------------- LLM must not block path
def test_sync_on_request_path_does_not_call_llm(count_llm, no_relations):
    """The request-path sync runs with allow_llm=False."""

    repo = KnowledgeGraphRepository()
    repo.sync_courseware_to_graph(_kp("同步不调模型"), allow_llm=False)

    assert count_llm == [], "sync on the request path invoked the LLM"


def test_llm_not_called_on_cache_hit(
    count_llm, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """Neither a first build nor a cache hit triggers LLM extraction."""

    content_graph["payload"] = _graph("变量与数据类型")
    repo = KnowledgeGraphRepository()
    name = _kp("命中不调模型")

    repo.get_visualization_graph(name, 2)
    repo.get_visualization_graph(name, 2)
    assert count_llm == []


def test_request_path_is_fast_even_when_llm_is_slow(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """A hanging LLM must not delay the request."""

    sleep_calls: list[str] = []

    def slow_extract(self, kp: str):
        sleep_calls.append(kp)
        time.sleep(5.0)
        return {"prereqs": [], "recs": []}

    monkeypatch.setattr(KnowledgeGraphRepository, "_extract_kp_labels_via_llm", slow_extract)
    content_graph["payload"] = _graph("变量与数据类型")

    repo = KnowledgeGraphRepository()
    started = time.monotonic()
    repo.get_visualization_graph(_kp("慢模型"), 2)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"request path blocked for {elapsed:.2f}s on the LLM"
    assert sleep_calls == [], "the request path invoked the slow LLM extractor"


def test_empty_result_is_not_cached(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """No real data keeps the original failure semantics and caches nothing."""

    content_graph["payload"] = None
    settings = KnowledgeGraphRepository()._settings
    monkeypatch.setattr(
        type(settings), "graph_llm_enrich_enabled", property(lambda self: False), raising=False
    )

    repo = KnowledgeGraphRepository()
    name = _kp("无数据")
    with pytest.raises(ValueError):
        repo.get_visualization_graph(name, 2)

    _assert_not_cached(name)


# ------------------------------------------------------------------ enrichment
def test_enrichment_caches_graph(monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j):
    """Background enrichment makes a previously empty key cacheable."""

    _remove_enrichment_delay(monkeypatch)
    content_graph["payload"] = None
    monkeypatch.setattr(
        KnowledgeGraphRepository,
        "_enrich_visualization_graph",
        lambda self, kp, depth: _graph("LLM 前置知识点"),
    )

    name = _kp("补全成功")
    repo = KnowledgeGraphRepository()
    with pytest.raises(ValueError):
        repo.get_visualization_graph(name, 2)

    # Read misses cannot create an unbudgeted background operation anymore.
    assert KnowledgeGraphRepository.visualization_cache_stats().entries == 0
    assert not KnowledgeGraphRepository._enrich_inflight


def test_enrichment_is_deferred_past_the_startup_grace_period(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """Enrichment must not start inline with the request that triggered it.

    This is the behaviour that removed the intermittent ~2.2s request stall: the
    dispatcher waits out a grace period instead of launching LLM work during the
    request.
    """

    from common.config import get_settings

    settings_type = type(get_settings())
    # Long grace period: enrichment must stay queued for the whole assertion.
    monkeypatch.setattr(
        settings_type,
        "graph_enrich_startup_delay_seconds",
        property(lambda self: 30.0),
        raising=False,
    )

    enrich_calls: list[str] = []

    def counting_enrich(self, kp, depth):
        enrich_calls.append(kp)
        return _graph("LLM 前置知识点")

    monkeypatch.setattr(KnowledgeGraphRepository, "_enrich_visualization_graph", counting_enrich)
    content_graph["payload"] = None

    repo = KnowledgeGraphRepository()
    name = _kp("延迟补全")
    started = time.monotonic()
    with pytest.raises(ValueError):
        repo.get_visualization_graph(name, 2)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, f"request waited {elapsed:.2f}s on enrichment"
    assert enrich_calls == [], "enrichment ran inline instead of being deferred"
    _assert_not_cached(name)


def test_concurrent_identical_requests_enrich_only_once(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """N concurrent identical requests must not spawn N enrichments."""

    _remove_enrichment_delay(monkeypatch)
    content_graph["payload"] = None
    enrich_calls: list[str] = []
    lock = threading.Lock()

    def counting_enrich(self, kp, depth):
        with lock:
            enrich_calls.append(kp)
        time.sleep(0.2)
        return _graph("LLM 前置知识点")

    monkeypatch.setattr(KnowledgeGraphRepository, "_enrich_visualization_graph", counting_enrich)

    name = _kp("并发")
    errors: list[Exception] = []

    def worker():
        repo = KnowledgeGraphRepository()
        try:
            repo.get_visualization_graph(name, 2)
        except ValueError:
            pass
        except Exception as exc:  # pragma: no cover - surfaced by the assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    time.sleep(_ASYNC_WAIT)

    assert not errors, errors
    assert enrich_calls == [], "read-only requests must not schedule paid enrichment"


def test_enrichment_failure_is_swallowed_and_not_cached(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """A failing enrichment must cache nothing and must not raise in the worker."""

    content_graph["payload"] = None
    monkeypatch.setattr(KnowledgeGraphRepository, "_persist_llm_relations", lambda self, kp: None)

    def boom(self, kp, depth):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(KnowledgeGraphRepository, "_enrich_visualization_graph", boom)

    repo = KnowledgeGraphRepository()
    name = _kp("模型失败")
    with pytest.raises(ValueError):
        repo.get_visualization_graph(name, 2)

    time.sleep(_ASYNC_WAIT)
    _assert_not_cached(name)


def test_enrichment_never_fabricates_when_model_returns_nothing(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j
):
    """An empty enrichment result must not be cached as a graph."""

    content_graph["payload"] = None
    monkeypatch.setattr(KnowledgeGraphRepository, "_persist_llm_relations", lambda self, kp: None)
    monkeypatch.setattr(
        KnowledgeGraphRepository,
        "_enrich_visualization_graph",
        lambda self, kp, depth: {"nodes": [], "edges": []},
    )

    repo = KnowledgeGraphRepository()
    name = _kp("空补全")
    with pytest.raises(ValueError):
        repo.get_visualization_graph(name, 2)

    time.sleep(_ASYNC_WAIT)
    _assert_not_cached(name)


# ------------------------------------------------------------------ HTTP layer
def test_http_endpoint_returns_graph_within_budget(
    content_graph, no_sql_graph, no_relations, no_neo4j, auth_headers
):
    """The endpoint answers fast when real data exists."""

    content_graph["payload"] = _graph("变量与数据类型")
    started = time.monotonic()
    response = CLIENT.post("/graph/visualization", json={"knowledge_point": _kp("接口快")}, headers=auth_headers)
    elapsed = time.monotonic() - started

    assert response.status_code == 200, response.text
    assert response.json()["nodes"]
    assert elapsed < 1.0, f"endpoint took {elapsed:.2f}s"


def test_http_endpoint_returns_404_when_no_data(
    content_graph, no_sql_graph, no_relations, no_neo4j, auth_headers
):
    """Contract preserved: no graph data still yields 404, not 500."""

    content_graph["payload"] = None
    response = CLIENT.post("/graph/visualization", json={"knowledge_point": _kp("接口无数据")}, headers=auth_headers)
    assert response.status_code == 404
    assert "图谱" in response.json()["detail"]


def test_http_endpoint_survives_llm_failure(
    monkeypatch, content_graph, no_sql_graph, no_relations, no_neo4j, auth_headers
):
    """An LLM outage must never produce a 500."""

    def boom(self, kp: str):
        raise RuntimeError("llm down")

    monkeypatch.setattr(KnowledgeGraphRepository, "_extract_kp_labels_via_llm", boom)
    content_graph["payload"] = _graph("变量与数据类型")

    response = CLIENT.post("/graph/visualization", json={"knowledge_point": _kp("模型故障")}, headers=auth_headers)
    assert response.status_code != 500
    assert response.status_code in (200, 404)


def test_graph_response_schema_is_unchanged(content_graph, no_sql_graph, no_relations, no_neo4j, auth_headers):
    """GraphVisualizationResponse keeps its shape (no frontend change needed)."""

    content_graph["payload"] = _graph("变量与数据类型")
    response = CLIENT.post("/graph/visualization", json={"knowledge_point": _kp("结构兼容")}, headers=auth_headers)
    payload = response.json()

    assert set(payload.keys()) == {"knowledge_point", "nodes", "edges"}
    for node in payload["nodes"]:
        assert {"id", "label", "category"} <= set(node.keys())
    for edge in payload["edges"]:
        assert {"source", "target", "label"} <= set(edge.keys())


def test_shared_repository_is_reused_across_requests():
    """The route no longer rebuilds the repository (which cost ~2s of imports)."""

    first = KnowledgeGraphRepository.acquire_shared()
    second = KnowledgeGraphRepository.acquire_shared()
    try:
        assert first is second, "shared repository was rebuilt per request"
    finally:
        KnowledgeGraphRepository.release_shared()
        KnowledgeGraphRepository.release_shared()
