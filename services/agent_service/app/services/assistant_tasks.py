"""Durable, authenticated assistant tasks built on the existing coordinator."""

from __future__ import annotations

import logging
import os
import re
import socket
import threading
from uuid import uuid4
from datetime import datetime, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from common.db.session import SessionLocal
from common.config import get_settings
from common.models.learning import (
    AnswerRecord,
    AssistantAgentExecution,
    AssistantTask,
    ChatMessage,
    ChatSession,
    Exercise,
    KnowledgePoint,
    Resource,
    TranscriptScore,
    UserProfile,
)
from common.schemas.agent import CoordinationRequest
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.assistant_attachments import attachment_context
from services.agent_service.app.services.assistant_execution import current_execution, ensure_write_allowed, lease_conditions
from services.resource_service.app.services.resource_manager import ResourceManager

LOGGER = logging.getLogger(__name__)

ACTIONS = {"qa", "profile", "search", "courseware", "exercise", "plan", "recommend", "combined"}
AGENTS_BY_ACTION = {
    "courseware": ["learner_profiling_agent", "knowledge_base_agent", "resource_generation_agent"],
    "exercise": ["learner_profiling_agent", "knowledge_base_agent", "exercise_generation_agent"],
    "plan": ["learner_profiling_agent", "knowledge_base_agent", "knowledge_graph_agent", "path_planning_agent"],
    "combined": [
        "learner_profiling_agent", "knowledge_base_agent", "resource_generation_agent",
        "exercise_generation_agent",
    ],
}


def task_execution_mode() -> str:
    mode = get_settings().assistant_task_execution_mode
    if mode not in {"background", "worker"}:
        raise ValueError("ASSISTANT_TASK_EXECUTION_MODE must be background or worker")
    return mode


class AssistantTaskRequestConflict(ValueError):
    """An idempotency key was reused for a different learning operation."""


def detect_action(message: str) -> str:
    """A bounded router: natural language cannot select arbitrary backend tools."""

    text = message.lower()
    has_courseware = any(word in text for word in ("课件", "讲义", "courseware"))
    has_exercise = any(word in text for word in ("练习", "习题", "出题", "exercise"))
    has_plan = any(word in text for word in ("计划", "学习路线", "复习安排", "plan"))
    if sum((has_courseware, has_exercise, has_plan)) > 1:
        return "combined"
    if any(word in text for word in ("推荐学习资源", "推荐资料", "资源推荐", "recommend")):
        return "recommend"
    if has_courseware:
        return "courseware"
    if has_exercise:
        return "exercise"
    if has_plan:
        return "plan"
    if any(word in text for word in ("学情", "薄弱", "掌握情况", "成绩分析")):
        return "profile"
    if any(word in text for word in ("查找资料", "检索资料", "教材资料", "知识库")):
        return "search"
    return "qa"


def requested_generation_actions(message: str) -> set[str]:
    text = message.lower()
    words = {
        "courseware": ("课件", "讲义", "courseware"),
        "exercise": ("练习", "习题", "出题", "exercise"),
        "plan": ("计划", "学习路线", "复习安排", "plan"),
    }
    return {action for action, keywords in words.items() if any(word in text for word in keywords)}


def infer_topic(message: str) -> str:
    """Extract a bounded topic from common Chinese task requests."""

    cleaned = re.sub(r"\s+", " ", message).strip(" 。！？,.，")
    first_clause = re.split(r"[，,；;]", cleaned, maxsplit=1)[0]
    topic = re.sub(r"^(?:依据|基于|根据)(?:附件|上传的?资料|上传的?文件|资料|文件).{0,40}?(?=生成|制作|整理)", "", first_clause)
    topic = re.sub(r"^(?:请|帮我|给我|请帮我|根据我的学习情况|按照我的成绩)*\s*(?:生成|制作|查找|检索|制定|分析|整理|推荐)\s*", "", topic)
    output = re.search(r"(?:的)?(?:完整|针对性|强化|复习|学习|章节|阶段)?(?:课件|讲义|练习题|练习|习题|学习计划|复习计划|教材资料|知识资料)", topic)
    if output is not None and output.start() > 0:
        topic = topic[:output.start()]
    topic = re.sub(r"^(?:\d{1,2}|[一二三四五六七八九十]{1,3})\s*道\s*", "", topic)
    topic = re.sub(r"(?:的)?(?:完整|针对性|强化|复习|学习|章节|阶段)?(?:课件|讲义|练习题|习题|教材资料|学习计划|复习计划|知识资料)$", "", topic).strip(" 的")
    return (topic or first_clause)[:120]


def infer_exercise_count(message: str, default: int = 5) -> int:
    """Read an explicitly requested exercise count without changing unrelated numbers."""
    match = re.search(r"(?:(\d{1,2})|([一二三四五六七八九]?十[一二三四五六七八九]?|[三四五六七八九]))\s*道[^。！？\n]{0,40}?(?:练习|习题|题)", message)
    if not match:
        return default
    if match.group(1):
        return int(match.group(1))
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    value = match.group(2)
    if "十" not in value:
        return digits[value]
    before, after = value.split("十", 1)
    return (digits.get(before, 1) * 10) + digits.get(after, 0)


