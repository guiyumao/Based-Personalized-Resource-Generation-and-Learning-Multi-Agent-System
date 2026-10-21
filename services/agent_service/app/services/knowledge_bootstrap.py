"""Student-triggered subject draft construction + automatic knowledge-base backfill.

Builds a structured subject outline for a learner when the public catalog has no
matching subject/point.  The draft is persisted in
``KnowledgeBuildTask.result_json`` keyed by ``actor_user_id + subject`` so it is
durable and reusable by the same learner.

Product decision (2026-10): the draft no longer waits for an administrator.
``promote_draft_to_knowledge_base`` publishes it straight into the shared
catalog (SystemSubject / KnowledgePoint / KnowledgeVersion + corpus file +
retrieval index), clearly marked as AI-built, so the NEXT request for the same
subject/point is served directly from the knowledge base instead of being
regenerated.  When the retrieval index is unavailable the promotion rolls back
cleanly and the request falls back to the owner-scoped personal draft.

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
import time
import unicodedata
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from common.models.learning import KnowledgeBuildTask

logger = logging.getLogger(__name__)

_OPERATION = "PERSONAL_SUBJECT_DRAFT"
# Bounded wait so concurrent learners queue behind one corpus write instead of
# racing each other into duplicate publications.
_AUTO_LOCK_TIMEOUT_SECONDS = 8.0
_AUTO_LOCK_POLL_SECONDS = 0.05
AUTO_BACKFILL_ORIGIN = "ai_generated_auto_published"
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


def build_subject_outline(db: Session, subject_id: int) -> dict | None:
    """Build a learning outline from the REAL database knowledge points of a subject.

    Unlike the AI draft, this mirrors the reviewed curriculum structure already
    stored in SystemSubject / KnowledgePoint, so generated plan tasks reference
    real catalog points instead of owner-scoped placeholders.
    """
    from common.models.learning import KnowledgePoint, SystemSubject
    subject = db.get(SystemSubject, subject_id)
    if subject is None:
        return None
    points = db.query(KnowledgePoint).filter_by(subject_id=subject_id).all()
    if not points:
        return None
    chapters: dict[str, list] = {}
    for point in points:
        chapters.setdefault(point.chapter or "默认章节", []).append({
            "name": point.name,
            "aliases": point.aliases_json or [],
            "prerequisites": point.prerequisites_json or [],
            "objectives": point.objectives_json or [f"掌握{point.name}"],
        })
    return {
        "name": subject.name,
        "code": subject.code or "",
        "aliases": subject.aliases_json or [],
        "description": subject.description or "",
        "chapters": [{"name": chapter, "points": items} for chapter, items in chapters.items()],
        "source": "curriculum",
    }


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


# ---------------------------------------------------------------------------
# Automatic knowledge-base backfill (publish AI-built drafts as public knowledge)
#
# SQL, the corpus filesystem and Chroma cannot share one atomic transaction, so
# every step below is written to be compensated and replayable:
#   * all writes for one target happen under the existing corpus write lock;
#   * before publishing we re-check for an already reusable publication;
#   * on any failure a compensating routine removes exactly the rows, files and
#     index records THIS call created (never pre-existing data), then replays the
#     project's idempotent ``reconcile`` and, if that is also incomplete, queues
#     a RECONCILE_PUBLICATIONS task and records an ERROR audit entry.
# ---------------------------------------------------------------------------


def _normalized(value: str) -> str:
    from services.agent_service.app.services.knowledge_construction import normalize_name

    return normalize_name(value or "")


def _auto_subject_code(subject: str) -> str:
    """Stable ASCII code derived from the NORMALIZED subject name.

    Two learners writing "计算机网络" / "计算机网络 " therefore target the same
    subject code instead of creating two catalogs.
    """
    return f"auto_{hashlib.sha256(_normalized(subject).encode()).hexdigest()[:12]}"


def _find_reusable_publication(db: Session, root, subject: str, knowledge_point: str) -> dict | None:
    """Return an already active, on-disk, indexed version for this target."""
    from common.models.learning import KnowledgePoint, KnowledgeVersion
    from services.agent_service.app.services.knowledge_construction import find_subject

    catalog = find_subject(db, subject)
    if catalog is None or not catalog.code:
        return None
    wanted = _normalized(knowledge_point)
    point = next(
        (
            item
            for item in db.query(KnowledgePoint).filter_by(subject_id=catalog.id).all()
            if wanted in {_normalized(item.name), *(_normalized(a) for a in item.aliases_json or [])}
        ),
        None,
    )
    if point is None:
        return None
    corpus_root = (root / "knowledge_base" / "corpus").resolve()
    for version in db.query(KnowledgeVersion).filter_by(
        subject=catalog.code, knowledge_point=point.name, is_active=True
    ).all():
        path = root / version.corpus_path
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not resolved.is_relative_to(corpus_root) or not path.is_file():
            continue
        return {
            "subject_id": catalog.id,
            "point_id": point.id,
            "candidate_id": version.candidate_id,
            "version_id": version.id,
            "corpus_path": version.corpus_path,
        }
    return None


def _admin_blocked_reason(db: Session, subject: str, knowledge_point: str) -> str | None:
    """Respect an explicit administrator decision instead of re-publishing."""
    from common.models.learning import KnowledgeCandidate
    from services.agent_service.app.services.knowledge_construction import find_subject

    catalog = find_subject(db, subject)
    if catalog is None or not catalog.code:
        return None
    wanted = _normalized(knowledge_point)
    for item in db.query(KnowledgeCandidate).filter_by(subject=catalog.code).all():
        if _normalized(item.knowledge_point) != wanted:
            continue
        if item.status == "WITHDRAWN":
            return "WITHDRAWN_BY_ADMIN"
        if item.status == "REJECTED":
            return "REJECTED_BY_ADMIN"
    return None


def _point_entry(outline: dict, knowledge_point: str) -> tuple[str, dict | None]:
    """Locate the requested point inside the outline (chapter name, point)."""
    wanted = _normalized(knowledge_point)
    for chapter in (outline or {}).get("chapters") or []:
        for item in chapter.get("points") or []:
            names = {_normalized(str(item.get("name") or ""))}
            names.update(_normalized(str(alias)) for alias in item.get("aliases") or [])
            if wanted in names:
                return str(chapter.get("name") or ""), item
    return "", None


def _draft_document(subject: str, point: str, outline: dict, chunks: list[dict]) -> str:
    """Render ONLY the requested knowledge point as corpus markdown.

    Scenario B: when a subject exists and only one point is missing the backfill
    must add that point, not re-publish the whole curriculum.
    """
    chapter_name, entry = _point_entry(outline, point)
    lines = [
        f"# {subject} · {point}",
        "",
        f"> 来源类型: {AUTO_BACKFILL_ORIGIN}",
        "> 审核状态: AI 自动生成并自动发布，未经人工审核；管理员可修订、复核或下架。",
        "",
    ]
    if chapter_name:
        lines.append(f"## 所属章节：{chapter_name}")
        lines.append("")
    lines.append(f"## 知识点：{point}")
    lines.append("")
    objectives = [str(o) for o in (entry or {}).get("objectives") or []] or [f"掌握{point}"]
    for objective in objectives:
        lines.append(f"- {objective}")
    prerequisites = [str(p) for p in (entry or {}).get("prerequisites") or []]
    if prerequisites:
        lines.append(f"- 前置知识：{'、'.join(prerequisites)}")
    lines.append("")
    for chunk in chunks or []:
        meta = chunk.get("metadata") or {}
        url = str(meta.get("source") or "")
        if url.startswith(("http://", "https://")):
            lines.append("## 参考资料（自动抓取，未经人工核验，不作为可信引用）")
            lines.append("")
            lines.append(f"- {meta.get('title') or url}：{url}")
            lines.append("")
            lines.append(str(chunk.get("content") or "")[:8000])
            lines.append("")
            break
    return "\n".join(lines).strip()


def _validate_draft(point: str, content: str, outline: dict) -> None:
    """Reject empty, mis-attributed or structurally broken drafts."""
    text = (content or "").strip()
    if len(text) < 20:
        raise ValueError("draft content is empty or too short")
    if len(text) > 30000:
        raise ValueError("draft content exceeds the publication size limit")
    if _normalized(point) not in _normalized(text):
        raise ValueError("draft content does not describe the requested knowledge point")
    names = [
        _normalized(str(item.get("name") or ""))
        for chapter in (outline or {}).get("chapters") or []
        for item in chapter.get("points") or []
    ]
    names = [name for name in names if name]
    if len(names) != len(set(names)):
        raise ValueError("outline contains duplicated knowledge points")


def _verify_publication(root, version, subject_code: str) -> None:
    """Verify the file AND the index agree with THIS version."""
    from services.agent_service.app.services.rag import ChromaRetriever

    path = root / version.corpus_path
    if not path.is_file():
        raise RuntimeError("published corpus file is missing")
    document_version = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    source = version.corpus_path.removeprefix("knowledge_base/corpus/")
    retriever = ChromaRetriever()
    if not retriever.is_available:
        raise RuntimeError("retrieval index is unavailable")
    collection = getattr(retriever, "collection", None)
    stored = (
        collection.get(
            where={
                "$and": [
                    {"subject": subject_code},
                    {"source": source},
                    {"document_version": document_version},
                ]
            },
            limit=1,
            include=["documents", "metadatas"],
        )
        if collection is not None
        else {}
    )
    if not (stored.get("ids") or []):
        raise RuntimeError("published version is not retrievable in the index")
    # The hit must belong to THIS subject and describe THIS knowledge point.
    metadata = (stored.get("metadatas") or [{}])[0] or {}
    if str(metadata.get("subject") or "") != subject_code:
        raise RuntimeError("indexed chunk belongs to a different subject")
    body = "\n".join(str(item) for item in stored.get("documents") or [])
    if _normalized(version.knowledge_point) not in _normalized(body):
        raise RuntimeError("indexed chunk does not describe the published knowledge point")


def _delete_index_records(subject_code: str, sources: set[str]) -> None:
    """Best-effort removal of the index rows created by a failed publication."""
    if not sources:
        return
    try:
        from services.agent_service.app.services.rag import (
            ChromaRetriever,
            clear_retrieval_runtime_caches,
        )

        retriever = ChromaRetriever()
        collection = getattr(retriever, "collection", None)
        if collection is None:
            return
        for source in sources:
            where = {"$and": [{"subject": subject_code}, {"source": source}]}
            try:
                collection.delete(where=where)
            except Exception:
                stored = collection.get(where=where, include=[])
                ids = list(stored.get("ids") or [])
                if ids:
                    collection.delete(ids=ids)
        clear_retrieval_runtime_caches()
    except Exception as exc:
        logger.warning("auto-backfill index cleanup failed: %s", exc)


def _record_audit(db: Session, *, level: str, event: str, user_id: int | None, message: str) -> None:
    try:
        from common.models.learning import AuditLog

        db.add(AuditLog(level=level, event=event, actor_user_id=user_id, message=message[:2000]))
        db.commit()
    except Exception as exc:
        logger.warning("auto-backfill audit entry failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def _compensate_publication(
    db: Session,
    *,
    root,
    token: str,
    user_id: int,
    subject_code: str,
    candidate_id: int | None = None,
    created_candidate: bool = False,
    point_id: int | None = None,
    created_point: bool = False,
    subject_id: int | None = None,
    created_subject: bool = False,
    version_ids=(),
    corpus_path: str | None = None,
) -> list[str]:
    """Undo exactly what THIS call created. Idempotent and repeatable."""
    from common.models.learning import (
        KnowledgeCandidate,
        KnowledgePoint,
        KnowledgeVersion,
        SystemSubject,
    )

    problems: list[str] = []
    # 1) Database first: public visibility is gated on SQL active versions, so
    #    removing the rows hides the knowledge even before file/index cleanup.
    try:
        for version_id in version_ids:
            row = db.get(KnowledgeVersion, version_id)
            if row is not None:
                db.delete(row)
        if candidate_id:
            row = db.get(KnowledgeCandidate, candidate_id)
            if row is not None:
                if row.status == "PUBLISHED":
                    # Keep the row for a later retry, but never leave it claiming
                    # a published version that no longer exists.
                    row.status = "AUTO_APPROVED"
                    row.published_version_id = None
                elif created_candidate:
                    db.delete(row)
        if created_point and point_id:
            row = db.get(KnowledgePoint, point_id)
            if row is not None and not db.query(KnowledgeVersion).filter_by(
                subject=subject_code, knowledge_point=row.name
            ).count():
                db.delete(row)
        if created_subject and subject_id:
            row = db.get(SystemSubject, subject_id)
            if row is not None and not db.query(KnowledgePoint).filter_by(subject_id=row.id).count():
                db.delete(row)
        db.commit()
    except Exception as exc:
        db.rollback()
        problems.append(f"db:{type(exc).__name__}:{exc}")

    # 2) Corpus file created by this publication.
    moved_sources: set[str] = set()
    try:
        from pathlib import Path

        corpus_dir = (root / "knowledge_base" / "corpus").resolve()
        targets: list = []
        if corpus_path:
            candidate_path = Path(root / corpus_path)
            if candidate_path.exists():
                targets.append(candidate_path)
        if candidate_id:
            directory = corpus_dir / subject_code
            if directory.is_dir():
                targets.extend(directory.glob(f"candidate_{candidate_id}_*.md"))
        for path in targets:
            resolved = path.resolve()
            if not resolved.is_relative_to(corpus_dir):
                continue
            relative = resolved.relative_to(root).as_posix()
            if db.query(KnowledgeVersion).filter_by(corpus_path=relative, is_active=True).count():
                continue
            pending = resolved.with_suffix(".pending")
            if pending.exists():
                pending.unlink()
            resolved.replace(pending)
            moved_sources.add(resolved.relative_to(corpus_dir).as_posix())
    except Exception as exc:
        problems.append(f"file:{type(exc).__name__}:{exc}")

    # 3) Index records for the retired sources.
    try:
        _delete_index_records(subject_code, moved_sources)
    except Exception as exc:
        problems.append(f"index:{type(exc).__name__}:{exc}")

    # 4) Replay the project's idempotent reconciliation (restores active files,
    #    retires uncommitted ones and reindexes).
    try:
        from services.agent_service.app.services.knowledge_publication import reconcile

        reconcile(db, lock_token=token)
    except Exception as exc:
        problems.append(f"reconcile:{type(exc).__name__}:{exc}")

    if problems:
        logger.error("auto-backfill compensation incomplete: %s", problems)
        _record_audit(
            db,
            level="ERROR",
            event="knowledge.auto_backfill.compensation_incomplete",
            user_id=user_id,
            message=f"subject={subject_code} candidate={candidate_id} problems={problems}",
        )
        # 5) Queue a deterministic, replayable recovery instead of pretending the
        #    rollback succeeded.
        try:
            from services.agent_service.app.services.knowledge_tasks import create_task

            create_task(
                db,
                actor_user_id=user_id,
                client_request_id=f"auto-compensate-{uuid4().hex}",
                operation_type="RECONCILE_PUBLICATIONS",
                subject=subject_code,
                trigger_source="ADMIN_MANUAL",
            )
        except Exception as exc:
            logger.error("auto-backfill recovery task could not be queued: %s", exc)
    return problems


def promote_draft_to_knowledge_base(
    db: Session,
    user_id: int,
    subject: str,
    knowledge_point: str,
    outline: dict,
    chunks: list[dict],
    task_id: int | None = None,
) -> dict | None:
    """Publish an AI-built draft into the shared knowledge base.

    Returns ``{"ok": True, ...}`` with the catalog ids when public knowledge is
    available (created now or reused), or ``{"ok": False, "reason": ...}`` when
    it is not; the caller must then fall back to the personal draft and must
    never present the result as public knowledge.
    """
    subject = (subject or "").strip()[:100]
    knowledge_point = (knowledge_point or "").strip()[:100]
    if not subject or not knowledge_point:
        return {"ok": False, "reason": "MISSING_TARGET"}

    from contextlib import ExitStack

    from common.knowledge_paths import KNOWLEDGE_ROOT
    from common.knowledge_lock import knowledge_write_lock

    created_subject = created_point = created_candidate = False
    catalog = point = candidate = None
    version_ids: list[int] = []
    try:
        with ExitStack() as stack:
            deadline = time.monotonic() + _AUTO_LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    token = stack.enter_context(knowledge_write_lock(KNOWLEDGE_ROOT))
                    break
                except RuntimeError as exc:  # another corpus write is running
                    if time.monotonic() >= deadline:
                        return {"ok": False, "reason": "LOCK_BUSY", "detail": str(exc)}
                    time.sleep(_AUTO_LOCK_POLL_SECONDS)
            try:
                # 1) Reuse first: never create a second active version for a
                #    target that already has public knowledge.
                reused = _find_reusable_publication(db, KNOWLEDGE_ROOT, subject, knowledge_point)
                if reused is not None:
                    return {"ok": True, "reused": True, **reused}

                # 2) An administrator withdrew or rejected this knowledge: do not
                #    silently re-publish it.
                blocked = _admin_blocked_reason(db, subject, knowledge_point)
                if blocked:
                    return {"ok": False, "reason": blocked}

                from sqlalchemy.exc import IntegrityError

                from common.models.learning import (
                    KnowledgeCandidate,
                    KnowledgePoint,
                    SystemSubject,
                )
                from services.agent_service.app.services.knowledge_candidates import (
                    AI_LICENSE_NAME,
                    AUTO_APPROVED_STATUS,
                    publish_candidate,
                )
                from services.agent_service.app.services.knowledge_construction import (
                    find_subject,
                )

                # 3) Catalog rows (identity is matched on the normalized names).
                catalog = find_subject(db, subject)
                if catalog is None:
                    catalog = SystemSubject(
                        name=subject,
                        code=_auto_subject_code(subject),
                        description=str((outline or {}).get("description") or f"{subject}（AI 自动补建）")[:200],
                        outline_json=outline if isinstance(outline, dict) else {},
                        construction_status="PLANNED",
                    )
                    db.add(catalog)
                    try:
                        db.commit()
                        created_subject = True
                    except IntegrityError:
                        db.rollback()
                        catalog = find_subject(db, subject)
                    if catalog is None:
                        return {"ok": False, "reason": "SUBJECT_CREATE_FAILED"}
                if not catalog.code:
                    catalog.code = _auto_subject_code(catalog.name)
                    db.commit()

                wanted = _normalized(knowledge_point)
                point = next(
                    (
                        item
                        for item in db.query(KnowledgePoint).filter_by(subject_id=catalog.id).all()
                        if wanted
                        in {_normalized(item.name), *(_normalized(a) for a in item.aliases_json or [])}
                    ),
                    None,
                )
                if point is None:
                    chapter_name, entry = _point_entry(outline, knowledge_point)
                    objectives = [str(o)[:200] for o in (entry or {}).get("objectives") or []][:10]
                    point = KnowledgePoint(
                        name=knowledge_point,
                        subject_id=catalog.id,
                        chapter=chapter_name[:160],
                        aliases_json=[],
                        objectives_json=objectives or [f"掌握{knowledge_point}"],
                        prerequisites_json=[],
                        construction_status="PLANNED",
                    )
                    db.add(point)
                    db.commit()
                    created_point = True

                # 4) Content + quality gates.
                content = _draft_document(catalog.name, point.name, outline, chunks)
                _validate_draft(point.name, content, outline)
                source_url = ""
                for chunk in chunks or []:
                    url = str((chunk.get("metadata") or {}).get("source") or "")
                    if url.startswith(("http://", "https://")):
                        source_url = url
                        break

                # 5) Candidate: reuse an existing row for the same target so a
                #    concurrent request cannot create a duplicate publication.
                if task_id is None:
                    request_key = json.dumps(
                        {"subject": subject, "knowledge_point": knowledge_point},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    backfill = KnowledgeBuildTask(
                        actor_user_id=user_id,
                        client_request_id=f"auto-backfill-{_slug(subject)}",
                        request_hash=hashlib.sha256(request_key.encode()).hexdigest(),
                        trigger_source="student",
                        operation_type=_OPERATION,
                        subject=subject,
                        requirements_json={"knowledge_point": knowledge_point},
                        status="COMPLETED",
                        current_step="学习知识草稿自动补建入库",
                        result_json={"outline": outline, "chunks": chunks, "scope": "auto_backfill"},
                        completed_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    db.add(backfill)
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                        backfill = (
                            db.query(KnowledgeBuildTask)
                            .filter_by(
                                actor_user_id=user_id,
                                client_request_id=f"auto-backfill-{_slug(subject)}",
                            )
                            .first()
                        )
                        if backfill is None:
                            raise
                    task_id = backfill.id

                candidate = db.query(KnowledgeCandidate).filter_by(source_task_id=task_id).first()
                if candidate is None:
                    candidate = (
                        db.query(KnowledgeCandidate)
                        .filter_by(subject=catalog.code, knowledge_point=point.name)
                        .filter(
                            KnowledgeCandidate.status.in_(
                                ("DRAFT", "PENDING_REVIEW", "APPROVED", AUTO_APPROVED_STATUS, "PUBLISHED")
                            )
                        )
                        .order_by(KnowledgeCandidate.id.desc())
                        .first()
                    )
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                license_evidence = (
                    source_url or f"https://autogen.example.com/license/{content_hash[:12]}"
                )
                review_note = (
                    "AI 自动生成并自动发布，未经人工审核；管理员可修订、复核或下架。"
                )
                if candidate is None:
                    candidate = KnowledgeCandidate(
                        creator_user_id=user_id,
                        source_task_id=task_id,
                        subject=catalog.code,
                        knowledge_point=point.name[:160],
                        title=f"{catalog.name} · {point.name}"[:240],
                        content=content,
                        source_url=source_url,
                        source_hash=hashlib.sha256(
                            (source_url or f"auto:{catalog.code}:{point.name}").encode()
                        ).hexdigest(),
                        content_hash=content_hash,
                        status=AUTO_APPROVED_STATUS,
                        review_notes=review_note,
                        license_name=AI_LICENSE_NAME,
                        license_evidence_url=license_evidence,
                        publication_allowed=True,
                    )
                    db.add(candidate)
                    created_candidate = True
                else:
                    candidate.subject = catalog.code
                    candidate.knowledge_point = point.name[:160]
                    candidate.title = f"{catalog.name} · {point.name}"[:240]
                    candidate.content = content
                    candidate.content_hash = content_hash
                    if source_url:
                        candidate.source_url = source_url
                        candidate.source_hash = hashlib.sha256(source_url.encode()).hexdigest()
                    candidate.status = AUTO_APPROVED_STATUS
                    candidate.review_notes = review_note
                    candidate.reviewed_by = None
                    candidate.reviewed_at = None
                    candidate.license_name = candidate.license_name or AI_LICENSE_NAME
                    candidate.license_evidence_url = (
                        candidate.license_evidence_url or license_evidence
                    )
                    candidate.publication_allowed = True
                db.commit()
                db.refresh(candidate)

                # 6) Publish through the normal pipeline under our lock ownership.
                version, _matches = publish_candidate(
                    db, candidate, publisher_user_id=user_id, lock_token=token
                )
                version_ids.append(version.id)
                # 7) Verify file + index agree with THIS version.
                _verify_publication(KNOWLEDGE_ROOT, version, catalog.code)
                _record_audit(
                    db,
                    level="INFO",
                    event="knowledge.auto_backfill.published",
                    user_id=user_id,
                    message=(
                        f"subject={catalog.code} point={point.name} candidate={candidate.id} "
                        f"version={version.id} origin={AUTO_BACKFILL_ORIGIN} (auto published, not human reviewed)"
                    ),
                )
                return {
                    "ok": True,
                    "reused": False,
                    "subject_id": catalog.id,
                    "point_id": point.id,
                    "candidate_id": candidate.id,
                    "version_id": version.id,
                    "corpus_path": version.corpus_path,
                }
            except Exception as exc:
                reason = f"{type(exc).__name__}:{exc}"[:200]
                logger.warning("draft auto-promotion failed, compensating: %s", reason)
                try:
                    db.rollback()
                except Exception:
                    pass
                _compensate_publication(
                    db,
                    root=KNOWLEDGE_ROOT,
                    token=token,
                    user_id=user_id,
                    subject_code=(catalog.code if catalog is not None else _auto_subject_code(subject)),
                    candidate_id=(candidate.id if candidate is not None else None),
                    created_candidate=created_candidate,
                    point_id=(point.id if point is not None else None),
                    created_point=created_point,
                    subject_id=(catalog.id if catalog is not None else None),
                    created_subject=created_subject,
                    version_ids=tuple(version_ids),
                    corpus_path=None,
                )
                _record_audit(
                    db,
                    level="WARNING",
                    event="knowledge.auto_backfill.failed",
                    user_id=user_id,
                    message=f"subject={subject} point={knowledge_point} reason={reason}",
                )
                return {"ok": False, "reason": "PUBLISH_FAILED", "detail": reason}
    except Exception as exc:
        # Unexpected failure outside the locked section (import/IO/lock setup).
        logger.error("draft auto-promotion could not run: %s", exc)
        return {"ok": False, "reason": "BACKFILL_UNAVAILABLE", "detail": str(exc)[:200]}
