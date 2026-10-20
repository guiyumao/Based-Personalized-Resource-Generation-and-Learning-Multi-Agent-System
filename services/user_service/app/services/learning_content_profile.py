"""Summarize a learner's persisted practice by the content actually studied."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from common.models.learning import (
    AnswerRecord,
    Exercise,
    KnowledgePoint,
    ResourceInteraction,
    UserProfile,
)


def build_learning_content_profile(db: Session, user_id: int, profile: UserProfile) -> dict[str, Any]:
    """Return bounded, user-scoped practice evidence; never infer preferences from it."""

    total_answers = db.query(AnswerRecord).filter(AnswerRecord.user_id == user_id).count()
    rows = (
        db.query(AnswerRecord, Exercise, KnowledgePoint)
        .join(Exercise, Exercise.id == AnswerRecord.exercise_id)
        .outerjoin(KnowledgePoint, KnowledgePoint.id == Exercise.knowledge_point_id)
        .filter(AnswerRecord.user_id == user_id)
        .order_by(AnswerRecord.id.desc())
        .limit(500)
        .all()
    )
    mastery = profile.mastery_json if isinstance(profile.mastery_json, dict) else {}
    topics: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"attempts": 0, "graded": 0, "correct": 0, "wrong": 0, "latest_answer_id": 0}
    )
    graded = correct = 0
    for answer, exercise, knowledge_point in rows:
        evaluation = answer.evaluation_json if isinstance(answer.evaluation_json, dict) else {}
        try:
            content = json.loads(exercise.content) if exercise.content else {}
        except (TypeError, ValueError):
            content = {}
        content = content if isinstance(content, dict) else {}
        raw_points = evaluation.get("knowledge_point_ids") or content.get("knowledge_point_ids")
        if not isinstance(raw_points, list) or not raw_points:
            raw_points = [knowledge_point.name] if knowledge_point is not None else []
        names = list(dict.fromkeys(str(point).strip() for point in raw_points if str(point).strip()))[:5]
        if isinstance(answer.is_correct, bool):
            graded += 1
            correct += int(answer.is_correct)
        for name in names:
            item = topics[name]
            item["attempts"] += 1
            item["latest_answer_id"] = max(item["latest_answer_id"], answer.id)
            if isinstance(answer.is_correct, bool):
                item["graded"] += 1
                item["correct"] += int(answer.is_correct)
                item["wrong"] += int(not answer.is_correct)

    knowledge_points = []
    for name, item in topics.items():
        saved = mastery.get(name)
        score = saved.get("score") if isinstance(saved, dict) else None
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            score = None
        knowledge_points.append(
            {
                "name": name,
                "attempts": item["attempts"],
                "wrong": item["wrong"],
                "accuracy": round(100 * item["correct"] / item["graded"])
                if item["graded"] else None,
                "mastery": round(max(0, min(100, score))) if score is not None else None,
                "weak": bool(saved.get("weak")) if isinstance(saved, dict) else False,
                "latest_answer_id": item["latest_answer_id"],
            }
        )
    knowledge_points.sort(key=lambda item: (-item["latest_answer_id"], item["name"]))
    interaction_rows = (
        db.query(ResourceInteraction.id, ResourceInteraction.knowledge_point)
        .filter(ResourceInteraction.user_id == user_id)
        .order_by(ResourceInteraction.id.desc())
        .limit(500)
        .all()
    )
    explored: dict[str, int] = {}
    for _, raw_name in interaction_rows:
        name = (raw_name or "").strip()
        if name:
            explored[name] = explored.get(name, 0) + 1
    return {
        "source": "answer_records_and_resource_interactions",
        "total_answers": total_answers,
        "sampled_answers": len(rows),
        "accuracy": round(100 * correct / graded) if graded else None,
        "latest_answer_id": rows[0][0].id if rows else None,
        "knowledge_points": knowledge_points[:12],
        "knowledge_point_count": len(knowledge_points),
        "resource_interaction_count": len(interaction_rows),
        "latest_resource_interaction_id": interaction_rows[0][0] if interaction_rows else None,
        "explored_points": [
            {"name": name, "interactions": count}
            for name, count in sorted(explored.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
        ],
    }
