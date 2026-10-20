"""One-off codemod: add `self-or-admin` ownership guards to evaluation report reads.

Kept next to the other global-testing tooling for auditability. Run from the repo root:

    python tests/global/_patch_eval_auth.py

It is idempotent: running it twice does not duplicate imports or guards.
"""

from __future__ import annotations

import pathlib
import re
import sys

TARGET = pathlib.Path("services/evaluation_service/app/api/routes/reports.py")

#: Bump this if the codemod is ever re-run on an already-patched tree. The script
#: refuses to touch the file once the marker is present, so a repeat invocation can
#: no longer re-insert the import block and create F811 redefinitions.
DONE_MARKER = "require_self_or_staff(user_id, current_user)"

IMPORT_MARKER = "from common.dependencies import get_current_user, require_role, require_self_or_admin"
DEP_OLD = "from fastapi import APIRouter, HTTPException"
DEP_NEW = "from fastapi import APIRouter, Depends, HTTPException"

# (endpoint function name, teacher-or-admin instead of self-or-admin)
TEACHER_ONLY = {"get_teacher_mistake_notebook"}


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    if DONE_MARKER in src:
        print("already patched; refusing to re-apply (avoids duplicate imports)")
        return 0
    original = src

    if IMPORT_MARKER not in src:
        src = src.replace(DEP_OLD, DEP_NEW)
        src = src.replace(
            "from common.config import get_settings",
            "from common.config import get_settings\n"
            f"{IMPORT_MARKER}\n"
            "from common.models.learning import User",
            1,
        )

    sig = re.compile(r"(async def (?:get|clear)_\w+\(user_id: int)\) ->")
    src = sig.sub(
        r"\1, current_user: User = Depends(get_current_user)) ->",
        src,
    )

    guard_re = re.compile(
        r'(async def ((?:get|clear)_\w+)\(user_id: int, current_user: User = Depends\(get_current_user\)\) -> [^\n]*\n    """[^"]*""")'
    )

    def add_guard(match: re.Match[str]) -> str:
        block, name = match.group(1), match.group(2)
        if "require_self_or_admin(user_id, current_user)" in src[match.end():match.end() + 200]:
            return block
        if name in TEACHER_ONLY:
            return block + "\n\n    require_self_or_staff(user_id, current_user)"
        return block + "\n\n    require_self_or_staff(user_id, current_user)"

    src = guard_re.sub(add_guard, src)
    # `require_role` is imported for parity with other routers; drop it if unused.
    if src.count("require_role") == 1:
        src = src.replace(
            "from common.dependencies import get_current_user, require_role, require_self_or_admin",
            "from common.dependencies import get_current_user, require_self_or_admin",
        )

    if src == original:
        print("no change (already patched)")
        return 0
    TARGET.write_text(src, encoding="utf-8")
    print(f"patched {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
