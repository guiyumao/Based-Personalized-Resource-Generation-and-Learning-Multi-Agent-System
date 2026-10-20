"""Private notes and spaced review cards for the authenticated learner."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.config import get_settings
from common.dependencies import get_current_user
from common.models.learning import CardReviewEvent, Resource, ReviewCard, StudyNote, User
from common.learning_context import validate_context
from services.agent_service.app.services.llm_factory import LLMFactory

router = APIRouter()


class NoteWrite(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=20000)
    source_resource_id: int | None = Field(default=None, gt=0)
    learning_context_id: str | None = Field(default=None, max_length=36)
    source_locator: str | None = Field(default=None, max_length=300)


class NoteRead(NoteWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
    source_resource_version: str | None = None


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


class NotePage(BaseModel):
    total: int
    items: list[NoteRead]


class CardPage(BaseModel):
    total: int
    due_count: int
    items: list[CardRead]


class ReviewRequest(BaseModel):
    grade: int = Field(ge=0, le=5)


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
    if resource is None or (
        resource.generated_for_user_id not in (None, user_id)
        and resource.publish_status != "published"
    ):
        raise HTTPException(status_code=404, detail="Resource not found")


@router.get("/notes", response_model=NotePage)
def list_notes(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotePage:
    query = db.query(StudyNote).filter(StudyNote.user_id == user.id)
    return NotePage(total=query.count(), items=query.order_by(StudyNote.updated_at.desc(), StudyNote.id.desc()).offset((page - 1) * size).limit(size).all())


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
    db.commit()
    db.refresh(note)
    return note


@router.put("/notes/{note_id}", response_model=NoteRead)
def update_note(note_id: int, payload: NoteWrite, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StudyNote:
    note = _owned_note(db, note_id, user.id)
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
    note.source_locator = payload.source_locator
    note.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    note = _owned_note(db, note_id, user.id)
    db.query(ReviewCard).filter(ReviewCard.user_id == user.id, ReviewCard.source_note_id == note.id).update({"source_note_id": None})
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
    return CardPage(total=query.count(), due_count=due_count, items=query.order_by(ReviewCard.due_at, ReviewCard.id).offset((page - 1) * size).limit(size).all())


@router.post("/cards", response_model=CardRead, status_code=201)
def create_card(payload: CardWrite, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ReviewCard:
    if payload.source_note_id is not None:
        _owned_note(db, payload.source_note_id, user.id)
    front, back = payload.front.strip(), payload.back.strip()
    if not front or not back:
        raise HTTPException(status_code=422, detail="Front and back cannot be blank")
    card = ReviewCard(user_id=user.id, front=front, back=back, source_note_id=payload.source_note_id)
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.post("/cards/{card_id}/review", response_model=CardRead)
def review_card(card_id: int, payload: ReviewRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ReviewCard:
    card = _owned_card(db, card_id, user.id)
    now = datetime.now(UTC).replace(tzinfo=None)
    if card.due_at > now:
        raise HTTPException(status_code=409, detail="Card is not due yet")
    grade = payload.grade
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
    db.add(CardReviewEvent(
        user_id=user.id, card_id=card.id, grade=grade,
        interval_days=card.interval_days, next_due_at=card.due_at, reviewed_at=now,
    ))
    db.commit()
    db.refresh(card)
    return card


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
    db.query(CardReviewEvent).filter(CardReviewEvent.card_id == card.id).delete()
    db.delete(card)
    db.commit()
