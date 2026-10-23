"""Student queries build shared knowledge; model review and publication fail closed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, StrictStr

from common.config import get_settings
from common.performance import traced_invoke
from services.agent_service.app.services.assistant_execution import (
    ExecutionStopped,
    ensure_execution_active,
)
from services.agent_service.app.services.llm_factory import LLMFactory

PROMPTS = Path(__file__).resolve().parents[4] / "prompts"


class KnowledgeReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["PASS", "REJECT"]
    reason: StrictStr
    issues: list[StrictStr]


def _invoke_public_model(template: str, data: dict, *, stage: str) -> tuple[str, str]:
    """Return the model text and its finish reason ("stop" / "length" / ...).

    The provider caps output at 8192 tokens. A long knowledge document can hit
    that cap, producing a body that ends mid-sentence; the caller must see
    "length" so it can ask for a shorter rewrite instead of publishing (and
    re-reviewing) a truncated document forever.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    ensure_execution_active()
    model = LLMFactory(get_settings()).build_chat_model(temperature=0.0 if stage == "audit" else 0.2)
    result = traced_invoke(model, [
        SystemMessage(content=(PROMPTS / template).read_text(encoding="utf-8")),
        HumanMessage(content=json.dumps(data, ensure_ascii=False)),
    ], stage=stage)
    content = getattr(result, "content", result)
    metadata = getattr(result, "response_metadata", None) or {}
    finish_reason = str(metadata.get("finish_reason") or "").lower()
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Public knowledge model returned no text")
    return content.strip(), finish_reason


def review_public_content(subject: str, topic: str, content: str) -> dict:
    """No rule-only approval, fallback PASS, or truncation of the reviewed body."""
    try:
        raw, _ = _invoke_public_model("public_knowledge_review.md", {
            "subject": subject, "knowledge_point": topic, "content": content,
        }, stage="audit")
        review = KnowledgeReview.model_validate_json(raw)
        if not review.reason.strip() or (review.verdict == "PASS" and review.issues):
            raise ValueError("Inconsistent model review")
        return {"passed": review.verdict == "PASS", "method": "llm",
                **review.model_dump(), "content_sha256": hashlib.sha256(content.encode()).hexdigest()}
    except ExecutionStopped:
        raise
    except Exception:
        # Provider errors, malformed JSON and missing credentials never approve.
        return {"passed": False, "method": "llm", "verdict": "UNAVAILABLE",
                "reason": "MODEL_REVIEW_UNAVAILABLE", "issues": []}


def advance_public_build(db, task, guard=None) -> dict:
    """One checkpointed model revision round; every unresolved state is retryable."""
    from services.agent_service.app.services.knowledge_bootstrap import (
        promote_draft_to_knowledge_base,
    )
    from services.agent_service.app.services.plan_knowledge import (
        plan_preflight,
        require_plan_knowledge,
    )

    topic = task.requirements_json["knowledge_point"]
    subject = task.subject
    state = dict(task.result_json or {})
    def checkpoint(step):
        if guard:
            guard(db)
        task.result_json = dict(state)
        task.current_step = step
        db.commit()
    try:
        initial = plan_preflight(db, task.actor_user_id, subject, topic)
        if initial["ready"]:
            return {**state, "ready": True, "published_versions": initial["published_versions"]}
        if initial["reason"] in {"INDEX_UNAVAILABLE", "INDEX_STALE_OR_MISSING"}:
            # Repair the existing public index instead of regenerating its content.
            from services.agent_service.app.services.knowledge_base_admin import (
                reindex_knowledge_base,
            )
            reindex_knowledge_base(subject=initial["subject"], force=False)
            verified = require_plan_knowledge(db, task.actor_user_id, subject, topic)
            return {**state, "ready": True, "published_versions": verified["published_versions"]}
        outline = {"name": subject, "source": "llm_public", "chapters": [
            {"name": "公共知识", "points": [{"name": topic, "objectives": [f"理解并应用{topic}"]}]}]}
        if not state.get("sources_checked") and task.requirements_json.get("allow_web"):
            state["sources_checked"] = True
            try:
                from services.agent_service.app.services.deepseek_search import search_sources
                state["public_references"] = [
                    {"url": row.get("url"), "title": row.get("title"), "content": str(row.get("content") or "")[:5000]}
                    for row in search_sources(f"{subject} {topic}"[:128], count=3, need_content=True)
                    if row.get("url") and row.get("content")][:3]
            except Exception:
                state["public_references"] = []
            try:
                from services.agent_service.app.services.knowledge_sources import (
                    store_public_sources,
                )

                state["stored_sources"] = store_public_sources(
                    subject_code=str(initial.get("subject") or ""),
                    knowledge_point=topic,
                    knowledge_point_id=str(initial.get("point_id") or ""),
                    sources=list(state["public_references"]),
                )
            except Exception:
                state["stored_sources"] = []
            checkpoint("公共资料准备完成，继续模型建设")
        if not state.get("public_body") or state.get("revision_issues"):
            state["rounds"] = int(state.get("rounds", 0)) + 1
            checkpoint("模型正在建设或修改公共知识")
            body, finish_reason = _invoke_public_model("public_knowledge_build.md", {
                "subject": subject, "knowledge_point": topic,
                "previous_content": state.get("public_body", ""),
                "revision_issues": state.get("revision_issues", []),
                "public_references": state.get("public_references", []),
            }, stage="generation")
            state["public_body"] = body
            state["revision_issues"] = []
            if finish_reason == "length":
                # Do not review or publish a document that the provider cut off.
                # Publishing it would loop: review rejects it as incomplete,
                # the rewrite overflows the same cap, and the task retries
                # forever (observed: 11 attempts, ~190k wasted tokens).
                state["truncations"] = int(state.get("truncations", 0)) + 1
                budget = max(1800, int(6000 / max(1, state["truncations"])))
                state["revision_issues"] = [
                    "上一轮输出达到模型长度上限被截断，正文不完整，无法入库。"
                    f"请把全文压缩到 {budget} 汉字以内（约 {budget * 2 // 3} tokens），"
                    "保留定义、原理、关键步骤、一个可验算案例、边界与常见错误，"
                    "删除重复段落与冗长推导，必须完整收尾。"
                ]
                checkpoint("正文超过模型输出上限被截断，已要求压缩重写")
                return {**state, "ready": False, "retry_reason": "OUTPUT_TRUNCATED"}
            checkpoint("公共正文已入数据库，模型正在审核")
        body = state["public_body"]
        if len(body) < 400 or len(body) > 28000:
            state["revision_issues"] = ["请将完整正文修订为400至28000字符，不得仅提供目录。"]
            checkpoint("正文已保存，等待模型自动修订篇幅")
            return {**state, "ready": False, "retry_reason": "MODEL_REVISING"}
        if guard:
            guard()
        result = promote_draft_to_knowledge_base(db, task.actor_user_id, subject, topic, outline, [
            {"content": body, "metadata": {"generated_for_public": True, "source": "model_generated"}},
        ], task_id=task.id, guard=guard) or {}
        state["publication"] = result
        if result.get("ok"):
            verified = require_plan_knowledge(db, task.actor_user_id, subject, topic)
            return {**state, "ready": True, "published_versions": verified["published_versions"]}
        review = result.get("review", {})
        state["review"] = review
        if result.get("reason") == "MODEL_REVIEW_REJECTED":
            issues = review.get("issues") or [review.get("reason") or "请检查并修改内容，完成知识库融入。"]
            # Hand-computed bit/number tables (CRC division is the usual offender)
            # are where the model keeps producing self-contradictory arithmetic;
            # asking it to "redo the same calculation" loops forever. Require a
            # different, arithmetic-free example instead.
            state["revision_issues"] = [
                "若审核意见涉及逐位或数值演算（例如 CRC 手算表、商位与余数），不要再次重算同一个示例："
                "直接删除该演算示例及相关余数/商位/自相矛盾的句子，改用一个不依赖复杂算术的案例"
                "（如帧封装流程、状态迁移表、字段含义对比），并保证全文只保留一份结果。"
            ] + list(issues)
        checkpoint("内容已入数据库，模型自动修改后继续融入知识库")
        return {**state, "ready": False, "retry_reason": result.get("reason", "PUBLICATION_RETRY")}
    except Exception:
        db.rollback()
        if guard:
            guard()  # Cancellation/lease loss still fences writes and retries.
        state["retry_reason"] = "PUBLIC_BUILD_RETRY"
        checkpoint("公共知识任务已保存，服务恢复后自动继续修改与融入")
        return {**state, "ready": False}


