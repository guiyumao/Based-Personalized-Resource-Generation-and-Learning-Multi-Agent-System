"""Reconcile the round-4 pip-audit result against the round-3 recorded findings.

Round 3 recorded 8 findings across chromadb / ecdsa / python-jose. This script
compares that record with the current report and prints every difference so the
change is explained rather than silently absorbed.

Usage:
    python tests/global/reconcile_pip_audit.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ARTIFACTS = pathlib.Path("artifacts/global-testing")
REPORT = ARTIFACTS / "pip-audit-report.json"

# What round 3 recorded in defect-register.md / 03-test-report.md.
ROUND3_RECORDED = {
    ("chromadb", "PYSEC-2026-311"): 2,
    ("chromadb", "PYSEC-2026-3813"): 1,
    ("chromadb", "PYSEC-2026-3814"): 1,
    ("chromadb", "PYSEC-2026-3815"): 1,
    ("ecdsa", "PYSEC-2026-1325"): 2,
    ("python-jose", "CVE-2026-85394"): 1,
}


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    deps = report.get("dependencies", [])

    current: dict[tuple[str, str], int] = {}
    versions: dict[str, str] = {}
    for dep in deps:
        name = str(dep.get("name", "")).lower()
        versions[name] = str(dep.get("version"))
        for vuln in dep.get("vulns") or []:
            key = (name, str(vuln.get("id")))
            current[key] = current.get(key, 0) + 1

    print(f"packages in report: {len(deps)}")
    print(f"packages with findings: {len({k[0] for k in current})}")
    print(f"total findings: {sum(current.values())}")
    print()

    print("--- round-3 recorded findings, re-checked now ---")
    for key, recorded in sorted(ROUND3_RECORDED.items()):
        package, advisory = key
        now = current.get(key, 0)
        installed = versions.get(package, "<not in report>")
        if now == 0:
            print(f"  GONE     {package:14} {advisory:20} recorded={recorded} now=0  installed={installed}")
        elif now != recorded:
            print(f"  CHANGED  {package:14} {advisory:20} recorded={recorded} now={now}  installed={installed}")
        else:
            print(f"  SAME     {package:14} {advisory:20} recorded={recorded} now={now}  installed={installed}")

    print()
    print("--- findings present now but NOT recorded in round 3 ---")
    new_keys = sorted(set(current) - set(ROUND3_RECORDED))
    for key in new_keys:
        package, advisory = key
        print(f"  NEW      {package:16} {advisory:20} count={current[key]}  version={versions.get(package)}")
    if not new_keys:
        print("  (none)")

    print()
    print("--- is ecdsa still installed and scanned? ---")
    print(f"  ecdsa in report: {'ecdsa' in versions} version={versions.get('ecdsa')}")
    try:
        import importlib.metadata as md

        print(f"  ecdsa importable : {md.version('ecdsa')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ecdsa importable : NO ({type(exc).__name__})")

    out = ARTIFACTS / "pip-audit-reconciliation.json"
    out.write_text(
        json.dumps(
            {
                "round3_recorded": {f"{k[0]}|{k[1]}": v for k, v in ROUND3_RECORDED.items()},
                "current": {f"{k[0]}|{k[1]}": v for k, v in current.items()},
                "new_since_round3": [f"{k[0]}|{k[1]}" for k in new_keys],
                "missing_since_round3": [
                    f"{k[0]}|{k[1]}" for k in ROUND3_RECORDED if k not in current
                ],
                "installed_versions": versions,
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
