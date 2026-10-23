"""Persist real external references into the public corpus and retrieval index.

The public knowledge base used to keep only the model-written version body. When
an existing version is a thin placeholder (or when a new point is built), the
retrieved web references were used once for the prompt and then lost. This
module turns those references into durable corpus documents:

* one Markdown file per source under ``knowledge_base/corpus/<subject>/source_*.md``
  with explicit provenance headers (URL, site, license note, fetch time);
* indexed with ``knowledge_point_name`` so retrieval for that point can find the
  raw source without re-fetching it;
* recognised as ``source_type=web_reference`` and never treated as a reviewed
  ``candidate_*`` publication.

Nothing here publishes or rewrites a reviewed knowledge version; it only adds
real reference material that retrieval may use in addition to the version body.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from common.knowledge_lock import knowledge_write_lock
from common.knowledge_paths import CORPUS_DIR, KNOWLEDGE_ROOT
from common.models.learning import KnowledgeBuildTask

SOURCE_TYPE = "web_reference"
_MIN_SOURCE_CHARS = 300
_MAX_SOURCE_CHARS = 12000
_ENRICH_OPERATION = "PUBLIC_SOURCE_ENRICH"
_ENRICH_SKIP_DAYS = 7
_CODE = re.compile(r"^[a-z0-9_]{1,100}$")


def _valid_code(value: str) -> bool:
    return bool(_CODE.fullmatch((value or "").strip()))


def _digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _source_document(
    *,
    subject_code: str,
    knowledge_point: str,
    knowledge_point_id: str,
    source: dict[str, Any],
    fetched_at: datetime,
) -> tuple[str, str]:
    content = str(source.get("content") or "").strip()
    url = str(source.get("url") or "").strip()
    title = re.sub(r"\s+", " ", str(source.get("title") or "")).strip()[:120] or knowledge_point or "外部检索资料"
    site = ""
    try:
        from urllib.parse import urlsplit

        site = urlsplit(url).hostname or ""
    except ValueError:
        site = ""
    digest = _digest(url, content)
    stamp = fetched_at.isoformat()
    header = [
        f"# {title}",
        "",
        f"> 文档ID: source-{digest[:20]}",
        f"> 来源: {url}",
        f"> 来源站点: {site}",
        f"> 来源类型: {SOURCE_TYPE}",
        "> 作者或机构: 外部检索来源",
        "> 授权: external-reference; 仅作检索参考，发布需另审",
        "> 采集范围: public-search",
        "> 语言: zh",
        f"> 爬取时间: {stamp}",
        f"> 更新时间: {stamp}",
        f"> 内容哈希: {hashlib.sha256(content.encode('utf-8')).hexdigest()}",
        f"> 学科: {subject_code} | 难度: 未标注",
        f"> 知识点: {knowledge_point}",
        f"> 知识点ID: {knowledge_point_id or ''}",
        "",
        "## 正文",
        "",
        content[:_MAX_SOURCE_CHARS],
        "",
    ]
    return "\n".join(header), digest


def store_public_sources(
    *,
    subject_code: str,
    knowledge_point: str,
    knowledge_point_id: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Write new external sources to the corpus and refresh the index.

    Returns the stored files (path/url/title). Duplicate URLs/content are
    skipped by deterministic file name, so a repeated fetch is harmless.
    """

    subject_code = (subject_code or "").strip()
    knowledge_point = (knowledge_point or "").strip()[:100]
    if not _valid_code(subject_code) or not knowledge_point or not sources:
        return []

    fetched_at = datetime.now(UTC)
    prepared: list[tuple[Path, str, dict[str, str]]] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        content = str(source.get("content") or "").strip()
        url = str(source.get("url") or "").strip()
        if len(content) < _MIN_SOURCE_CHARS or not url:
            continue
        document, digest = _source_document(
            subject_code=subject_code,
            knowledge_point=knowledge_point,
            knowledge_point_id=str(knowledge_point_id or ""),
            source=source,
            fetched_at=fetched_at,
        )
        if digest in seen:
            continue
        seen.add(digest)
        path = CORPUS_DIR / subject_code / f"source_{digest[:16]}.md"
        prepared.append((path, document, {"url": url, "title": str(source.get("title") or "")}))
    if not prepared:
        return []

    stored: list[dict[str, str]] = []
    with knowledge_write_lock(KNOWLEDGE_ROOT) as token:
        for path, document, meta in prepared:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                continue
            path.write_text(document, encoding="utf-8")
            stored.append({"path": path.relative_to(KNOWLEDGE_ROOT).as_posix(), **meta})
        if stored:
            from services.agent_service.app.services.knowledge_base_admin import (
                _run_index_command,
            )

            _run_index_command(subject=subject_code, force=False, lock_token=token)
    return stored


