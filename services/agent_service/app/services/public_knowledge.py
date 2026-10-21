"""Student queries build shared knowledge; model review and publication fail closed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, StrictStr

from common.config import get_settings
from common.performance import get_current_trace, traced_invoke
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


def _invoke_public_model(template: str, data: dict, *, stage: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    ensure_execution_active()
    model = LLMFactory(get_settings()).build_chat_model(temperature=0.0 if stage == "audit" else 0.2)
    result = traced_invoke(model, [
        SystemMessage(content=(PROMPTS / template).read_text(encoding="utf-8")),
        HumanMessage(content=json.dumps(data, ensure_ascii=False)),
    ], stage=stage)
    content = getattr(result, "content", result)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Public knowledge model returned no text")
    return content.strip()


def review_public_content(subject: str, topic: str, content: str) -> dict:
    """No rule-only approval, fallback PASS, or truncation of the reviewed body."""
    try:
        raw = _invoke_public_model("public_knowledge_review.md", {
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


def ensure_public_knowledge(db, user_id: int, subject: str, topic: str, *, allow_web: bool = True) -> dict:
    """Return only verified current public chunks, never owner-scoped drafts."""
    from services.agent_service.app.services.knowledge_bootstrap import (
        promote_draft_to_knowledge_base,
    )
    from services.agent_service.app.services.plan_knowledge import (
        plan_preflight,
        require_plan_knowledge,
    )

    initial = plan_preflight(db, user_id, subject, topic)
    if initial["ready"]:
        return {**initial, "mode": "public"}
    if initial["reason"] in {"INDEX_UNAVAILABLE", "INDEX_STALE_OR_MISSING"}:
        raise HTTPException(503, {"code": initial["reason"], "gap_id": initial.get("gap_id"),
                                  "message": "公共知识已发布但索引不可用；未创建重复内容，也不使用个人草稿。"})
    # Only the public target enters these calls; no user profile or private attachments.
    outline = {"name": subject, "source": "llm_public", "chapters": [
        {"name": "公共知识", "points": [{"name": topic, "objectives": [f"理解并应用{topic}"]}]}]}
    references = []
    if allow_web:
        try:
            from services.agent_service.app.services.deepseek_search import search_sources
            references = [{"url": row.get("url"), "title": row.get("title"),
                           "content": str(row.get("content") or "")[:5000]}
                          for row in search_sources(f"{subject} {topic}"[:128], count=3, need_content=True)
                          if row.get("content") and row.get("url")][:3]
        except Exception:
            references = []  # Model-origin content remains explicitly marked; no fake sources.
    issues = []
    for attempt in range(2):
        ensure_execution_active()
        if attempt:
            trace = get_current_trace()
            if trace and not trace.can_retry():
                break
            if trace:
                trace.record_retry(stage="public_knowledge", reason="model_review_rejected", audit=True)
        try:
            body = _invoke_public_model("public_knowledge_build.md", {
                "subject": subject, "knowledge_point": topic, "revision_issues": issues,
                "public_references": references,
            }, stage="generation")
        except ExecutionStopped:
            raise
        except Exception as exc:
            raise HTTPException(503, {"code": "PUBLIC_KNOWLEDGE_BUILD_UNAVAILABLE",
                                      "message": "公共知识模型建设失败，未生成个人草稿。"}) from exc
        if len(body) < 400 or len(body) > 28000:
            issues = ["正文须为400至28000字符的完整知识讲解，不能只有提纲。"]
            continue
        ensure_execution_active()
        result = promote_draft_to_knowledge_base(db, user_id, subject, topic, outline, [
            {"content": body, "metadata": {"generated_for_public": True, "source": "model_generated"}},
        ]) or {}
        if result.get("ok"):
            verified = require_plan_knowledge(db, user_id, subject, topic)
            return {**verified, "mode": "public", "auto_build": result}
        if result.get("reason") != "MODEL_REVIEW_REJECTED":
            raise HTTPException(503, {"code": result.get("reason", "PUBLIC_PUBLICATION_FAILED"),
                                      "message": "公共知识审核或发布未完成，未进入学习生成，也未回退私人草稿。"})
        issues = result.get("review", {}).get("issues") or [result.get("review", {}).get("reason", "模型审核未通过")]
    raise HTTPException(422, {"code": "PUBLIC_KNOWLEDGE_REJECTED", "issues": issues,
                              "message": "公共知识经修订仍未通过模型审核，未发布、未生成学习计划。"})
