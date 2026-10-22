"""Routes for learning-path, knowledge-base, and exercise capabilities."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import get_db
from common.dependencies import get_current_user, require_role, require_self_or_admin
from common.models.learning import LearningPath, User
from common.performance import set_trace_context
from common.schemas.agent import (
    CoordinationRequest,
    ExerciseGenerationRequest,
    ExerciseGenerationResponse,
    LearningPathAdjustRequest,
    LearningPathRequest,
    LearningPathResponse,
)
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow
from services.agent_service.app.services.knowledge_base_admin import (
    crawl_knowledge_sources,
    knowledge_base_status,
    list_knowledge_sources,
    list_knowledge_subject_catalog,
    reindex_knowledge_base,
)
from services.agent_service.app.services.learning_path import (
    LearningPathPrerequisiteError,
    LearningPathRevisionConflict,
    LearningPathService,
)
from services.agent_service.app.services.path_adaptation import PathAdaptationService
from services.agent_service.app.services.plan_feedback import PlanFeedbackService
from services.agent_service.app.services.task_feedback import TaskFeedbackService

router = APIRouter()


class PlanPreflightRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    knowledge_point: str = Field(min_length=1, max_length=100)


@router.post("/paths/preflight")
def check_plan_knowledge(payload: PlanPreflightRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from services.agent_service.app.services.plan_knowledge import assess_plan_knowledge
    result = assess_plan_knowledge(db, user.id, payload.subject, payload.knowledge_point)
    return {key: value for key, value in result.items() if key != "usable_chunks"}


class PlanAdaptationPreview(BaseModel):
    daily_minutes: int | None = Field(default=None, ge=5, le=480)


@router.post("/paths/adaptation/preview")
def preview_plan_adaptation(payload: PlanAdaptationPreview, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)) -> dict:
    try:
        return PathAdaptationService(db).preview(user.id, payload.daily_minutes)
    except LearningPathRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/paths/adaptation/{proposal_id}/confirm")
def confirm_plan_adaptation(proposal_id: str, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)) -> dict:
    try:
        return PathAdaptationService(db).confirm(user.id, proposal_id)
    except LearningPathRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class PlanFeedbackRequest(BaseModel):
    feedback_text: str = Field(min_length=1, max_length=2000)


@router.post("/paths/feedback/preview")
def preview_plan_feedback(payload: PlanFeedbackRequest, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)) -> dict:
    try:
        return PlanFeedbackService(db).preview(user.id, payload.feedback_text)
    except LearningPathRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/paths/feedback/{proposal_id}/confirm")
def confirm_plan_feedback(proposal_id: str, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)) -> dict:
    try:
        return PlanFeedbackService(db).confirm(user.id, proposal_id)
    except LearningPathRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class TaskFeedbackRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=120)
    feedback_type: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=500)


@router.post("/paths/task-feedback/preview")
def preview_task_feedback(payload: TaskFeedbackRequest, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)) -> dict:
    try:
        return TaskFeedbackService(db).preview(user.id, payload.task_id, payload.feedback_type, payload.note)
    except LearningPathRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class KnowledgeBaseReindexRequest(BaseModel):
    subject: str | None = None
    force: bool = False


class KnowledgeBaseCrawlRequest(BaseModel):
    subjects: list[str] = Field(default_factory=list, max_length=10)
    topics: list[str] = Field(default_factory=list, max_length=30)
    skip_existing: bool = True
    reindex: bool = True


@router.post("/paths/generate", response_model=LearningPathResponse)
def generate_learning_path(
    payload: LearningPathRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LearningPathResponse:
    """Generate a personalized learning path through the multi-agent workflow."""
    require_self_or_admin(payload.user_id, current_user)

    from services.agent_service.app.services.plan_knowledge import assess_plan_knowledge
    assess_plan_knowledge(db, payload.user_id, payload.subject, payload.knowledge_point)

    settings = get_settings()
    set_trace_context(
        user_id=payload.user_id,
        task_type="learning_path_generation",
        deadline_seconds=settings.learning_path_deadline_seconds,
        retry_budget=settings.max_total_retries,
    )
    result = CoordinatorWorkflow(db).run(
        CoordinationRequest(
            user_id=payload.user_id,
            intent="learning path plan",
            knowledge_point=payload.knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "force_agents": [
                    "learner_profiling_agent",
                    "knowledge_graph_agent",
                    "path_planning_agent",
                ],
            },
        )
    )
    output = result.get("outputs", {}).get("path_planning_agent", {})
    if output.get("status") == "failed":
        error_code = str(output.get("error_code") or "LEARNING_PATH_GENERATION_FAILED")
        if error_code == "AI_MODEL_INITIALIZATION_TIMEOUT":
            status_code = 503
        elif error_code == "AI_INFERENCE_TIMEOUT":
            status_code = 504
        else:
            status_code = 503
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error_code,
                "message": str(output.get("user_message") or output.get("error") or "学习路径暂时无法生成，请稍后重试"),
            },
        )
    learning_path = output.get("learning_path")
    if not isinstance(learning_path, dict):
        raise HTTPException(status_code=503, detail="Path planning agent did not return a learning path")
    return LearningPathResponse(**learning_path)


@router.get("/paths/history/{user_id}")
def list_path_history(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
) -> dict:
    """Lightweight history for the "历史生成" panel.

    Only summary fields are computed and the page size is bounded; the full
    stage/task JSON is fetched per item on demand by /paths/history/item/{id}.
    """

    require_self_or_admin(user_id, current_user)
    query = (
        db.query(LearningPath)
        .filter(LearningPath.user_id == user_id)
        .order_by(LearningPath.id.desc())
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    items = []
    for row in rows:
        data = row.path_data_json if isinstance(row.path_data_json, dict) else {}
        stages = data.get("stages") if isinstance(data.get("stages"), list) else []
        teacher_scope = data.get("teacher_scope") if isinstance(data.get("teacher_scope"), dict) else {}
        items.append(
            {
                "id": row.id,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "subject": str(data.get("subject") or ""),
                "knowledge_point": str(data.get("knowledge_point") or ""),
                "overview": str(data.get("overview") or "")[:120],
                "estimated_days": data.get("estimated_days"),
                "stage_count": len(stages),
                "task_count": sum(
                    len(stage.get("tasks") or []) for stage in stages if isinstance(stage, dict)
                ),
                "teacher_scope_title": str(teacher_scope.get("courseware_title") or ""),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/paths/history/item/{path_id}")
def get_path_history_item(
    path_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return one stored learning path (full stage/task payload)."""

    row = db.get(LearningPath, path_id)
    if row is None:
        raise HTTPException(status_code=404, detail="学习路径不存在")
    require_self_or_admin(row.user_id, current_user)
    return row.path_data_json or {}


