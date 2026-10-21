"""Private notes and spaced review cards for the authenticated learner."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import get_db
from common.dependencies import get_current_user
from common.learning_context import validate_context
from common.models.learning import (
    CardReviewEvent,
    KnowledgePoint,
    LearningContext,
    LearningPath,
    Resource,
    ReviewCard,
    StudyNote,
    SystemSubject,
    User,
)
from common.models.study import CardKnowledgeBinding, CardReviewReceipt, NoteRevision
from common.resource_version import resource_version
from common.study_evidence import (
    NOTE_FIELDS,
    bind_card,
    card_payload,
    note_payload,
    note_version,
    record_card_evidence,
    refresh_review_profile,
    snapshot_note,
)
from services.agent_service.app.services.llm_factory import LLMFactory

router = APIRouter()


class NoteWrite(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=20000)
    source_resource_id: int | None = Field(default=None, gt=0)
    learning_context_id: str | None = Field(default=None, max_length=36)
    source_locator: str | None = Field(default=None, max_length=300)
    expected_version: str | None = Field(default=None, min_length=64, max_length=64)


class NoteRead(NoteWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
    source_resource_version: str | None = None
    version: str
    classification: dict = Field(default_factory=dict)


class CardWrite(BaseModel):
    front: str = Field(min_length=1, max_length=500)
    back: str = Field(min_length=1, max_length=10000)
    source_note_id: int | None = Field(default=None, gt=0)


class CardRead(CardWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int
    due_at: datetime
    interval_days: int
    ease_factor: float
    repetitions: int
    review_count: int
    created_at: datetime
    knowledge_point_id: int | None = None
    knowledge_point: str = ""
    source_resource_version: str | None = None
    review_evidence: dict | None = None


class NotePage(BaseModel):
    total: int
    items: list[NoteRead]


class CardPage(BaseModel):
    total: int
    due_count: int
    items: list[CardRead]


class ReviewRequest(BaseModel):
    grade: int = Field(ge=0, le=5)
    client_request_id: str | None = Field(None,min_length=8,max_length=80)


class ReviewEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    grade: int
    interval_days: int
    next_due_at: datetime
    reviewed_at: datetime


class CardSuggestion(BaseModel):
    front: str = Field(min_length=1, max_length=500)
    back: str = Field(min_length=1, max_length=10000)


class NoteOrganization(BaseModel):
    organized_note: str = Field(min_length=1, max_length=20000)
    cards: list[CardSuggestion] = Field(min_length=1, max_length=5)
    input_truncated: bool = False


def _owned_note(db: Session, note_id: int, user_id: int) -> StudyNote:
    note = db.query(StudyNote).filter(StudyNote.id == note_id, StudyNote.user_id == user_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def _owned_card(db: Session, card_id: int, user_id: int) -> ReviewCard:
    card = db.query(ReviewCard).filter(ReviewCard.id == card_id, ReviewCard.user_id == user_id).first()
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


def _check_resource(db: Session, resource_id: int | None, user_id: int) -> None:
    if resource_id is None:
        return
    resource = db.get(Resource, resource_id)
    if resource is None or resource.publish_status == "archived" or not (
        resource.generated_for_user_id == user_id or
        (resource.generated_for_user_id is None and resource.publish_status == "published" and resource.audit_status == "passed")
    ):
        raise HTTPException(status_code=404, detail="Resource not found")


@router.get("/notes", response_model=NotePage)
def list_notes(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    q: str = Query(default="",max_length=160),
    subject: str = Query(default="",max_length=200),
    knowledge_point_id: int | None = Query(default=None,gt=0),
    resource_id: int | None = Query(default=None,gt=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotePage:
    query = db.query(StudyNote).filter(StudyNote.user_id == user.id)
    if q.strip():
        query = query.filter(StudyNote.title.contains(q.strip(),autoescape=True) | StudyNote.body.contains(q.strip(),autoescape=True))
    if resource_id:
        query = query.filter(StudyNote.source_resource_id == resource_id)
    if subject.strip() or knowledge_point_id:
        query = query.outerjoin(LearningContext,StudyNote.learning_context_id==LearningContext.id).outerjoin(
            Resource,StudyNote.source_resource_id==Resource.id).outerjoin(KnowledgePoint,
            KnowledgePoint.id==func.coalesce(LearningContext.knowledge_point_id,Resource.knowledge_point_id)).outerjoin(
            SystemSubject,SystemSubject.id==KnowledgePoint.subject_id).outerjoin(LearningPath,LearningPath.id==LearningContext.plan_id)
        if knowledge_point_id:
            query = query.filter(KnowledgePoint.id==knowledge_point_id)
        if subject.strip():
            query = query.filter(func.lower(func.coalesce(SystemSubject.name,LearningPath.path_data_json['subject'].as_string()))==subject.strip().lower())
    return NotePage(total=query.count(), items=[note_payload(db,note) for note in query.order_by(StudyNote.updated_at.desc(), StudyNote.id.desc()).offset((page - 1) * size).limit(size).all()])


@router.post("/notes", response_model=NoteRead, status_code=201)
def create_note(payload: NoteWrite, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StudyNote:
    context = validate_context(db, user.id, payload.learning_context_id)[0] if payload.learning_context_id else None
    if context and payload.source_resource_id not in (None, context.resource_id):
        raise HTTPException(409, "Note source differs from learning context")
    _check_resource(db, payload.source_resource_id, user.id)
    note = StudyNote(user_id=user.id, title=payload.title.strip(), body=payload.body.strip(), source_resource_id=payload.source_resource_id)
    if context:
        note.learning_context_id = context.id
        note.source_resource_id = context.resource_id
        note.source_resource_version = context.resource_version
    note.source_locator = payload.source_locator
    if not note.title or not note.body:
        raise HTTPException(status_code=422, detail="Title and body cannot be blank")
    db.add(note)
    db.flush()
    if note.source_resource_id and not note.source_resource_version:
        note.source_resource_version = resource_version(db.get(Resource,note.source_resource_id))
    snapshot_note(db,note)
    db.commit()
    db.refresh(note)
    return note_payload(db,note)


@router.put("/notes/{note_id}", response_model=NoteRead)
def update_note(note_id: int, payload: NoteWrite, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StudyNote:
    note = _owned_note(db, note_id, user.id)
    if payload.expected_version and payload.expected_version != note_version(note):
        raise HTTPException(409,"Note was edited in another tab; reload before saving")
    original = {key:getattr(note,key) for key in NOTE_FIELDS}
    original_updated_at = note.updated_at
    snapshot_note(db,note)
    note = SimpleNamespace(**original)
    if note.learning_context_id:
        if payload.learning_context_id not in (None, note.learning_context_id) or payload.source_resource_id not in (None, note.source_resource_id):
            raise HTTPException(409, "A sourced note cannot be moved to another learning context")
    elif payload.learning_context_id:
        context = validate_context(db, user.id, payload.learning_context_id)[0]
        if payload.source_resource_id not in (None, context.resource_id):
            raise HTTPException(409, "Note source differs from learning context")
        note.learning_context_id = context.id
        note.source_resource_id = context.resource_id
        note.source_resource_version = context.resource_version
    _check_resource(db, payload.source_resource_id, user.id)
    title, body = payload.title.strip(), payload.body.strip()
    if not title or not body:
        raise HTTPException(status_code=422, detail="Title and body cannot be blank")
    note.title, note.body = title, body
    if not note.learning_context_id:
        note.source_resource_id = payload.source_resource_id
        source = db.get(Resource,note.source_resource_id) if note.source_resource_id else None
        if original['source_resource_id'] != note.source_resource_id or not note.source_resource_version:
            note.source_resource_version = resource_version(source) if source else None
    if 'source_locator' in payload.model_fields_set:
        note.source_locator = payload.source_locator
    # Execute a compare-and-set against the original row, not a blind ORM save.
    values = {key:getattr(note,key) for key in NOTE_FIELDS}
    values['updated_at'] = datetime.now(UTC).replace(tzinfo=None)
    predicates = [StudyNote.id==note_id,StudyNote.user_id==user.id,StudyNote.updated_at==original_updated_at]
    predicates.extend(getattr(StudyNote,key)==value for key,value in original.items())
    with db.no_autoflush:
        changed = db.execute(update(StudyNote).where(*predicates).values(**values))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409,"Note changed during save")
    note = _owned_note(db,note_id,user.id)
    snapshot_note(db,note)
    db.commit()
    db.refresh(note)
    return note_payload(db,note)


@router.get('/notes/{note_id}/history')
def note_history(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_note(db,note_id,user.id)
    return {'items':[{'id':row.id,'version':row.version,'snapshot':row.snapshot_json,'created_at':row.created_at}
        for row in db.query(NoteRevision).filter_by(note_id=note_id,user_id=user.id).order_by(NoteRevision.id.desc()).limit(100).all()],
        'coverage':'Recorded saves only; historical edits before deployment are not reconstructed'}


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    note = _owned_note(db, note_id, user.id)
    db.query(ReviewCard).filter(ReviewCard.user_id == user.id, ReviewCard.source_note_id == note.id).update({"source_note_id": None})
    db.query(NoteRevision).filter_by(note_id=note.id,user_id=user.id).delete()
    db.delete(note)
    db.commit()


@router.post("/notes/{note_id}/organize", response_model=NoteOrganization)
def organize_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> NoteOrganization:
    """Suggest a cleaned note and cards; the learner chooses what to save."""

    note = _owned_note(db, note_id, user.id)
    source = note.body[:6000]
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = LLMFactory(get_settings()).build_for_task("summarize", temperature=0.2)
        result = model.invoke([
            SystemMessage(content=(
                "你是学习笔记整理助手。仅依据用户笔记整理层级清晰的中文内容，并给出1到5张问答闪卡。"
                "不得补造事实、引用或答案。只返回JSON对象："
                '{"organized_note":"整理后的笔记","cards":[{"front":"问题","back":"答案"}]}。'
                "将笔记中无法确定的内容标为待核实。"
            )),
            HumanMessage(content=f"标题：{note.title}\n原始笔记：\n{source}"),
        ])
        raw = str(result.content).strip()
        if raw.startswith("```"):
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        return NoteOrganization.model_validate({**parsed, "input_truncated": len(note.body) > len(source)})
    except (ImportError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="AI 笔记整理暂不可用，请稍后重试。") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="AI 笔记整理失败，请稍后重试。") from exc


@router.get("/cards", response_model=CardPage)
def list_cards(
    due_only: bool = False,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CardPage:
    now = datetime.now(UTC).replace(tzinfo=None)
    query = db.query(ReviewCard).filter(ReviewCard.user_id == user.id)
    due_count = query.filter(ReviewCard.due_at <= now).count()
    if due_only:
        query = query.filter(ReviewCard.due_at <= now)
    return CardPage(total=query.count(), due_count=due_count, items=[card_payload(db,card) for card in query.order_by(ReviewCard.due_at, ReviewCard.id).offset((page - 1) * size).limit(size).all()])


@router.post("/cards", response_model=CardRead, status_code=201)
def create_card(payload: CardWrite, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ReviewCard:
    source_note = _owned_note(db, payload.source_note_id, user.id) if payload.source_note_id else None
    front, back = payload.front.strip(), payload.back.strip()
    if not front or not back:
        raise HTTPException(status_code=422, detail="Front and back cannot be blank")
    card = ReviewCard(user_id=user.id, front=front, back=back, source_note_id=payload.source_note_id)
    db.add(card)
    db.flush()
    if source_note:
        bind_card(db,card,source_note)
    db.commit()
    db.refresh(card)
    return card_payload(db,card)


@router.post("/cards/{card_id}/review", response_model=CardRead)
def review_card(card_id: int, payload: ReviewRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ReviewCard:
    card = _owned_card(db, card_id, user.id)
    if payload.client_request_id:
        receipt = db.get(CardReviewReceipt,(payload.client_request_id,user.id))
        if receipt:
            if (receipt.user_id,receipt.card_id,receipt.grade)!=(user.id,card_id,payload.grade):
                raise HTTPException(409,'Review request ID already used')
            return card_payload(db,card)
    now = datetime.now(UTC).replace(tzinfo=None)
    if card.due_at > now:
        raise HTTPException(status_code=409, detail="Card is not due yet")
    grade = payload.grade
    original_count, original_due = card.review_count, card.due_at
    card.review_count += 1
    card.ease_factor = max(1.3, round(card.ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)), 2))
    if grade < 3:
        card.repetitions = 0
        card.interval_days = 0
        card.due_at = now + timedelta(minutes=10)
    else:
        card.repetitions += 1
        card.interval_days = 1 if card.repetitions == 1 else 3 if card.repetitions == 2 else max(4, round(card.interval_days * card.ease_factor))
        card.due_at = now + timedelta(days=card.interval_days)
    values = {key:getattr(card,key) for key in ('review_count','ease_factor','repetitions','interval_days','due_at')}
    db.expunge(card)
    with db.no_autoflush:
        changed = db.execute(update(ReviewCard).where(ReviewCard.id==card_id,ReviewCard.user_id==user.id,
            ReviewCard.review_count==original_count,ReviewCard.due_at==original_due).values(**values))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409,'Card was reviewed in another tab')
    card = _owned_card(db,card_id,user.id)
    event = CardReviewEvent(
        user_id=user.id, card_id=card.id, grade=grade,
        interval_days=card.interval_days, next_due_at=card.due_at, reviewed_at=now,
    )
    db.add(event)
    db.flush()
    if payload.client_request_id:
        db.add(CardReviewReceipt(request_id=payload.client_request_id,user_id=user.id,card_id=card.id,event_id=event.id,grade=grade))
    with db.no_autoflush:
        record_card_evidence(db,card,event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Review request already recorded; refresh before retry') from None
    db.refresh(card)
    return card_payload(db,card)


@router.get("/cards/{card_id}/reviews", response_model=list[ReviewEventRead])
def list_card_reviews(
    card_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CardReviewEvent]:
    _owned_card(db, card_id, user.id)
    return db.query(CardReviewEvent).filter(
        CardReviewEvent.user_id == user.id, CardReviewEvent.card_id == card_id
    ).order_by(CardReviewEvent.reviewed_at.desc(), CardReviewEvent.id.desc()).limit(50).all()


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    card = _owned_card(db, card_id, user.id)
    binding = db.get(CardKnowledgeBinding,card.id)
    point_id = binding.knowledge_point_id if binding else None
    db.query(CardReviewReceipt).filter_by(card_id=card.id,user_id=user.id).delete()
    db.query(CardKnowledgeBinding).filter_by(card_id=card.id,user_id=user.id).delete()
    db.query(CardReviewEvent).filter(CardReviewEvent.card_id == card.id).delete()
    db.delete(card)
    if point_id:
        refresh_review_profile(db,user.id,point_id)
    db.commit()