def has_external_sources(subject_code: str, knowledge_point: str) -> bool:
    """True when this point already has at least one indexed web reference."""

    if not _valid_code(subject_code) or not knowledge_point:
        return False
    try:
        from services.agent_service.app.services.rag import ChromaRetriever

        retriever = ChromaRetriever()
        collection = getattr(retriever, "collection", None)
        if collection is None:
            return False
        result = collection.get(
            where={
                "$and": [
                    {"subject": subject_code},
                    {"knowledge_point_name": knowledge_point},
                    {"source_type": SOURCE_TYPE},
                ]
            },
            limit=1,
            include=["metadatas"],
        )
        return bool(result.get("ids"))
    except Exception:
        return False


def _marker_key(subject_code: str, knowledge_point: str) -> str:
    return _digest("source-enrich", subject_code, knowledge_point.casefold())


def _fresh_marker(db: Session, request_hash: str) -> bool:
    task = (
        db.query(KnowledgeBuildTask)
        .filter_by(operation_type=_ENRICH_OPERATION, request_hash=request_hash)
        .order_by(KnowledgeBuildTask.id.desc())
        .first()
    )
    if task is None or task.status != "COMPLETED" or task.completed_at is None:
        return False
    return task.completed_at >= datetime.utcnow() - timedelta(days=_ENRICH_SKIP_DAYS)


def _save_marker(
    db: Session,
    *,
    actor_user_id: int,
    subject_code: str,
    knowledge_point: str,
    request_hash: str,
    stored_count: int,
    error: str = "",
) -> None:
    task = (
        db.query(KnowledgeBuildTask)
        .filter_by(operation_type=_ENRICH_OPERATION, request_hash=request_hash)
        .order_by(KnowledgeBuildTask.id.desc())
        .first()
    )
    if task is None:
        task = KnowledgeBuildTask(
            actor_user_id=actor_user_id,
            client_request_id=f"source-enrich-{request_hash[:48]}",
            request_hash=request_hash,
            trigger_source="student",
            operation_type=_ENRICH_OPERATION,
            subject=subject_code,
            requirements_json={"knowledge_point": knowledge_point},
            status="COMPLETED",
            current_step="外部检索资料已入库",
            result_json={},
        )
        db.add(task)
    task.status = "COMPLETED"
    task.completed_at = datetime.utcnow()
    task.current_step = f"外部检索资料已入库 {stored_count} 条" + (f"（{error}）" if error else "")
    task.result_json = {
        "stored_count": stored_count,
        "error": error,
        "knowledge_point": knowledge_point,
        "subject": subject_code,
    }
    db.commit()


def ensure_external_sources(
    db: Session,
    *,
    actor_user_id: int,
    subject_label: str,
    subject_code: str,
    knowledge_point: str,
    knowledge_point_id: str = "",
    allow_web: bool,
) -> list[dict[str, str]]:
    """Fetch real references once per point and persist them in the corpus.

    The marker makes a failed/empty search bounded: the same point is not
    searched on every request. Existing indexed sources short-circuit first.
    """

    subject_code = (subject_code or "").strip()
    knowledge_point = (knowledge_point or "").strip()[:100]
    if not allow_web or not _valid_code(subject_code) or not knowledge_point:
        return []
    if has_external_sources(subject_code, knowledge_point):
        return []
    request_hash = _marker_key(subject_code, knowledge_point)
    if _fresh_marker(db, request_hash):
        return []

    query = f"{subject_label or subject_code} {knowledge_point} 教程 详解".strip()[:128]
    try:
        from services.agent_service.app.services.deepseek_search import search_sources

        references = search_sources(query, count=3, need_content=True)
    except Exception as exc:  # network / provider / budget failure is bounded
        _save_marker(
            db,
            actor_user_id=actor_user_id,
            subject_code=subject_code,
            knowledge_point=knowledge_point,
            request_hash=request_hash,
            stored_count=0,
            error=type(exc).__name__,
        )
        return []

    usable = [row for row in references if len(str(row.get("content") or "").strip()) >= _MIN_SOURCE_CHARS]
    try:
        stored = store_public_sources(
            subject_code=subject_code,
            knowledge_point=knowledge_point,
            knowledge_point_id=str(knowledge_point_id or ""),
            sources=usable,
        )
    except Exception as exc:  # index/corpus failure must not retry on every request
        _save_marker(
            db,
            actor_user_id=actor_user_id,
            subject_code=subject_code,
            knowledge_point=knowledge_point,
            request_hash=request_hash,
            stored_count=0,
            error=type(exc).__name__,
        )
        return []
    _save_marker(
        db,
        actor_user_id=actor_user_id,
        subject_code=subject_code,
        knowledge_point=knowledge_point,
        request_hash=request_hash,
        stored_count=len(stored),
    )
    return stored
