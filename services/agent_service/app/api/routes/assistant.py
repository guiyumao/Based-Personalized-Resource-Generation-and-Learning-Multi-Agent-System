"""Authenticated entry point for XiaoZhi conversations and learning tasks."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import logging
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import SessionLocal, get_db
from common.ai_errors import AIServiceError
from common.dependencies import get_current_user
from common.models.learning import AssistantAgentExecution, AssistantAttachment, AssistantMemory, AssistantTask, ChatMessage, ChatSession, User
from common.schemas.agent import ChatMessageInput, ChatSessionCreate
from services.agent_service.app.services.assistant_tasks import (
    ACTIONS,
    AssistantTaskRequestConflict,
    create_task,
    detect_action,
    execute_task,
    expire_stale_tasks,
    infer_exercise_count,
    infer_topic,
    requested_generation_actions,
    task_to_dict,
    task_execution_mode,
)
from services.agent_service.app.services.chat_service import ChatService
from services.agent_service.app.services.assistant_attachments import MAX_FILE_BYTES, attachment_context, extract_document_text, safe_file_name
from services.agent_service.app.services.learning_path import LearningPathRevisionConflict, LearningPathService
from common.learning_context import context_reference, validate_context

router = APIRouter()
LOGGER = logging.getLogger(__name__)


class AssistantChatInput(BaseModel):
    conversation_id: int | None = None
    client_request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=8, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    action: str | None = None
    knowledge_point: str = Field(default="", max_length=120)
    exercise_count: int = Field(default=5, ge=3, le=20)
    teaching_mode: Literal["basic", "standard", "deep", "socratic", "exam"] = "standard"
    use_learning_context: bool = False
    allow_web_knowledge: bool = True
    course_key: str = Field(default="", max_length=100)
    attachment_ids: list[int] = Field(default_factory=list, max_length=3)
    learning_context_id: str | None = Field(default=None, max_length=36)


def _workspace_reference(db: Session, user_id: int, payload: AssistantChatInput, document_context: str) -> str:
    if not payload.learning_context_id:
        if payload.conversation_id:
            existing_session = db.get(ChatSession, payload.conversation_id)
            if existing_session and (existing_session.subject or "").startswith("ctx:"):
                raise HTTPException(409, "Workspace conversation requires its learning context")
        return document_context
    validate_context(db, user_id, payload.learning_context_id)
    if payload.conversation_id:
        session = db.get(ChatSession, payload.conversation_id)
        if not session or session.user_id != user_id:
            raise HTTPException(404, "Conversation not found")
        if session.subject != f"ctx:{payload.learning_context_id}":
            raise HTTPException(409, "Conversation belongs to a different learning context")
    return context_reference(db, user_id, payload.learning_context_id) + "\n" + document_context


class AssistantMemoryInput(BaseModel):
    memory_type: Literal["goal", "preference", "focus", "context"]
    content: str = Field(min_length=1, max_length=500)
    course_key: str = Field(default="", max_length=100)


class AssistantRetryInput(BaseModel):
    client_request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=8, max_length=80)
    confirm_side_effects: bool = False


def _memory_to_dict(memory: AssistantMemory) -> dict:
    return {
        "id": memory.id,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "course_key": memory.course_key,
        "source_reference": memory.source_reference,
        "created_at": memory.created_at.isoformat() if memory.created_at else "",
        "updated_at": memory.updated_at.isoformat() if memory.updated_at else "",
    }


def _attachment_to_dict(attachment: AssistantAttachment) -> dict:
    return {
        "id": attachment.id,
        "file_name": attachment.file_name,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "created_at": attachment.created_at.isoformat() if attachment.created_at else "",
    }


@router.post("/attachments", status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    data = await file.read(MAX_FILE_BYTES + 1)
    name = safe_file_name(file.filename or "")
    content_type, text_content = extract_document_text(name, data)
    digest = hashlib.sha256(data).hexdigest()
    previous = db.query(AssistantAttachment).filter(
        AssistantAttachment.user_id == current_user.id,
        AssistantAttachment.sha256 == digest,
        AssistantAttachment.file_name == name,
    ).first()
    if previous is not None:
        return _attachment_to_dict(previous)
    attachment = AssistantAttachment(
        user_id=current_user.id,
        file_name=name,
        content_type=content_type,
        size_bytes=len(data),
        sha256=digest,
        text_content=text_content,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _attachment_to_dict(attachment)


@router.get("/attachments")
def list_attachments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[dict]:
    rows = db.query(AssistantAttachment).filter(AssistantAttachment.user_id == current_user.id).order_by(
        AssistantAttachment.id.desc(),
    ).limit(100).all()
    return [_attachment_to_dict(row) for row in rows]


@router.delete("/attachments/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = db.query(AssistantAttachment).filter(
        AssistantAttachment.id == attachment_id, AssistantAttachment.user_id == current_user.id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    db.delete(row)
    db.commit()
    return {"deleted": True}


def _get_session(db: Session, user_id: int, conversation_id: int | None, *, commit: bool = True):
    service = ChatService(db)
    if conversation_id is not None:
        session = service.get_session(conversation_id, user_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        return db.get(ChatSession, conversation_id)
    created = service.create_session(ChatSessionCreate(user_id=user_id, title="小智学习助手", subject="智能学习"), commit=commit)
    return db.get(ChatSession, created.id)


def _create_learning_task(db: Session, **kwargs):
    try:
        return create_task(db, **kwargs)
    except AssistantTaskRequestConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/chat")
def assistant_chat(
    payload: AssistantChatInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    action = payload.action or detect_action(payload.message)
    if action not in ACTIONS:
        raise HTTPException(status_code=422, detail="不支持的助手任务类型")
    if action not in {"qa", "search"} and current_user.role not in {"student", "admin"}:
        raise HTTPException(status_code=403, detail="当前身份不能执行学生学习任务")
    if payload.attachment_ids and action not in {"qa", "courseware", "exercise", "combined"}:
        raise HTTPException(status_code=422, detail="附件支持知识问答、课件和练习生成；当前任务暂不支持附件")
    document_context, attachments = attachment_context(db, current_user.id, payload.attachment_ids)
    document_context = _workspace_reference(db, current_user.id, payload, document_context)
    if payload.learning_context_id:
        _, _, _, _, point, _ = validate_context(db, current_user.id, payload.learning_context_id)
        if payload.knowledge_point and payload.knowledge_point.strip() != point.name:
            raise HTTPException(409, "Learning context knowledge point differs")
        payload = payload.model_copy(update={"knowledge_point": point.name})
        if action == "plan" or (action == "combined" and "plan" in requested_generation_actions(payload.message)):
            raise HTTPException(422, "Create new plans outside the current workspace")
    topic = payload.knowledge_point.strip() or infer_topic(payload.message)
    exercise_count = infer_exercise_count(payload.message, payload.exercise_count) if action in {"exercise", "combined"} else payload.exercise_count
    if not 3 <= exercise_count <= 20:
        raise HTTPException(status_code=422, detail="练习题数量应为 3 到 20 道")
    existing = db.query(AssistantTask).filter(
        AssistantTask.user_id == current_user.id,
        AssistantTask.client_request_id == payload.client_request_id,
    ).first()
    if existing is not None:
        previous_request = existing.request_json or {}
        expected_request = {"message": payload.message.strip(), "knowledge_point": topic, "exercise_count": exercise_count,
                            "use_learning_context": payload.use_learning_context}
        if payload.attachment_ids:
            expected_request["attachment_ids"] = payload.attachment_ids
        if payload.course_key.strip():
            expected_request["knowledge_subject"] = payload.course_key.strip()
        if payload.allow_web_knowledge:
            expected_request["allow_web_knowledge"] = True
        if payload.learning_context_id:
            expected_request["learning_context_id"] = payload.learning_context_id
        if (existing.task_type != action or previous_request != expected_request
                or (payload.conversation_id is not None and existing.session_id != payload.conversation_id)):
            raise HTTPException(status_code=409, detail="请求标识已用于另一项任务")
        return {"kind": "task", "conversation_id": existing.session_id, "task": task_to_dict(existing)}
    session = _get_session(db, current_user.id, payload.conversation_id, commit=action == "qa")
    if payload.learning_context_id and session.subject != f"ctx:{payload.learning_context_id}":
        session.subject = f"ctx:{payload.learning_context_id}"
        db.commit()
    if action == "qa":
        try:
            response = ChatService(db).send_message(ChatMessageInput(
                session_id=session.id,
                user_id=current_user.id,
                content=payload.message.strip(),
                context={
                    "source": "assistant_pet",
                    "teaching_mode": payload.teaching_mode,
                    "use_learning_context": payload.use_learning_context,
                    "course_key": payload.course_key.strip(),
                    "attachment_context": document_context,
                    "attachments": attachments,
                    "learning_context_id": payload.learning_context_id,
                },
            ))
        except AIServiceError as exc:
            raise HTTPException(
                status_code=exc.http_status,
                detail={"code": exc.code, "message": exc.user_message},
            ) from exc
        return {"kind": "message", "conversation_id": session.id, "message": response.model_dump()}
    task, created = _create_learning_task(
        db,
        user_id=current_user.id,
        session=session,
        client_request_id=payload.client_request_id,
        action=action,
        message=payload.message.strip(),
        knowledge_point=topic,
        exercise_count=exercise_count,
        allow_session_reuse=payload.conversation_id is None,
        attachment_ids=payload.attachment_ids,
        use_learning_context=payload.use_learning_context,
        knowledge_subject=payload.course_key.strip(),
        allow_web_knowledge=payload.allow_web_knowledge,
        learning_context_id=payload.learning_context_id,
    )
    if created and task_execution_mode() == "background":
        background_tasks.add_task(execute_task, task.id)
    return {"kind": "task", "conversation_id": task.session_id, "task": task_to_dict(task)}


@router.post("/chat/stream")
def stream_assistant_chat(
    payload: AssistantChatInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    action = payload.action or detect_action(payload.message)
    if action != "qa":
        raise HTTPException(status_code=422, detail="流式接口仅支持知识问答；资源生成请使用任务接口")
    document_context, attachments = attachment_context(db, current_user.id, payload.attachment_ids)
    document_context = _workspace_reference(db, current_user.id, payload, document_context)
    prior = db.query(ChatMessage).join(ChatSession, ChatMessage.session_id == ChatSession.id).filter(
        ChatSession.user_id == current_user.id,
        ChatMessage.role == "user",
        ChatMessage.metadata_json["client_request_id"].as_string() == payload.client_request_id,
    ).order_by(ChatMessage.id.desc()).first()
    if prior is not None and prior.content != payload.message.strip():
        raise HTTPException(status_code=409, detail="请求标识已用于另一条消息")
    if prior is not None and (prior.metadata_json or {}).get("learning_context_id") != payload.learning_context_id:
        raise HTTPException(409, "Request belongs to another learning context")
    if prior is not None and payload.conversation_id not in {None, prior.session_id}:
        raise HTTPException(status_code=409, detail="请求标识属于其他会话")
    session = _get_session(db, current_user.id, prior.session_id if prior is not None else payload.conversation_id)
    if payload.learning_context_id:
        marker = f"ctx:{payload.learning_context_id}"
        if prior is not None and session.subject != marker:
            raise HTTPException(409, "Conversation belongs to another learning context")
        session.subject = marker
        db.commit()
    request = ChatMessageInput(
        session_id=session.id,
        user_id=current_user.id,
        content=payload.message.strip(),
        context={
            "source": "assistant_stream",
            "client_request_id": payload.client_request_id,
            "teaching_mode": payload.teaching_mode,
            "use_learning_context": payload.use_learning_context,
            "course_key": payload.course_key.strip(),
            "attachment_context": document_context,
            "attachments": attachments,
            "learning_context_id": payload.learning_context_id,
        },
    )

    def events():
        with SessionLocal() as stream_db:
            for index, item in enumerate(ChatService(stream_db).stream_message(request), start=1):
                body = json.dumps(item["data"], ensure_ascii=False)
                yield f"id: {index}\nevent: {item['event']}\ndata: {body}\n\n"

    return StreamingResponse(
        events(), media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/tasks")
def list_tasks(
    conversation_id: int | None = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    expire_stale_tasks(db, current_user.id)
    query = db.query(AssistantTask).filter(AssistantTask.user_id == current_user.id)
    if conversation_id is not None:
        query = query.filter(AssistantTask.session_id == conversation_id)
    return [task_to_dict(task) for task in query.order_by(AssistantTask.id.desc()).limit(min(max(limit, 1), 100)).all()]


@router.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    expire_stale_tasks(db, current_user.id)
    task = db.query(AssistantTask).filter(
        AssistantTask.id == task_id,
        AssistantTask.user_id == current_user.id,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = task_to_dict(task)
    if task.status in {"RUNNING", "FAILED"} and task.task_type in {"courseware", "combined"}:
        from common.models.learning import Resource
        root = (task.request_json or {}).get("side_effect_root_task_id") or task.id
        partial = db.query(Resource).filter_by(
            assistant_operation_key=f"assistant:{root}:resource", generated_for_user_id=current_user.id,
            generation_status="generating").first()
        if partial and partial.publish_status != "archived" and partial.content:
            result["partial_resource"] = {"id": partial.id, "title": partial.title,
                                          "content": partial.content, "structured_json": partial.structured_json}
    result["agent_executions"] = [
        {"agent_code": row.agent_code, "status": row.status, "elapsed_ms": row.elapsed_ms, "error_code": row.error_code}
        for row in db.query(AssistantAgentExecution).filter(AssistantAgentExecution.task_id == task.id).order_by(AssistantAgentExecution.id).all()
    ]
    return result


@router.post("/tasks/{task_id}/cancel")
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    task = db.query(AssistantTask).filter(
        AssistantTask.id == task_id,
        AssistantTask.user_id == current_user.id,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    # Preserve the original endpoint contract: a running task cannot be
    # cancelled synchronously through this endpoint.
    db.query(AssistantTask).filter(
        AssistantTask.id == task.id,
        AssistantTask.user_id == current_user.id,
        AssistantTask.status == "PENDING",
    ).update({
        AssistantTask.status: "CANCELLED", AssistantTask.current_step: "任务已取消",
        AssistantTask.completed_at: datetime.utcnow(), AssistantTask.updated_at: datetime.utcnow(),
    }, synchronize_session=False)
    db.commit()
    db.refresh(task)
    if task.status == "RUNNING":
        raise HTTPException(status_code=409, detail="任务正在执行；请使用请求停止接口，在当前步骤结束后取消")
    LOGGER.info("assistant_cancel task_id=%s status=%s", task_id, task.status)
    return task_to_dict(task)


@router.post("/tasks/{task_id}/request-cancel")
def request_running_task_cancel(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    task = db.query(AssistantTask).filter(
        AssistantTask.id == task_id, AssistantTask.user_id == current_user.id,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    db.query(AssistantTask).filter(
        AssistantTask.id == task_id, AssistantTask.user_id == current_user.id,
        AssistantTask.status == "RUNNING",
    ).update({
        AssistantTask.status: "CANCEL_REQUESTED",
        AssistantTask.current_step: "正在停止，当前步骤结束后取消；已保存成果会保留",
        AssistantTask.updated_at: datetime.utcnow(),
    }, synchronize_session=False)
    db.commit()
    db.refresh(task)
    LOGGER.info("assistant_cancel_requested task_id=%s worker_id=%s attempt=%s cancellation_status=%s", task_id, task.worker_id, task.execution_attempt, task.status)
    return task_to_dict(task)


@router.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: int,
    payload: AssistantRetryInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    original = db.query(AssistantTask).filter(
        AssistantTask.id == task_id,
        AssistantTask.user_id == current_user.id,
    ).first()
    if original is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if original.status not in {"FAILED", "TIMED_OUT"}:
        raise HTTPException(status_code=409, detail="只有失败或超时的任务可以重试")
    session = db.get(ChatSession, original.session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    request = original.request_json or {}
    previous = db.query(AssistantTask).filter(
        AssistantTask.user_id == current_user.id,
        AssistantTask.client_request_id == payload.client_request_id,
    ).first()
    if previous is not None:
        previous_request = dict(previous.request_json or {})
        previous_root = previous_request.pop("side_effect_root_task_id", None)
        original_request = dict(request)
        original_request.pop("side_effect_root_task_id", None)
        expected_root = int(request.get("side_effect_root_task_id") or original.id)
        if previous.id == original.id or previous.session_id != original.session_id or previous.task_type != original.task_type or previous_request != original_request or previous_root not in (None, expected_root):
            raise HTTPException(status_code=409, detail="请求标识已用于另一项任务")
        return {"kind": "task", "conversation_id": session.id, "original_task_id": original.id, "task": task_to_dict(previous)}
    if original.task_type in {"courseware", "exercise", "plan", "combined", "courseware_revision"} and not payload.confirm_side_effects:
        raise HTTPException(
            status_code=409,
            detail="原任务可能已保存部分课件、练习或学习路径。请先检查已有成果，确认可能重复生成后再重试。",
        )
    if payload.confirm_side_effects and original.task_type in {"courseware", "combined", "courseware_revision"}:
        from common.models.learning import Resource
        root_task = int(request.get("side_effect_root_task_id") or original.id)
        operation_key = f"chapter-revision:{root_task}" if original.task_type == "courseware_revision" else f"assistant:{root_task}:resource"
        partial = db.query(Resource).filter_by(assistant_operation_key=operation_key, generated_for_user_id=current_user.id, generation_status="generating").first()
        if partial:
            metadata = json.loads(partial.structured_json or "{}")
            metadata["ambiguous_retry_acknowledged"] = {"task_id": original.id, "at": datetime.utcnow().isoformat()}
            metadata["in_flight"] = None
            partial.structured_json = json.dumps(metadata, ensure_ascii=False)
            db.flush()
    task, created = _create_learning_task(
        db,
        user_id=current_user.id,
        session=session,
        client_request_id=payload.client_request_id,
        action=original.task_type,
        message=str(request.get("message") or ""),
        knowledge_point=str(request.get("knowledge_point") or ""),
        exercise_count=int(request.get("exercise_count") or 5),
        attachment_ids=list(request.get("attachment_ids") or []),
        use_learning_context=request.get("use_learning_context"),
        side_effect_root_task_id=int(request.get("side_effect_root_task_id") or original.id),
        knowledge_subject=str(request.get("knowledge_subject") or ""),
        learning_context_id=request.get("learning_context_id"),
        artifact_kind=request.get("artifact_kind"),
        chapter_revision=request.get("chapter_revision"),
        allow_web_knowledge=request.get("allow_web_knowledge") is True,
    )
    if created and task_execution_mode() == "background":
        background_tasks.add_task(execute_task, task.id)
    return {"kind": "task", "conversation_id": session.id, "original_task_id": original.id, "task": task_to_dict(task)}


@router.post("/tasks/{task_id}/confirm-path")
def confirm_learning_path(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    task = db.query(AssistantTask).filter(
        AssistantTask.id == task_id,
        AssistantTask.user_id == current_user.id,
    ).with_for_update().first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    # A write acquires SQLite's writer lock as well as serializing this row on
    # databases with row locks. Refresh after waiting so a repeated confirmation
    # observes the first request's result before saving another path.
    db.query(AssistantTask).filter(
        AssistantTask.id == task.id, AssistantTask.user_id == current_user.id,
    ).update({AssistantTask.updated_at: datetime.utcnow()}, synchronize_session=False)
    db.refresh(task)
    result = dict(task.result_json or {})
    if result.get("path_saved") is True:
        return task_to_dict(task)
    draft = result.get("path_draft")
    if task.status not in {"SUCCEEDED", "CANCELLED"} or task.task_type not in {"plan", "combined"} or not isinstance(draft, dict):
        raise HTTPException(status_code=409, detail="该任务没有可确认的学习计划草案")
    try:
        LearningPathService(db).save_assistant_draft(current_user.id, task.id, draft)
    except LearningPathRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["path_saved"] = True
    result["cards"] = [
        {"type": "plan", "title": "查看学习路径", "route": "/student/learning-path"}
        if card.get("type") == "plan_draft" else card
        for card in result.get("cards", []) if isinstance(card, dict)
    ]
    result["content"] = str(result.get("content") or "") + "\n\n学习路径已确认保存，可在学习路径页面查看。"
    task.result_json = result
    for message in db.query(ChatMessage).filter(
        ChatMessage.session_id == task.session_id, ChatMessage.role == "assistant",
    ).order_by(ChatMessage.id.desc()).limit(100):
        if (message.metadata_json or {}).get("task_id") == task.id:
            message.content = result["content"]
            message.metadata_json = {**(message.metadata_json or {}), "cards": result["cards"]}
            break
    db.commit()
    db.refresh(task)
    return task_to_dict(task)


@router.get("/capabilities")
def capabilities(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "actions": ["qa", "search"] if current_user.role == "teacher" else ["qa", "profile", "search", "courseware", "exercise", "plan", "recommend", "combined"],
        "max_exercise_count": 20,
        "teaching_modes": ["basic", "standard", "deep", "socratic", "exam"],
        "supports_file_upload": True,
        "supported_attachment_formats": ["txt", "md", "pdf", "docx"],
        "attachment_actions": ["qa"] if current_user.role == "teacher" else ["qa", "courseware", "exercise", "combined"],
        "supports_streaming": True,
        "task_execution_mode": task_execution_mode(),
    }


@router.get("/memory")
def list_memory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    rows = db.query(AssistantMemory).filter(AssistantMemory.user_id == current_user.id).order_by(
        AssistantMemory.updated_at.desc(), AssistantMemory.id.desc(),
    ).limit(100).all()
    return [_memory_to_dict(row) for row in rows]


@router.post("/memory", status_code=201)
def create_memory(
    payload: AssistantMemoryInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="记忆内容不能为空")
    memory = AssistantMemory(
        user_id=current_user.id,
        memory_type=payload.memory_type,
        content=content,
        course_key=payload.course_key.strip(),
        source_reference="user_confirmed",
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return _memory_to_dict(memory)


@router.put("/memory/{memory_id}")
def update_memory(
    memory_id: int,
    payload: AssistantMemoryInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    memory = db.query(AssistantMemory).filter(
        AssistantMemory.id == memory_id, AssistantMemory.user_id == current_user.id,
    ).first()
    if memory is None:
        raise HTTPException(status_code=404, detail="学习记忆不存在")
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="记忆内容不能为空")
    memory.memory_type = payload.memory_type
    memory.content = content
    memory.course_key = payload.course_key.strip()
    db.commit()
    db.refresh(memory)
    return _memory_to_dict(memory)


@router.delete("/memory/{memory_id}")
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    memory = db.query(AssistantMemory).filter(
        AssistantMemory.id == memory_id, AssistantMemory.user_id == current_user.id,
    ).first()
    if memory is None:
        raise HTTPException(status_code=404, detail="学习记忆不存在")
    db.delete(memory)
    db.commit()
    return {"status": "deleted", "id": memory_id}
