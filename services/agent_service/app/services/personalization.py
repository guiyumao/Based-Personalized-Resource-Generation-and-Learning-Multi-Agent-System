"""Utilities for building real learner personalization context from the database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from common.learning_evidence import load_evidence, resolve_point, summarize
from common.models.learning import UserProfile
from services.agent_service.app.services.profile_mapping import build_zhishu_profile_view


@dataclass
class LearnerPersonalizationSnapshot:
    """Normalized learner snapshot used by generation services."""

    learner_profile: dict[str, Any]
    mastery_score: int | None
    recent_mistakes: list[dict[str, Any]]
    answered_count: int
    correct_rate: int | None


class PersonalizationService:
    """Load and merge real learner performance data for personalized generation."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def build_snapshot(self, user_id: int, knowledge_point: str, fallback_profile: dict[str, Any], *, point_id=None, subject="", chapter="") -> LearnerPersonalizationSnapshot:
        """Return a real personalization snapshot for one learner and knowledge point."""

        if fallback_profile.get("history_disabled"):
            return LearnerPersonalizationSnapshot({"history_disabled": True}, None, [], 0, None)
        profile = self.db.get(UserProfile, user_id)
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

        point = resolve_point(self.db, knowledge_point, point_id=point_id, subject=subject, chapter=chapter)
        records = load_evidence(self.db, user_id, point=point) if point else []
        evidence = summarize(records)
        answered_count = evidence["sample_size"]
        correct_rate = evidence["correct_rate"]
        explicit_mastery = evidence["mastery_score"]
        # Global inferred summaries are not evidence about the selected point.
        profile_analysis = {}
        profile_analysis_summaries = {}
        collaboration_context = {}
        records = list({item["exercise_id"]: item for item in records}.values())
        for item in records:
            item["difficulty_level"] = item["difficulty"]
            item["difficulty"] = self._map_difficulty(item["difficulty"])

        recent_mistakes = [item for item in records if not item["is_correct"]][-5:]
        weakest_types = self._count_labels(item["question_type"] for item in recent_mistakes)

        learner_profile = {
            **fallback_profile,
            "learning_style": learning_style,
            "profile_dimensions": profile_dimensions,
            "profile_fact_sources": habits.get("profile_fact_sources", {}) if isinstance(habits.get("profile_fact_sources"), dict) else {},
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
            "evidence": evidence,
            "evidence_scope": {"level": "knowledge_point", "knowledge_point_id": point.id if point else None, "subject_id": point.subject_id if point else None},
            "cognitive_abilities": cognitive_abilities,
            "habits": habits,
            "answered_count": answered_count,
            "correct_rate": correct_rate,
            "recent_mistakes": recent_mistakes,
            "weak_question_types": weakest_types,
        }
        learner_profile["zhishu_profile"] = build_zhishu_profile_view(
            learner_profile=learner_profile,
            mastery_score=explicit_mastery,
            answered_count=answered_count,
            correct_rate=correct_rate,
            recent_mistakes=recent_mistakes,
            records=records,
        )

        return LearnerPersonalizationSnapshot(
            learner_profile=learner_profile,
            mastery_score=explicit_mastery,
            recent_mistakes=recent_mistakes,
            answered_count=answered_count,
            correct_rate=correct_rate,
        )

    def _load_records(self, user_id: int, knowledge_point: str) -> list[dict[str, Any]]:
        point = resolve_point(self.db, knowledge_point)
        return load_evidence(self.db, user_id, point=point) if point else []

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
