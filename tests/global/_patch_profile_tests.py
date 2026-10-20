"""One-off codemod: make profile endpoint tests present the owner's bearer token.

The `/users/{user_id}/...` endpoints are now object-level protected, so every
TestClient call in the profile suites must carry an Authorization header.

    python tests/global/_patch_profile_tests.py
"""

from __future__ import annotations

import pathlib
import re
import sys

TARGETS = [
    pathlib.Path("tests/unit/test_profile_analysis.py"),
    pathlib.Path("tests/unit/test_profile_chat.py"),
]

# client.<method>( ... )  ->  add headers=auth_headers
CALL_RE = re.compile(
    r"(?P<indent>[ \t]*)client\.(?P<method>get|put|post|delete)\((?P<args>.*?)\)\n",
    re.DOTALL,
)


def main() -> int:
    changed = 0
    for path in TARGETS:
        src = path.read_text(encoding="utf-8")
        if "auth_headers" in src:
            print(f"{path}: already patched")
            continue

        def patch_call(match: re.Match[str]) -> str:
            indent, method, args = match.group("indent"), match.group("method"), match.group("args")
            args = args.strip()
            if args.endswith(","):
                args = args[:-1]
            return (
                f"{indent}client.{method}(\n"
                f"{indent}    {args},\n"
                f"{indent}    headers=auth_headers,\n"
                f"{indent})\n"
            )

        src = CALL_RE.sub(patch_call, src)
        # thread the fixture through every test signature
        src = re.sub(
            r"def (test_\w+)\((test_user)\) -> None:",
            r"def \1(test_user, auth_headers) -> None:",
            src,
        )
        path.write_text(src, encoding="utf-8")
        changed += 1
        print(f"{path}: patched")

    return 0 if changed or True else 1


if __name__ == "__main__":
    sys.exit(main())
