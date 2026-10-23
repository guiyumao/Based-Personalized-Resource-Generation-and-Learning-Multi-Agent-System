"""Evidence-based coverage and one shared public context for learning agents."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from common.knowledge_paths import CORPUS_DIR
from common.models.learning import KnowledgeCandidate, KnowledgePoint
from services.agent_service.app.services.knowledge_construction import find_subject, normalize_name
from services.agent_service.app.services.rag import ChromaRetriever


def prepare_generation_context(db: Session, request, *, knowledge_point: str = "") -> dict:
    """Shared gate for courseware, notes, maps, code cases and exercise generation."""
    topic = knowledge_point or request.knowledge_point
    if request.teaching_scope_id:
        return {}  # Keep the existing authenticated private retrieval path.
    point = db.get(KnowledgePoint, int(request.knowledge_point_id)) if str(request.knowledge_point_id).isdigit() else None
    if point is None and not request.subject:
        matches = db.query(KnowledgePoint).filter(KnowledgePoint.name == topic,
            KnowledgePoint.subject_id.is_not(None)).limit(2).all()
        point = matches[0] if len(matches) == 1 else None
    if point and point.subject_id and not request.subject:
        from common.models.learning import SystemSubject
        catalog = db.get(SystemSubject, point.subject_id)
        if catalog:
            request.subject = catalog.name
            request.knowledge_point_id = str(point.id)
    if not request.subject:
        return {}
    acquired = acquire_context(db, actor_user_id=request.user_id, subject=request.subject,
                               knowledge_point=topic, allow_web=getattr(request, 'allow_web_knowledge', True))
    context = acquired['retrieval_context']
    context['knowledge_evidence'] = {key: value for key, value in acquired.items() if key != 'retrieval_context'}
    request.retrieval_context = context
    return context


def assess_coverage(db: Session, *, subject: str, knowledge_point: str, max_source_age_days: int = 365) -> dict[str, Any]:
    catalog = find_subject(db, subject)
    code = catalog.code if catalog and catalog.code else subject
    points = db.query(KnowledgePoint).filter_by(subject_id=catalog.id).all() if catalog else []
    wanted = normalize_name(knowledge_point)
    point = next((item for item in points if wanted in {normalize_name(item.name), *(normalize_name(alias) for alias in item.aliases_json or [])}), None)
    aliases = [knowledge_point, point.name, *(point.aliases_json or [])] if point else [knowledge_point]
    terms = [normalize_name(term) for term in aliases if len(term.strip()) >= 2]
    corpus_evidence = []
    corpus_chunks = []
    corpus_text = ""
    from common.models.learning import KnowledgeVersion
    active_paths = {version.corpus_path.removeprefix("knowledge_base/corpus/")
                    for version in db.query(KnowledgeVersion).filter_by(is_active=True).all()}
    stale_sources = []
    corpus_dir = (CORPUS_DIR / str(code)).resolve()
    if not corpus_dir.is_relative_to(CORPUS_DIR.resolve()):
        raise ValueError("Invalid subject corpus path")
    for path in sorted(corpus_dir.rglob("*.md"))[:500] if corpus_dir.exists() else []:
        if path.name.startswith("candidate_") and path.relative_to(CORPUS_DIR).as_posix() not in active_paths:
            continue
        text = path.read_text(encoding="utf-8")
        if any(term in normalize_name(text) for term in terms):
            corpus_evidence.append(path.relative_to(CORPUS_DIR).as_posix())
            corpus_chunks.append({"id": "corpus:" + path.relative_to(CORPUS_DIR).as_posix(), "content": text[:8000],
                                  "metadata": {"source": path.relative_to(CORPUS_DIR).as_posix(),
                                               "subject": code, "title": path.stem}})
            corpus_text += text[:10000]
            if datetime.utcfromtimestamp(path.stat().st_mtime) < datetime.utcnow() - timedelta(days=max_source_age_days):
                stale_sources.append(path.relative_to(CORPUS_DIR).as_posix())
    retriever = ChromaRetriever()
    indexed: list[dict[str, Any]] = []
    failure = ""
    try:
        if retriever.is_available:
            indexed = retriever.retrieve_with_metadata(knowledge_point, top_k=8, filters={"subject": code})
        else:
            failure = "INDEX_UNAVAILABLE"
    except Exception as exc:
        failure = type(exc).__name__
    exact_indexed = [row for row in indexed if any(term in normalize_name(str(row.get("content") or "") + str(row.get("metadata") or {})) for term in terms)]
    facets = {"definition": ("定义", "definition", "overview"), "principle": ("原理", "algorithm", "mechanism"), "example": ("示例", "案例", "example")}
    combined = (corpus_text + " ".join(str(row.get("content") or "") for row in exact_indexed)).casefold()
    missing = [name for name, words in facets.items() if not any(word in combined for word in words)]
    published = db.query(KnowledgeCandidate).filter_by(subject=str(code), knowledge_point=point.name if point else knowledge_point, status="PUBLISHED").all()
    stale = bool(stale_sources) or bool(published) and all(item.updated_at < datetime.utcnow() - timedelta(days=max_source_age_days) for item in published)
    if failure:
        state = "RETRIEVAL_FAILURE"
    elif stale:
        state = "STALE"
    elif corpus_evidence or exact_indexed:
        state = "PARTIAL" if missing else "COMPLETE"
    elif point and catalog:
        state = "MISSING"
    else:
        state = "UNCERTAIN"
    return {"state": state, "subject": code, "point_id": point.id if point else None,
            "knowledge_point": point.name if point else knowledge_point, "aliases": aliases,
            "corpus_sources": corpus_evidence[:20], "chunks": (exact_indexed + corpus_chunks)[:8],
            "missing_facets": missing, "retrieval_error": failure,
            "stale_sources": stale_sources,
            "assessment": "metadata_alias_keyword_and_semantic_evidence"}


def acquire_context(
    db: Session,
    *,
    actor_user_id: int,
    subject: str,
    knowledge_point: str,
    allow_web: bool,
    enrich_sources: bool = False,
) -> dict[str, Any]:
    from common.config import get_settings
    from services.agent_service.app.services.public_knowledge import ensure_public_knowledge

    verified = ensure_public_knowledge(db, actor_user_id, subject, knowledge_point, allow_web=allow_web)
    chunks = verified["usable_chunks"]
    # A published version can be a thin AI placeholder. When no real external
    # reference is indexed for this point yet, fetch it once, persist it in the
    # corpus and re-read the merged chunks. The marker in knowledge_sources
    # bounds failures so this is not a search on every request.
    if enrich_sources and allow_web and not any(
        str((row.get("metadata") or {}).get("source_type") or "") == "web_reference"
        for row in chunks
    ):
        try:
            from services.agent_service.app.services.knowledge_sources import (
                ensure_external_sources,
            )
            from services.agent_service.app.services.plan_knowledge import (
                require_plan_knowledge,
            )

            stored = ensure_external_sources(
                db,
                actor_user_id=actor_user_id,
                subject_label=subject,
                subject_code=verified["subject"],
                knowledge_point=knowledge_point,
                knowledge_point_id=str(verified.get("point_id") or ""),
                allow_web=allow_web,
            )
            if stored:
                verified = require_plan_knowledge(db, actor_user_id, subject, knowledge_point)
                chunks = verified["usable_chunks"]
        except Exception:
            # Enrichment is additive: the already-verified public chunks remain.
            pass
    now = datetime.utcnow()
    context = {"context_id": hashlib.sha256(f"{subject}:{knowledge_point}:{now.isoformat()}".encode()).hexdigest()[:24],
               "query": knowledge_point, "knowledge_point_id": knowledge_point, "scope_id": "public",
               "knowledge_base_version": get_settings().knowledge_base_version, "retrieved_chunks": chunks,
               "source_ids": [str(row.get("id") or "") for row in chunks], "created_at": f"{now.isoformat()}Z",
               "expire_at": f"{(now + timedelta(minutes=5)).isoformat()}Z", "filters": {"subject": verified["subject"]}}
    return {"coverage": {"state": "COMPLETE", "subject": verified["subject"],
                         "point_id": verified["point_id"], "published_versions": verified["published_versions"]},
            "retrieval_context": context,
            "sources": [
                {
                    "source": (row.get("metadata") or {}).get("source"),
                    "review_status": (
                        "EXTERNAL_REFERENCE"
                        if str((row.get("metadata") or {}).get("source_type") or "") == "web_reference"
                        else "PUBLISHED"
                    ),
                }
                for row in chunks
            ],
            "supplementation": {"status": "MODEL_REVIEWED_PUBLISHED" if verified.get("auto_build") else "NOT_NEEDED",
                                "candidate_ids": [verified["auto_build"]["candidate_id"]] if verified.get("auto_build", {}).get("candidate_id") else [],
                                "reused": not bool(verified.get("auto_build"))}}
