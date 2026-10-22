"""Administrator handling of learner coverage requests using existing construction."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import LearningKnowledgeGap, User
from services.agent_service.app.services import knowledge_documents
from services.agent_service.app.services.knowledge_tasks import (
    KnowledgeTaskConflict,
    create_task,
    serialize_task,
)
from services.agent_service.app.services.plan_knowledge import plan_preflight

router = APIRouter(
    prefix="/knowledge-base/admin/learning-gaps", dependencies=[Depends(require_role("admin"))]
)


@router.get("")
def learning_gaps(db: Session = Depends(get_db)):
    gaps = (
        db.query(LearningKnowledgeGap)
        .order_by(LearningKnowledgeGap.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "subject": row.subject,
                "knowledge_point": row.knowledge_point,
                "reason": row.reason,
                "status": row.status,
                "knowledge_task_id": row.knowledge_task_id,
            }
            for row in gaps
        ]
    }


class GapConstruction(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=80)


@router.post("/{gap_id}/construction", status_code=202)
def construct_learning_gap(
    gap_id: str,
    payload: GapConstruction,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    gap = db.get(LearningKnowledgeGap, gap_id)
    if gap is None:
        raise HTTPException(404, "Learning gap not found")
    assessment = plan_preflight(db, gap.user_id, gap.subject, gap.knowledge_point, record_gap=False)
    if assessment["ready"]:
        gap.status = "RESOLVED"
        from common.notifications import emit
        emit(db, user_id=gap.user_id, sender_id=user.id, event_key=f"gap:{gap.id}:RESOLVED",
            title="知识内容请求已处理", content=f"{gap.subject} / {gap.knowledge_point} 已通过当前可用性检查，可以重新制定学习计划。", type="knowledge")
        db.commit()
        return {"status": "RESOLVED", "gap_id": gap.id}
    operation = "BUILD_POINT" if assessment["point_id"] else "AI_SUBJECT_PLAN"
    requirements = (
        {"point_id": assessment["point_id"], "mode": "COMPLETE_POINT"}
        if assessment["point_id"]
        else {"name": gap.subject, "requirements": f"审核学习者请求的知识点：{gap.knowledge_point}"}
    )
    try:
        task = create_task(
            db,
            actor_user_id=user.id,
            client_request_id=payload.client_request_id,
            operation_type=operation,
            subject=assessment["subject"] or gap.subject,
            requirements=requirements,
        )
    except KnowledgeTaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    gap.knowledge_task_id = task.id
    gap.status = "PENDING_REVIEW"
    from common.notifications import emit
    emit(db, user_id=gap.user_id, sender_id=user.id, event_key=f"gap:{gap.id}:task:{task.id}",
        title="知识内容请求已受理", content=f"{gap.subject} / {gap.knowledge_point} 已进入建设任务 #{task.id}，当前仍待处理和审核，尚未确认发布。", type="knowledge")
    knowledge_documents.audit(
        db, user.id, "knowledge.gap.construction", f"gap={gap.id};task={task.id}"
    )
    db.commit()
    return serialize_task(task)
