"""A small cross-process lock for corpus and Chroma mutations."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def knowledge_write_lock(root: Path, *, inherited_token: str = "") -> Iterator[str]:
    lock_path = root / ".cache" / "knowledge-write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if inherited_token:
        try:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        if current.get("token") != inherited_token:
            raise RuntimeError("Knowledge write lock ownership could not be verified")
        yield inherited_token
        return

    token = uuid.uuid4().hex
    payload = json.dumps({"token": token, "pid": os.getpid(), "created_at": time.time()})
    # Keep a stable inode. Unlinking a stale lock can let two recoverers each
    # acquire a different file; kernel locks also release on process death.
    stream = open(lock_path, "a+b")
    try:
        stream.seek(8192)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another knowledge-base write is already running") from exc
        stream.seek(0)
        stream.truncate()
        stream.write(payload.encode("utf-8"))
        stream.flush()
        yield token
    finally:
        stream.close()
