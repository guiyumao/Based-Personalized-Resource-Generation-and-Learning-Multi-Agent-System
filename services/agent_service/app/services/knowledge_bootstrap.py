"""Student-triggered personal subject draft (P0-2).

Builds a structured subject outline for a learner when the public catalog has no
matching subject/point, **without ever adding to the public SystemSubject /
KnowledgePoint catalog**.  The draft is persisted in
``KnowledgeBuildTask.result_json`` keyed by ``actor_user_id + subject`` so it is
durable, reusable by the same learner, and invisible to other learners and to
public retrieval / public publication.

This is deliberately additive to the existing V8.3 knowledge-construction stack:
the LLM path reuses ``knowledge_construction.plan_subject`` (schema-validated),
and when the live model is not authorized (the default for tests / no-cost
deployments) it falls back to a deterministic, clearly-labelled AI draft.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from common.models.learning import KnowledgeBuildTask

logger = logging.getLogger(__name__)

_OPERATION = "PERSONAL_SUBJECT_DRAFT"
_TEMPLATE = (
    ("基础概念", ("核心定义", "基本术语", "应用场景")),
    ("核心原理", ("关键机制", "原理推导", "典型例题")),
    ("实践应用", ("综合案例", "常见错误", "进阶拓展")),
)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return (slug or "subject")[:100]


def _live_llm_authorized() -> bool:
    """Reuse the project's double gate; a configured key alone is not enough."""
    truthy = {"1", "true", "yes", "on"}
    return (
        os.getenv("RUN_LIVE_LLM", "").strip().lower() in truthy
        and os.getenv("DEEPSEEK_LIVE_PAID_ACK", "").strip().lower() in truthy
    )


def _deterministic_outline(subject: str, knowledge_point: str) -> dict:
    chapters = []
    for name, points in _TEMPLATE:
        chapters.append({
            "name": name,
            "points": [
                {"name": f"{knowledge_point}·{point}" if knowledge_point else point,
                 "aliases": [], "prerequisites": [], "objectives": [f"掌握{point}"]}
                for point in points
            ],
        })
    return {
        "name": subject,
        "code": _slug(subject),
        "aliases": [],
        "description": f"{subject} 的个人学习知识草稿（AI 生成，未经公共审核）",
        "chapters": chapters,
        "source": "deterministic_fallback",
    }


def _chunks_from_outline(outline: dict, subject: str) -> list[dict]:
    chunks: list[dict] = []
    for chapter in outline.get("chapters", []) or []:
        for point in chapter.get("points", []) or []:
            objectives = "；".join(point.get("objectives") or [])
            chunks.append({
                "content": f"{subject} · {chapter.get('name', '')} · {point.get('name', '')}：{objectives}",
                "metadata": {"source": "personal_draft", "scope": "personal_draft",
                             "subject": subject, "chapter": chapter.get("name", "")},
            })
    return chunks


def _try_llm_outline(subject: str, knowledge_point: str) -> dict | None:
    if not _live_llm_authorized():
        return None
    try:
        from services.agent_service.app.services.knowledge_construction import (
            SubjectOutline,
            plan_subject,
        )
        result = plan_subject({"subject": subject, "knowledge_point": knowledge_point})
        outline = result.get("outline")
        if not isinstance(outline, dict):
            return None
        data = SubjectOutline.model_validate(outline).model_dump()  # schema-check before persistence
        data["source"] = "llm"
        return data
    except Exception as exc:  # no credentials / budget / model / validation failure
        logger.warning("personal subject outline LLM unavailable, using deterministic fallback: %s", exc)
        return None


