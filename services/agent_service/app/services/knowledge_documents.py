"""One administrative catalog over existing corpus files and staged uploads.

Reads never import or publish files. Uploads remain outside CORPUS_DIR until the
existing candidate review/version pipeline publishes them.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from common.knowledge_paths import CORPUS_DIR, KNOWLEDGE_ROOT
from common.models.learning import (
    AuditLog,
    KnowledgeBuildTask,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeDocumentPoint,
    KnowledgePoint,
    KnowledgeVersion,
    SystemSubject,
)
from scripts.index_resources import _extract_source_metadata, _extract_title
from services.agent_service.app.services.assistant_attachments import (
    extract_document_text,
    safe_file_name,
)
from services.agent_service.app.services.knowledge_base_admin import _read_manifest
from services.agent_service.app.services.knowledge_construction import normalize_name

UPLOADS = KNOWLEDGE_ROOT / "knowledge_base" / "originals"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise HTTPException(422, "Unsafe document path")
    return path


def audit(db: Session, actor: int, event: str, message: str):
    db.add(AuditLog(level="INFO", event=event, actor_user_id=actor, message=message))


def catalog(db: Session) -> list[dict]:
    records = {row.id: row for row in db.query(KnowledgeDocument).all()}
    subjects = {row.id: row for row in db.query(SystemSubject).all()}
    versions = {row.id: row for row in db.query(KnowledgeVersion).all()}
    candidates = {row.id: row for row in db.query(KnowledgeCandidate).all()}
    point_ids: dict[str, list[int]] = {}
    for link in db.query(KnowledgeDocumentPoint).all():
        point_ids.setdefault(link.document_id, []).append(link.point_id)
    manifest = _read_manifest().get("documents", {})
    if not isinstance(manifest, dict):
        manifest = {}
    files: dict[str, tuple[str, str]] = {}
    for path in sorted(CORPUS_DIR.rglob("*.md")) if CORPUS_DIR.exists() else []:
        if not path.resolve().is_relative_to(CORPUS_DIR.resolve()) or not path.is_file():
            continue
        relative = path.relative_to(CORPUS_DIR).as_posix()
        files[digest(relative)[:24]] = (
            relative,
            path.read_text(encoding="utf-8", errors="replace"),
        )
    # Hide the physical publication's duplicate entry when an upload owns it.
    owned_paths = {
        versions[candidates[r.candidate_id].published_version_id].corpus_path.removeprefix(
            "knowledge_base/corpus/"
        )
        for r in records.values()
        if r.candidate_id in candidates
        and candidates[r.candidate_id].published_version_id in versions
    }
    result = []
    for doc_id in sorted(set(files) | set(records)):
        row = records.get(doc_id)
        relative, text = (
            files.get(doc_id, (row.corpus_path or "", row.text_content)) if row else files[doc_id]
        )
        if row is None and relative in owned_paths:
            continue
        candidate = candidates.get(row.candidate_id) if row else None
        version = versions.get(candidate.published_version_id) if candidate else None
        if version:
            relative = version.corpus_path.removeprefix("knowledge_base/corpus/")
        path = contained(CORPUS_DIR, relative) if relative else None
        metadata = _extract_source_metadata(text)
        if row and row.original_path:
            metadata = {
                **metadata,
                "source_type": "uploaded_document",
                "source_url": f"upload://{row.id}/{row.file_name}",
            }
        subject = subjects.get(row.subject_id) if row else None
        # Legacy directory labels may suggest a subject, but never create a link.
        corpus_subject = relative.split("/")[0] if "/" in relative else ""
        entry = manifest.get(relative)
        index_state = "NOT_INDEXED"
        if isinstance(entry, dict):
            if path and path.is_file():
                current_hash = digest(path.read_text(encoding="utf-8"))
                index_state = (
                    "INDEXED" if entry.get("document_version") == current_hash else "STALE"
                )
            else:
                index_state = "MISSING_FILE"
        status = candidate.status if candidate else "LEGACY_CORPUS" if relative else "DRAFT"
        if row and row.archived:
            status = "ARCHIVED"
        original = contained(UPLOADS, row.original_path) if row and row.original_path else path
        result.append(
            {
                "id": doc_id,
                "title": row.title if row else _extract_title(text, path),
                "file_name": row.file_name if row else path.name,
                "format": Path(row.file_name if row else path.name).suffix.lstrip("."),
                "content_type": row.content_type if row else "text/markdown",
                "subject_id": row.subject_id if row else None,
                "subject_name": subject.name if subject else "",
                "corpus_subject": corpus_subject,
                "chapter": row.chapter if row else "",
                "tags": row.tags_json if row else [],
                "point_ids": point_ids.get(doc_id, []),
                "status": status,
                "index_status": index_state,
                "candidate_id": candidate.id if candidate else None,
                "active_version": bool(version and version.is_active),
                "source": metadata,
                "source_url": metadata.get("source_url", ""),
                "text": text,
                "corpus_path": relative,
                "original_available": bool(original and original.is_file()),
                "updated_at": (
                    row.updated_at.replace(tzinfo=UTC).isoformat()
                    if row
                    else datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
                ),
                "parsed": bool(text.strip()),
                "parse_status": "EXTRACTED" if text.strip() else "UNAVAILABLE",
                "created_at": row.created_at.replace(tzinfo=UTC).isoformat()
                if row
                else datetime.fromtimestamp(path.stat().st_ctime, UTC).isoformat(),
                "content_hash": digest(text),
            }
        )
    return sorted(result, key=lambda item: item["updated_at"], reverse=True)


def get_document(db: Session, doc_id: str) -> dict:
    item = next((item for item in catalog(db) if item["id"] == doc_id), None)
    if item is None:
        raise HTTPException(404, "Document not found")
    return item


def summary(item: dict) -> dict:
    return {key: value for key, value in item.items() if key != "text"}


def inventory(db: Session, items: list[dict]) -> dict:
    from scripts.crawl_resources import TARGETS

    urls = {
        item["source_url"]
        for item in items
        if item["source_url"].startswith(("https://", "http://"))
    }
    return {
        "subjects": db.query(SystemSubject).count(),
        "documents": len(items),
        "physical_corpus_files": sum(
            1
            for p in CORPUS_DIR.rglob("*.md")
            if p.is_file() and p.resolve().is_relative_to(CORPUS_DIR.resolve())
        ),
        "original_upload_files": sum(1 for p in UPLOADS.rglob("*") if p.is_file())
        if UPLOADS.exists()
        else 0,
        "metadata_records": db.query(KnowledgeDocument).count(),
        "parsed": sum(item["parsed"] for item in items),
        "indexed": sum(item["index_status"] == "INDEXED" for item in items),
        "source_websites": len({urlsplit(url).hostname for url in urls}),
        "source_urls": len(urls),
        "allowlist_rules": len(TARGETS),
        "published": sum(item["active_version"] for item in items),
        "pending_review": sum(item["status"] == "PENDING_REVIEW" for item in items),
        "unclassified": sum(item["subject_id"] is None for item in items),
        "index_anomalies": sum(item["index_status"] in {"STALE", "MISSING_FILE"} for item in items),
        "index_evidence": "manifest; live chunks are queried separately",
    }


def upload(db: Session, actor: int, file_name: str, data: bytes) -> KnowledgeDocument:
    content_type, text = extract_document_text(file_name, data)
    doc_id = uuid4().hex
    name = safe_file_name(file_name)
    original_path = doc_id + Path(name).suffix.lower()
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = contained(UPLOADS, original_path)
    path.write_bytes(data)
    row = KnowledgeDocument(
        id=doc_id,
        title=Path(name).stem[:240],
        file_name=name,
        original_path=original_path,
        content_type=content_type,
        text_content=text,
        content_hash=digest(text),
        creator_user_id=actor,
    )
    try:
        db.add(row)
        audit(db, actor, "knowledge.document.uploaded", f"document={doc_id} bytes={len(data)}")
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return row


def classify(
    db: Session,
    actor: int,
    ids: list[str],
    subject_id: int,
    point_ids: list[int],
    chapter: str,
    tags: list[str],
):
    subject = db.get(SystemSubject, subject_id)
    if subject is None:
        raise HTTPException(422, "Subject not found")
    points = db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()
    if len(points) != len(set(point_ids)) or any(p.subject_id != subject_id for p in points):
        raise HTTPException(422, "Knowledge points must belong to the selected subject")
    items = [get_document(db, doc_id) for doc_id in ids]  # validate all before writes
    for item in items:
        if item["candidate_id"] and item["status"] not in {"DRAFT", "REJECTED"}:
            raise HTTPException(
                409, "Start a reviewed revision before changing classified publication"
            )
    for item in items:
        row = db.get(KnowledgeDocument, item["id"])
        if row is None:
            row = KnowledgeDocument(
                id=item["id"],
                title=item["title"],
                file_name=item["file_name"],
                corpus_path=item["corpus_path"],
                content_type=item["content_type"],
                text_content="",
                content_hash=item["content_hash"],
                creator_user_id=actor,
            )
            db.add(row)
        row.subject_id, row.chapter, row.tags_json = subject_id, chapter, tags
        if row.candidate_id:
            # Keep draft and catalog in agreement; existing review is invalidated.
            candidate = db.get(KnowledgeCandidate, row.candidate_id)
            if candidate.published_version_id and candidate.subject != subject.code:
                raise HTTPException(
                    409,
                    "Published documents keep their original subject; create a separate classified document",
                )
            if not subject.code:
                raise HTTPException(
                    422, "A canonical subject code is required for candidate classification"
                )
            candidate.subject = subject.code
            candidate.knowledge_point = ", ".join(p.name for p in points)[:160] or row.title[:160]
        db.flush()
        db.query(KnowledgeDocumentPoint).filter_by(document_id=row.id).delete()
        db.add_all(
            KnowledgeDocumentPoint(document_id=row.id, point_id=point_id)
            for point_id in set(point_ids)
        )
    audit(
        db,
        actor,
        "knowledge.document.classified",
        f"documents={','.join(ids)} subject={subject_id} points={point_ids}",
    )
    db.commit()


def stage_candidate(db: Session, actor: int, doc_id: str) -> KnowledgeCandidate:
    row = db.get(KnowledgeDocument, doc_id)
    if row is None or row.corpus_path or row.archived:
        raise HTTPException(409, "Only active uploaded documents can enter this review flow")
    if row.candidate_id:
        return db.get(KnowledgeCandidate, row.candidate_id)
    subject = db.get(SystemSubject, row.subject_id) if row.subject_id else None
    if subject is None or not subject.code:
        raise HTTPException(422, "Classify under a subject with a canonical code first")
    if len(row.text_content) < 20:
        raise HTTPException(422, "Review requires at least 20 extracted characters")
    # This is a completed local parsing receipt, never a forged fetch/LLM call.
    task = KnowledgeBuildTask(
        actor_user_id=actor,
        client_request_id=f"import-{doc_id}",
        request_hash=row.content_hash,
        trigger_source="document_upload",
        operation_type="IMPORT_DOCUMENT",
        subject=subject.code,
        status="COMPLETED",
        current_step="本地文档解析完成",
        completed_at=datetime.utcnow(),
        result_json={"document_id": doc_id, "model_calls": 0, "source_type": "uploaded_document"},
    )
    db.add(task)
    db.flush()
    points = (
        db.query(KnowledgePoint)
        .join(KnowledgeDocumentPoint, KnowledgeDocumentPoint.point_id == KnowledgePoint.id)
        .filter(KnowledgeDocumentPoint.document_id == doc_id)
        .all()
    )
    source = f"upload://{doc_id}/{row.file_name}"
    item = KnowledgeCandidate(
        creator_user_id=actor,
        source_task_id=task.id,
        subject=subject.code,
        knowledge_point=", ".join(p.name for p in points)[:160] or row.title[:160],
        title=row.title,
        content=row.text_content,
        source_url=source,
        source_hash=digest(source),
        content_hash=row.content_hash,
    )
    db.add(item)
    db.flush()
    row.candidate_id = item.id
    audit(
        db,
        actor,
        "knowledge.document.staged",
        f"document={doc_id} candidate={item.id} task={task.id}",
    )
    db.commit()
    return item


def coverage(db: Session, subject_id: int) -> dict:
    if db.get(SystemSubject, subject_id) is None:
        raise HTTPException(404, "Subject not found")
    points = db.query(KnowledgePoint).filter_by(subject_id=subject_id).all()
    covered = set()
    for item in catalog(db):
        if (
            item["subject_id"] == subject_id
            and item["status"] != "ARCHIVED"
            and item["active_version"]
            and item["index_status"] == "INDEXED"
        ):
            covered.update(item["point_ids"])
    missing = [{"id": p.id, "name": p.name} for p in points if p.id not in covered]
    total = len(points)
    return {
        "total_points": total,
        "covered_points": total - len(missing),
        "missing_points": missing,
        "coverage": round((total - len(missing)) / total, 4) if total else None,
        "basis": "explicit point links + active reviewed publication + current manifest; live retrieval must be verified separately",
    }


def preflight(db: Session, name: str) -> dict:
    wanted = normalize_name(name)
    if not wanted:
        raise HTTPException(422, "Subject name cannot be blank")
    subjects = db.query(SystemSubject).all()
    matches = []
    for subject in subjects:
        names = {
            normalize_name(value)
            for value in [subject.name, subject.code or "", *(subject.aliases_json or [])]
            if value
        }
        if wanted in names or any(wanted in value or value in wanted for value in names):
            matches.append(
                {
                    "id": subject.id,
                    "name": subject.name,
                    "code": subject.code,
                    "match": "EXACT" if wanted in names else "SIMILAR",
                    "point_count": db.query(KnowledgePoint)
                    .filter_by(subject_id=subject.id)
                    .count(),
                }
            )
    terms = {wanted, *(normalize_name(item["code"]) for item in matches if item["code"])}
    documents = [
        summary(item)
        for item in catalog(db)
        if item["subject_id"] is None
        and any(
            term and term in normalize_name(item["title"] + " " + item["corpus_subject"])
            for term in terms
        )
    ]
    tasks = [
        task for task in db.query(KnowledgeBuildTask).all() if normalize_name(task.subject) in terms
    ]
    return {
        "subjects": matches,
        "unlinked_documents": documents,
        "tasks": [
            {"id": task.id, "status": task.status, "operation_type": task.operation_type}
            for task in tasks
        ],
        "chroma_metadata": "NOT_QUERIED; use document chunks to inspect live metadata",
        "requires_confirmation": True,
    }
