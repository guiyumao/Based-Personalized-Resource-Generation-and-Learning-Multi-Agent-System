"""Aggregate several probe_perf.py JSON reports into a historical baseline.

The first real measurement round becomes the baseline; later runs are compared
against it with the policy ``p95 <= baseline * 1.2`` (plus fixed absolute SLOs).

Usage:
    python tests/global/build_perf_baseline.py \
        --inputs artifacts/global-testing/_base-r1.json ... \
        --out artifacts/global-testing/perf-baseline.json
    python tests/global/build_perf_baseline.py --check current.json \
        --baseline artifacts/global-testing/perf-baseline.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

REGRESSION_FACTOR = 1.2

#: Absolute floor below which a relative regression is measurement noise rather
#: than a real slowdown. Scheduling jitter on a 30ms endpoint easily exceeds 20%
#: between runs, so a pure ×1.2 rule produces false positives. A regression is
#: only reported when BOTH the relative and the absolute condition hold.
REGRESSION_MIN_DELTA_MS = 25.0


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregate(reports: list[dict]) -> dict:
    by_label: dict[str, list[dict]] = {}
    for report in reports:
        for result in report.get("results", []):
            by_label.setdefault(result["label"], []).append(result)

    endpoints = []
    for label, runs in sorted(by_label.items()):

        def median(field: str, _runs: list[dict] = runs) -> float | None:
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
                "samples_ms": [s for r in runs for s in r.get("samples_ms", [])],
            }
        )

    cache_stats = [r.get("cache_stats") for r in reports if isinstance(r.get("cache_stats"), dict)]
    hit_rates = [c["hit_rate"] for c in cache_stats if isinstance(c.get("hit_rate"), (int, float))]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "role": "historical performance baseline (round 3, first real measurement)",
        "policy": {
            "regression_factor": REGRESSION_FACTOR,
            "min_absolute_delta_ms": REGRESSION_MIN_DELTA_MS,
            "rule": (
                "p95 must not exceed baseline p95 x1.2 AND must not exceed it by more than "
                f"{REGRESSION_MIN_DELTA_MS} ms; the absolute floor suppresses jitter false "
                "positives on low-latency endpoints"
            ),
            "absolute_slo_ms": {"fast": 200.0, "normal": 500.0, "graph": 2000.0},
        },
        "rounds_aggregated": len(reports),
        "cache_hit_rate_median": round(statistics.median(hit_rates), 4) if hit_rates else None,
        "cache_stats_samples": cache_stats,
        "endpoints": endpoints,
    }


def _check(current: dict, baseline: dict) -> int:
    base = {e["label"]: e for e in baseline.get("endpoints", [])}
    failures: list[str] = []
    notes: list[str] = []

    for result in current.get("results", []):
        label = result["label"]
        reference = base.get(label)
        if reference is None:
            notes.append(f"{label}: new endpoint, no baseline to compare")
            continue

        p95 = result.get("p95_ms")
        base_p95 = reference.get("p95_ms")
        if p95 is not None and base_p95:
            limit = base_p95 * REGRESSION_FACTOR
            delta = p95 - base_p95
            # Require both a relative breach and a meaningful absolute increase.
            if p95 > limit and delta > REGRESSION_MIN_DELTA_MS:
                failures.append(
                    f"{label}: p95 {p95:.1f}ms > baseline {base_p95:.1f}ms x1.2 ({limit:.1f}ms) "
                    f"and +{delta:.1f}ms > floor {REGRESSION_MIN_DELTA_MS:.0f}ms"
                )
            elif p95 > limit:
                notes.append(
                    f"{label}: p95 {p95:.1f}ms is >x1.2 of baseline {base_p95:.1f}ms but only "
                    f"+{delta:.1f}ms, within the {REGRESSION_MIN_DELTA_MS:.0f}ms noise floor"
                )

        slo = result.get("slo_ms")
        if slo is not None and p95 is not None and p95 > slo:
            failures.append(f"{label}: p95 {p95:.1f}ms exceeds absolute SLO {slo:.0f}ms")

    for note in notes:
        print(f"  NOTE      {note}")
    for failure in failures:
        print(f"  REGRESSED {failure}")
    if failures:
        print("RESULT: FAIL (performance regression)")
        return 1
    print("RESULT: PASS (no regression beyond baseline x1.2)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or check the performance baseline")
    parser.add_argument("--inputs", nargs="*", default=[], help="probe_perf.py reports to aggregate")
    parser.add_argument("--out", default=None, help="baseline output path")
    parser.add_argument("--check", default=None, help="a current report to compare")
    parser.add_argument("--baseline", default=None, help="baseline to compare against")
    args = parser.parse_args(argv)

    if args.check:
        if not args.baseline:
            print("--check requires --baseline")
            return 1
        return _check(_load(pathlib.Path(args.check)), _load(pathlib.Path(args.baseline)))

    if not args.inputs or not args.out:
        print("building requires --inputs and --out")
        return 1

    reports = [_load(pathlib.Path(p)) for p in args.inputs]
    baseline = _aggregate(reports)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"baseline written to {out}")
    print(f"  rounds aggregated : {baseline['rounds_aggregated']}")
    print(f"  cache hit rate    : {baseline['cache_hit_rate_median']}")
    print(f"{'endpoint':<24} {'p50':>9} {'p95':>9} {'p99':>9} {'cold':>9}  passed")
    for endpoint in baseline["endpoints"]:
        print(
            f"{endpoint['label']:<24} {endpoint['p50_ms']:>9} {endpoint['p95_ms']:>9} "
            f"{endpoint['p99_ms']:>9} {str(endpoint['cold_start_ms']):>9}  {endpoint['all_rounds_passed']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