def ensure_public_knowledge(db, user_id: int, subject: str, topic: str, *, allow_web: bool = True) -> dict:
    """Persist first; models revise and integrate automatically, without rejection."""
    from datetime import datetime

    from sqlalchemy.exc import IntegrityError

    from common.models.learning import KnowledgeBuildTask
    from services.agent_service.app.services.knowledge_tasks import execute_task
    from services.agent_service.app.services.plan_knowledge import (
        plan_preflight,
        require_plan_knowledge,
    )

    initial = plan_preflight(db, user_id, subject, topic)
    if initial["ready"]:
        return {**initial, "mode": "public"}
    request_key = hashlib.sha256(f"{subject.strip().casefold()}:{topic.strip().casefold()}".encode()).hexdigest()
    task = db.query(KnowledgeBuildTask).filter_by(operation_type="PUBLIC_KNOWLEDGE_BUILD", request_hash=request_key).order_by(KnowledgeBuildTask.id.desc()).first()
    if task is None:
        task = KnowledgeBuildTask(actor_user_id=user_id, client_request_id=f"public-{request_key[:48]}",
            request_hash=request_key, trigger_source="student", operation_type="PUBLIC_KNOWLEDGE_BUILD",
            subject=subject, requirements_json={"knowledge_point": topic, "allow_web": allow_web},
            status="QUEUED", current_step="公共建设请求已入数据库，等待模型自动处理", result_json={})
        db.add(task)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            task = db.query(KnowledgeBuildTask).filter_by(operation_type="PUBLIC_KNOWLEDGE_BUILD", request_hash=request_key).order_by(KnowledgeBuildTask.id.desc()).first()
            if task is None:
                raise
    if task.status in {"FAILED", "COMPLETED"}:
        task.status = "QUEUED"
        task.completed_at = None
        task.next_attempt_at = None
        db.commit()
    if task.status == "QUEUED" and (task.next_attempt_at is None or task.next_attempt_at <= datetime.utcnow()):
        execute_task(task.id)
    db.expire_all()
    task = db.get(KnowledgeBuildTask, task.id)
    verified = plan_preflight(db, user_id, subject, topic)
    if verified["ready"]:
        return {**require_plan_knowledge(db, user_id, subject, topic), "mode": "public", "auto_build": (task.result_json or {}).get("publication", {})}
    raise HTTPException(202, {"code": "PUBLIC_KNOWLEDGE_PROCESSING", "task_id": task.id,
        "status": task.status, "message": "内容已保存，模型正在自动审核、修改并融入公共知识库；完成后自动继续生成，无需管理员处理。"})
