"""Trim the round-2 tail from the round-3 test report.

`Set-Content` previously corrupted the encoding; this versioned helper does the
edit in Python with explicit UTF-8 so it can be reviewed and re-run safely.

    python tests/global/_trim_report.py
"""

from __future__ import annotations

import pathlib
import sys

TARGET = pathlib.Path("artifacts/global-testing/03-test-report.md")
#: The round-2 report begins at the second occurrence of this heading.
MARKER = "## 1. 摘要（结论先行）"


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    first = text.find(MARKER)
    if first == -1:
        print("round-3 heading not found")
        return 1
    second = text.find(MARKER, first + 1)
    if second == -1:
        print("no stale round-2 section found; nothing to trim")
        return 0

    trimmed = text[:second].rstrip() + "\n"
    TARGET.write_text(trimmed, encoding="utf-8")
    print(f"trimmed {len(text) - len(trimmed)} characters of stale round-2 content")
    return 0


if __name__ == "__main__":
    sys.exit(main())