def _index_personal_chunks(user_id: int, subject: str, chunks: list[dict]) -> None:
    """Best-effort upsert of personal chunks into the owner-scoped Chroma namespace.

    Public retrieval fail-closes ``scope=personal_draft`` (see ``visible_chunks``);
    the owner reads them through ``ChromaRetriever.retrieve_personal``. If Chroma
    is unavailable the structured chunks still ground plan generation directly.
    """
    try:
        from services.agent_service.app.services.rag import ChromaRetriever
        retriever = ChromaRetriever()
        if not retriever.is_available:
            return
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        for index, chunk in enumerate(chunks):
            meta = dict(chunk.get("metadata") or {})
            meta["owner_user_id"] = str(user_id)
            meta["scope"] = "personal_draft"
            meta.setdefault("subject", subject)
            key = hashlib.sha256(
                json.dumps(chunk, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()[:24]
            ids.append(f"personal-{user_id}-{key}-{index}")
            documents.append(str(chunk.get("content") or ""))
            metadatas.append(meta)
        if ids:
            retriever.upsert_documents(ids, documents, metadatas)
    except Exception as exc:  # Chroma down / not installed must not block the plan
        logger.warning("personal draft vector index skipped: %s", exc)


def _search_and_fetch_personal(db: Session, user_id: int, subject: str, knowledge_point: str) -> dict | None:
    """P0-3: one bounded Search+Fetch+andidate for a personal subject.

    Reuses the durable ``SEARCH_SOURCES`` / ``FETCH_SOURCE`` knowledge tasks and
    ``create_from_fetch`` candidate layer, but does not require a public
    ``KnowledgePoint``.  Guarded by the same double gate; any external failure
    returns ``None`` so the deterministic draft still works.
    """
    if not _live_llm_authorized():
        return None
    try:
        from common.models.learning import KnowledgeBuildTask as _Task
        from services.agent_service.app.services.deepseek_search import search_sources
        from services.agent_service.app.services.knowledge_candidates import (
            create_from_fetch,
        )

        query = f"{subject} {knowledge_point}".strip()[:128]
        # The public DeepSeek API has no /v1/tools/fetch endpoint (it 404s).
        # Search with need_content=True returns the page body inline, so the
        # "fetch" stage is satisfied without a separate call.
        results = search_sources(query, count=3, need_content=True)
        source = next((row for row in results if row.get("content")), None)
        if not source:
            return None
        key = hashlib.sha256(
            f"{subject}:{knowledge_point}:{source.get('url')}".encode()
        ).hexdigest()[:30]
        fetch_task = _Task(
            actor_user_id=user_id,
            client_request_id=f"personal-fetch-{key}",
            request_hash=hashlib.sha256(str(source.get("url") or "").encode()).hexdigest(),
            trigger_source="student",
            operation_type="FETCH_SOURCE",
            subject=subject,
            requirements_json={"query": query, "source_url": source.get("url")},
            status="COMPLETED",
            current_step="来源正文由搜索结果内联提供",
            result_json={"source": {
                "url": source.get("url") or "",
                "title": source.get("title") or "",
                "content": source.get("content") or "",
            }},
            completed_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(fetch_task)
        try:
            db.commit()
        except Exception:
            db.rollback()
            existing = (
                db.query(_Task)
                .filter_by(actor_user_id=user_id,
                           client_request_id=f"personal-fetch-{key}")
                .first()
            )
            if existing is None:
                raise
            fetch_task = existing
        db.refresh(fetch_task)
        # Candidate/version subject codes must be ASCII slugs; a personal Chinese
        # subject gets a deterministic personal code so it never collides with a
        # public subject code and still validates.
        subject_code = f"personal_{hashlib.sha256(subject.encode()).hexdigest()[:12]}"
        candidate = create_from_fetch(
            db, actor_user_id=user_id, source_task_id=fetch_task.id,
            subject=subject_code, knowledge_point=knowledge_point or subject,
        )
        return {
            "candidate_id": candidate.id,
            "source": {"url": source.get("url"), "title": source.get("title")},
            "chunk": {
                "content": str(source.get("content") or "")[:8000],
                "metadata": {
                    "source": str(source.get("url") or ""),
                    "title": str(source.get("title") or ""),
                    "scope": "personal_draft", "subject": subject,
                    "review_status": "PENDING",
                },
            },
        }
    except Exception as exc:  # no key / budget / network / endpoint failure
        logger.warning("personal Search+Fetch enrichment skipped: %s", exc)
        return None


def build_personal_draft(db: Session, user_id: int, subject: str, knowledge_point: str) -> dict:
    """Return ``{outline, chunks, reused, task_id}`` for a personal subject draft."""
    subject = (subject or "").strip()[:100]
    knowledge_point = (knowledge_point or "").strip()[:100]
    existing = (
        db.query(KnowledgeBuildTask)
        .filter(KnowledgeBuildTask.actor_user_id == user_id,
                KnowledgeBuildTask.subject == subject,
                KnowledgeBuildTask.operation_type == _OPERATION)
        .order_by(KnowledgeBuildTask.id.desc())
        .first()
    )
    if existing is not None and isinstance(existing.result_json, dict) and existing.result_json.get("outline"):
        outline = existing.result_json["outline"]
        chunks = existing.result_json.get("chunks") or _chunks_from_outline(outline, subject)
        return {"outline": outline, "chunks": chunks, "reused": True, "task_id": existing.id,
                "sources": existing.result_json.get("sources") or []}

    outline = _try_llm_outline(subject, knowledge_point) or _deterministic_outline(subject, knowledge_point)
    chunks = _chunks_from_outline(outline, subject)
    # P0-3: when Search/Fetch is authorized, enrich the draft with one real source
    # and persist it as a reviewable candidate. Any failure falls back cleanly.
    enriched = _search_and_fetch_personal(db, user_id, subject, knowledge_point)
    sources: list[dict] = []
    if enriched:
        chunks = [*chunks, enriched["chunk"]]
        sources = [enriched["source"]]
    request_key = json.dumps({"subject": subject, "knowledge_point": knowledge_point},
                             ensure_ascii=False, sort_keys=True)
    task = KnowledgeBuildTask(
        actor_user_id=user_id,
        client_request_id=f"personal-subject-{_slug(subject)}",
        request_hash=hashlib.sha256(request_key.encode()).hexdigest(),
        trigger_source="student",
        operation_type=_OPERATION,
        subject=subject,
        requirements_json={"knowledge_point": knowledge_point},
        status="COMPLETED",
        current_step="个人学科草稿已生成",
        result_json={
            "outline": outline, "chunks": chunks, "scope": "personal_draft",
            "sources": sources,
            "candidate_id": enriched["candidate_id"] if enriched else None,
        },
        completed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(task)
    try:
        db.commit()
    except Exception:
        # Concurrent builder won the unique (actor_user_id, client_request_id) race.
        db.rollback()
        existing = (
            db.query(KnowledgeBuildTask)
            .filter(KnowledgeBuildTask.actor_user_id == user_id,
                    KnowledgeBuildTask.subject == subject,
                    KnowledgeBuildTask.operation_type == _OPERATION)
            .order_by(KnowledgeBuildTask.id.desc())
            .first()
        )
        if existing is not None and isinstance(existing.result_json, dict) and existing.result_json.get("outline"):
            outline = existing.result_json["outline"]
            chunks = existing.result_json.get("chunks") or _chunks_from_outline(outline, subject)
            return {"outline": outline, "chunks": chunks, "reused": True, "task_id": existing.id,
                "sources": existing.result_json.get("sources") or []}
        raise
    db.refresh(task)
    _index_personal_chunks(user_id, subject, chunks)
    return {"outline": outline, "chunks": chunks, "reused": False, "task_id": task.id,
            "sources": sources}
