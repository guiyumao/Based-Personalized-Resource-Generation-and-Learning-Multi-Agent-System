"""Reuse existing subject/point models for reviewed AI construction."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import require_role
from common.models.learning import KnowledgeBuildTask, KnowledgePoint, SystemSubject, User
from services.agent_service.app.services.knowledge_construction import OutlinePoint, SubjectOutline, confirm_outline, find_subject, normalize_name
from services.agent_service.app.services.knowledge_tasks import create_task, serialize_task, KnowledgeTaskConflict

router = APIRouter(prefix="/knowledge-base/construction", tags=["knowledge-construction"])


class SubjectPlanRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    stage: str = Field(default="本科", max_length=100)
    requirements: str = Field(default="", max_length=4000)
    reference_material: str = Field(default="", max_length=16000)


class PointBuildRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=60)
    point_ids: list[int] = Field(min_length=1, max_length=10)
    mode: Literal["CREATE_POINT", "COMPLETE_POINT", "REVISE_POINT"] = "COMPLETE_POINT"
    focus: str = Field(default="", max_length=300)


class ManualSubjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    description: str = Field(default="", max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=10)


class ManualPointRequest(OutlinePoint):
    chapter: str = Field(default="", max_length=160)


@router.post("/subjects", status_code=201)
def manual_subject(payload: ManualSubjectRequest, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    existing = find_subject(db, payload.name) or find_subject(db, payload.code)
    if existing:
        if existing.code and existing.code != payload.code:
            raise HTTPException(409, "Subject already has a different canonical code")
        existing.code = payload.code
        existing.aliases_json = list(dict.fromkeys([*(existing.aliases_json or []), *payload.aliases]))
    else:
        existing = SystemSubject(name=payload.name.strip(), code=payload.code, description=payload.description, aliases_json=payload.aliases)
        db.add(existing)
    db.commit(); db.refresh(existing)
    return {"id": existing.id, "name": existing.name, "code": existing.code, "status": existing.construction_status}


@router.post("/subjects/{subject_id}/points", status_code=201)
def manual_point(subject_id: int, payload: ManualPointRequest, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    if db.get(SystemSubject, subject_id) is None:
        raise HTTPException(404, "Subject not found")
    wanted = normalize_name(payload.name)
    existing = next((item for item in db.query(KnowledgePoint).filter_by(subject_id=subject_id).all()
                     if wanted in {normalize_name(item.name), *(normalize_name(alias) for alias in item.aliases_json or [])}), None)
    if existing is None:
        existing = KnowledgePoint(subject_id=subject_id, name=payload.name.strip(), chapter=payload.chapter,
                                   aliases_json=payload.aliases, prerequisites_json=payload.prerequisites,
                                   objectives_json=payload.objectives)
        db.add(existing); db.commit(); db.refresh(existing)
    return {"id": existing.id, "name": existing.name, "chapter": existing.chapter, "status": existing.construction_status}


@router.post("/subject-plans", status_code=202)
def plan_subject(payload: SubjectPlanRequest, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    existing = find_subject(db, payload.name)
    if existing and existing.outline_json:
        raise HTTPException(409, "Subject already has a confirmed outline")
    try:
        task = create_task(db, actor_user_id=user.id, client_request_id=payload.client_request_id,
                           operation_type="AI_SUBJECT_PLAN", requirements=payload.model_dump(exclude={"client_request_id"}))
        return serialize_task(task)
    except KnowledgeTaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/subject-plans/{task_id}/confirm")
def confirm_subject(task_id: int, payload: SubjectOutline, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    task = db.get(KnowledgeBuildTask, task_id)
    if task is None:
        raise HTTPException(404, "Outline task not found")
    try:
        subject = confirm_outline(db, task, payload)
        return {"subject_id": subject.id, "code": subject.code, "status": subject.construction_status}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.get("/subjects")
def subjects(db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    return {"items": [{"id": item.id, "name": item.name, "code": item.code, "status": item.construction_status,
                       "outline": item.outline_json} for item in db.query(SystemSubject).all()]}


@router.get("/subjects/{subject_id}/points")
def points(subject_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))) -> dict:
    return {"items": [{"id": point.id, "name": point.name, "chapter": point.chapter,
                       "status": point.construction_status, "aliases": point.aliases_json}
                      for point in db.query(KnowledgePoint).filter_by(subject_id=subject_id).all()]}


@router.post("/points/build", status_code=202)
def build_points(payload: PointBuildRequest, db: Session = Depends(get_db), user: User = Depends(require_role("admin"))) -> dict:
    ids = list(dict.fromkeys(payload.point_ids))
    if db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(ids)).count() != len(ids):
        raise HTTPException(422, "Unknown knowledge point")
    try:
        tasks = [create_task(db, actor_user_id=user.id, client_request_id=f"{payload.client_request_id}-{point_id}",
                             operation_type="BUILD_POINT", requirements={"point_id": point_id, "mode": payload.mode, "focus": payload.focus})
                 for point_id in ids]
        return {"items": [serialize_task(task) for task in tasks], "search_limit": len(ids), "fetch_limit": 2 * len(ids)}
    except KnowledgeTaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc
