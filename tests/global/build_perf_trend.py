"""Aggregate round-4 performance rounds into a trend record and run the gate.

Combines the round-3 historical baseline with the fresh round-4 samples so the
long-term trend is comparable, then applies the existing regression policy
(p95 <= baseline x1.2 AND an absolute increase > 25 ms).

Usage:
    python tests/global/build_perf_trend.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time

ARTIFACTS = pathlib.Path("artifacts/global-testing")
BASELINE = ARTIFACTS / "perf-baseline.json"
ROUND_FILES = [ARTIFACTS / f"_r4-perf-round{i}.json" for i in (1, 2, 3)]
TREND_OUT = ARTIFACTS / "perf-trend.json"
AGG_OUT = ARTIFACTS / "_r4-perf-aggregate.json"


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    baseline = _load(BASELINE)
    rounds = [_load(p) for p in ROUND_FILES]

    by_label: dict[str, list[dict]] = {}
    for report in rounds:
        for result in report.get("results", []):
            by_label.setdefault(result["label"], []).append(result)

    endpoints = []
    for label, runs in sorted(by_label.items()):
        def median(field: str, _runs: list[dict] = runs):
            values = [r.get(field) for r in _runs if isinstance(r.get(field), (int, float))]
            return round(statistics.median(values), 1) if values else None

        endpoints.append(
            {
                "label": label,
                "group": runs[0]["group"],
                "url": runs[0]["url"],
                "method": runs[0]["method"],
                "rounds": len(runs),
                "p50_ms": median("p50_ms"),
                "p95_ms": median("p95_ms"),
                "p99_ms": median("p99_ms"),
                "max_ms": round(max(r["max_ms"] for r in runs if r.get("max_ms") is not None), 1),
                "cold_start_ms": median("cold_start_ms"),
                "slo_ms": runs[0].get("slo_ms"),
                "slo_kind": runs[0].get("slo_kind"),
                "all_rounds_passed": all(r.get("verdict") in {"pass", "no-gate"} for r in runs),
            }
        )

    cache_samples = [r.get("cache_stats") for r in rounds if isinstance(r.get("cache_stats"), dict)]
    hit_rates = [c["hit_rate"] for c in cache_samples if isinstance(c.get("hit_rate"), (int, float))]
    breaches = sorted({b for r in rounds for b in r.get("breaches", [])})

    aggregate = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rounds_aggregated": len(rounds),
        "breaches": breaches,
        "cache_stats": cache_samples[-1] if cache_samples else None,
        "results": [
            {
                "label": e["label"],
                "group": e["group"],
                "url": e["url"],
                "method": e["method"],
                "p50_ms": e["p50_ms"],
                "p95_ms": e["p95_ms"],
                "p99_ms": e["p99_ms"],
                "max_ms": e["max_ms"],
                "cold_start_ms": e["cold_start_ms"],
                "slo_ms": e["slo_ms"],
                "slo_kind": e["slo_kind"],
                "verdict": "pass" if e["all_rounds_passed"] else "breach",
            }
            for e in endpoints
        ],
    }
    AGG_OUT.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")

    base_by_label = {e["label"]: e for e in baseline.get("endpoints", [])}
    trend_rows = []
    for entry in endpoints:
        ref = base_by_label.get(entry["label"], {})
        base_p95 = ref.get("p95_ms")
        cur_p95 = entry["p95_ms"]
        delta = round(cur_p95 - base_p95, 1) if (base_p95 and cur_p95) else None
        limit = round(base_p95 * 1.2, 1) if base_p95 else None
        regressed = bool(
            base_p95 and cur_p95 and cur_p95 > limit and (delta or 0) > 25.0
        )
        trend_rows.append(
            {
                "label": entry["label"],
                "round3_baseline_p95_ms": base_p95,
                "round4_median_p95_ms": cur_p95,
                "delta_ms": delta,
                "relative_limit_ms": limit,
                "relative_exceeded": bool(base_p95 and cur_p95 and cur_p95 > limit),
                "regression": regressed,
                "absolute_slo_ms": entry["slo_ms"],
                "slo_ok": (cur_p95 is None or entry["slo_ms"] is None or cur_p95 <= entry["slo_ms"]),
            }
        )

    trend = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "policy": baseline.get("policy"),
        "round3_baseline": {
            "rounds_aggregated": baseline.get("rounds_aggregated"),
            "cache_hit_rate_median": baseline.get("cache_hit_rate_median"),
            "endpoints": {
                e["label"]: {
                    "p50_ms": e["p50_ms"],
                    "p95_ms": e["p95_ms"],
                    "p99_ms": e["p99_ms"],
                    "cold_start_ms": e["cold_start_ms"],
                }
                for e in baseline.get("endpoints", [])
            },
        },
        "round4": {
            "rounds_aggregated": len(rounds),
            "round_files": [p.name for p in ROUND_FILES],
            "cache_hit_rates": hit_rates,
            "cache_hit_rate_median": round(statistics.median(hit_rates), 4) if hit_rates else None,
            "breaches": breaches,
            "endpoints": {
                e["label"]: {
                    "p50_ms": e["p50_ms"],
                    "p95_ms": e["p95_ms"],
                    "p99_ms": e["p99_ms"],
                    "cold_start_ms": e["cold_start_ms"],
                }
                for e in endpoints
            },
        },
        "comparison": trend_rows,
        "any_regression": any(r["regression"] for r in trend_rows),
    }
    TREND_OUT.write_text(json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'endpoint':<24}{'r3 p95':>10}{'r4 p95':>10}{'delta':>9}{'x1.2':>9}  verdict")
    for row in trend_rows:
        verdict = "REGRESSED" if row["regression"] else ("within-noise" if row["relative_exceeded"] else "ok")
        if not row["slo_ok"]:
            verdict = "SLO-BREACH"
        print(
            f"{row['label']:<24}{row['round3_baseline_p95_ms']!s:>10}"
            f"{row['round4_median_p95_ms']!s:>10}{row['delta_ms']!s:>9}"
            f"{row['relative_limit_ms']!s:>9}  {verdict}"
        )
    print()
    print(f"round-4 cache hit rates : {hit_rates}")
    print(f"round-4 breaches        : {breaches or 'none'}")
    print(f"any regression          : {trend['any_regression']}")
    print(f"trend written to {TREND_OUT}")
    return 1 if trend["any_regression"] or breaches else 0


if __name__ == "__main__":
    sys.exit(main())
