"""Owner-scoped progress for every durable resource generation entry point."""

import json
import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import AssistantTask, CoordinationTask, LearningContext, Resource, User

router = APIRouter(prefix="/generation", tags=["generation-progress"])
ACTIVE = ("PENDING", "QUEUED", "RUNNING", "CANCEL_REQUESTED")
KINDS = {"courseware", "exercise", "combined", "plan", "artifact", "resource_video", "courseware_revision"}
LABELS = {"courseware": "课件", "exercise": "练习", "combined": "学习资源", "plan": "学习路径",
          "resource_video": "课件视频", "courseware_revision": "章节修订", "artifact": "学习产物",
          "pptx": "PPTX", "video": "字幕视频", "audio": "语音", "animation": "步骤动画"}


def _json(value):
    try:
        return json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}


@router.get("/tasks")
def generation_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Filter before reading; an administrator also sees only their own work.
    tasks = db.query(AssistantTask).filter(AssistantTask.user_id == user.id,
        AssistantTask.status.in_(ACTIVE), AssistantTask.task_type.in_(KINDS)).order_by(AssistantTask.id.desc()).all()
    resources = db.query(Resource).filter(Resource.generated_for_user_id == user.id,
        Resource.generation_status == "generating", Resource.publish_status != "archived").all()
    partials = {row.assistant_operation_key: row for row in resources if row.assistant_operation_key}
    contexts = {row.id: row for row in db.query(LearningContext).filter(LearningContext.user_id == user.id,
        LearningContext.id.in_([(task.request_json or {}).get("learning_context_id") for task in tasks])).all()}
    items = []
    seen_resources = set()
    for task in tasks:
        request = task.request_json or {}
        root = request.get("side_effect_root_task_id") or task.id
        partial = partials.get(f"assistant:{root}:resource")
        context = contexts.get(request.get("learning_context_id"))
        kind = request.get("artifact_kind") if task.task_type == "artifact" else task.task_type
        step = task.current_step or "等待后台执行"
        match = re.search(r"课件章节\s*(\d+)\s*/\s*(\d+)", step)
        if partial:
            seen_resources.add(partial.id)
        items.append({"key": f"assistant:{task.id}", "id": task.id, "source": "assistant",
            "task_type": task.task_type, "label": LABELS.get(kind, "资源"), "topic": request.get("knowledge_point", ""),
            "status": task.status, "current_step": step,
            "created_at": task.created_at.isoformat(), "started_at": task.started_at.isoformat() if task.started_at else None,
            "learning_context_id": context.id if context else None,
            "plan_id": context.plan_id if context else None, "module_id": context.module_id if context else None,
            "task_key": context.task_key if context else None,
            "resource_id": partial.id if partial else None,
            "progress": {"completed": int(match[1]), "total": int(match[2]), "unit": "章"} if match else None,
            "route": f"/student/workspace/{context.id}" if context else "/student/exercise" if task.task_type == "exercise" else "/student/learning-path" if task.task_type == "plan" else "/student/courseware"})
    for task in db.query(CoordinationTask).filter(CoordinationTask.user_id == user.id,
            CoordinationTask.status.in_(ACTIVE)).order_by(CoordinationTask.id.desc()).all():
        request = task.request_json or {}
        items.append({"key": f"coordination:{task.id}", "id": task.id, "source": "coordination", "label": "学习路径与配套资源",
            "topic": request.get("knowledge_point", ""), "status": task.status,
            "current_step": "等待后台执行" if task.status == "QUEUED" else "后台正在规划路径并生成配套资源",
            "created_at": task.created_at.isoformat(), "started_at": task.started_at.isoformat() if task.started_at else None,
            "progress": None, "route": "/student/learning-path"})
    for row in resources:
        if row.id in seen_resources:
            continue
        # A partial resource may survive a failed/interrupted task. Do not claim
        # that an unowned partial is still executing or invent remaining time.
        saved = _json(row.structured_json)
        chapters = saved.get("chapters") or []
        items.append({"key": f"resource:{row.id}", "id": row.id, "source": "resource", "label": "课件", "topic": row.title,
            "status": "UNKNOWN", "current_step": f"已保存 {len(chapters)} 章，后台执行状态待确认",
            "created_at": row.created_at.isoformat(), "progress": None, "resource_id": row.id, "route": "/student/resources"})
    return {"items": items, "active_count": sum(item["status"] in ACTIVE for item in items)}