def task_to_dict(task: AssistantTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "conversation_id": task.session_id,
        "task_type": task.task_type,
        "status": task.status,
        "current_step": task.current_step,
        "result": task.result_json or {},
        "error_code": task.error_code,
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "execution_attempt": task.execution_attempt,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "heartbeat_at": task.heartbeat_at.isoformat() if task.heartbeat_at else None,
    }


def create_task(
    db: Session,
    *,
    user_id: int,
    session: ChatSession,
    client_request_id: str,
    action: str,
    message: str,
    knowledge_point: str,
    exercise_count: int,
    allow_session_reuse: bool = False,
    attachment_ids: list[int] | None = None,
    use_learning_context: bool | None = None,
    side_effect_root_task_id: int | None = None,
    knowledge_subject: str = "",
    allow_web_knowledge: bool = False,
    learning_context_id: str | None = None,
    artifact_kind: str | None = None,
    resource_video: dict | None = None,
    chapter_revision: dict | None = None,
) -> tuple[AssistantTask, bool]:
    session_id = session.id
    request = {"message": message, "knowledge_point": knowledge_point, "exercise_count": exercise_count}
    if chapter_revision:
        request["chapter_revision"] = chapter_revision
    if artifact_kind:
        request["artifact_kind"] = artifact_kind
    if resource_video:
        request["resource_video"] = resource_video
    if learning_context_id:
        from common.learning_context import validate_context
        validate_context(db, user_id, learning_context_id)
        request["learning_context_id"] = learning_context_id
    if attachment_ids:
        request["attachment_ids"] = list(attachment_ids)
    if use_learning_context is not None:
        request["use_learning_context"] = use_learning_context
    if side_effect_root_task_id is not None:
        request["side_effect_root_task_id"] = side_effect_root_task_id
    if knowledge_subject:
        request["knowledge_subject"] = knowledge_subject
    if allow_web_knowledge:
        request["allow_web_knowledge"] = True

    def reuse(previous: AssistantTask) -> tuple[AssistantTask, bool]:
        if previous.task_type != action or previous.request_json != request or (not allow_session_reuse and previous.session_id != session_id):
            raise AssistantTaskRequestConflict("请求标识已用于另一项任务")
        return previous, False

    previous = db.query(AssistantTask).filter(
        AssistantTask.user_id == user_id,
        AssistantTask.client_request_id == client_request_id,
    ).first()
    if previous is not None:
        # A new conversation may have been flushed by this request. Roll it
        # back when another request already committed the same operation.
        db.rollback()
        return reuse(previous)
    task = AssistantTask(
        user_id=user_id,
        session_id=session.id,
        client_request_id=client_request_id,
        task_type=action,
        status="PENDING",
        current_step="等待执行",
        request_json=request,
        result_json={},
        error_code="",
    )
    _reference_text, attachments = attachment_context(db, user_id, attachment_ids or [])
    db.add(ChatMessage(
        session_id=session.id,
        role="user",
        content=message,
        model_used="",
        metadata_json={"source": "assistant", "action": action, "client_request_id": client_request_id, "attachments": attachments},
    ))
    db.add(task)
    session.last_message_at = datetime.utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.query(AssistantTask).filter(
            AssistantTask.user_id == user_id, AssistantTask.client_request_id == client_request_id,
        ).first()
        if previous is None:
            raise
        return reuse(previous)
    db.refresh(task)
    return task, True


def _profile_result(db: Session, user_id: int) -> dict[str, Any]:
    profile = db.get(UserProfile, user_id)
    mastery = profile.mastery_json if profile and isinstance(profile.mastery_json, dict) else {}
    rows = (
        db.query(AnswerRecord, KnowledgePoint.name)
        .join(Exercise, AnswerRecord.exercise_id == Exercise.id)
        .join(KnowledgePoint, Exercise.knowledge_point_id == KnowledgePoint.id)
        .filter(AnswerRecord.user_id == user_id)
        .order_by(AnswerRecord.id.desc()).limit(200).all()
    )
    scores = db.query(TranscriptScore).filter(TranscriptScore.student_user_id == user_id).count()
    if not rows and not mastery and not scores:
        return {
            "content": "目前没有可用于分析的练习、成绩或知识掌握记录。先完成练习或导入成绩单，再让小智分析学情。",
            "cards": [],
            "sources": [],
            "evidence": {"answer_records": 0, "transcript_scores": 0, "profile_mastery_items": 0},
        }
    counts: dict[str, list[int]] = {}
    for record, point in rows:
        stats = counts.setdefault(point, [0, 0])
        stats[0] += 1
        if record.is_correct is True:
            stats[1] += 1
    weak = sorted(
        (point for point, (total, correct) in counts.items() if total >= 2 and correct / total < .6),
        key=lambda point: counts[point][1] / counts[point][0],
    )[:5]
    lines = [f"已读取你最近 {len(rows)} 条练习记录、{scores} 条成绩记录和 {len(mastery)} 项画像掌握记录。"]
    if weak:
        lines.append("练习正确率较低的知识点：" + "、".join(
            f"{point}（{counts[point][1]}/{counts[point][0]}）" for point in weak
        ) + "。")
    else:
        lines.append("现有练习记录不足以判定明确的薄弱知识点；可以继续完成有答案的练习。")
    return {
        "content": "\n\n".join(lines),
        "cards": [{"type": "profile", "title": "查看完整学情", "route": "/student/profile-analysis"}],
        "sources": [],
        "evidence": {"answer_records": len(rows), "transcript_scores": scores, "profile_mastery_items": len(mastery)},
    }