@router.get("/paths/{user_id}", response_model=LearningPathResponse)
def get_latest_learning_path(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LearningPathResponse:
    """Return the latest active learning path for one learner."""
    require_self_or_admin(user_id, current_user)

    service = LearningPathService(db)
    payload = service.get_latest_path(user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    return LearningPathResponse(**payload)


@router.post("/paths/adjust", response_model=LearningPathResponse)
def adjust_learning_path(
    payload: LearningPathAdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LearningPathResponse:
    """Adjust one task state in the learner's active path.

    Completing a task whose prerequisites are unfinished is refused with 409 and
    the blocking task ids, so the client can explain why instead of silently
    allowing the learner to jump ahead.
    """

    require_self_or_admin(payload.user_id, current_user)
    service = LearningPathService(db)
    try:
        updated = service.adjust_path(payload)
    except LearningPathRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LearningPathPrerequisiteError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": exc.error_code,
                "message": str(exc),
                "blocked_task_ids": exc.blocked_task_ids,
            },
        ) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Learning path task not found")
    return LearningPathResponse(**updated)


@router.get("/knowledge-base")
def list_knowledge_base(subject: str | None = None) -> dict[str, object]:
    """Return knowledge articles through the knowledge-base agent."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=0,
            intent="knowledge base catalog",
            payload={
                "execute": True,
                "force_agents": ["knowledge_base_agent"],
                "operation": "list",
                "subject": subject,
            },
        )
    )
    output = result.get("outputs", {}).get("knowledge_base_agent", {})
    if output.get("status") == "failed":
        raise HTTPException(status_code=503, detail=str(output.get("error") or "Knowledge-base agent failed"))
    return {
        "subjects": output.get("subjects", []),
        "items": output.get("items", []),
    }


@router.get("/knowledge-base/subjects")
def list_knowledge_base_subjects() -> dict[str, object]:
    """List all corpus subjects for learning-resource generation."""

    subjects = list_knowledge_subject_catalog()
    return {"total": len(subjects), "subjects": subjects}


@router.get("/knowledge-base/catalog/subjects")
def list_catalog_subjects(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    """List REAL subjects from the database catalog (for the student KB page).

    The frontend must render these instead of a hardcoded subject card list.
    """
    from common.models.learning import KnowledgePoint, SystemSubject
    subjects = db.query(SystemSubject).order_by(SystemSubject.id).all()
    items = []
    for subject in subjects:
        point_count = db.query(KnowledgePoint).filter_by(subject_id=subject.id).count()
        items.append({
            "id": subject.id,
            "name": subject.name,
            "code": subject.code or "",
            "description": subject.description or "",
            "status": subject.construction_status,
            "point_count": point_count,
        })
    return {"total": len(items), "items": items}


@router.get("/knowledge-base/search")
def search_knowledge_base(
    q: str = Query(default="", min_length=0),
    top_k: int = Query(default=6, ge=1, le=20),
    subject: str | None = None,
    course: str | None = None,
    chapter: str | None = None,
    difficulty: str | None = None,
    university: str | None = None,
    source: str | None = None,
    source_site: str | None = None,
    language: str | None = None,
    license: str | None = None,
    retrieval_mode: Literal["hybrid", "lexical", "vector"] = "hybrid",
) -> dict[str, object]:
    """Search knowledge articles through the knowledge-base agent."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=0,
            intent="knowledge base search",
            payload={
                "execute": True,
                "force_agents": ["knowledge_base_agent"],
                "operation": "search",
                "query": q,
                "top_k": top_k,
                "subject": subject,
                "course": course,
                "chapter": chapter,
                "difficulty": difficulty,
                "university": university,
                "source": source,
                "source_site": source_site,
                "language": language,
                "license": license,
                "retrieval_mode": retrieval_mode,
            },
        )
    )
    output = result.get("outputs", {}).get("knowledge_base_agent", {})
    if output.get("status") == "failed":
        raise HTTPException(status_code=503, detail=str(output.get("error") or "Knowledge-base agent failed"))
    return {
        "query": output.get("query", q),
        "items": output.get("items", []),
    }


