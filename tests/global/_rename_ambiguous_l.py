"""One-off codemod: rename the ambiguous loop variable ``l`` in the graph connector.

Ruff E741 flags ``l`` as ambiguous. The rename is limited to the exact expression
shapes used in this file so no unrelated identifier is touched.

    python tests/global/_rename_ambiguous_l.py
"""

from __future__ import annotations

import pathlib
import sys

TARGET = pathlib.Path("services/agent_service/app/connectors/neo4j_connector.py")

REPLACEMENTS = [
    # comprehension filters
    ('[l for l in llm_result["prereqs"] if self._is_meaningful_label(l, kp)]',
     '[label for label in llm_result["prereqs"] if self._is_meaningful_label(label, kp)]'),
    ('[l for l in llm_result["recs"] if self._is_meaningful_label(l, kp)]',
     '[label for label in llm_result["recs"] if self._is_meaningful_label(label, kp)]'),
    ('[l for l in labels if self._is_meaningful_label(l, kp)]',
     '[label for label in labels if self._is_meaningful_label(label, kp)]'),
    # _finalize_labels loop
    ("        for l in n:\n            if not l or l == nkp:\n                continue\n            res.append(l)",
     "        for label in n:\n            if not label or label == nkp:\n                continue\n            res.append(label)"),
]

# _clean_text_label body: each statement assigns/uses `l`
CLEAN_BLOCK_OLD = """        l = re.sub(r"^[\\-\\*\\d\\.\\s]+", "", value).strip()"""
CLEAN_BLOCK_MARKER = 'l = re.sub('


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    original = src
    for old, new in REPLACEMENTS:
        src = src.replace(old, new)

    # Rename the local variable inside _clean_text_label only.
    start = src.find("def _clean_text_label(")
    if start == -1:
        print("_clean_text_label not found", file=sys.stderr)
        return 1
    end = src.find("\n    def ", start + 1)
    block = src[start:end if end != -1 else len(src)]
    if CLEAN_BLOCK_MARKER in block:
        # word-boundary rename of the single-letter name within this block
        import re

        renamed = re.sub(r"\bl\b", "cleaned", block)
        src = src[:start] + renamed + (src[end:] if end != -1 else "")

    if src == original:
        print("no change")
        return 0
    TARGET.write_text(src, encoding="utf-8")
    print(f"patched {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
