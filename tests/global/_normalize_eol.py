"""Normalize line endings back to LF for files touched during this session.

Writing files on Windows introduced CRLF, which makes `git diff` report every line
as changed even when only a few lines were semantically edited. This restores the
repository's original LF endings so reviews show real changes only.

    python tests/global/_normalize_eol.py <path> [<path> ...]
"""

from __future__ import annotations

import pathlib
import sys

TARGETS = [
    "common/security/auth.py",
    "common/dependencies.py",
    "common/ttl_cache.py",
    "common/config.py",
    "services/user_service/app/api/routes/users.py",
    "services/user_service/app/services/profile_analysis.py",
    "services/evaluation_service/app/api/routes/reports.py",
    "services/teacher_service/app/services/teacher_manager.py",
    "services/resource_service/app/api/routes/resources.py",
    "services/system_service/app/api/routes/admin.py",
    "services/agent_service/app/connectors/neo4j_connector.py",
    "services/agent_service/app/api/routes/graph.py",
    "services/agent_service/app/main.py",
    "tests/conftest.py",
    "tests/unit/test_profile_chat.py",
    "tests/unit/test_profile_analysis.py",
    "tests/unit/test_teacher_insights.py",
    "tests/unit/test_resource_manager.py",
]


def main(argv: list[str]) -> int:
    paths = argv[1:] or TARGETS
    for raw in paths:
        path = pathlib.Path(raw)
        if not path.is_file():
            print(f"skip (missing): {path}")
            continue
        data = path.read_bytes()
        if b"\r\n" not in data:
            print(f"already LF: {path}")
            continue
        path.write_bytes(data.replace(b"\r\n", b"\n"))
        print(f"normalized: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