@router.get("/knowledge-base/status")
def get_knowledge_base_status(
    _user: User = Depends(require_role("teacher", "admin")),
) -> dict[str, object]:
    """Return live corpus and Chroma statistics to authorized operators."""

    return knowledge_base_status()


@router.get("/knowledge-base/sources")
def get_knowledge_base_sources(
    _user: User = Depends(require_role("teacher", "admin")),
) -> dict[str, object]:
    """List allow-listed sources and their crawl state."""

    items = list_knowledge_sources()
    return {"total": len(items), "items": items}


@router.post("/knowledge-base/reindex")
def reindex_knowledge_base_route(
    payload: KnowledgeBaseReindexRequest,
    _user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Incrementally rebuild the vector index; admin-only."""

    try:
        return reindex_knowledge_base(subject=payload.subject, force=payload.force)
    except RuntimeError as exc:
        status_code = 409 if "already running" in str(exc) else 500
        raise HTTPException(status_code=status_code, detail=str(exc)[-1000:]) from exc


@router.post("/knowledge-base/sources/crawl")
def crawl_knowledge_base_sources_route(
    payload: KnowledgeBaseCrawlRequest,
    _user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Crawl a bounded selection from the source allow-list; admin-only."""

    try:
        return crawl_knowledge_sources(
            subjects=payload.subjects,
            topics=payload.topics,
            skip_existing=payload.skip_existing,
            reindex=payload.reindex,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        status_code = 409 if "already running" in str(exc) else 500
        raise HTTPException(status_code=status_code, detail=str(exc)[-1000:]) from exc


@router.get("/knowledge-base/{article_id}")
def get_knowledge_article(article_id: str) -> dict[str, object]:
    """Return one knowledge article through the knowledge-base agent."""

    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=0,
            intent="knowledge base article",
            payload={
                "execute": True,
                "force_agents": ["knowledge_base_agent"],
                "operation": "article",
                "article_id": article_id,
            },
        )
    )
    output = result.get("outputs", {}).get("knowledge_base_agent", {})
    if output.get("status") == "completed" and isinstance(output.get("article"), dict):
        return output["article"]
    raise HTTPException(status_code=404, detail="Knowledge article not found")


@router.post("/exercises/generate", response_model=ExerciseGenerationResponse)
def generate_exercises(
    payload: ExerciseGenerationRequest,
    current_user: User = Depends(get_current_user),
) -> ExerciseGenerationResponse:
    """Generate a structured exercise set through the multi-agent workflow."""
    require_self_or_admin(payload.user_id, current_user)

    settings = get_settings()
    set_trace_context(
        user_id=payload.user_id,
        task_type="exercise_generation",
        deadline_seconds=settings.exercise_deadline_seconds,
        retry_budget=settings.max_total_retries,
    )
    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=payload.user_id,
            intent="exercise practice generation",
            knowledge_point=payload.knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "only_exercises": True,
                "force_agents": ["learner_profiling_agent", "exercise_generation_agent"],
            },
        )
    )
    output = result.get("outputs", {}).get("exercise_generation_agent", {})
    exercise_set = output.get("exercise_set")
    if not isinstance(exercise_set, dict):
        raise HTTPException(status_code=503, detail="Exercise generation agent did not return exercises")
    return ExerciseGenerationResponse(**exercise_set)
