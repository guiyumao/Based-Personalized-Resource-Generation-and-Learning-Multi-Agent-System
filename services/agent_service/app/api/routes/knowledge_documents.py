"""Administrator document catalog, preview and explicit subject association."""

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import (
    AuditLog,
    KnowledgeBuildTask,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeVersion,
    User,
)
from services.agent_service.app.services import knowledge_documents as service
from services.agent_service.app.services.assistant_attachments import MAX_FILE_BYTES
from services.agent_service.app.services.knowledge_candidates import serialize_candidate

router = APIRouter(
    prefix="/knowledge-base/admin",
    tags=["knowledge-documents"],
    dependencies=[Depends(require_role("admin"))],
)


class Classification(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=100)
    subject_id: int
    point_ids: list[int] = Field(default_factory=list, max_length=100)
    chapter: str = Field(default="", max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=30)


@router.get("/documents")
def documents(
    q: str = Query("", max_length=200),
    subject_id: int | None = None,
    status: str = "",
    format: str = "",
    index_status: str = "",
    unclassified: bool = False,
    source: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    all_items = service.catalog(db)
    items = [
        item
        for item in all_items
        if (not q or q.casefold() in (item["title"] + item["file_name"]).casefold())
        and (subject_id is None or item["subject_id"] == subject_id)
        and (not status or item["status"] == status)
        and (not format or item["format"] == format)
        and (not index_status or item["index_status"] == index_status)
        and (not unclassified or item["subject_id"] is None)
        and (not source or source.casefold() in item["source_url"].casefold())
    ]
    return {
        "items": [service.summary(item) for item in items[(page - 1) * size : page * size]],
        "total": len(items),
        "page": page,
        "size": size,
        "inventory": service.inventory(db, all_items),
    }


@router.get("/auto-backfill/stats")
def auto_backfill_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """How much knowledge the system published on its own, and how often it failed."""
    from services.agent_service.app.services.knowledge_audit import auto_backfill_stats as collect

    return collect(db, days=days)


@router.get("/inspection/orphans")
def orphan_inspection(db: Session = Depends(get_db)):
    """Read-only sweep: do SQL rows, corpus files and the vector index still agree?"""
    from services.agent_service.app.services.knowledge_audit import orphan_inspection as inspect

    return inspect(db)


@router.post("/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    try:
        data = await file.read(MAX_FILE_BYTES + 1)
        row = service.upload(db, user.id, file.filename or "", data)
        return service.get_document(db, row.id)
    finally:
        await file.close()


@router.post("/documents/classify")
def classify(
    payload: Classification,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    try:
        service.classify(
            db,
            user.id,
            **payload.model_dump(exclude={"document_ids"}),
            ids=list(dict.fromkeys(payload.document_ids)),
        )
        return {"updated": len(set(payload.document_ids))}
    except Exception:
        db.rollback()
        raise


@router.get("/subjects/preflight")
def preflight(name: str = Query(min_length=1, max_length=100), db: Session = Depends(get_db)):
    return service.preflight(db, name)


@router.post("/reconcile", status_code=202)
def reconcile_publications(
    db: Session = Depends(get_db), user: User = Depends(require_role("admin"))
):
    from uuid import uuid4

    from services.agent_service.app.services.knowledge_tasks import create_task, serialize_task

    return serialize_task(
        create_task(
            db,
            actor_user_id=user.id,
            client_request_id=f"reconcile-{uuid4().hex}",
            operation_type="RECONCILE_PUBLICATIONS",
        )
    )


@router.get("/subjects/{subject_id}/coverage")
def coverage(subject_id: int, db: Session = Depends(get_db)):
    return service.coverage(db, subject_id)


@router.get("/documents/{document_id}")
def detail(document_id: str, db: Session = Depends(get_db)):
    return service.get_document(db, document_id)


@router.get("/documents/{document_id}/original")
def original(
    document_id: str,
    disposition: Literal["inline", "attachment"] = "attachment",
    db: Session = Depends(get_db),
):
    item = service.get_document(db, document_id)
    row = db.get(KnowledgeDocument, document_id)
    path = (
        service.contained(service.UPLOADS, row.original_path)
        if row and row.original_path
        else (
            service.contained(service.CORPUS_DIR, item["corpus_path"])
            if item["corpus_path"]
            else None
        )
    )
    if path is None or not path.is_file():
        raise HTTPException(404, "Original file is unavailable; extracted text may still be viewed")
    return FileResponse(
        path,
        filename=item["file_name"],
        media_type=item["content_type"],
        content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.get("/documents/{document_id}/history")
def history(document_id: str, db: Session = Depends(get_db)):
    item = service.get_document(db, document_id)
    candidate = db.get(KnowledgeCandidate, item["candidate_id"]) if item["candidate_id"] else None
    task = db.get(KnowledgeBuildTask, candidate.source_task_id) if candidate else None
    from services.agent_service.app.services.knowledge_versions import serialize_version

    versions = (
        db.query(KnowledgeVersion)
        .filter_by(candidate_id=candidate.id)
        .order_by(KnowledgeVersion.id.desc())
        .all()
        if candidate
        else []
    )
    events = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(1000).all()
    markers = [f"document={document_id}", f"documents={document_id}"]
    if candidate:
        markers.append(f"candidate={candidate.id}")

    def associated(message):
        return any(marker in message.split() for marker in markers)

    return {
        "versions": [serialize_version(v) for v in versions],
        "origin": {"operation": task.operation_type, "task_id": task.id}
        if task
        else {"operation": "LEGACY_CORPUS"},
        "review": {
            "status": candidate.status,
            "reviewed_by": candidate.reviewed_by,
            "notes": candidate.review_notes,
        }
        if candidate
        else None,
        "events": [
            {
                "id": event.id,
                "event": event.event,
                "message": event.message,
                "actor_user_id": event.actor_user_id,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
            if associated(event.message)
        ],
    }


@router.get("/documents/{document_id}/chunks")
def chunks(
    document_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    item = service.get_document(db, document_id)
    if not item["corpus_path"]:
        return {
            "available": True,
            "total": 0,
            "items": [],
            "reason": "Document is not published to the corpus",
        }
    from services.agent_service.app.services.rag import ChromaRetriever

    try:
        retriever = ChromaRetriever()
        if retriever.collection is None:
            raise RuntimeError("unavailable")
        data = retriever.collection.get(
            where={"source": item["corpus_path"]},
            include=["documents", "metadatas"],
            limit=limit,
            offset=offset,
        )
        return {
            "available": True,
            "items": [
                {"id": chunk_id, "text": text, "metadata": metadata}
                for chunk_id, text, metadata in zip(
                    data.get("ids", []),
                    data.get("documents", []),
                    data.get("metadatas", []),
                    strict=True,
                )
            ],
            "offset": offset,
            "limit": limit,
        }
    except Exception as exc:
        raise HTTPException(
            503, "Live Chroma chunks are unavailable; parsed text remains available"
        ) from exc


@router.post("/documents/{document_id}/candidate", status_code=201)
def stage(
    document_id: str, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))
):
    try:
        return serialize_candidate(service.stage_candidate(db, user.id, document_id))
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "Document review was created concurrently; reload the document"
        ) from exc


@router.post("/documents/{document_id}/archive")
def archive(
    document_id: str, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))
):
    item = service.get_document(db, document_id)
    row = db.get(KnowledgeDocument, document_id)
    if row is None or row.corpus_path or item["candidate_id"]:
        raise HTTPException(
            409, "Only unstaged uploads can be archived; published corpus requires version review"
        )
    row.archived = True
    service.audit(db, user.id, "knowledge.document.archived", f"document={document_id}")
    db.commit()
    return {"id": document_id, "status": "ARCHIVED"}
