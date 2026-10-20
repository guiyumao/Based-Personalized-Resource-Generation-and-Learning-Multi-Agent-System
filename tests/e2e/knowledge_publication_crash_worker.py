"""Test-only hard exit after a real index write, before publication SQL commit."""

import os
import sys

from services.agent_service.app.services import knowledge_base_admin

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
original = knowledge_base_admin._run_index_command


def crash_after_index(**kwargs):
    result = original(**kwargs)
    if list(knowledge_base_admin.CRAWLED_DIR.rglob("candidate_*.md")):
        os._exit(79)
    return result


knowledge_base_admin._run_index_command = crash_after_index
from services.agent_service.app.services.knowledge_worker import main  # noqa: E402 -- inject test crash before worker imports collaborators

sys.argv = [sys.argv[0], "--once"]
main()
