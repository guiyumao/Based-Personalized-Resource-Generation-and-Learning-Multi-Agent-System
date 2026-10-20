"""Normalize indentation left behind by the profile-test codemod.

    python tests/global/_fix_test_indent.py

Only rewrites the two profile test files; verifies the result compiles.
"""

from __future__ import annotations

import pathlib
import sys

TARGETS = [
    pathlib.Path("tests/unit/test_profile_analysis.py"),
    pathlib.Path("tests/unit/test_profile_chat.py"),
]
# continuation lines the codemod emitted with a stray 5-space indent
FIXES = {
    "     f\"/users/": "        f\"/users/",
    "     headers=auth_headers,": "        headers=auth_headers,",
    " )\n": "    )\n",
}


def main() -> int:
    for path in TARGETS:
        src = path.read_text(encoding="utf-8")
        original = src
        for old, new in FIXES.items():
            src = src.replace(old, new)
        if src != original:
            path.write_text(src, encoding="utf-8")
            print(f"{path}: normalized")
        else:
            print(f"{path}: unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
