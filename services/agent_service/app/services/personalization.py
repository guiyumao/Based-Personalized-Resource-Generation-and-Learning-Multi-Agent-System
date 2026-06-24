"""Utilities for building real learner personalization context from the database."""

from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from common.models.learning import AnswerRecord, Exercise, UserProfile


@dataclass
class LearnerPersonalizationSnapshot:
    """Normalized learner snapshot used by generation services."""

    learner_profile: dict[str, Any]
    mastery_score: int
    recent_mistakes: list[dict[str, Any]]
    answered_count: int
    correct_rate: int


class PersonalizationService:
    """Load and merge real learner performance data for personalized generation."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def build_snapshot(self, user_id: int, knowledge_point: str, fallback_profile: dict[str, Any]) -> LearnerPersonalizationSnapshot:
        """Return a real personalization snapshot for one learner and knowledge point."""

        profile = self.db.get(UserProfile, user_id)
        mastery_json = profile.mastery_json if profile and isinstance(profile.mastery_json, dict) else {}
        learning_style = profile.learning_style if profile and profile.learning_style else fallback_profile.get("learning_style", "")
        cognitive_abilities = profile.cognitive_abilities if profile and isinstance(profile.cognitive_abilities, dict) else {}
        habits = profile.habits if profile and isinstance(profile.habits, dict) else {}
        profile_dimensions = habits.get("profile_dimensions") if isinstance(habits.get("profile_dimensions"), dict) else {}
        collaboration_context = (
            habits.get("agent_collaboration_context")
            if isinstance(habits.get("agent_collaboration_context"), dict)
            else {}
        )
        profile_analysis = profile.profile_analysis if profile and isinstance(profile.profile_analysis, dict) else {}
        profile_analysis_summaries = (
            profile_analysis.get("summaries")
            if isinstance(profile_analysis.get("summaries"), dict)
            else {}
        )

        records = self._load_records(user_id, knowledge_point)
        correct_count = sum(1 for item in records if item["is_correct"])
        answered_count = len(records)
        correct_rate = round((correct_count / answered_count) * 100) if answered_count else 0

        explicit_mastery = self._lookup_mastery(mastery_json, knowledge_point)
        if explicit_mastery is None:
            explicit_mastery = self._estimate_mastery_from_records(records)

        recent_mistakes = [item for item in records if not item["is_correct"]][-5:]
        weakest_types = self._count_labels(item["question_type"] for item in recent_mistakes)

        learner_profile = {
            **fallback_profile,
            "learning_style": learning_style,
            "profile_dimensions": profile_dimensions,
            "profile_analysis": profile_analysis,
            "profile_analysis_summaries": profile_analysis_summaries,
            "agent_collaboration_context": collaboration_context,
            "agent_handoff": collaboration_context.get("agent_handoff", {}) if isinstance(collaboration_context, dict) else {},
            "preferred_resource_modes": collaboration_context.get("preferred_resource_modes", []) if isinstance(collaboration_context, dict) else [],
            "known_background": collaboration_context.get("known_background", "") if isinstance(collaboration_context, dict) else "",
            "interest_direction": collaboration_context.get("interest_direction", "") if isinstance(collaboration_context, dict) else "",
            "goal_orientation": collaboration_context.get("goal_orientation", "") if isinstance(collaboration_context, dict) else "",
            "weakness_hint": collaboration_context.get("weakness_hint", "") if isinstance(collaboration_context, dict) else "",
            "learning_speed": collaboration_context.get("learning_speed", "") if isinstance(collaboration_context, dict) else "",
            "mastery": explicit_mastery,
            "cognitive_abilities": cognitive_abilities,
            "habits": habits,
            "answered_count": answered_count,
            "correct_rate": correct_rate,
            "recent_mistakes": recent_mistakes,
            "weak_question_types": weakest_types,
        }

        return LearnerPersonalizationSnapshot(
            learner_profile=learner_profile,
            mastery_score=int(explicit_mastery),
            recent_mistakes=recent_mistakes,
            answered_count=answered_count,
            correct_rate=correct_rate,
        )

    def _lookup_mastery(self, mastery_json: dict[str, Any], knowledge_point: str) -> int | None:
        if knowledge_point in mastery_json:
            value = mastery_json.get(knowledge_point)
            if isinstance(value, (int, float)):
                return max(0, min(100, int(round(value))))
            if isinstance(value, dict):
                score = value.get("score")
                if isinstance(score, (int, float)):
                    return max(0, min(100, int(round(score))))

        normalized = knowledge_point.strip().lower()
        for key, value in mastery_json.items():
            if normalized in str(key).strip().lower() or str(key).strip().lower() in normalized:
                if isinstance(value, (int, float)):
                    return max(0, min(100, int(round(value))))
                if isinstance(value, dict):
                    score = value.get("score")
                    if isinstance(score, (int, float)):
                        return max(0, min(100, int(round(score))))
        return None

    def _estimate_mastery_from_records(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        scores: list[int] = []
        for item in records:
            base = 85 if item["is_correct"] else 40
            if item["time_spent"] > 0:
                speed_bonus = max(-10, min(8, 20 - item["time_spent"]))
            else:
                speed_bonus = 0
            difficulty_bonus = {"foundation": 0, "intermediate": 4, "advanced": 8}.get(item["difficulty"], 0)
            scores.append(max(0, min(100, base + speed_bonus + difficulty_bonus)))
        return int(round(mean(scores)))

    def _load_records(self, user_id: int, knowledge_point: str) -> list[dict[str, Any]]:
        query = (
            self.db.query(AnswerRecord, Exercise)
            .join(Exercise, Exercise.id == AnswerRecord.exercise_id)
            .filter(AnswerRecord.user_id == user_id)
            .order_by(AnswerRecord.id.asc())
        )
        records: list[dict[str, Any]] = []
        normalized = knowledge_point.strip().lower()
        for answer_record, exercise in query.all():
            exercise_payload = self._parse_exercise_payload(exercise.content)
            exercise_knowledge = str(exercise_payload.get("knowledge_point") or knowledge_point)
            if normalized not in exercise_knowledge.strip().lower() and exercise_knowledge.strip().lower() not in normalized:
                continue
            records.append(
                {
                    "exercise_id": exercise.id,
                    "knowledge_point": exercise_knowledge,
                    "question_type": str(exercise_payload.get("question_type") or exercise.type),
                    "difficulty": self._map_difficulty(exercise.difficulty),
                    "prompt": str(exercise_payload.get("prompt") or ""),
                    "correct_answer": exercise.answer,
                    "analysis": exercise.analysis,
                    "user_answer": answer_record.user_answer,
                    "is_correct": bool(answer_record.is_correct),
                    "time_spent": answer_record.time_spent,
                }
            )
        return records

    def _parse_exercise_payload(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _map_difficulty(self, difficulty: int) -> str:
        if difficulty <= 1:
            return "foundation"
        if difficulty == 2:
            return "intermediate"
        return "advanced"

    def _count_labels(self, values: Any) -> list[str]:
        counts: dict[str, int] = {}
        for value in values:
            label = str(value).strip()
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
        return [key for key, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
