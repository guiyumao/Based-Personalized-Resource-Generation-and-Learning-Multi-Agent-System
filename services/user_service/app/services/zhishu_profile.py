"""Build the persisted user's evidence-based ZhiShu profile view."""

from __future__ import annotations

from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from common.models.learning import AnswerRecord, Exercise, UserProfile
from common.profile_scoring import normalize_answer_row, score_zhishu_profile


def build_user_zhishu_profile(db: Session, profile: UserProfile) -> dict[str, Any]:
    """Compute one profile snapshot directly from persisted learner facts."""

    rows = (
        db.query(AnswerRecord, Exercise)
        .join(Exercise, Exercise.id == AnswerRecord.exercise_id)
        .filter(AnswerRecord.user_id == profile.user_id)
        .order_by(AnswerRecord.id.asc())
        .all()
    )
    records = [normalize_answer_row(answer_record, exercise) for answer_record, exercise in rows]
    habits = profile.habits if isinstance(profile.habits, dict) else {}
    dimensions = habits.get("profile_dimensions")
    dimensions = dimensions if isinstance(dimensions, dict) else {}
    cognitive = profile.cognitive_abilities if isinstance(profile.cognitive_abilities, dict) else {}
    learner_profile = {
        "profile_dimensions": dimensions,
        "profile_fact_sources": habits.get("profile_fact_sources", {})
        if isinstance(habits.get("profile_fact_sources"), dict)
        else {},
        "goal_orientation": cognitive.get("goalOrientation") or dimensions.get("goalOrientation", ""),
    }
    return score_zhishu_profile(
        learner_profile=learner_profile,
        records=records,
        explicit_mastery=_mastery_average(profile.mastery_json),
    )


def _mastery_average(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    scores: list[float] = []
    for key, item in value.items():
        if str(key).startswith("_"):
            continue
        if isinstance(item, (int, float)):
            scores.append(float(item))
        elif isinstance(item, dict) and isinstance(item.get("score"), (int, float)):
            scores.append(float(item["score"]))
    return mean(scores) if scores else None
