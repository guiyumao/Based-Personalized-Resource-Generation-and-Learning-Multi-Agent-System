"""Plan generation gate: catalog + reviewed publication + current live chunks."""

import hashlib
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.knowledge_paths import KNOWLEDGE_ROOT
from common.models.learning import KnowledgePoint, KnowledgeVersion, LearningKnowledgeGap, Resource
from services.agent_service.app.services.knowledge_construction import find_subject, normalize_name
from services.agent_service.app.services.rag import ChromaRetriever


def plan_preflight(
    db: Session, user_id: int, subject: str, knowledge_point: str, *, record_gap: bool = True
) -> dict:
    subject, knowledge_point = subject.strip()[:100], knowledge_point.strip()[:100]
    catalog = find_subject(db, subject)
    point = None
    if catalog:
        wanted = normalize_name(knowledge_point)
        point = next(
            (
                item
                for item in db.query(KnowledgePoint).filter_by(subject_id=catalog.id).all()
                if wanted
                in {
                    normalize_name(item.name),
                    *(normalize_name(alias) for alias in item.aliases_json or []),
                }
            ),
            None,
        )
    result = {
        "ready": False,
        "subject_id": catalog.id if catalog else None,
        "point_id": point.id if point else None,
        "knowledge_point": point.name if point else knowledge_point,
        "subject": catalog.code if catalog else subject,
        "published_versions": [],
        "usable_chunks": [],
        "public_resources": 0,
        "retrieval_error": None,
    }
    reason = (
        "SUBJECT_MISSING"
        if not catalog
        else "POINT_MISSING"
        if not point
        else "PUBLISHED_CONTENT_MISSING"
    )
    if point:
        versions = (
            db.query(KnowledgeVersion)
            .filter_by(subject=catalog.code, knowledge_point=point.name, is_active=True)
            .all()
        )
        sources = {}
        for version in versions:
            path = (KNOWLEDGE_ROOT / version.corpus_path).resolve()
            if (
                not path.is_relative_to((KNOWLEDGE_ROOT / "knowledge_base/corpus").resolve())
                or not path.is_file()
            ):
                continue
            relative = path.relative_to(KNOWLEDGE_ROOT / "knowledge_base/corpus").as_posix()
            sources[relative] = hashlib.sha256(
                path.read_text(encoding="utf-8").encode()
            ).hexdigest()
            result["published_versions"].append(version.id)
        result["public_resources"] = (
            db.query(Resource)
            .filter_by(
                knowledge_point_id=point.id,
                publish_status="published",
                audit_status="passed",
                generated_for_user_id=None,
            )
            .count()
        )
        if sources:
            reason = "INDEX_UNAVAILABLE"
            try:
                retriever = ChromaRetriever()
                if not retriever.is_available:
                    result["retrieval_error"] = "INDEX_UNAVAILABLE"
                else:
                    chunks = retriever.retrieve_with_metadata(
                        point.name,
                        top_k=8,
                        filters={"subject": catalog.code},
                        retrieval_mode="lexical",
                    )
                    # Publication explicitly binds these sources to the point.
                    # Verify their actual stored chunks even when the point name
                    # does not occur verbatim in a PDF's text; no embedding/model
                    # initialization is needed for this availability check.
                    collection = getattr(retriever, "collection", None)
                    if not chunks and collection is not None:
                        for source, version_hash in list(sources.items())[:8]:
                            stored = collection.get(
                                where={
                                    "$and": [
                                        {"subject": catalog.code},
                                        {"source": source},
                                        {"document_version": version_hash},
                                    ]
                                },
                                limit=1,
                                include=["documents", "metadatas"],
                            )
                            chunks.extend(
                                {"id": chunk_id, "content": text, "metadata": meta}
                                for chunk_id, text, meta in zip(
                                    stored.get("ids") or [],
                                    stored.get("documents") or [],
                                    stored.get("metadatas") or [],
                                    strict=True,
                                )
                                if text
                            )
                    result["usable_chunks"] = [
                        row
                        for row in chunks
                        if (meta := row.get("metadata") or {}).get("source") in sources
                        and meta.get("document_version") == sources[meta["source"]]
                        and meta.get("subject") == catalog.code
                        and meta.get("teacher_scope", "public") == "public"
                    ]
                    reason = "READY" if result["usable_chunks"] else "INDEX_STALE_OR_MISSING"
            except Exception as exc:
                result["retrieval_error"] = type(exc).__name__
    result["ready"], result["reason"] = reason == "READY", reason
    messages = {
        "SUBJECT_MISSING": "公共学科尚未建立，生成时将自动建设并由模型审核。",
        "POINT_MISSING": "学科存在，但目标知识点尚未建立。",
        "PUBLISHED_CONTENT_MISSING": "知识点尚无有效的已审核发布资料。",
        "INDEX_UNAVAILABLE": "检索服务当前不可用，未调用模型。",
        "INDEX_STALE_OR_MISSING": "当前公共版本尚未检索命中，请稍后重试；不会使用个人草稿。",
        "READY": "已验证知识点、正式发布资料和当前检索版本。",
    }
    result["message"] = messages[reason]
    if record_gap:
        key = hashlib.sha256(
            f"{user_id}:{normalize_name(subject)}:{normalize_name(knowledge_point)}".encode()
        ).hexdigest()
        gap = db.query(LearningKnowledgeGap).filter_by(request_key=key).first()
        if result["ready"]:
            if gap and gap.status != "RESOLVED":
                gap.status = "RESOLVED"
                from common.notifications import emit
                emit(db, user_id=user_id, event_key=f"gap:{gap.id}:RESOLVED", title="知识内容请求已处理",
                    content=f"{gap.subject} / {gap.knowledge_point} 已通过当前可用性检查，可以继续制定学习计划。", type="knowledge")
                db.commit()
            return result
        if not gap:
            gap = LearningKnowledgeGap(
                id=str(uuid4()),
                user_id=user_id,
                request_key=key,
                subject=subject,
                knowledge_point=knowledge_point,
                reason=reason,
                status="REQUESTED",
            )
            db.add(gap)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                gap = db.query(LearningKnowledgeGap).filter_by(request_key=key).one()
        elif gap.reason != reason or gap.status == "RESOLVED":
            gap.reason = reason
            if gap.status == "RESOLVED":
                gap.status = "REQUESTED"
            db.commit()
        result["gap_id"] = gap.id
    return result


def require_plan_knowledge(db: Session, user_id: int, subject: str, knowledge_point: str) -> dict:
    result = plan_preflight(db, user_id, subject, knowledge_point)
    if not result["ready"]:
        raise HTTPException(
            409, {key: value for key, value in result.items() if key != "usable_chunks"}
        )
    return result


def assess_plan_knowledge(db: Session, user_id: int, subject: str, knowledge_point: str) -> dict:
    """Read-only model-construction preflight; generation performs the build."""
    result = plan_preflight(db, user_id, subject, knowledge_point)
    result["mode"] = "public" if result["ready"] else "public_build_pending"
    if not result["ready"]:
        result["message"] = (
            "公共知识尚未就绪；生成时自动建设，经模型审核、发布及检索验证通过后再使用。"
            "发现问题自动修订，服务暂不可用时保存进度并自动重试，不需要管理员处理。"
        )
    return result
