"""Evidence-based coverage and one shared public context for learning agents."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from common.knowledge_paths import CORPUS_DIR
from common.models.learning import KnowledgeBuildTask, KnowledgeCandidate, KnowledgePoint
from services.agent_service.app.services.knowledge_construction import find_subject, normalize_name
from services.agent_service.app.services.rag import ChromaRetriever


def assess_coverage(db: Session, *, subject: str, knowledge_point: str, max_source_age_days: int = 365) -> dict[str, Any]:
    catalog = find_subject(db, subject)
    code = catalog.code if catalog and catalog.code else subject
    points = db.query(KnowledgePoint).filter_by(subject_id=catalog.id).all() if catalog else []
    wanted = normalize_name(knowledge_point)
    point = next((item for item in points if wanted in {normalize_name(item.name), *(normalize_name(alias) for alias in item.aliases_json or [])}), None)
    aliases = [knowledge_point, point.name, *(point.aliases_json or [])] if point else [knowledge_point]
    terms = [normalize_name(term) for term in aliases if len(term.strip()) >= 2]
    corpus_evidence = []
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
            "corpus_sources": corpus_evidence[:20], "chunks": indexed,
            "missing_facets": missing, "retrieval_error": failure,
            "stale_sources": stale_sources,
            "assessment": "metadata_alias_keyword_and_semantic_evidence"}


def acquire_context(db: Session, *, actor_user_id: int, subject: str, knowledge_point: str, allow_web: bool) -> dict[str, Any]:
    coverage = assess_coverage(db, subject=subject, knowledge_point=knowledge_point)
    chunks = list(coverage["chunks"])
    sources = []
    if allow_web and coverage["point_id"] and coverage["state"] in {"MISSING", "PARTIAL", "STALE"}:
        from services.agent_service.app.services.knowledge_tasks import create_task, execute_task
        from services.agent_service.app.services.knowledge_candidates import create_from_fetch
        query = f"{coverage['subject']} {coverage['knowledge_point']} {' '.join(coverage['missing_facets'])}"[:128]
        key = hashlib.sha256(query.encode()).hexdigest()[:30]
        day = datetime.utcnow().strftime("%Y%m%d")
        searched = create_task(db, actor_user_id=actor_user_id, client_request_id=f"dynamic-{day}-{key}-search",
                               operation_type="SEARCH_SOURCES", subject=str(coverage["subject"]), requirements={"query": query})
        execute_task(searched.id)
        db.expire_all(); searched = db.get(KnowledgeBuildTask, searched.id)
        if searched.status == "COMPLETED" and searched.result_json.get("sources"):
            fetched = create_task(db, actor_user_id=actor_user_id, client_request_id=f"dynamic-{day}-{key}-fetch", operation_type="FETCH_SOURCE",
                                  subject=str(coverage["subject"]), requirements={"source_task_id": searched.id, "source_index": 0})
            execute_task(fetched.id)
            db.expire_all(); fetched = db.get(KnowledgeBuildTask, fetched.id)
            if fetched.status == "COMPLETED":
                source = fetched.result_json["source"]
                candidate = create_from_fetch(db, actor_user_id=actor_user_id, source_task_id=fetched.id,
                                              subject=str(coverage["subject"]), knowledge_point=str(coverage["knowledge_point"]))
                chunks.append({"id": f"candidate-{candidate.id}", "content": source["content"][:8000],
                               "metadata": {"source_url": source["url"], "title": source["title"], "review_status": "PENDING", "subject": coverage["subject"]}})
                sources.append({"url": source["url"], "title": source["title"], "review_status": "PENDING"})
    from common.config import get_settings
    seen_urls = {item["url"] for item in sources}
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        url = metadata.get("source_url")
        if url and url not in seen_urls:
            sources.append({"url": url, "title": metadata.get("title") or knowledge_point,
                            "review_status": metadata.get("review_status") or "PUBLISHED"})
            seen_urls.add(url)
    now = datetime.utcnow()
    context = {"context_id": hashlib.sha256(f"{subject}:{knowledge_point}:{now.isoformat()}".encode()).hexdigest()[:24],
               "query": knowledge_point, "knowledge_point_id": knowledge_point, "scope_id": "public",
               "knowledge_base_version": get_settings().knowledge_base_version, "retrieved_chunks": chunks,
               "source_ids": [str(row.get("id") or "") for row in chunks], "created_at": f"{now.isoformat()}Z",
               "expire_at": f"{(now + timedelta(minutes=5)).isoformat()}Z", "filters": {"subject": coverage["subject"]}}
    return {"coverage": {key: value for key, value in coverage.items() if key != "chunks"},
            "retrieval_context": context, "sources": sources}
