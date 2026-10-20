"""Round-4 verification summary. Reads the evidence files and prints a digest.

Usage:
    python tests/global/summarize_round4.py
"""

from __future__ import annotations

import json
import pathlib
import sys

A = pathlib.Path("artifacts/global-testing")


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    section("middleware-integration.json")
    mw = json.loads((A / "middleware-integration.json").read_text(encoding="utf-8"))
    print(f"generated_at: {mw.get('generated_at')}")
    print(f"{'middleware':<20}{'level':<12}{'status':<10}{'sub?':<6}app code path")
    for row in mw["results"]:
        sub = row.get("substitution") or {}
        code = row.get("app_code_path") or "<none>"
        print(
            f"{row['middleware']:<20}{row['level']:<12}{row['status']:<10}"
            f"{str(sub.get('used')):<6}{code[:64]}"
        )

    section("e2e-results.json")
    e2e = json.loads((A / "e2e-results.json").read_text(encoding="utf-8"))
    print(f"base_url: {e2e.get('base_url')}   viewport: {e2e.get('viewport')}")
    print(f"browsers: {[(b.get('name'), b.get('version')) for b in e2e.get('browsers', [])]}")
    cases = e2e.get("cases", [])
    passed = sum(1 for c in cases if c["status"] == "passed")
    failed = sum(1 for c in cases if c["status"] == "failed")
    print(f"cases: {len(cases)}  passed: {passed}  failed: {failed}")
    for c in cases:
        print(f"   {c['id']:<28}{c['status']:<9}{c.get('failure_reason') or ''}")
    print(f"page_errors: {e2e.get('page_errors')}")
    print("axe violations per page:")
    for page in e2e.get("axe", []):
        print(f"   {page['page']:<24} {[(v['id'], v['impact'], v['nodes']) for v in page['violations']]}")

    section("perf-trend.json")
    trend = json.loads((A / "perf-trend.json").read_text(encoding="utf-8"))
    print(f"round4 cache hit rates : {trend['round4']['cache_hit_rates']}")
    print(f"round4 median hit rate : {trend['round4']['cache_hit_rate_median']}")
    print(f"round4 breaches        : {trend['round4']['breaches']}")
    print(f"any_regression         : {trend['any_regression']}")
    print(f"{'endpoint':<24}{'r3 p95':>10}{'r4 p95':>10}{'delta':>9}  regression")
    for row in trend["comparison"]:
        print(
            f"{row['label']:<24}{row['round3_baseline_p95_ms']!s:>10}"
            f"{row['round4_median_p95_ms']!s:>10}{row['delta_ms']!s:>9}  {row['regression']}"
        )

    section("coverage + api probe")
    cov = json.loads((A / "coverage.json").read_text(encoding="utf-8"))
    print(f"coverage: {round(cov['totals']['percent_covered'], 2)}% "
          f"({cov['totals']['covered_lines']}/{cov['totals']['num_statements']})")
    probe = json.loads((A / "api-probe-postfix.json").read_text(encoding="utf-8"))
    if isinstance(probe, dict):
        summary = probe.get("summary") or {
            k: probe.get(k) for k in ("pass", "fail", "error", "manual_only", "total")
        }
        print(f"api probe summary: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
