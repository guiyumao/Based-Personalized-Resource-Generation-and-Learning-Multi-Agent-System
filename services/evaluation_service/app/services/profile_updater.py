"""Real learner profile updater driven by practice results."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from common.models.learning import UserProfile


class LearnerProfileUpdater:
    """Update learner mastery and behavior profile from real answer records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def update_after_practice(
        self,
        user_id: int,
        knowledge_point: str,
        is_correct: bool,
        time_spent: int,
        question_type: str,
    ) -> UserProfile:
        """Apply one incremental update to learner profile after a submission."""

        profile = self.db.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(
                user_id=user_id,
                mastery_json={},
                learning_style="VARK",
                cognitive_abilities={},
                habits={},
            )
            self.db.add(profile)
            self.db.flush()

        mastery_json = dict(profile.mastery_json or {})
        habits = dict(profile.habits or {})
        cognitive = dict(profile.cognitive_abilities or {})

        item = mastery_json.get(knowledge_point, {})
        if not isinstance(item, dict):
            item = {"score": int(item) if isinstance(item, (int, float)) else 62}

        previous_score = int(item.get("score", 62))
        attempt_count = int(item.get("attempt_count", 0)) + 1
        correct_count = int(item.get("correct_count", 0)) + (1 if is_correct else 0)

        speed_adjustment = 0
        if time_spent > 0:
            if time_spent <= 15:
                speed_adjustment = 3
            elif time_spent <= 35:
                speed_adjustment = 1
            elif time_spent >= 120:
                speed_adjustment = -3
            elif time_spent >= 60:
                speed_adjustment = -1

        correctness_adjustment = 6 if is_correct else -8
        type_bonus = 2 if question_type in {"short_answer", "programming"} and is_correct else 0
        new_score = max(0, min(100, previous_score + correctness_adjustment + speed_adjustment + type_bonus))

        item.update(
            {
                "score": new_score,
                "attempt_count": attempt_count,
                "correct_count": correct_count,
                "accuracy": round((correct_count / attempt_count) * 100),
                "last_is_correct": is_correct,
                "last_time_spent": time_spent,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        mastery_json[knowledge_point] = item

        recent_hours = habits.get("study_hours", {})
        hour_key = str(datetime.now().hour)
        if not isinstance(recent_hours, dict):
            recent_hours = {}
        recent_hours[hour_key] = int(recent_hours.get(hour_key, 0)) + 1
        habits["study_hours"] = recent_hours
        habits["average_time_spent"] = self._rolling_average(int(habits.get("average_time_spent", 0)), time_spent, attempt_count)

        speed_metric = cognitive.get("response_speed", 60)
        logic_metric = cognitive.get("logic_accuracy", 60)
        speed_metric = max(0, min(100, int(speed_metric) + (2 if time_spent and time_spent <= 20 else -1 if time_spent >= 90 else 0)))
        logic_metric = max(0, min(100, int(logic_metric) + (3 if is_correct and question_type in {"short_answer", "programming"} else 1 if is_correct else -2)))
        cognitive["response_speed"] = speed_metric
        cognitive["logic_accuracy"] = logic_metric

        profile.mastery_json = mastery_json
        profile.habits = habits
        profile.cognitive_abilities = cognitive
        profile.updated_at = datetime.utcnow()
        return profile

    def _rolling_average(self, current_value: int, new_value: int, attempt_count: int) -> int:
        if attempt_count <= 1:
            return new_value
        return round(((current_value * (attempt_count - 1)) + new_value) / attempt_count)
