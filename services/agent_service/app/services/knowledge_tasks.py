"""Persist and execute bounded knowledge-base maintenance operations."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import case, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.db.session import SessionLocal
from common.models.learning import KnowledgeBuildTask
from services.agent_service.app.services.deepseek_search import (
    DeepSeekSearchUnavailable,
    fetch_source,
    search_sources,
)
from services.agent_service.app.services.knowledge_base_admin import (
    knowledge_base_status,
    list_knowledge_sources,
    list_knowledge_subject_catalog,
    reindex_knowledge_base,
)

SUPPORTED_OPERATIONS = frozenset({"KNOWLEDGE_HEALTH_CHECK", "INDEX_REPAIR", "SEARCH_SOURCES", "FETCH_SOURCE", "AI_SUBJECT_PLAN", "BUILD_POINT", "MAINTENANCE_RUN", "PUBLISH_CANDIDATE", "RECONCILE_PUBLICATIONS", "PUBLIC_KNOWLEDGE_BUILD"})
LOGGER = logging.getLogger(__name__)
LEASE_SECONDS = 45
MAX_ATTEMPTS = 3
#: Public builds are allowed more retries than recovery operations, but not
#: unbounded retries: each round costs one full generation plus one review.
PUBLIC_ATTEMPT_LIMIT = 8
SAFE_RECOVERY_OPERATIONS = {"KNOWLEDGE_HEALTH_CHECK", "SEARCH_SOURCES", "FETCH_SOURCE", "BUILD_POINT", "PUBLISH_CANDIDATE", "RECONCILE_PUBLICATIONS"}


class KnowledgeTaskConflict(ValueError):
    pass


def _failure_code(exc: Exception) -> str:
    from services.agent_service.app.services.knowledge_budget import KnowledgeBudgetExceeded
    if isinstance(exc, KnowledgeBudgetExceeded):
        return "KNOWLEDGE_BUDGET_EXCEEDED"
    if isinstance(exc, DeepSeekSearchUnavailable):
        return exc.code
    if isinstance(exc, httpx.HTTPStatusError):
        return {
            402: "DEEPSEEK_BUDGET_EXCEEDED",
            429: "DEEPSEEK_RATE_LIMITED",
            404: "SOURCE_NOT_FOUND", 403: "SOURCE_ACCESS_DENIED", 410: "SOURCE_GONE",
        }.get(exc.response.status_code, "DEEPSEEK_HTTP_ERROR")
    if isinstance(exc, httpx.TimeoutException):
        return "DEEPSEEK_TIMEOUT"
    return "KNOWLEDGE_OPERATION_FAILED"


def serialize_task(task: KnowledgeBuildTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "trigger_source": task.trigger_source,
        "operation_type": task.operation_type,
        "subject": task.subject,
        "status": task.status,
        "current_step": task.current_step,
        "result": task.result_json or {},
        "error_code": task.error_code,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "execution_attempt": task.execution_attempt,
        "heartbeat_at": f"{task.heartbeat_at.isoformat()}Z" if task.heartbeat_at else None,
        "lease_expires_at": f"{task.lease_expires_at.isoformat()}Z" if task.lease_expires_at else None,
        "cancel_requested": task.cancel_requested,
    }


def create_task(
    db: Session,
    *,
    actor_user_id: int,
    client_request_id: str,
    operation_type: str,
    subject: str = "",
    requirements: dict[str, Any] | None = None,
    trigger_source: str = "ADMIN_MANUAL",
    parent_task_id: int | None = None,
) -> KnowledgeBuildTask:
    if operation_type not in SUPPORTED_OPERATIONS:
        raise ValueError("Unsupported knowledge operation")
    if trigger_source not in {"ADMIN_MANUAL", "ADMIN_SCHEDULED", "ADMIN_ONE_TIME_SCHEDULED"}:
        raise ValueError("Unsupported knowledge task source")
    subject = subject.strip()
    requirements = requirements or {}
    if operation_type == "PUBLISH_CANDIDATE":
        from common.models.learning import KnowledgeCandidate
        candidate = db.get(KnowledgeCandidate, requirements.get("candidate_id"))
        if candidate is None or candidate.status not in {"APPROVED", "AUTO_APPROVED", "PUBLISHED"}:
            raise ValueError("An approved candidate is required")
        requirements = {"candidate_id": candidate.id, "content_hash": candidate.content_hash}
    elif operation_type == "SEARCH_SOURCES":
        query = str(requirements.get("query") or "").strip()
        if not 1 <= len(query) <= 128:
            raise ValueError("Search query must contain 1–128 characters")
        requirements = {"query": query}
    elif operation_type == "FETCH_SOURCE":
        source_task_id = requirements.get("source_task_id")
        source_index = requirements.get("source_index")
        if not isinstance(source_task_id, int) or not isinstance(source_index, int) or source_index < 0:
            raise ValueError("A search task and source index are required")
        parent = db.get(KnowledgeBuildTask, source_task_id)
        if parent is None or parent.status != "COMPLETED" or parent.operation_type != "SEARCH_SOURCES":
            raise ValueError("Completed search task not found")
        subject = subject or parent.subject
        sources = (parent.result_json or {}).get("sources", [])
        if not isinstance(sources, list) or source_index >= len(sources):
            raise ValueError("Source index is out of range")
        requirements = {"source_task_id": source_task_id, "source_index": source_index}
    elif operation_type == "AI_SUBJECT_PLAN":
        name = str(requirements.get("name") or "").strip()
        teaching = str(requirements.get("requirements") or "").strip()
        if not name or len(name) > 100 or len(teaching) > 4000:
            raise ValueError("Subject name and bounded teaching requirements are required")
        requirements = {"name": name, "requirements": teaching,
                        "stage": str(requirements.get("stage") or "本科")[:100],
                        "reference_material": str(requirements.get("reference_material") or "")[:16000]}
    elif operation_type == "BUILD_POINT":
        from common.models.learning import KnowledgePoint
        point_id = requirements.get("point_id")
        mode = requirements.get("mode")
        if not isinstance(point_id, int) or db.get(KnowledgePoint, point_id) is None or mode not in {"CREATE_POINT", "COMPLETE_POINT", "REVISE_POINT"}:
            raise ValueError("Existing point and valid construction mode required")
        requirements = {"point_id": point_id, "mode": mode, "focus": str(requirements.get("focus") or "")[:300]}
    elif operation_type == "MAINTENANCE_RUN":
        from services.agent_service.app.services.knowledge_maintenance import MaintenancePolicy
        requirements = {"plan_id": int(requirements["plan_id"]), "policy": MaintenancePolicy.model_validate(requirements["policy"]).model_dump()}
    elif requirements:
        raise ValueError("Requirements are not supported for this operation")
    canonical = json.dumps(
        {"trigger_source": trigger_source, "operation_type": operation_type, "subject": subject, "requirements": requirements},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.query(KnowledgeBuildTask).filter_by(
        actor_user_id=actor_user_id, client_request_id=client_request_id,
    ).first()
    if existing:
        if existing.request_hash != request_hash:
            raise KnowledgeTaskConflict("Request ID already belongs to a different knowledge task")
        return existing
    active = db.query(KnowledgeBuildTask).filter(
        KnowledgeBuildTask.actor_user_id == actor_user_id,
        KnowledgeBuildTask.request_hash == request_hash,
        KnowledgeBuildTask.status.in_(("QUEUED", "RUNNING")),
    ).order_by(KnowledgeBuildTask.id.desc()).first()
    if active:
        return active
    if operation_type in {"SEARCH_SOURCES", "FETCH_SOURCE"}:
        reusable = db.query(KnowledgeBuildTask).filter(
            KnowledgeBuildTask.request_hash == request_hash,
            KnowledgeBuildTask.status == "COMPLETED",
            KnowledgeBuildTask.created_at >= datetime.utcnow() - timedelta(hours=24),
        ).order_by(KnowledgeBuildTask.id.desc()).first()
        if reusable:
            return reusable
        if operation_type == "FETCH_SOURCE":
            wanted_url = str(sources[source_index].get("url") or "")
            recent = db.query(KnowledgeBuildTask).filter(
                KnowledgeBuildTask.operation_type == "FETCH_SOURCE", KnowledgeBuildTask.subject == subject,
                KnowledgeBuildTask.status == "COMPLETED", KnowledgeBuildTask.created_at >= datetime.utcnow() - timedelta(hours=24),
            ).order_by(KnowledgeBuildTask.id.desc()).limit(1000).all()
            cached = next((item for item in recent if ((item.result_json or {}).get("source") or {}).get("url") == wanted_url), None)
            if cached:
                return cached
    task = KnowledgeBuildTask(
        actor_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_hash=request_hash,
        trigger_source=trigger_source,
        operation_type=operation_type,
        subject=subject,
        requirements_json=requirements,
        status="QUEUED",
        current_step="等待执行",
        result_json={},
        error_code="",
        parent_task_id=parent_task_id,
    )
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(KnowledgeBuildTask).filter_by(
            actor_user_id=actor_user_id, client_request_id=client_request_id,
        ).one()
        if existing.request_hash != request_hash:
            raise KnowledgeTaskConflict("Request ID already belongs to a different knowledge task")
        return existing
    db.refresh(task)
    return task


def cancel_task(db: Session, task: KnowledgeBuildTask) -> KnowledgeBuildTask:
    if task.status != "QUEUED":
        raise KnowledgeTaskConflict("Only queued tasks can be cancelled")
    result = db.execute(
        update(KnowledgeBuildTask)
        .where(KnowledgeBuildTask.id == task.id, KnowledgeBuildTask.status == "QUEUED")
        .values(status="CANCELLED", current_step="已取消", completed_at=datetime.utcnow())
    )
    db.commit()
    if result.rowcount != 1:
        raise KnowledgeTaskConflict("Task is already running")
    db.refresh(task)
    return task


def request_cancel(db: Session, task: KnowledgeBuildTask) -> KnowledgeBuildTask:
    if task.status == "QUEUED":
        return cancel_task(db, task)
    if task.status != "RUNNING":
        raise KnowledgeTaskConflict("Task is no longer active")
    db.execute(update(KnowledgeBuildTask).where(
        KnowledgeBuildTask.id == task.id, KnowledgeBuildTask.status == "RUNNING",
    ).values(cancel_requested=True, current_step="等待当前操作安全停止"))
    db.commit(); db.refresh(task)
    return task


def retry_task(db: Session, task: KnowledgeBuildTask) -> KnowledgeBuildTask:
    if task.status != "FAILED" or task.operation_type not in SAFE_RECOVERY_OPERATIONS or task.execution_attempt >= MAX_ATTEMPTS:
        raise KnowledgeTaskConflict("Task cannot be safely retried")
    changed = db.execute(update(KnowledgeBuildTask).where(KnowledgeBuildTask.id == task.id,
                         KnowledgeBuildTask.status == "FAILED", KnowledgeBuildTask.execution_attempt < MAX_ATTEMPTS)
                         .values(status="QUEUED", worker_id=None, lease_expires_at=None, completed_at=None,
                                 cancel_requested=False, next_attempt_at=None, error_code="", current_step="等待断点恢复"))
    db.commit(); db.refresh(task)
    if changed.rowcount != 1:
        raise KnowledgeTaskConflict("Task state changed before retry")
    return task


class KnowledgeLeaseLost(RuntimeError):
    pass


def _owned(task_id: int, worker_id: str, attempt: int):
    return (
        KnowledgeBuildTask.id == task_id, KnowledgeBuildTask.status == "RUNNING",
        KnowledgeBuildTask.worker_id == worker_id, KnowledgeBuildTask.execution_attempt == attempt,
        KnowledgeBuildTask.lease_expires_at > datetime.utcnow(),
    )


def renew_lease(task_id: int, worker_id: str, attempt: int) -> bool:
    with SessionLocal() as db:
        now = datetime.utcnow()
        result = db.execute(update(KnowledgeBuildTask).where(
            *_owned(task_id, worker_id, attempt), KnowledgeBuildTask.cancel_requested.is_(False),
        ).values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS)))
        db.commit()
        return result.rowcount == 1


def guard_write(db: Session, task_id: int, worker_id: str, attempt: int) -> None:
    """Hold the task write fence in the same transaction as a workflow mutation."""
    now = datetime.utcnow()
    changed = db.execute(update(KnowledgeBuildTask).where(
        *_owned(task_id, worker_id, attempt), KnowledgeBuildTask.cancel_requested.is_(False),
    ).values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS)))
    if changed.rowcount != 1:
        raise KnowledgeLeaseLost()


def _notify_terminal(db: Session, task: KnowledgeBuildTask) -> None:
    if task.status in {"COMPLETED", "FAILED"}:
        from common.notifications import emit
        emit(db, user_id=task.actor_user_id, event_key=f"knowledge:{task.id}:{task.execution_attempt}:{task.status}",
            title="知识库任务处理结果", content=f"{task.subject}：{task.current_step}。任务完成不代表内容已审核发布，请查看实际审核状态。",
            type="task", related_type="knowledge_task", related_id=task.id)
        from common.models.learning import LearningKnowledgeGap
        for gap in db.query(LearningKnowledgeGap).filter_by(knowledge_task_id=task.id):
            emit(db, user_id=gap.user_id, event_key=f"gap:{gap.id}:task:{task.id}:{task.execution_attempt}:{task.status}",
                title="知识内容请求处理进度", content=f"{gap.subject} / {gap.knowledge_point} 建设任务：{task.current_step}。当前请求状态：{gap.status}；建设完成不等于内容已审核发布。", type="knowledge")


def _finish(task_id: int, worker_id: str, attempt: int, **values: Any) -> bool:
    with SessionLocal() as db:
        queued = values.get("status") == "QUEUED"
        cancelled = KnowledgeBuildTask.cancel_requested.is_(True)
        values["status"] = case((cancelled, "CANCELLED"), else_=values.get("status", "FAILED"))
        values["current_step"] = case((cancelled, "已安全停止"), else_=values.get("current_step", "执行失败"))
        # The cancellation predicate must be evaluated by the same UPDATE that
        # writes the result; reading it first races an administrator's request.
        from sqlalchemy import literal
        from sqlalchemy.types import JSON
        if "result_json" in values:
            values["result_json"] = case((cancelled, literal({}, type_=JSON)), else_=literal(values["result_json"], type_=JSON))
        result = db.execute(update(KnowledgeBuildTask).where(*_owned(task_id, worker_id, attempt)).values(
            **values, completed_at=case((cancelled, datetime.utcnow()), else_=None if queued else datetime.utcnow()), lease_expires_at=None,
        ))
        if result.rowcount == 1:
            task = db.get(KnowledgeBuildTask, task_id)
            db.refresh(task)
            _notify_terminal(db, task)
        db.commit()
        return result.rowcount == 1


def execute_task(task_id: int) -> bool:
    """Claim a queue item atomically, then run one bounded operation."""
    worker_id = f"{os.getpid()}-{uuid.uuid4().hex[:16]}"
    stop = threading.Event()
    deadline = time.monotonic() + 1000
    def heartbeat() -> None:
        while not stop.wait(5):
            try:
                if time.monotonic() >= deadline or not renew_lease(task_id, worker_id, attempt):
                    break
            except Exception:
                LOGGER.exception("knowledge_heartbeat_failed task_id=%s", task_id)

    with SessionLocal() as db:
        now = datetime.utcnow()
        claimed = db.execute(
            update(KnowledgeBuildTask)
            .where(KnowledgeBuildTask.id == task_id, KnowledgeBuildTask.status == "QUEUED",
                   or_(KnowledgeBuildTask.next_attempt_at.is_(None), KnowledgeBuildTask.next_attempt_at <= now))
            .values(status="RUNNING", current_step="正在执行知识任务", worker_id=worker_id,
                    execution_attempt=KnowledgeBuildTask.execution_attempt + 1,
                    heartbeat_at=now, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS))
        )
        db.commit()
        if claimed.rowcount != 1:
            return False
        task = db.get(KnowledgeBuildTask, task_id)
        assert task is not None
        attempt = task.execution_attempt
        from common.task_attempts import started as record_attempt_started
        record_attempt_started(db, "knowledge", task)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        from services.agent_service.app.services.knowledge_budget import (
            current_knowledge_task,
            task_usage,
        )
        budget_token = current_knowledge_task.set(task_id)
        try:
            if task.operation_type == "PUBLIC_KNOWLEDGE_BUILD":
                from services.agent_service.app.services.public_knowledge import (
                    advance_public_build,
                )
                def public_guard(write_db=None):
                    if write_db is not None:
                        guard_write(write_db, task_id, worker_id, attempt)
                    elif not renew_lease(task_id, worker_id, attempt):
                        raise KnowledgeLeaseLost()
                result = advance_public_build(db, task, public_guard)
                if not result.get("ready"):
                    db.rollback()
                    if attempt >= PUBLIC_ATTEMPT_LIMIT:
                        # A public build used to requeue unconditionally, so a
                        # document the model could never finish (output cap,
                        # repeated review rejection) burned tokens forever.
                        # Fail closed: the learner keeps the personal draft and
                        # an administrator can retry from the knowledge console.
                        _finish(task_id, worker_id, attempt, result_json=result, status="FAILED",
                                next_attempt_at=None,
                                current_step="公共知识自动建设达到重试上限，已停止；可稍后由管理员重试",
                                error_code="PUBLIC_BUILD_RETRY_EXHAUSTED")
                        return True
                    _finish(task_id, worker_id, attempt, result_json=result, status="QUEUED",
                            next_attempt_at=datetime.utcnow() + timedelta(seconds=min(300, 15 * max(1, attempt))),
                            current_step="模型自动修改与融入中，无需人工审核", error_code="")
                    return True
            elif task.operation_type == "KNOWLEDGE_HEALTH_CHECK":
                status = knowledge_base_status()
                catalog = list_knowledge_subject_catalog()
                selected = [item for item in catalog if item["value"] == task.subject] if task.subject else catalog
                sources = [
                    item for item in list_knowledge_sources()
                    if not task.subject or item["subject"] == task.subject
                ]
                issues: list[dict[str, str]] = []
                if task.subject and not selected:
                    issues.append({"code": "SUBJECT_CORPUS_EMPTY", "subject": task.subject})
                if not status.get("available"):
                    issues.append({"code": "INDEX_UNAVAILABLE", "subject": task.subject})
                corpus_documents = int((status.get("corpus") or {}).get("documents") or 0)
                indexed_documents = int((status.get("index") or {}).get("documents") or 0)
                if not task.subject and indexed_documents < corpus_documents:
                    issues.append({"code": "INDEX_BEHIND_CORPUS", "subject": ""})
                for source in sources:
                    if source.get("status") != "available":
                        issues.append({
                            "code": "CONFIGURED_SOURCE_NOT_CRAWLED",
                            "subject": str(source.get("subject") or ""),
                            "topic": str(source.get("topic") or ""),
                        })
                result = {
                    "status": status,
                    "subjects": selected,
                    "subject_found": bool(selected) if task.subject else None,
                    "issues": issues[:100],
                    "issues_total": len(issues),
                }
            elif task.operation_type in {"PUBLISH_CANDIDATE", "RECONCILE_PUBLICATIONS"}:
                from common.config import get_settings
                from common.models.learning import KnowledgeCandidate
                from services.agent_service.app.services.knowledge_publication import reconcile
                if get_settings().chroma_mode != "http":
                    raise RuntimeError("Publication Worker requires Chroma HTTP mode")
                def publication_guard(write_db=None):
                    if write_db is not None:
                        guard_write(write_db, task_id, worker_id, attempt)
                    elif not renew_lease(task_id, worker_id, attempt):
                        raise KnowledgeLeaseLost()
                with SessionLocal() as write_db:
                    result = reconcile(write_db, guard=publication_guard)
                    if task.operation_type == "PUBLISH_CANDIDATE":
                        from services.agent_service.app.services.knowledge_candidates import (
                            publish_candidate,
                        )
                        candidate = write_db.get(KnowledgeCandidate, task.requirements_json["candidate_id"])
                        if candidate is None or candidate.content_hash != task.requirements_json["content_hash"]:
                            raise ValueError("Candidate changed after publication was queued")
                        version, matches = publish_candidate(write_db, candidate, publisher_user_id=task.actor_user_id, guard=publication_guard)
                        result = {"version_id": version.id, "retrieval_matches": len(matches), "reconciled": result}
            elif task.operation_type == "INDEX_REPAIR":
                from common.config import get_settings
                if get_settings().chroma_mode != "http":
                    raise RuntimeError("Worker index repair requires Chroma HTTP mode; embedded indexing belongs to the administrator API process")
                if not renew_lease(task_id, worker_id, attempt):
                    raise KnowledgeLeaseLost()
                result = reindex_knowledge_base(subject=task.subject or None, force=False)
            elif task.operation_type == "SEARCH_SOURCES":
                query = str((task.requirements_json or {}).get("query") or "")
                result = {"query": query, "sources": search_sources(query)}
            elif task.operation_type == "FETCH_SOURCE":
                requirements = task.requirements_json or {}
                parent = db.get(KnowledgeBuildTask, int(requirements["source_task_id"]))
                sources = (parent.result_json or {}).get("sources", []) if parent else []
                source = sources[int(requirements["source_index"])]
                result = {"source": fetch_source(str(source["url"])), "review_status": "PENDING"}
            elif task.operation_type == "AI_SUBJECT_PLAN":
                from services.agent_service.app.services.knowledge_construction import plan_subject
                result = plan_subject(task.requirements_json)
            elif task.operation_type == "BUILD_POINT":
                from services.agent_service.app.services.knowledge_construction import build_point
                def guard(write_db: Session | None = None) -> None:
                    if write_db is not None:
                        guard_write(write_db, task_id, worker_id, attempt)
                    elif not renew_lease(task_id, worker_id, attempt):
                        raise KnowledgeLeaseLost()
                result = build_point(task, guard)
            elif task.operation_type == "MAINTENANCE_RUN":
                from services.agent_service.app.services.knowledge_maintenance import (
                    run_maintenance,
                )
                def guard(write_db: Session | None = None) -> None:
                    if write_db is not None:
                        guard_write(write_db, task_id, worker_id, attempt)
                    elif not renew_lease(task_id, worker_id, attempt):
                        raise KnowledgeLeaseLost()
                result = run_maintenance(task, guard)
            else:
                raise ValueError("Unsupported knowledge operation")
            db.rollback()
            result["usage_reservations"] = task_usage(task_id)
            pricing = any(os.getenv(name) for name in ("KNOWLEDGE_SEARCH_COST_MICROS", "KNOWLEDGE_FETCH_COST_MICROS", "KNOWLEDGE_MODEL_COST_MICROS", "KNOWLEDGE_INPUT_TOKEN_COST_MICROS", "KNOWLEDGE_OUTPUT_TOKEN_COST_MICROS"))
            result["cost"] = {"amount": result["usage_reservations"]["reserved_cost_micros"] / 1000000 if pricing else None,
                              "currency": os.getenv("KNOWLEDGE_COST_CURRENCY") if pricing else None,
                              "status": "CONSERVATIVE_RESERVATION" if pricing else "PRICING_NOT_CONFIGURED"}
            _finish(task_id, worker_id, attempt, result_json=result, status="COMPLETED", current_step="已完成", error_code="")
        except Exception as exc:
            db.rollback()
            if not isinstance(exc, KnowledgeLeaseLost):
                if task.operation_type == "PUBLIC_KNOWLEDGE_BUILD":
                    _finish(task_id, worker_id, attempt, status="QUEUED",
                            next_attempt_at=datetime.utcnow() + timedelta(seconds=60),
                            current_step="内容已保存，自动恢复后继续融入", error_code="")
                    return True
                _finish(task_id, worker_id, attempt, status="FAILED", current_step="执行失败", error_code=_failure_code(exc))
                raise
        finally:
            stop.set()
            thread.join(timeout=2)
            current_knowledge_task.reset(budget_token)
            from common.task_attempts import finished as record_attempt_finished
            record_attempt_finished(db, "knowledge", task_id, attempt, KnowledgeBuildTask)
    return True


def run_pending_tasks(batch_size: int = 1) -> int:
    if not 1 <= batch_size <= 20:
        raise ValueError("batch_size must be between 1 and 20")
    with SessionLocal() as db:
        task_ids = [
            row.id for row in db.query(KnowledgeBuildTask.id)
            .filter(KnowledgeBuildTask.status == "QUEUED",
                    or_(KnowledgeBuildTask.next_attempt_at.is_(None), KnowledgeBuildTask.next_attempt_at <= datetime.utcnow()))
            .order_by(KnowledgeBuildTask.id).limit(batch_size).all()
        ]
    for task_id in task_ids:
        try:
            execute_task(task_id)
        except Exception:
            LOGGER.exception("knowledge_task_failed task_id=%s", task_id)
    return len(task_ids)


def expire_interrupted_tasks() -> int:
    """Requeue bounded safe work; invalidate ownership before another worker claims."""
    with SessionLocal() as db:
        now = datetime.utcnow()
        rows = db.query(KnowledgeBuildTask).filter(
            KnowledgeBuildTask.status == "RUNNING",
            or_(KnowledgeBuildTask.lease_expires_at <= now,
                (KnowledgeBuildTask.lease_expires_at.is_(None)) & (KnowledgeBuildTask.updated_at < now - timedelta(minutes=30))),
        ).all()
        changed = 0
        for task in rows:
            retry = not task.cancel_requested and (task.operation_type == "PUBLIC_KNOWLEDGE_BUILD" or (task.operation_type in SAFE_RECOVERY_OPERATIONS and task.execution_attempt < MAX_ATTEMPTS))
            state = "QUEUED" if retry else "CANCELLED" if task.cancel_requested else "FAILED"
            result = db.execute(update(KnowledgeBuildTask).where(
                KnowledgeBuildTask.id == task.id, KnowledgeBuildTask.status == "RUNNING",
                KnowledgeBuildTask.execution_attempt == task.execution_attempt,
                or_(KnowledgeBuildTask.lease_expires_at <= now, KnowledgeBuildTask.lease_expires_at.is_(None)),
            ).values(status=state, worker_id=None, lease_expires_at=None,
                     next_attempt_at=now + timedelta(seconds=min(300, 2 ** min(task.execution_attempt, 8))) if retry else None,
                     current_step="等待安全恢复" if retry else "执行中断", error_code="WORKER_INTERRUPTED",
                     completed_at=None if retry else now))
            changed += result.rowcount
            if result.rowcount == 1 and state == "FAILED":
                db.refresh(task)
                _notify_terminal(db, task)
        db.commit()
        return changed
