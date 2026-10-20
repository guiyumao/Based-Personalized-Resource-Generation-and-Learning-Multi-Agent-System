#!/usr/bin/env python3
"""Summarize AI performance JSONL traces and compare two measurement windows."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

METRICS = (
    "total_ms",
    "retrieval_ms",
    "query_rewrite_ms",
    "embedding_ms",
    "vector_search_ms",
    "rerank_ms",
    "generation_ms",
    "audit_ms",
    "retry_ms",
    "persistence_ms",
    "prompt_tokens",
    "completion_tokens",
    "context_tokens",
    "retrieved_chunks",
    "retry_count",
)


def load_traces(path: Path) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    if not path.exists():
        return traces
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
        if isinstance(item, dict) and item.get("event") == "ai_performance_trace":
            traces.append(item)
    return traces


def percentile(values: list[float], percent: float) -> float:
    """Use nearest-rank percentiles so small samples stay easy to audit."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percent * len(ordered)) - 1))
    return ordered[index]


def summarize(traces: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        grouped[str(trace.get("task_type") or "unknown")].append(trace)
    output: dict[str, dict[str, float | int]] = {}
    for task_type, items in sorted(grouped.items()):
        summary: dict[str, float | int] = {"samples": len(items)}
        for metric in METRICS:
            values = [float(item.get(metric) or 0.0) for item in items]
            summary[f"avg_{metric}"] = round(mean(values), 3) if values else 0.0
            if metric == "total_ms":
                summary["p50_total_ms"] = round(percentile(values, 0.50), 3)
                summary["p95_total_ms"] = round(percentile(values, 0.95), 3)
        summary["cache_hit_rate"] = round(
            sum(bool(item.get("cache_hit")) for item in items) / len(items), 4
        )
        summary["success_rate"] = round(
            sum(200 <= int(item.get("status_code") or 0) < 400 for item in items) / len(items),
            4,
        )
        output[task_type] = summary
    return output


def markdown_report(
    current: dict[str, dict[str, float | int]],
    baseline: dict[str, dict[str, float | int]] | None = None,
) -> str:
    lines = [
        "# AI 性能报告",
        "",
        "| 任务 | 样本 | P50 总耗时(ms) | P95 总耗时(ms) | 平均检索(ms) | 平均生成(ms) | 平均审核(ms) | 平均输入 Token | 缓存命中率 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for task, item in current.items():
        lines.append(
            f"| {task} | {item['samples']} | {item['p50_total_ms']} | {item['p95_total_ms']} | "
            f"{item['avg_retrieval_ms']} | {item['avg_generation_ms']} | {item['avg_audit_ms']} | "
            f"{item['avg_prompt_tokens']} | {float(item['cache_hit_rate']) * 100:.1f}% |"
        )
    if baseline is not None:
        lines.extend([
            "",
            "## 基线对比",
            "",
            "| 任务 | 指标 | 优化前 | 优化后 | 改善 |",
            "|---|---|---:|---:|---:|",
        ])
        for task in sorted(set(baseline) & set(current)):
            for label, key in (
                ("P50 总耗时", "p50_total_ms"),
                ("P95 总耗时", "p95_total_ms"),
                ("平均输入 Token", "avg_prompt_tokens"),
                ("平均检索耗时", "avg_retrieval_ms"),
                ("平均生成耗时", "avg_generation_ms"),
                ("平均审核耗时", "avg_audit_ms"),
            ):
                before = float(baseline[task].get(key, 0.0))
                after = float(current[task].get(key, 0.0))
                improvement = ((before - after) / before * 100) if before else 0.0
                lines.append(f"| {task} | {label} | {before:.3f} | {after:.3f} | {improvement:.1f}% |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_file", type=Path, help="Current JSONL trace file")
    parser.add_argument("--baseline", type=Path, help="Optional baseline JSONL trace file")
    parser.add_argument("--output", type=Path, help="Write Markdown report to this path")
    parser.add_argument("--json-output", type=Path, help="Write machine-readable summary")
    args = parser.parse_args()

    current_traces = load_traces(args.trace_file)
    if not current_traces:
        raise SystemExit(f"No ai_performance_trace entries found in {args.trace_file}")
    current = summarize(current_traces)
    baseline = summarize(load_traces(args.baseline)) if args.baseline else None
    report = markdown_report(current, baseline)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps({"current": current, "baseline": baseline}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