def _search_result(query: str) -> dict[str, Any]:
    service = KnowledgeBaseService()
    articles = service.search_by_keywords(query, top_k=5)
    if not articles:
        return {
            "content": "本地知识库暂无匹配资料。你可以继续用普通问答获取通用解释，但该解释不会有本地教材引用。",
            "cards": [], "sources": [], "evidence": {"matches": 0},
        }
    sources = [
        {"title": article.title, "summary": article.summary[:250], "source": service.article_to_dict(article)}
        for article in articles
    ]
    return {
        "content": "找到以下本地知识资料：\n" + "\n".join(f"- {item['title']}" for item in sources),
        "cards": [], "sources": sources, "evidence": {"matches": len(sources)},
    }


def _recommend_result(db: Session, user_id: int) -> dict[str, Any]:
    items = ResourceManager(db).recommend_resources(user_id, limit=6)
    if not items:
        return {
            "content": "当前还没有可推荐的已审核学习资源。可以先浏览资源库，或让小智围绕具体知识点生成资源。",
            "cards": [], "sources": [], "evidence": {"recommendation_count": 0},
        }
    cards = [{
        "type": "recommendation", "title": item.title,
        "resource_id": item.id, "route": "/student/resources",
        "reason": item.recommendation_reason,
    } for item in items]
    return {
        "content": "根据当前可见资源及真实学习行为，推荐：\n" + "\n".join(
            f"- {item.title}：{item.recommendation_reason}" for item in items
        ),
        "cards": cards, "sources": [], "evidence": {"recommendation_count": len(items)},
    }


def _cancellation_requested(task_id: int) -> bool:
    # A fresh session sees cancellation committed by another API process.
    with SessionLocal() as status_db:
        row = status_db.get(AssistantTask, task_id)
        guard = current_execution.get()
        stopped = row is None or row.status != "RUNNING" or (
            guard is not None and (row.worker_id != guard[1] or row.execution_attempt != guard[2])
        )
        if stopped or guard is None:
            return stopped
        return status_db.query(AssistantTask.id).filter(
            AssistantTask.id == task_id, *lease_conditions(),
        ).first() is None


def _heartbeat(task_id: int, worker_id: str, attempt: int, stop: threading.Event) -> None:
    interval = max(1, getattr(get_settings(), "assistant_worker_heartbeat_seconds", 5))
    while not stop.wait(interval):
        try:
            with SessionLocal() as heartbeat_db:
                expire_stale_tasks(heartbeat_db, task_id=task_id)
                changed = heartbeat_db.query(AssistantTask).filter(
                    AssistantTask.id == task_id,
                    AssistantTask.worker_id == worker_id,
                    AssistantTask.execution_attempt == attempt,
                    AssistantTask.status.in_(["RUNNING", "CANCEL_REQUESTED"]),
                    *lease_conditions(),
                ).update({AssistantTask.heartbeat_at: datetime.utcnow()}, synchronize_session=False)
                heartbeat_db.commit()
            if changed != 1:
                return
        except Exception:
            LOGGER.exception("assistant_heartbeat_failed task_id=%s worker_id=%s attempt=%s", task_id, worker_id, attempt)


def _run_task_workflow(db: Session, task: AssistantTask, request: CoordinationRequest) -> dict:
    workflow = CoordinatorWorkflow(db)
    if isinstance(task, AssistantTask):
        workflow.assistant_operation_root = str((task.request_json or {}).get("side_effect_root_task_id") or task.id)
        workflow.cancellation_check = lambda: _cancellation_requested(task.id)
        def mark_stage(agent_name: str) -> None:
            ensure_write_allowed(db)
            task.current_step = f"正在执行 {agent_name}"[:100]
            db.commit()
        workflow.stage_callback = mark_stage
    return workflow.run(request)


