"""Source-backed classification and private note/card evidence; never infer graded mastery."""
import hashlib
import json
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import case, func, update

from common.learning_context import validate_context
from common.models.learning import (
    CardReviewEvent,
    KnowledgePoint,
    LearningContext,
    LearningPath,
    Resource,
    SystemSubject,
    UserProfile,
)
from common.models.study import CardKnowledgeBinding, NoteRevision

NOTE_FIELDS = ("title", "body", "source_resource_id", "learning_context_id", "source_resource_version", "source_locator")


def note_version(note):
    return hashlib.sha256(json.dumps({key:getattr(note,key) for key in NOTE_FIELDS},ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def classify_note(db, note):
    context = db.get(LearningContext, note.learning_context_id) if note.learning_context_id else None
    resource = db.get(Resource, note.source_resource_id) if note.source_resource_id else None
    if context and context.user_id != note.user_id:
        context = None
    if resource and not (resource.generated_for_user_id == note.user_id or
                         (resource.generated_for_user_id is None and resource.publish_status == 'published' and resource.audit_status == 'passed')):
        resource = None
    point_id = context.knowledge_point_id if context else resource.knowledge_point_id if resource else None
    point = db.get(KnowledgePoint, point_id) if point_id else None
    subject = db.get(SystemSubject, point.subject_id) if point and point.subject_id else None
    plan = db.get(LearningPath, context.plan_id) if context else None
    return {"subject":subject.name if subject else str((plan.path_data_json or {}).get("subject", "")) if plan else "",
            "knowledge_point_id":point.id if point else None, "knowledge_point":point.name if point else ""}


def note_payload(db, note):
    return {column.name:getattr(note,column.name) for column in note.__table__.columns} | {"version":note_version(note),"classification":classify_note(db,note)}


def snapshot_note(db, note):
    latest = db.query(NoteRevision).filter_by(note_id=note.id,user_id=note.user_id).order_by(NoteRevision.id.desc()).first()
    version = note_version(note)
    if latest is None or latest.version != version:
        payload = {key:getattr(note,key) for key in NOTE_FIELDS}
        payload["classification"] = classify_note(db,note)
        db.add(NoteRevision(note_id=note.id,user_id=note.user_id,version=version,snapshot_json=payload))


def bind_card(db, card, note):
    classification = classify_note(db,note)
    if classification["knowledge_point_id"]:
        db.add(CardKnowledgeBinding(card_id=card.id,user_id=card.user_id,knowledge_point_id=classification["knowledge_point_id"],
            context_id=note.learning_context_id,resource_id=note.source_resource_id,resource_version=note.source_resource_version))


def card_payload(db, card):
    result = {column.name:getattr(card,column.name) for column in card.__table__.columns}
    binding = db.get(CardKnowledgeBinding,card.id)
    point = db.get(KnowledgePoint,binding.knowledge_point_id) if binding else None
    result.update(knowledge_point_id=point.id if point else None,knowledge_point=point.name if point else "",
                  source_resource_version=binding.resource_version if binding else None)
    profile = db.query(UserProfile).filter_by(user_id=card.user_id).first() if binding else None
    result['review_evidence'] = ((profile.mastery_json or {}).get('flashcard_review',{}).get(str(binding.knowledge_point_id))
                                 if profile and binding else None)
    return result


def refresh_review_profile(db,user_id,point_id):
    query = db.query(CardReviewEvent).join(CardKnowledgeBinding,CardKnowledgeBinding.card_id==CardReviewEvent.card_id).filter(
        CardReviewEvent.user_id==user_id,CardKnowledgeBinding.user_id==user_id,CardKnowledgeBinding.knowledge_point_id==point_id)
    count, remembered = query.with_entities(func.count(CardReviewEvent.id),func.sum(case((CardReviewEvent.grade>=3,1),else_=0))).one()
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    if profile is None:
        if not count:
            return
        profile = UserProfile(user_id=user_id,mastery_json={})
        db.add(profile)
    mastery = deepcopy(profile.mastery_json) if isinstance(profile.mastery_json,dict) else {}
    if not isinstance(mastery.get('flashcard_review'),dict):
        mastery['flashcard_review'] = {}
    reviews = mastery['flashcard_review']
    key = str(point_id)
    if count:
        latest = query.order_by(CardReviewEvent.id.desc()).first()
        reviews[key] = {'review_count':count,'remembered_count':remembered or 0,'recall_rate':(remembered or 0)/count,
                        'source':'self_reported_flashcard','knowledge_point_id':point_id,'latest_event_id':latest.id,'latest_grade':latest.grade}
    else:
        reviews.pop(key,None)
    profile.mastery_json = mastery
    profile.profile_analysis = None


def record_card_evidence(db, card, event):
    binding = db.get(CardKnowledgeBinding,card.id)
    if not binding or binding.user_id != card.user_id:
        return
    refresh_review_profile(db,card.user_id,binding.knowledge_point_id)
    if binding.context_id:
        try:
            context, plan, _, task, _, _ = validate_context(db,card.user_id,binding.context_id)
        except HTTPException:
            # The private card remains reviewable after a plan/resource changes.
            # Stale evidence never changes the new plan or another resource.
            return
        before = deepcopy(plan.path_data_json)
        after = deepcopy(before)
        for stage in after.get("stages",[]):
            if stage.get('stage_id') != context.module_id:
                continue
            for target in stage.get("tasks",[]):
                if target.get("task_id") == task.get("task_id"):
                    target.setdefault("learning_evidence",{}).setdefault("flashcard_reviews",{})[str(card.id)] = {
                        "event_id":event.id,"grade":event.grade,"review_count":card.review_count,
                        "source":"self_reported_flashcard","knowledge_point_id":binding.knowledge_point_id}
        changed = db.execute(update(LearningPath).where(LearningPath.id==plan.id,LearningPath.user_id==card.user_id,
            LearningPath.path_data_json==before).values(path_data_json=after).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise HTTPException(409,"Plan changed during flashcard review; refresh and retry")
