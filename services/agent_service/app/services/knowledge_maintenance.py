"""Dispatch persistent inspection plans into the common knowledge task queue."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from common.db.session import SessionLocal
from common.models.learning import KnowledgeBuildTask, KnowledgeCandidate, KnowledgeMaintenancePlan, KnowledgePoint, SystemSubject
from services.agent_service.app.services.knowledge_tasks import create_task


class MaintenancePolicy(BaseModel):
    mode: Literal["INSPECT_ONLY", "AUTO_SUPPLEMENT_REVIEW", "POLICY_BASED_AUTO_PUBLISH"] = "INSPECT_ONLY"
    chapter: str = Field(default="", max_length=160)
    point_ids: list[int] = Field(default_factory=list, max_length=50)
    max_supplement_points: int = Field(default=3, ge=0, le=10)
    max_search_calls: int = Field(default=3, ge=0, le=10)
    max_fetch_calls: int = Field(default=3, ge=0, le=10)
    max_model_calls: int = Field(default=3, ge=0, le=10)
    max_source_age_days: int = Field(default=365, ge=1, le=3650)
    scan_after_point_id: int = Field(default=0, ge=0)
    repair_index: bool = False
    auto_publish_authorized: bool = False
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    allowed_licenses: list[str] = Field(default_factory=list, max_length=20)


def plan_to_dict(plan: KnowledgeMaintenancePlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "name": plan.name,
        "subject": plan.subject,
        "interval_hours": plan.interval_hours,
        "enabled": plan.enabled,
        "next_run_at": f"{plan.next_run_at.isoformat()}Z" if plan.next_run_at else None,
        "last_task_id": plan.last_task_id,
        "policy": plan.policy_json or {},
    }


def _require_existing_subject(db: Session, subject: str) -> None:
    """Reject free-typed subjects that do not match any catalog entry.

    A typo here would otherwise produce a plan that silently no-ops with
    SUBJECT_NOT_IN_CATALOG on every run, so fail fast at creation time.
    """
    if not subject:
        return
    from services.agent_service.app.services.knowledge_construction import find_subject
    if find_subject(db, subject) is None:
        raise ValueError("Unknown subject: pick an existing subject name or code from the subject catalog")


def create_plan(
    db: Session, *, actor_user_id: int, name: str, subject: str,
    next_run_at: datetime, interval_hours: int | None,
    policy: dict[str, Any] | None = None,
) -> KnowledgeMaintenancePlan:
    if interval_hours is not None and not 24 <= interval_hours <= 24 * 365:
        raise ValueError("Maintenance interval must be between 24 hours and one year")
    if next_run_at.tzinfo is None:
        raise ValueError("An explicit timezone is required")
    utc_run = next_run_at.astimezone(timezone.utc).replace(tzinfo=None)
    if utc_run <= datetime.utcnow():
        raise ValueError("First run must be in the future")
    _require_existing_subject(db, subject.strip())
    plan = KnowledgeMaintenancePlan(
        actor_user_id=actor_user_id, name=name.strip(), subject=subject.strip(),
        interval_hours=interval_hours, enabled=True, next_run_at=utc_run,
        policy_json=MaintenancePolicy.model_validate(policy).model_dump() if policy else {},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def dispatch_due_plans(now: datetime | None = None, *, batch_size: int = 20) -> int:
    """A stable slot key makes crash-after-enqueue dispatch safe to retry."""
    now = now or datetime.utcnow()
    dispatched = 0
    with SessionLocal() as db:
        due_ids = [
            row.id for row in db.query(KnowledgeMaintenancePlan.id)
            .filter(
                KnowledgeMaintenancePlan.enabled.is_(True),
                KnowledgeMaintenancePlan.next_run_at <= now,
            ).order_by(KnowledgeMaintenancePlan.next_run_at).limit(batch_size).all()
        ]
    for plan_id in due_ids:
        with SessionLocal() as db:
            plan = db.get(KnowledgeMaintenancePlan, plan_id)
            if not plan or not plan.enabled or not plan.next_run_at or plan.next_run_at > now:
                continue
            slot = plan.next_run_at
            task = create_task(
                db, actor_user_id=plan.actor_user_id,
                client_request_id=f"maintenance-{plan.id}-{slot:%Y%m%d%H%M%S}",
                operation_type="MAINTENANCE_RUN" if plan.policy_json else "KNOWLEDGE_HEALTH_CHECK", subject=plan.subject,
                requirements={"plan_id": plan.id, "policy": plan.policy_json} if plan.policy_json else {},
                trigger_source="ADMIN_SCHEDULED" if plan.interval_hours else "ADMIN_ONE_TIME_SCHEDULED",
            )
            plan.last_task_id = task.id
            if plan.interval_hours is None:
                plan.enabled = False
                plan.next_run_at = None
            else:
                next_run = slot + timedelta(hours=plan.interval_hours)
                while next_run <= now:
                    next_run += timedelta(hours=plan.interval_hours)
                plan.next_run_at = next_run
            db.commit()
            dispatched += 1
    return dispatched


def run_maintenance(task: KnowledgeBuildTask, guard) -> dict[str, Any]:
    from services.agent_service.app.services.knowledge_acquisition import assess_coverage
    from services.agent_service.app.services.knowledge_construction import find_subject
    from services.agent_service.app.services.knowledge_tasks import execute_task
    from services.agent_service.app.services.knowledge_base_admin import reindex_knowledge_base
    policy = MaintenancePolicy.model_validate(task.requirements_json["policy"])
    with SessionLocal() as db:
        query = db.query(KnowledgePoint)
        if task.subject:
            subject = find_subject(db, task.subject)
            if subject is None:
                return {"issues": [{"code": "SUBJECT_NOT_IN_CATALOG"}], "child_task_ids": [], "candidate_ids": []}
            query = query.filter_by(subject_id=subject.id)
        if policy.chapter:
            query = query.filter_by(chapter=policy.chapter)
        if policy.point_ids:
            query = query.filter(KnowledgePoint.id.in_(policy.point_ids))
        total_points = query.count()
        remaining_query = query.filter(KnowledgePoint.id > policy.scan_after_point_id)
        points = remaining_query.order_by(KnowledgePoint.id).limit(50).all()
        if not points and total_points:
            remaining_query = query
            points = query.order_by(KnowledgePoint.id).limit(50).all()
        remaining_points = max(0, remaining_query.count() - len(points))
        next_cursor = points[-1].id if remaining_points and points else 0
        issues, child_ids, candidate_ids = [], [], []
        supplement_limit = min(policy.max_supplement_points, policy.max_search_calls, policy.max_fetch_calls, policy.max_model_calls)
        for point in points:
            guard()
            subject = db.get(SystemSubject, point.subject_id)
            if subject is None or not subject.code:
                continue
            coverage = assess_coverage(db, subject=subject.code, knowledge_point=point.name, max_source_age_days=policy.max_source_age_days)
            issues.append({"point_id": point.id, "knowledge_point": point.name, "state": coverage["state"], "missing_facets": coverage["missing_facets"]})
            if policy.mode == "INSPECT_ONLY" or len(child_ids) >= supplement_limit or coverage["state"] not in {"MISSING", "PARTIAL", "STALE"}:
                continue
            guard(db)
            child = create_task(db, actor_user_id=task.actor_user_id, client_request_id=f"maintenance-{task.id}-point-{point.id}",
                                operation_type="BUILD_POINT", requirements={"point_id": point.id, "mode": "COMPLETE_POINT"}, parent_task_id=task.id)
            child_id = child.id
            db.commit()
            execute_task(child_id)
            db.expire_all(); child = db.get(KnowledgeBuildTask, child_id)
            child_ids.append(child_id)
            candidate_ids.extend((child.result_json or {}).get("candidate_ids", []))
        guard()
        from common.config import get_settings
        if policy.repair_index and get_settings().chroma_mode != "http":
            raise RuntimeError("Scheduled index repair requires Chroma HTTP mode")
        repair = reindex_knowledge_base(subject=task.subject or None, force=False) if policy.repair_index else None
        published_count = 0
        if policy.mode == "POLICY_BASED_AUTO_PUBLISH" and policy.auto_publish_authorized:
            from urllib.parse import urlsplit
            from common.models.learning import KnowledgeVersion
            from services.agent_service.app.services.knowledge_candidates import publish_candidate, review_candidate, submit_candidate
            for candidate_id in set(candidate_ids):
                candidate = db.get(KnowledgeCandidate, candidate_id)
                old = db.get(KnowledgeVersion, candidate.published_version_id) if candidate and candidate.published_version_id else None
                # Only formatting changes of an explicitly licensed source can
                # publish automatically. New facts always require human review.
                eligible = bool(candidate and old and candidate.status == "DRAFT" and candidate.publication_allowed
                                and candidate.license_name in policy.allowed_licenses
                                and candidate.license_evidence_url
                                and urlsplit(candidate.source_url).hostname in policy.allowed_domains
                                and candidate.source_url == old.source_url
                                and "".join(candidate.content.split()) == "".join(old.content.split()))
                if eligible and get_settings().chroma_mode == "http":
                    guard(db); submit_candidate(db, candidate)
                    guard(db); review_candidate(db, candidate, reviewer_user_id=task.actor_user_id, approved=True,
                                                notes=f"Maintenance plan {task.requirements_json['plan_id']}: licensed formatting-only update")
                    guard(db); publish_candidate(db, candidate, publisher_user_id=task.actor_user_id)
                    published_count += 1
        plan = db.get(KnowledgeMaintenancePlan, task.requirements_json["plan_id"])
        if plan and plan.last_task_id == task.id:
            guard(db)
            plan.policy_json = {**(plan.policy_json or {}), "scan_after_point_id": next_cursor}
            db.commit()
        return {"plan_id": task.requirements_json["plan_id"], "mode": policy.mode,
                "scope": {"subject": task.subject, "chapter": policy.chapter, "point_ids": policy.point_ids},
                "scanned_points": len(points), "issues": issues, "child_task_ids": child_ids,
                "total_scope_points": total_points, "remaining_points": remaining_points, "next_scan_after_point_id": next_cursor,
                "candidate_ids": candidate_ids, "pending_review": len(set(candidate_ids)) - published_count, "published": published_count,
                "auto_publish_block_reason": "NEW_FACTS_OR_UNVERIFIED_PERMISSIONS_REQUIRE_REVIEW" if policy.mode == "POLICY_BASED_AUTO_PUBLISH" and len(set(candidate_ids)) > published_count else "",
                "index_repair": repair, "completed_at": datetime.utcnow().isoformat() + "Z"}
