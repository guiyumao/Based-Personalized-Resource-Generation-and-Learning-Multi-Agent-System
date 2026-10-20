"""Classify working-tree diff hunks as pure-reflow (formatter) vs substantive.

Background
----------
A previous session ran ``ruff format`` across the repository, which reflowed files
that also carry the user's own uncommitted work. A plain ``git diff`` cannot tell
the two apart, and refusing to guess matters more than tidiness here.

Method
------
For every added line we look for a *matching* removed line elsewhere in the same
file's diff after both are normalised:

* collapse all whitespace runs to a single space
* strip trailing commas and wrapping parentheses

If every added line has such a partner and vice versa, the hunk is wrapping noise.
Anything unmatched is substantive and must be preserved.

This is a heuristic report, not an automatic rewriter.
"""

from __future__ import annotations

import re
import subprocess
import sys

NORMALISE = [
    (re.compile(r"\s+"), " "),
    (re.compile(r",\s*\)"), ")"),
    (re.compile(r"\(\s*"), "("),
]


def _norm(line: str) -> str:
    text = line.strip()
    text = text.lstrip("+-").strip()
    for pattern, repl in NORMALISE:
        text = pattern.sub(repl, text)
    return text


def _diff(path: str) -> tuple[list[str], list[str]]:
    out = subprocess.run(
        ["git", "diff", "--no-color", "--unified=0", "--", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    added = [ln for ln in out.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln for ln in out.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    return added, removed


def main(paths: list[str]) -> int:
    print(f"{'file':<58} {'added':>6} {'removed':>8} {'noise%':>7}  verdict")
    print("-" * 100)
    for path in paths:
        added, removed = _diff(path)
        if not added and not removed:
            print(f"{path.split('/')[-1]:<58} {'-':>6} {'-':>8} {'-':>7}  no diff vs HEAD")
            continue

        remaining_removed = [_norm(x) for x in removed]
        matched_added = 0
        leftover_removed: list[str] = list(remaining_removed)
        for line in added:
            key = _norm(line)
            if key in leftover_removed:
                leftover_removed.remove(key)
                matched_added += 1
        total = max(len(added), 1)
        noise = matched_added / total * 100
        verdict = "mostly reflow" if noise >= 80 else ("mixed" if noise >= 30 else "substantive")
        print(
            f"{path.split('/')[-1]:<58} {len(added):>6} {len(removed):>8} {noise:>6.1f}%  {verdict}"
        )
        if len(leftover_removed) <= 6 and leftover_removed:
            for line in leftover_removed:
                print(f"      unmatched-removed> {line[:96]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
