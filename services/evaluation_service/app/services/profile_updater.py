"""Mastery and weakness update helpers for the evaluation service."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from common.models.learning import UserProfile

ALPHA = 0.2
DEFAULT_INITIAL_MASTERY = 50.0
DIFFICULTY_WEIGHTS = {
    "basic": 0.8,
    "intermediate": 1.0,
    "advanced": 1.2,
}


@dataclass(slots=True)
class KnowledgePointUpdate:
    """One updated knowledge-point snapshot."""

    knowledge_point_id: str
    mastery_score: float
    recent_accuracy: float
    consecutive_incorrect: int
    weak: bool
    error_pattern: str


class LearnerProfileUpdater:
    """Apply evaluation outcomes to the persisted learner profile."""

    def update_profile(
        self,
        profile: UserProfile,
        *,
        knowledge_point_ids: list[str],
        is_correct: bool,
        time_spent: float,
        max_time: float,
        difficulty: str,
        exercise_id: str,
        answer_record_id: int,
        score: float,
        ratio: float,
        error_pattern: str,
        chapter_id: str | None,
        answered_at: datetime,
    ) -> list[KnowledgePointUpdate]:
        """Update mastery history and weak-point tags from one real answer."""

        mastery_json = deepcopy(profile.mastery_json or {})
        updates: list[KnowledgePointUpdate] = []

        for knowledge_point_id in knowledge_point_ids:
            record = mastery_json.get(knowledge_point_id, {})
            if not isinstance(record, dict):
                record = {}

            history = record.get("history", [])
            if not isinstance(history, list):
                history = []

            previous_score = float(record.get("score", DEFAULT_INITIAL_MASTERY))
            difficulty_weight = DIFFICULTY_WEIGHTS[difficulty]
            time_factor = max(0.0, 1 - (time_spent / max(max_time, 1.0)))
            delta = (1.0 if is_correct else -0.5) * time_factor * difficulty_weight
            new_score = max(0.0, min(100.0, previous_score + (ALPHA * delta)))

            history_entry = {
                "answer_record_id": answer_record_id,
                "exercise_id": exercise_id,
                "is_correct": is_correct,
                "time_spent": round(time_spent, 3),
                "max_time": round(max_time, 3),
                "difficulty": difficulty,
                "score": round(score, 3),
                "ratio": round(ratio, 4),
                "error_pattern": error_pattern,
                "chapter_id": chapter_id,
                "answered_at": answered_at.isoformat(),
            }
            history.append(history_entry)

            recent_ten = history[-10:]
            recent_accuracy = round(
                (sum(1 for item in recent_ten if item.get("is_correct")) / len(recent_ten)) * 100,
                2,
            )
            consecutive_incorrect = self._count_recent_incorrect(history)
            weak = consecutive_incorrect >= 3 or (len(recent_ten) >= 10 and recent_accuracy < 60)
            error_tags = self._build_error_tags(history)
            dominant_error = max(error_tags, key=error_tags.get) if error_tags else error_pattern

            record.update(
                {
                    "score": round(new_score, 4),
                    "recent_accuracy": recent_accuracy,
                    "consecutive_incorrect": consecutive_incorrect,
                    "weak": weak,
                    "history": history,
                    "attempt_count": len(history),
                    "correct_count": sum(1 for item in history if item.get("is_correct")),
                    "last_error_pattern": error_pattern,
                    "error_tags": error_tags,
                    "updated_at": answered_at.isoformat(),
                }
            )
            mastery_json[knowledge_point_id] = record
            updates.append(
                KnowledgePointUpdate(
                    knowledge_point_id=knowledge_point_id,
                    mastery_score=round(new_score, 4),
                    recent_accuracy=recent_accuracy,
                    consecutive_incorrect=consecutive_incorrect,
                    weak=weak,
                    error_pattern=dominant_error,
                )
            )

        profile.mastery_json = mastery_json
        profile.updated_at = answered_at
        return updates

    def _count_recent_incorrect(self, history: list[dict[str, Any]]) -> int:
        count = 0
        for item in reversed(history):
            if item.get("is_correct"):
                break
            count += 1
        return count

    def _build_error_tags(self, history: list[dict[str, Any]]) -> dict[str, int]:
        tags: dict[str, int] = {}
        for item in history:
            label = str(item.get("error_pattern") or "unknown")
            tags[label] = tags.get(label, 0) + 1
        return tags
