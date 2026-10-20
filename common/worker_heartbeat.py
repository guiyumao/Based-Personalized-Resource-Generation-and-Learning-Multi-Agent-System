"""Independent process heartbeat continues while idle or inside a blocking call."""
import logging
import os
import threading
from datetime import datetime
from uuid import uuid4

from common.db.session import SessionLocal
from common.models.operations import WorkerInstance

LOGGER = logging.getLogger(__name__)


class WorkerHeartbeat:
    def __init__(self, kind, capabilities, *, interval=5, session_factory=None):
        self.id, self.kind, self.capabilities = str(uuid4()), kind, capabilities
        self.interval = max(1, interval)
        self.factory = session_factory or SessionLocal
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        now = datetime.utcnow()
        with self.factory() as db:
            db.add(WorkerInstance(id=self.id, kind=self.kind, pid=os.getpid(), capabilities=self.capabilities,
                status="RUNNING", started_at=now, heartbeat_at=now, heartbeat_interval=self.interval, batches=0))
            db.commit()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def _loop(self):
        while not self.stop.wait(self.interval):
            try:
                with self.factory() as db:
                    row = db.get(WorkerInstance, self.id)
                    if row and row.status == "RUNNING":
                        row.heartbeat_at = datetime.utcnow()
                        db.commit()
            except Exception:
                LOGGER.exception("worker_heartbeat_persist_failed instance=%s", self.id)

    def batch(self, error=None):
        with self.factory() as db:
            row = db.get(WorkerInstance, self.id)
            row.batches += 1
            row.error_code = type(error).__name__[:80] if error else None
            db.commit()

    def __exit__(self, *error):
        self.stop.set()
        self.thread.join(timeout=self.interval+2)
        with self.factory() as db:
            row = db.get(WorkerInstance, self.id)
            row.status = "FAILED" if error[0] else "STOPPED"
            row.stopped_at = datetime.utcnow()
            row.error_code = error[0].__name__[:80] if error[0] else row.error_code
            db.commit()
