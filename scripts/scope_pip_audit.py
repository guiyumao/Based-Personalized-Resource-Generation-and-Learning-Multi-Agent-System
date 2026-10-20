"""Scope a pip-audit report down to the dependencies this project declares.

The shared Anaconda interpreter also contains several hundred unrelated
pre-installed packages, so a raw ``pip-audit`` run reports their advisories too.
This script answers the question that actually matters for a release gate:
*which advisories belong to the dependency closure declared in pyproject.toml?*

It never hides anything: both the project-scoped and the environment-wide counts
are written to the output so the residual risk stays visible.

Usage:
    python scripts/scope_pip_audit.py artifacts/global-testing/pip-audit-report.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _declared_names() -> tuple[set[str], str]:
    payload = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = payload.get("project", {})
    raw = list(project.get("dependencies", []))
    for group in (project.get("optional-dependencies") or {}).values():
        raw.extend(group)
    names = set()
    for spec in raw:
        name = re.split(r"[<>=!\[; ]", spec.strip(), maxsplit=1)[0].strip()
        if name:
            names.add(name.lower().replace("_", "-"))
    return names, str(project.get("version", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scope pip-audit output to project dependencies")
    parser.add_argument("report")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if tomllib is None:
        print("FAIL: python>=3.11 required for tomllib")
        return 1

    declared, version = _declared_names()
    report = json.loads(pathlib.Path(args.report).read_text(encoding="utf-8"))
    deps = report.get("dependencies", [])

    in_scope = []
    for dep in deps:
        name = str(dep.get("name", "")).lower().replace("_", "-")
        vulns = dep.get("vulns") or []
        if not vulns:
            continue
        entry = {
            "name": dep["name"],
            "version": dep.get("version"),
            "declared": name in declared,
            "findings": [
                {
                    "id": v.get("id"),
                    "fix_versions": v.get("fix_versions") or [],
                    "aliases": v.get("aliases") or [],
                }
                for v in vulns
            ],
        }
        in_scope.append(entry)

    project_scope = [e for e in in_scope if e["declared"]]
    environment_only = [e for e in in_scope if not e["declared"]]

    def _count(entries: list[dict]) -> int:
        return sum(len(e["findings"]) for e in entries)

    fixable = [
        {"package": e["name"], "version": e["version"], "id": f["id"], "fix": f["fix_versions"]}
        for e in project_scope
        for f in e["findings"]
        if f["fix_versions"]
    ]

    result = {
        "project_version": version,
        "declared_dependency_count": len(declared),
        "packages_scanned_in_environment": len(deps),
        "environment_wide": {
            "packages_with_findings": len(in_scope),
            "finding_count": _count(in_scope),
            "note": (
                "Includes unrelated pre-installed Anaconda packages. "
                "This is NOT the project's risk surface but is reported for honesty."
            ),
        },
        "project_scope": {
            "packages_with_findings": len(project_scope),
            "finding_count": _count(project_scope),
            "entries": project_scope,
        },
        "environment_only_top": sorted(
            environment_only, key=lambda e: len(e["findings"]), reverse=True
        )[:15],
        "fixable_in_project_scope": fixable,
    }

    print(f"declared project dependencies : {len(declared)}")
    print(f"packages scanned (environment): {len(deps)}")
    print(f"environment-wide findings     : {_count(in_scope)} in {len(in_scope)} packages")
    print(f"PROJECT-SCOPE findings        : {_count(project_scope)} in {len(project_scope)} packages")
    for entry in project_scope:
        for finding in entry["findings"]:
            fix = ", ".join(finding["fix_versions"]) or "NONE"
            print(f"  {entry['name']:16} {entry['version']:12} {finding['id']:20} fix={fix}")
    if fixable:
        print()
        print("BLOCKING: a fix version exists for the following project dependencies:")
        for item in fixable:
            print(f"  {item['package']} {item['version']} {item['id']} -> {item['fix']}")
    else:
        print()
        print("No project-scope finding has an upstream fix version.")

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"scoped report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
