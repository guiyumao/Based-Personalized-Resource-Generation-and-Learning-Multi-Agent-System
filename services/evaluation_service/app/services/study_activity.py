"""Bounded active-study evidence, with one atomic cursor across tabs/devices."""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.models.learning import StudyActivity, StudySession

LEASE_SECONDS = 45


class ActivityHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tab_id: UUID
    sequence: int = Field(ge=1, le=2_147_483_647, strict=True)
    active: bool = Field(strict=True)
    page: Literal["courseware", "exercise", "learning-path", "resources", "study-tools", "knowledge-graph", "qa"]


def activity_schema_ready(db: Session) -> bool:
    inspector = inspect(db.connection())
    return inspector.has_table("study_sessions") and inspector.has_table("study_activities")


def record_heartbeat(db: Session, user_id: int, payload: ActivityHeartbeat, *, now: datetime | None = None) -> dict:
    """Credit consecutive active heartbeats only; never accept client durations.

    First heartbeat, idle/hidden transition, stale (>45s) gaps, and tab takeover
    credit zero. Revision CAS and interval insert commit together, including on
    SQLite where SELECT FOR UPDATE cannot protect against competing requests.
    """
    from datetime import UTC
    now = now or datetime.now(UTC).replace(tzinfo=None)
    tab = str(payload.tab_id)
    for _ in range(3):
        cursor = db.get(StudySession, user_id, populate_existing=True)
        if cursor is None:
            db.add(StudySession(user_id=user_id, tab_id=tab, sequence=payload.sequence,
                                revision=0, active=payload.active, heartbeat_at=now))
            try:
                db.commit()
                return {"status": "started", "credited_seconds": 0}
            except IntegrityError:
                db.rollback()
                continue
        same_tab = cursor.tab_id == tab
        elapsed = (now - cursor.heartbeat_at).total_seconds()
        if same_tab and payload.sequence <= cursor.sequence:
            return {"status": "replayed", "credited_seconds": 0}
        if elapsed < 0:
            return {"status": "clock_rollback", "credited_seconds": 0}
        if not same_tab and (not payload.active or (cursor.active and elapsed <= LEASE_SECONDS)):
            return {"status": "another_tab", "credited_seconds": 0}
        credit = same_tab and cursor.active and payload.active and 0 < elapsed <= LEASE_SECONDS
        start = cursor.heartbeat_at
        previous_revision = cursor.revision
        changed = db.execute(update(StudySession).where(
            StudySession.user_id == user_id, StudySession.revision == previous_revision,
        ).values(tab_id=tab, sequence=payload.sequence, revision=previous_revision + 1,
                 active=payload.active, heartbeat_at=now).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            db.rollback()
            continue
        if credit:
            db.add(StudyActivity(user_id=user_id, started_at=start, ended_at=now, page=payload.page))
        db.commit()
        return {"status": "recorded" if credit else "resumed", "credited_seconds": round(elapsed, 3) if credit else 0}
    raise HTTPException(status_code=409, detail="学习活动同时更新，请稍后重试。")


def measured_daily_seconds(db: Session, user_id: int, start: datetime, end: datetime, timezone) -> dict[str, float]:
    """Split intervals at local midnight; clip the requested window exactly."""
    from datetime import UTC

    result: dict[str, float] = {}
    rows = db.query(StudyActivity.started_at, StudyActivity.ended_at).filter(
        StudyActivity.user_id == user_id, StudyActivity.ended_at > start, StudyActivity.started_at < end,
    ).all()
    for since, until in rows:
        current, stop = max(since, start), min(until, end)
        while current < stop:
            local = current.replace(tzinfo=UTC).astimezone(timezone)
            midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), timezone)
            boundary = min(stop, midnight.astimezone(UTC).replace(tzinfo=None))
            key = local.date().isoformat()
            result[key] = result.get(key, 0) + (boundary - current).total_seconds()
            current = boundary
    return result
