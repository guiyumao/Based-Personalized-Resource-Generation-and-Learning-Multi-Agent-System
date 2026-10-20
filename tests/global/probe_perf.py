"""Latency / SLO probe for the locally running services.

Complements ``probe_api.py`` (which checks *correctness*) by measuring *how fast*
each representative endpoint responds, so performance regressions and the
knowledge-graph hot spot stay visible.

Usage:
    python tests/global/probe_perf.py --out artifacts/global-testing/perf-probe.json
    python tests/global/probe_perf.py --repeat 5 --only graph

SLO policy encoded below (see the test report, section on quality gates):
* plain reads/writes          P95 <= 500 ms
* AI-backed endpoints         reported only, no hard gate (LLM-bound)
* anonymous/health endpoints P95 <= 200 ms

Only 127.0.0.1 is targeted, and the probe creates its own throwaway account.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys
import time
import uuid

import httpx

USER = os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001")
AGENT = os.getenv("AGENT_SERVICE_URL", "http://127.0.0.1:8002")
EVALUATION = os.getenv("EVALUATION_SERVICE_URL", "http://127.0.0.1:8004")
RESOURCE = os.getenv("RESOURCE_SERVICE_URL", "http://127.0.0.1:8003")

SLO_MS = {"fast": 200.0, "normal": 500.0, "graph": 2000.0}


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(pct / 100 * len(ordered) + 0.5)) - 1))
    return ordered[index]


def _fetch_cache_stats(client: httpx.Client, url: str, auth: dict[str, str]) -> dict | None:
    """Read the graph cache counters; returns None when unavailable."""

    try:
        response = client.get(url, headers=auth)
        if response.status_code == 200:
            return response.json()
        return {"error": f"HTTP {response.status_code}"}
    except httpx.HTTPError as exc:
        return {"error": type(exc).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Latency / SLO probe (localhost only)")
    parser.add_argument("--repeat", type=int, default=5, help="requests per endpoint")
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="skip the warm-up pass so the first touch is included in the samples",
    )
    parser.add_argument("--only", default=None, help="health | read | ai | graph")
    parser.add_argument("--out", default=None, help="JSON report path")
    args = parser.parse_args(argv)

    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    with httpx.Client(timeout=90) as client:
        reg = client.post(
            f"{USER}/users/register",
            json={
                "username": f"perf_{suffix}",
                "email": f"perf_{suffix}@example.com",
                "password": "Probe#Passw0rd123",
                "role": "student",
            },
        )
        reg.raise_for_status()
        payload = reg.json()
        user_id = payload["user_id"]
        auth = {"Authorization": f"Bearer {payload['access_token']}"}

        # (group, label, method, url, kwargs, slo_kind)
        cases: list[tuple[str, str, str, str, dict, str]] = [
            ("health", "user health", "GET", f"{USER}/health", {}, "fast"),
            ("health", "agent health", "GET", f"{AGENT}/health", {}, "fast"),
            ("read", "users/me", "GET", f"{USER}/users/me", {"headers": auth}, "normal"),
            (
                "read",
                "own profile",
                "GET",
                f"{USER}/users/{user_id}/profile",
                {"headers": auth},
                "normal",
            ),
            (
                "read",
                "profile status",
                "GET",
                f"{USER}/users/{user_id}/profile/status",
                {"headers": auth},
                "normal",
            ),
            ("read", "resource list", "GET", f"{RESOURCE}/resources", {}, "normal"),
            ("read", "kb subjects", "GET", f"{AGENT}/knowledge-base/subjects", {}, "normal"),
            (
                "read",
                "mistakes",
                "GET",
                f"{EVALUATION}/evaluation/mistakes/{user_id}",
                {"headers": auth},
                "normal",
            ),
            (
                "ai",
                "chat session create",
                "POST",
                f"{AGENT}/chat/sessions/new",
                {"headers": auth, "json": {"user_id": user_id, "title": "perf"}},
                "ai",
            ),
            (
                "graph",
                "graph visualization",
                "POST",
                f"{AGENT}/graph/visualization",
                {"headers": auth, "json": {"knowledge_point": "数据结构的栈与队列"}},
                "graph",
            ),
        ]
        # Optional authenticated probe of the graph cache counters (teacher/admin
        # only). When unavailable the cache-hit rate is reported as null instead of
        # being guessed from latency.
        cache_stats_url = f"{AGENT}/graph/cache-stats"

        results: list[dict] = []
        cold_start_ms: dict[str, float] = {}
        cache_stats: dict | None = None
        for group, label, method, url, kwargs, slo_kind in cases:
            if args.only and args.only != group:
                continue

            # Warm-up pass: the first touch of an endpoint absorbs one-off costs
            # (lazy imports, cache priming, connection setup). It is reported
            # separately as cold_start_ms instead of polluting the percentiles.
            if not args.no_warmup:
                started = time.perf_counter()
                try:
                    client.request(method, url, **kwargs)
                except httpx.HTTPError:
                    pass
                cold_start_ms[label] = round((time.perf_counter() - started) * 1000, 1)

            samples: list[float] = []
            status = None
            for _ in range(args.repeat):
                started = time.perf_counter()
                try:
                    response = client.request(method, url, **kwargs)
                    status = response.status_code
                except httpx.HTTPError as exc:
                    status = f"error:{type(exc).__name__}"
                samples.append((time.perf_counter() - started) * 1000)

            p50, p95, worst = statistics.median(samples), _pct(samples, 95), max(samples)
            p99 = _pct(samples, 99)
            slo = SLO_MS.get(slo_kind)
            verdict = "no-gate" if slo is None else ("pass" if p95 <= slo else "breach")
            results.append(
                {
                    "group": group,
                    "label": label,
                    "method": method,
                    "url": url.replace("http://127.0.0.1", ""),
                    "samples_ms": [round(s, 1) for s in samples],
                    "p50_ms": round(p50, 1),
                    "p95_ms": round(p95, 1),
                    "p99_ms": round(p99, 1),
                    "max_ms": round(worst, 1),
                    "cold_start_ms": cold_start_ms.get(label),
                    "status": status,
                    "slo_kind": slo_kind,
                    "slo_ms": slo,
                    "verdict": verdict,
                }
            )
            print(
                f"{label:<24} p50={p50:8.1f}ms p95={p95:8.1f}ms "
                f"p99={p99:8.1f}ms cold={cold_start_ms.get(label, float('nan')):8.1f}ms  {verdict}"
            )

        # Read the cache counters while the client is still open.
        cache_stats = _fetch_cache_stats(client, cache_stats_url, auth)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "target": "127.0.0.1 local development services",
        "repeat": args.repeat,
        "warmup": not args.no_warmup,
        "slo_policy_ms": SLO_MS,
        "breaches": [r["label"] for r in results if r["verdict"] == "breach"],
        "cold_start_ms": cold_start_ms,
        "cache_stats": cache_stats,
        "results": results,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[perf] report written to {out}")
    print(f"[perf] breaches: {report['breaches'] or 'none'}")
    return 1 if report["breaches"] else 0


if __name__ == "__main__":
    sys.exit(main())