def _coordinated_result(db: Session, task: AssistantTask) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    request = task.request_json or {}
    action = task.task_type
    topic = str(request.get("knowledge_point") or "").strip()
    message = str(request.get("message") or "")
    workspace_context_id = request.get("learning_context_id")
    workspace_subject = ""
    workspace_point_id = ""
    workspace_goal = ""
    if workspace_context_id:
        from common.learning_context import validate_context
        _, workspace_plan, _, workspace_task, point, _ = validate_context(db, task.user_id, workspace_context_id)
        workspace_subject = str((workspace_plan.path_data_json or {}).get("subject") or "")
        workspace_point_id = str(point.id)
        workspace_goal = f"\n当前学习任务：{workspace_task.get('title', '')}；任务目标：{workspace_task.get('objective', '')}。围绕该任务展开讲解、案例和练习。"
        if topic != point.name:
            raise ValueError("Learning context knowledge point differs")
    generation_actions = requested_generation_actions(message) if action == "combined" else {action}
    if workspace_context_id and "plan" in generation_actions:
        raise ValueError("请在计划管理中创建新计划。")
    if action == "combined" and not generation_actions:
        raise ValueError("请明确需要生成课件、练习或学习计划中的哪些成果。")
    wants_exercises = "exercise" in generation_actions
    explicit_history = any(phrase in message for phrase in (
        "我的错题", "我的薄弱", "根据我的学习情况", "按照我的成绩", "基于我的学情", "根据我的成绩", "我的学情",
    ))
    use_history = bool(request.get("use_learning_context", True)) or explicit_history
    try:
        reference_materials, attachments = attachment_context(db, task.user_id, list(request.get("attachment_ids") or []))
    except HTTPException as exc:
        raise ValueError("任务引用的资料已删除或无权访问，请重新添加资料后再生成。") from exc
    if not workspace_context_id and action in {"exercise", "combined"} and ("我的薄弱" in message or "我的错题" in message):
        rows = (
            db.query(KnowledgePoint.name, AnswerRecord.is_correct)
            .join(Exercise, Exercise.knowledge_point_id == KnowledgePoint.id)
            .join(AnswerRecord, AnswerRecord.exercise_id == Exercise.id)
            .filter(AnswerRecord.user_id == task.user_id)
            .order_by(AnswerRecord.id.desc()).limit(200).all()
        )
        counts: dict[str, list[int]] = {}
        for point, correct in rows:
            stats = counts.setdefault(point, [0, 0])
            stats[0] += 1
            stats[1] += int(correct is True)
        weak = sorted(
            (point for point, (total, correct) in counts.items() if total >= 2 and correct / total < .6),
            key=lambda point: counts[point][1] / counts[point][0],
        )
        if not weak:
            raise ValueError("目前没有足够的错题记录识别薄弱知识点。请先完成练习，或明确输入需要强化的知识点。")
        topic = weak[0]
    if action == "plan" and ("根据我的" in message or "按照我的" in message):
        profile = db.get(UserProfile, task.user_id)
        has_profile = bool(profile and isinstance(profile.mastery_json, dict) and profile.mastery_json)
        has_answers = db.query(AnswerRecord.id).filter(AnswerRecord.user_id == task.user_id).first() is not None
        has_scores = db.query(TranscriptScore.id).filter(TranscriptScore.student_user_id == task.user_id).first() is not None
        if not (has_profile or has_answers or has_scores):
            raise ValueError("还没有足够的学习记录制定个性化计划。请先完成练习或导入成绩；也可以明确课程主题来创建普通学习路径。")
    if not topic:
        raise ValueError("请提供要学习的课程或知识点。")
    requested_count = int(request.get("exercise_count") or 5)
    if workspace_context_id:
        from common.learning_context import context_reference
        reference_materials = context_reference(db, task.user_id, workspace_context_id) + "\n" + reference_materials
    first_count = min(10, requested_count - 3) if requested_count > 10 else requested_count
    context = {
        "execute": True,
        "force_agents": (
            ["learner_profiling_agent", "knowledge_base_agent"]
            + (["resource_generation_agent"] if "courseware" in generation_actions else [])
            + (["exercise_generation_agent"] if wants_exercises else [])
        ) if action == "combined" else AGENTS_BY_ACTION[action],
        "operation": "search",
        "query": topic,
        "request_text": str(request.get("message") or "") + workspace_goal,
        "exercise_count": first_count,
        "only_exercises": wants_exercises and "courseware" not in generation_actions,
        "persist_path": False,
        "reference_materials": reference_materials[:12000],
        "use_learning_context": use_history,
        "assistant_operation_root": str(request.get("side_effect_root_task_id") or getattr(task, "id", "")),
        "subject": workspace_subject or str(request.get("knowledge_subject") or ""),
        "knowledge_point_id": workspace_point_id,
        "dynamic_knowledge": bool(workspace_subject or request.get("knowledge_subject")),
        "allow_web_knowledge": request.get("allow_web_knowledge") is True,
    }
    raw = _run_task_workflow(db, task, CoordinationRequest(
        user_id=task.user_id,
        intent=str(request.get("message") or action),
        knowledge_point=topic,
        payload=context,
    ))
    if wants_exercises and requested_count > 10 and raw.get("status") != "cancelled":
        task.current_step = f"首批练习已生成，正在生成剩余 {requested_count - first_count} 道"
        db.commit()
        extra = _run_task_workflow(db, task, CoordinationRequest(
            user_id=task.user_id,
            intent=message,
            knowledge_point=topic,
            payload={**context, "exercise_count": requested_count - first_count,
                     "force_agents": ["exercise_generation_agent"], "assistant_exercise_batch": 1},
        ))
        first_output = (raw.get("outputs") or {}).get("exercise_generation_agent") or {}
        extra_output = (extra.get("outputs") or {}).get("exercise_generation_agent") or {}
        first_set = jsonable_encoder(first_output.get("exercise_set")) if isinstance(first_output, dict) else None
        extra_set = jsonable_encoder(extra_output.get("exercise_set")) if isinstance(extra_output, dict) else None
        if isinstance(first_set, dict) and isinstance(extra_set, dict):
            first_set["exercises"] = [*(first_set.get("exercises") or []), *(extra_set.get("exercises") or [])]
            first_output["exercise_set"] = first_set
        raw["agent_calls"] = [*(raw.get("agent_calls") or []), *(extra.get("agent_calls") or [])]
        raw["citations"] = [*(raw.get("citations") or []), *(extra.get("citations") or [])]
        if extra.get("status") == "cancelled":
            raw["status"] = "cancelled"
        elif extra.get("status") != "success" or not isinstance(extra_set, dict):
            raw["status"] = "partial"
    if action == "combined" and "plan" in generation_actions and raw.get("status") != "cancelled":
        task.current_step = "资料检索与资源生成已执行，正在制定学习路径"
        db.commit()
        # A plan must follow the generated learning materials. The existing
        # coordinator executes path planning before resource generation when
        # all agents are requested in one call, so run the final step separately.
        profile_output = (raw.get("outputs") or {}).get("learner_profiling_agent") or {}
        learner_profile = profile_output.get("learner_profile") if isinstance(profile_output, dict) else {}
        plan = _run_task_workflow(db, task, CoordinationRequest(
            user_id=task.user_id,
            intent=str(request.get("message") or action),
            knowledge_point=topic,
            payload={**context, "learner_profile": learner_profile or {}, "force_agents": ["path_planning_agent"]},
        ))
        raw["outputs"] = {**(raw.get("outputs") or {}), **(plan.get("outputs") or {})}
        raw["agent_calls"] = [*(raw.get("agent_calls") or []), *(plan.get("agent_calls") or [])]
        raw["selected_agents"] = [*(raw.get("selected_agents") or []), *(plan.get("selected_agents") or [])]
        raw["citations"] = [*(raw.get("citations") or []), *(plan.get("citations") or [])]
        if plan.get("status") == "cancelled":
            raw["status"] = "cancelled"
        elif raw.get("status") != "success" or plan.get("status") != "success":
            raw["status"] = "partial"
    outputs = raw.get("outputs") or {}
    cards: list[dict[str, Any]] = []
    lines: list[str] = []
    resource = (outputs.get("resource_generation_agent") or {}).get("resource")
    if isinstance(resource, dict) and resource.get("id"):
        linked_context_id = None
        if workspace_context_id:
            from common.learning_context import create_context, validate_context
            from common.resource_version import resource_version
            origin, *_ = validate_context(db, task.user_id, workspace_context_id)
            generated = db.get(Resource, int(resource["id"]))
            if not generated or generated.generated_for_user_id != task.user_id:
                raise ValueError("Generated resource does not belong to learner")
            ensure_write_allowed(db)
            linked = create_context(db, task.user_id, client_request_id=f"assistant-{task.id}-resource-{generated.id}",
                                    plan_id=origin.plan_id, module_id=origin.module_id, task_key=origin.task_key,
                                    resource_id=generated.id, expected_resource_version=resource_version(generated))
            linked_context_id = linked.id
        cards.append({
            "type": "courseware", "title": str(resource.get("title") or topic),
            "resource_id": resource["id"], "route": "/student/resources",
            "learning_context_id": linked_context_id,
        })
        lines.append(f"课件已保存到资源库（编号 {resource['id']}）。")
        if resource.get('reused'):
            lines.append('本次复用相同目标、学情、资料和模板版本的已有课件，未重复调用生成模型。')
        video = (resource.get('media') or {}).get('video') or {}
        if video.get('status') == 'ready':
            lines.append('字幕课件视频已保存，可在课件阅读器内播放（无声）。')
        elif video.get('status') == 'failed':
            lines.append('课件已保存；本地视频制作失败，可在阅读器内单独重试。')
    exercises = (outputs.get("exercise_generation_agent") or {}).get("exercise_set")
    exercise_data = None
    valid_exercises = False
    if exercises:
        exercise_data = jsonable_encoder(exercises)
        items = exercise_data.get("exercises", []) if isinstance(exercise_data, dict) else []
        exercise_ids = [item.get("exercise_id") for item in items if isinstance(item, dict)]
        valid_exercises = bool(items) and len(exercise_ids) == len(items) and all(exercise_ids) and len(set(exercise_ids)) == len(exercise_ids)
        if valid_exercises:
            if workspace_context_id:
                from common.learning_context import bind_generated_exercises
                ensure_write_allowed(db)
                bind_generated_exercises(db, task.user_id, workspace_context_id, task.id, exercise_ids)
            cards.append({"type": "exercise", "title": f"{len(items)} 道练习", "exercise_ids": [item["exercise_id"] for item in items]})
            lines.append(f"已生成并保存 {len(items)} 道练习。")
            if exercise_data.get("audit_reason") == "deterministic_fallback":
                lines.append("本次题组由系统规则生成，未使用模型生成结果。")
            if len(items) < requested_count:
                raw["status"] = "partial"
    path = (outputs.get("path_planning_agent") or {}).get("learning_path")
    path_draft = jsonable_encoder(path) if isinstance(path, dict) and path.get("stages") else None
    if path_draft:
        cards.append({"type": "plan_draft", "title": "确认保存学习路径"})
        preview = ["学习路径草案已生成。确认保存后才会替换当前计划："]
        for stage in path_draft["stages"][:7]:
            if not isinstance(stage, dict):
                continue
            tasks = stage.get("tasks") or []
            task_names = "、".join(str(item.get("title") or "学习任务")[:40] for item in tasks[:5] if isinstance(item, dict))
            preview.append(f"- {str(stage.get('title') or '学习阶段')[:60]}：{task_names}")
        lines.append("\n".join(preview))
    citations = jsonable_encoder(raw.get("citations") or [])
    acquisition = outputs.get("knowledge_acquisition") or (resource.get("knowledge_evidence") if isinstance(resource, dict) else None) or {}
    for source in acquisition.get("sources") or []:
        if not isinstance(source, dict) or not source.get("url"):
            continue
        citations.append({**source, "summary": "公开补充资料，尚待审核。" if source.get("review_status") == "PENDING" else "课程知识参考资料。"})
    citations.extend({
        "title": str(attachment["file_name"]),
        "summary": "用户上传资料的文字摘录，未作为本地教材校验。",
        "source": {"type": "uploaded_attachment", "attachment_id": attachment["id"]},
    } for attachment in attachments)
    if not lines and raw.get("status") != "cancelled":
        failed = [name for name, output in outputs.items() if isinstance(output, dict) and output.get("status") == "failed"]
        if failed:
            raise RuntimeError("、".join(failed) + " 暂时未完成，请稍后重试。")
        raise RuntimeError("专业智能体没有返回可使用的学习成果。")
    coverage_state = (acquisition.get("coverage") or {}).get("state")
    if coverage_state in {"PARTIAL", "MISSING", "STALE", "UNCERTAIN", "RETRIEVAL_FAILURE"}:
        lines.append("当前知识资料仍有缺口或待核实内容，请结合参考来源学习。")
    if any(source.get("review_status") == "PENDING" for source in acquisition.get("sources") or [] if isinstance(source, dict)):
        lines.append("本次使用的公开补充资料尚待管理员审核。")
    if raw.get("status") == "cancelled":
        lines.append("任务已取消，后续步骤已停止；已保存的成果仍可查看。")
    if raw.get("status") == "partial":
        lines.append("部分步骤未完成，请查看执行记录后重试。")
    result = {
        "learning_context_id": workspace_context_id,
        "content": "\n".join(lines),
        "cards": cards,
        "sources": citations,
        "exercise_set": exercise_data if valid_exercises else None,
        "path_draft": path_draft,
        "evidence": {"selected_agents": raw.get("selected_agents") or [], "learning_context_used": use_history,
                     "learning_context_basis": "explicit_request" if explicit_history else "preference" if use_history else "disabled",
                     "knowledge_coverage": (outputs.get("knowledge_acquisition") or {}).get("coverage"),
                     "knowledge_supplementation": acquisition.get("supplementation"),
                     "shared_knowledge_context_id": ((outputs.get("knowledge_acquisition") or {}).get("retrieval_context") or {}).get("context_id"),
                     "public_knowledge_sources": (outputs.get("knowledge_acquisition") or {}).get("sources", [])},
        "partial": raw.get("status") == "partial",
    }
    return result, list(raw.get("agent_calls") or [])


