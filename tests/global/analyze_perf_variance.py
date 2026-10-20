"""Variance analysis for the round-4 performance samples.

The regression gate compares medians across rounds, which can hide single-round
spikes. This script prints the full sample distribution per endpoint so a spike
can be classified as a transient outlier or a sustained slowdown.

Usage:
    python tests/global/analyze_perf_variance.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys

ARTIFACTS = pathlib.Path("artifacts/global-testing")
FILES = [ARTIFACTS / f"_r4-perf-round{i}.json" for i in (1, 2, 3)]


def main() -> int:
    rounds = [json.loads(p.read_text(encoding="utf-8")) for p in FILES]
    by_label: dict[str, list[dict]] = {}
    for report in rounds:
        for result in report.get("results", []):
            by_label.setdefault(result["label"], []).append(result)

    rows = []
    print(f"{'endpoint':<24}{'n':>4}{'min':>9}{'med':>9}{'max':>9}{'stdev':>9}  outliers")
    for label, runs in sorted(by_label.items()):
        samples = [s for r in runs for s in r.get("samples_ms", [])] + [
            r.get("cold_start_ms") for r in runs if isinstance(r.get("cold_start_ms"), (int, float))
        ]
        if not samples:
            continue
        med = statistics.median(samples)
        stdev = statistics.stdev(samples) if len(samples) > 1 else 0.0
        outliers = [round(s, 1) for s in samples if stdev and s > med + 2 * stdev]
        rows.append(
            {
                "label": label,
                "n": len(samples),
                "min_ms": round(min(samples), 1),
                "median_ms": round(med, 1),
                "max_ms": round(max(samples), 1),
                "stdev_ms": round(stdev, 1),
                "spike_samples": outliers,
                "per_round_p95": [r.get("p95_ms") for r in runs],
            }
        )
        print(
            f"{label:<24}{len(samples):>4}{min(samples):>9.1f}{med:>9.1f}"
            f"{max(samples):>9.1f}{stdev:>9.1f}  {outliers or '-'}"
        )

    out = ARTIFACTS / "perf-variance.json"
    out.write_text(
        json.dumps(
            {
                "files": [p.name for p in FILES],
                "note": (
                    "Outliers are samples above median + 2 stdev within this 3-round pool. "
                    "Single-request spikes on a shared developer workstation are expected; "
                    "they are reported rather than discarded."
                ),
                "endpoints": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
