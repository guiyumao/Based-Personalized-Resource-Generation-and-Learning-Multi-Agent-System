import json
import subprocess
import sys
from pathlib import Path

import pytest

from common.knowledge_lock import knowledge_write_lock


def test_lock_blocks_competing_writer_and_recovers_stale_owner(tmp_path: Path) -> None:
    with knowledge_write_lock(tmp_path):
        with pytest.raises(RuntimeError, match="already running"):
            with knowledge_write_lock(tmp_path):
                pass
    lock_path = tmp_path / ".cache" / "knowledge-write.lock"
    lock_path.write_text(json.dumps({"pid": 99999999, "token": "stale"}), encoding="utf-8")
    with knowledge_write_lock(tmp_path) as token:
        assert token != "stale"


def test_os_releases_lock_after_owner_process_dies(tmp_path: Path):
    code = "from pathlib import Path; from common.knowledge_lock import knowledge_write_lock; import time,sys\nwith knowledge_write_lock(Path(sys.argv[1])):\n print('locked', flush=True)\n time.sleep(60)"
    owner = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], stdout=subprocess.PIPE, text=True)
    try:
        assert owner.stdout.readline().strip() == "locked"
        with pytest.raises(RuntimeError):
            with knowledge_write_lock(tmp_path):
                pass
        owner.terminate(); owner.wait(timeout=10)
        with knowledge_write_lock(tmp_path):
            pass
    finally:
        if owner.poll() is None:
            owner.kill(); owner.wait(timeout=10)
