"""Targeted homework access shared by lists, uploads and notifications."""
from sqlalchemy import or_, select

from common.models.learning import Assignment
from common.models.teacher_support import ReinforcementDraft


def student_assignment_clause(student_id):
    targeted = select(ReinforcementDraft.assignment_id).where(ReinforcementDraft.assignment_id.is_not(None))
    own = select(ReinforcementDraft.assignment_id).where(ReinforcementDraft.student_user_id == student_id)
    return or_(Assignment.id.not_in(targeted), Assignment.id.in_(own))


def can_access_assignment(db, assignment_id, student_id):
    target = db.query(ReinforcementDraft.student_user_id).filter_by(assignment_id=assignment_id).first()
    return target is None or target[0] == student_id