def execute_task(task_id: int) -> None:
    """Run after the HTTP response; final state survives a browser refresh."""

    with SessionLocal() as db:
        task = db.get(AssistantTask, task_id)
        if task is None or task.status != "PENDING" or (task.next_attempt_at and task.next_attempt_at > datetime.utcnow()):
            return
        current_step = {
            "profile": "正在汇总真实学习记录",
            "search": "正在检索本地知识资料",
            "recommend": "正在根据真实学习记录筛选资源",
            "courseware": "正在检索资料并生成课件",
            "exercise": "正在检索资料并生成练习",
            "plan": "正在分析学情并生成学习路径",
            "combined": "正在分析学情、检索资料并生成资源",
        }.get(task.task_type, "正在执行学习任务")
        worker_id = f"{socket.gethostname()[:40]}:{os.getpid()}:{uuid4().hex[:12]}"
        started_at = datetime.utcnow()
        claimed = db.query(AssistantTask).filter(
            AssistantTask.id == task_id, AssistantTask.status == "PENDING",
            or_(AssistantTask.next_attempt_at.is_(None), AssistantTask.next_attempt_at <= started_at),
        ).update({
            AssistantTask.status: "RUNNING",
            AssistantTask.current_step: current_step,
            AssistantTask.updated_at: started_at,
            AssistantTask.started_at: started_at,
            AssistantTask.heartbeat_at: started_at,
            AssistantTask.worker_id: worker_id,
            AssistantTask.execution_attempt: AssistantTask.execution_attempt + 1,
            AssistantTask.next_attempt_at: None,
        }, synchronize_session=False)
        db.commit()
        if claimed != 1:
            return
        db.refresh(task)
        attempt = task.execution_attempt
        from common.task_attempts import started as record_attempt_started
        record_attempt_started(db, "assistant", task)
        LOGGER.info("assistant_task_claimed task_id=%s worker_id=%s attempt=%s task_type=%s", task_id, worker_id, attempt, task.task_type)
        guard_token = current_execution.set((task_id, worker_id, attempt))
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=_heartbeat, args=(task_id, worker_id, attempt, heartbeat_stop), daemon=True,
        )
        heartbeat_thread.start()
        try:
            if task.task_type == "profile":
                result = _profile_result(db, task.user_id)
                calls = [{"agent": "learner_profiling_agent", "output_status": "completed", "elapsed_ms": 0}]
            elif task.task_type == "search":
                result = _search_result(str((task.request_json or {}).get("knowledge_point") or ""))
                calls = [{"agent": "knowledge_base_agent", "output_status": "completed", "elapsed_ms": 0}]
            elif task.task_type == "recommend":
                result = _recommend_result(db, task.user_id)
                calls = [{"agent": "resource_recommendation_agent", "output_status": "completed", "elapsed_ms": 0}]
            elif task.task_type == "artifact":
                from services.agent_service.app.services.resource_artifacts import produce_artifact
                result = produce_artifact(db, task)
                calls = [{"agent": "local_artifact_renderer", "output_status": "completed", "elapsed_ms": 0}]
            elif task.task_type == "resource_video":
                from common.resource_version import resource_version
                from services.agent_service.app.services.resource_artifacts import ensure_resource_video
                spec = task.request_json["resource_video"]
                source = db.get(Resource, spec["resource_id"])
                if not source or source.generated_for_user_id != task.user_id or source.publish_status == "archived" or resource_version(source) != spec["version"]:
                    raise ValueError("原课件已改变，请重新打开")
                media = ensure_resource_video(source)
                db.expire_all()
                source = db.get(Resource, spec["resource_id"])
                if not source or source.publish_status == "archived" or resource_version(source) != spec["version"]:
                    raise ValueError("课件在视频制作期间发生改变，请重新打开")
                result = {"content": "字幕视频已保存（无声）", "media": media}
                calls = [{"agent": "local_video_renderer", "output_status": "completed", "elapsed_ms": 0}]
            elif task.task_type == "courseware_revision":
                from services.agent_service.app.services.resource_generation import ResourceGenerationService
                revision = dict(task.request_json["chapter_revision"])
                db.rollback()  # no write transaction during provider invocation
                generated = ResourceGenerationService().regenerate_chapter(task.user_id, int(task.request_json.get("side_effect_root_task_id") or task.id), **revision)
                result = {"content": "新章节版本已生成；原课件保留。", "resource": generated}
                calls = [{"agent": "resource_generation_agent", "output_status": "completed", "elapsed_ms": 0}]
            else:
                result, calls = _coordinated_result(db, task)
            expire_stale_tasks(db, task_id=task_id)
            finished = db.query(AssistantTask).filter(
                AssistantTask.id == task_id, AssistantTask.status == "RUNNING",
                AssistantTask.worker_id == worker_id, AssistantTask.execution_attempt == attempt,
                *lease_conditions(),
            ).update({AssistantTask.status: "SUCCEEDED"}, synchronize_session=False)
            db.refresh(task)
            if finished != 1:
                cancelled = db.query(AssistantTask).filter(
                    AssistantTask.id == task_id, AssistantTask.status == "CANCEL_REQUESTED",
                    AssistantTask.worker_id == worker_id, AssistantTask.execution_attempt == attempt,
                ).update({AssistantTask.status: "CANCELLED"}, synchronize_session=False)
                if cancelled != 1:
                    db.rollback()
                    return
                db.refresh(task)
                result = {**result, "content": str(result.get("content") or "")}
                if "任务已取消" not in result["content"]:
                    result["content"] += "\n任务已取消，后续步骤已停止；已保存的成果仍可查看。"
            for call in calls:
                db.add(AssistantAgentExecution(
                    task_id=task.id,
                    agent_code=str(call.get("agent") or "unknown")[:80],
                    status=str(call.get("output_status") or "completed").upper()[:20],
                    elapsed_ms=int(call.get("elapsed_ms") or 0),
                    error_code=str(call.get("error_code") or "")[:80],
                    completed_at=datetime.utcnow(),
                ))
            task.current_step = "任务已取消" if task.status == "CANCELLED" else "任务完成"
            task.result_json = result
            task.completed_at = datetime.utcnow()
            db.add(ChatMessage(
                session_id=task.session_id,
                role="assistant",
                content=result["content"],
                model_used="assistant_orchestrator",
                metadata_json={"task_id": task.id, "cards": result.get("cards", []), "sources": result.get("sources", [])},
            ))
            db.commit()
            LOGGER.info("assistant_task_final task_id=%s worker_id=%s attempt=%s final_status=%s", task_id, worker_id, attempt, task.status)
        except Exception as exc:
            LOGGER.exception("assistant_task_failed task_id=%s worker_id=%s attempt=%s", task_id, worker_id, attempt)
            db.rollback()
            expire_stale_tasks(db, task_id=task_id)
            locked = db.query(AssistantTask).filter(
                AssistantTask.id == task_id,
                AssistantTask.status.in_(["RUNNING", "CANCEL_REQUESTED"]),
                AssistantTask.worker_id == worker_id, AssistantTask.execution_attempt == attempt,
                *lease_conditions(),
            ).update({AssistantTask.updated_at: datetime.utcnow()}, synchronize_session=False)
            task = db.get(AssistantTask, task_id)
            if locked == 1 and task is not None:
                db.refresh(task)
                cancelled = task.status == "CANCEL_REQUESTED"
                task.status = "CANCELLED" if cancelled else "FAILED"
                task.current_step = "任务已取消" if cancelled else "任务未完成"
                task.error_code = "" if cancelled else "ASSISTANT_TASK_FAILED"
                task.result_json = {"content": "任务已取消，后续步骤已停止；当前步骤可能已保存部分成果，请查看资源库和练习。" if cancelled else str(exc) if isinstance(exc, ValueError) else "任务暂时未完成，请稍后重试。"}
                task.completed_at = datetime.utcnow()
                db.commit()
                LOGGER.info("assistant_task_final task_id=%s worker_id=%s attempt=%s final_status=%s", task_id, worker_id, attempt, task.status)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)
            current_execution.reset(guard_token)
            from common.task_attempts import finished as record_attempt_finished
            record_attempt_finished(db, "assistant", task_id, attempt, AssistantTask)


