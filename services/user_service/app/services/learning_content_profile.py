"""Summarize a learner's persisted practice by the content actually studied."""

from __future__ import annotations

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
    from common.learning_evidence import EVIDENCE_VERSION, load_evidence, summarize
    evidence = load_evidence(db, user_id)
    grouped = defaultdict(list)
    for row in evidence:
        grouped[row["knowledge_point_id"]].append(row)
    knowledge_points = []
    for point_id, records in grouped.items():
        stats = summarize(records)
        latest = records[-1]
        knowledge_points.append({"name": latest["knowledge_point"], "knowledge_point_id": point_id,
            "subject_id": latest["subject_id"], "attempts": stats["sample_size"],
            "wrong": sum(not r["is_correct"] for r in {r["exercise_id"]: r for r in records}.values()),
            "accuracy": stats["correct_rate"], "mastery": stats["mastery_score"],
            "weak": stats["mastery_score"] is not None and stats["mastery_score"] < 60,
            "latest_answer_id": latest["attempt_id"], "evidence": stats})
    all_stats = summarize(evidence)
    graded = all_stats["sample_size"]
    correct = all_stats["correct_rate"] or 0
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
        "evidence_version": EVIDENCE_VERSION,
        "total_answers": total_answers,
        "sampled_answers": len(rows),
        "accuracy": correct if graded else None,
        "latest_answer_id": rows[0][0].id if rows else None,
        "knowledge_points": knowledge_points[:12],
        "knowledge_point_count": len(knowledge_points),
        "resource_interaction_count": len(interaction_rows),
        "latest_resource_interaction_id": interaction_rows[0][0] if interaction_rows else None,
        "explored_points": [
            {"name": name, "interactions": count}
            for name, count in sorted(explored.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
        ],
        "flashcard_review_evidence": (profile.mastery_json or {}).get("flashcard_review", {}),
    }
