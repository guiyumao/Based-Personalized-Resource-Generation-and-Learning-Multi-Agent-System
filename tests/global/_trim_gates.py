"""Trim stale sections appended after the round-3 rewrite of a deliverable.

Used for ``05-regression-and-gates.md``: the round-3 content was prepended while
the round-2 body remained below it. Everything from the second occurrence of the
section marker onward is stale.

    python tests/global/_trim_gates.py
"""

from __future__ import annotations

import pathlib
import sys

TARGET = pathlib.Path("artifacts/global-testing/05-regression-and-gates.md")
MARKER = "## 1. 冒烟集"


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    first = text.find(MARKER)
    if first == -1:
        print("marker not found")
        return 1
    second = text.find(MARKER, first + 1)
    if second == -1:
        print("no stale section found; nothing to trim")
        return 0
    trimmed = text[:second].rstrip() + "\n"
    TARGET.write_text(trimmed, encoding="utf-8")
    print(f"trimmed {len(text) - len(trimmed)} characters of stale content")
    return 0


if __name__ == "__main__":
    sys.exit(main())
