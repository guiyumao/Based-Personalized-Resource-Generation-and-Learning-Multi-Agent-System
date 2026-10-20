#!/usr/bin/env python3
"""Benchmark fixed RAG queries across Top-K values and metadata filtering."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.agent_service.app.services.rag import ChromaRetriever, clear_retrieval_runtime_caches


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
    return ordered[index]


def evaluate_case(
    retriever: ChromaRetriever,
    case: dict[str, Any],
    *,
    top_k: int,
    metadata_enabled: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    results = retriever.retrieve_with_metadata(
        str(case["query"]),
        top_k=top_k,
        filters=case.get("filters") if metadata_enabled else None,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    texts = [str(item.get("content") or "") for item in results]
    expected = [str(term).casefold() for term in case.get("expected_terms", [])]
    first_rank = 0
    for index, text in enumerate(texts, 1):
        if any(term in text.casefold() for term in expected):
            first_rank = index
            break
    return {
        "id": case["id"],
        "elapsed_ms": elapsed_ms,
        "hit": first_rank > 0,
        "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
        "context_chars": sum(len(text) for text in texts),
        "returned": len(results),
        "strategy": (
            str(results[0].get("retrieval_strategy", "vector")) if results else "empty"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries", type=Path, default=Path("benchmarks/rag_queries.json")
    )
    parser.add_argument("--top-k", type=int, nargs="+", default=[3, 5, 8, 10])
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/rag.json"))
    args = parser.parse_args()

    cases = json.loads(args.queries.read_text(encoding="utf-8"))
    if len(cases) < 50:
        raise SystemExit("RAG benchmark requires at least 50 queries")
    retriever = ChromaRetriever()
    if not retriever.is_available:
        raise SystemExit(
            "Chroma is unavailable. Start the configured store and install chromadb before benchmarking."
        )

    report: dict[str, Any] = {"knowledge_base": retriever.describe(), "runs": []}
    for metadata_enabled in (False, True):
        for top_k in args.top_k:
            clear_retrieval_runtime_caches()
            rows = [
                evaluate_case(
                    retriever, case, top_k=top_k, metadata_enabled=metadata_enabled
                )
                for case in cases
            ]
            times = [row["elapsed_ms"] for row in rows]
            report["runs"].append({
                "mode": "metadata_vector" if metadata_enabled else "vector_only",
                "top_k": top_k,
                "samples": len(rows),
                "recall_at_k": round(sum(row["hit"] for row in rows) / len(rows), 4),
                "mrr": round(mean(row["reciprocal_rank"] for row in rows), 4),
                "avg_retrieval_ms": round(mean(times), 3),
                "p50_retrieval_ms": round(percentile(times, 0.50), 3),
                "p95_retrieval_ms": round(percentile(times, 0.95), 3),
                "avg_context_chars": round(mean(row["context_chars"] for row in rows), 1),
                "strategy_counts": dict(Counter(row["strategy"] for row in rows)),
                "cases": rows,
            })
    probe = cases[0]
    clear_retrieval_runtime_caches()
    probe_times: list[float] = []
    for _ in range(2):
        started = time.perf_counter()
        retriever.retrieve_with_metadata(
            str(probe["query"]), top_k=5, filters=probe.get("filters")
        )
        probe_times.append((time.perf_counter() - started) * 1000)
    report["cache_probe"] = {
        "query_id": probe["id"],
        "cold_ms": round(probe_times[0], 3),
        "warm_ms": round(probe_times[1], 3),
        "speedup": round(probe_times[0] / max(probe_times[1], 0.001), 2),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(report['runs'])} benchmark runs to {args.output}")


if __name__ == "__main__":
    main()