def expire_stale_tasks(db: Session, user_id: int | None = None, *, task_id: int | None = None) -> int:
    """Fence dead workers; only read-only work can be automatically replayed."""
    now = datetime.utcnow()
    settings = get_settings()
    heartbeat_interval = max(1, getattr(settings, "assistant_worker_heartbeat_seconds", 5))
    stale_seconds = max(heartbeat_interval * 3, getattr(settings, "assistant_worker_stale_seconds", 45))
    heartbeat_cutoff = now - timedelta(seconds=stale_seconds)
    task_cutoff = now - timedelta(seconds=max(1, getattr(settings, "assistant_task_max_seconds", 1800)))
    cancel_cutoff = now - timedelta(seconds=max(1, getattr(settings, "assistant_cancel_wait_seconds", 60)))
    stale_statuses = ["RUNNING", "CANCEL_REQUESTED"] if task_execution_mode() == "worker" else ["PENDING", "RUNNING", "CANCEL_REQUESTED"]
    query = db.query(AssistantTask).filter(
        AssistantTask.status.in_(stale_statuses),
    )
    if user_id is not None:
        query = query.filter(AssistantTask.user_id == user_id)
    if task_id is not None:
        query = query.filter(AssistantTask.id == task_id)
    tasks = query.populate_existing().all()
    expired = 0
    for task in tasks:
        if task.status == "PENDING" and task.updated_at >= task_cutoff:
            continue
        heartbeat = task.heartbeat_at or task.updated_at
        stale_heartbeat = heartbeat is not None and heartbeat < heartbeat_cutoff
        max_duration = task.started_at is not None and task.started_at < task_cutoff
        cancelling_too_long = task.status == "CANCEL_REQUESTED" and task.updated_at < cancel_cutoff
        if not (stale_heartbeat or max_duration or cancelling_too_long):
            continue
        conditions = [AssistantTask.id == task.id, AssistantTask.status == task.status,
                      AssistantTask.execution_attempt == task.execution_attempt]
        conditions.append(AssistantTask.worker_id == task.worker_id if task.worker_id is not None else AssistantTask.worker_id.is_(None))
        conditions.append(AssistantTask.heartbeat_at == task.heartbeat_at if task.heartbeat_at is not None else AssistantTask.heartbeat_at.is_(None))
        if task.status == "CANCEL_REQUESTED":
            status, code, content = "CANCELLED", "", "任务已取消；当前步骤已停止或执行权已收回。"
        elif task.status == "RUNNING" and task.task_type in {"profile", "search", "recommend"} and task.execution_attempt < max(1, getattr(settings, "assistant_safe_retry_limit", 2)) and not max_duration and task_execution_mode() == "worker":
            backoff = max(0, getattr(settings, "assistant_safe_retry_backoff_seconds", 5)) * (2 ** max(0, task.execution_attempt - 1))
            changed = db.query(AssistantTask).filter(*conditions).update({
                AssistantTask.status: "PENDING", AssistantTask.current_step: "Worker 失活，等待安全重试",
                AssistantTask.worker_id: None, AssistantTask.heartbeat_at: None,
                AssistantTask.next_attempt_at: now + timedelta(seconds=min(backoff, 300)),
                AssistantTask.updated_at: now,
            }, synchronize_session=False)
            expired += changed
            if changed:
                LOGGER.warning("assistant_task_requeued task_id=%s attempt=%s reason=heartbeat_stale", task.id, task.execution_attempt)
            continue
        else:
            status, code, content = "TIMED_OUT", "WORKER_INTERRUPTED" if stale_heartbeat else "TASK_DEADLINE_EXCEEDED", "任务执行中断；已提交操作不会自动重放，请检查已有成果。"
        changed = db.query(AssistantTask).filter(*conditions).update({
            AssistantTask.status: status, AssistantTask.current_step: "任务已取消" if status == "CANCELLED" else "任务执行超时",
            AssistantTask.error_code: code,
            AssistantTask.result_json: {"content": content},
            AssistantTask.completed_at: now, AssistantTask.updated_at: now,
        }, synchronize_session=False)
        expired += changed
        if changed:
            LOGGER.warning("assistant_task_recovered task_id=%s worker_id=%s attempt=%s final_status=%s reason=%s", task.id, task.worker_id, task.execution_attempt, status, code or "cancel_wait")
    if expired:
        db.commit()
        db.expire_all()
    return expired


def fail_interrupted_tasks() -> int:
    """Expire work abandoned before startup without touching active workers."""
    with SessionLocal() as db:
        return expire_stale_tasks(db)
