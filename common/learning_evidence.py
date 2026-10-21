"""Authoritative practice attribution shared by profiles and generation.

Only persisted exercise FKs / confirmed memberships are accepted. JSON labels,
page selection and model suggestions can never assign an answer to a topic.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from common.models.learning import (
    AnswerRecord,
    Exercise,
    ExerciseKnowledgePoint,
    KnowledgePoint,
    SystemSubject,
)
from common.profile_scoring import normalize_answer_row

EVIDENCE_VERSION = "point-evidence-v4"


def point_memberships(db, exercise):
    try:
        payload = json.loads(exercise.content or "{}")
    except (ValueError, TypeError):
        payload = {}
    if isinstance(payload, dict) and payload.get("classification_status") == "pending":
        return []
    links = db.query(ExerciseKnowledgePoint).filter_by(exercise_id=exercise.id, confirmed=True).all()
    weights = {link.knowledge_point_id: link.weight for link in links if math.isfinite(link.weight) and link.weight > 0}
    # The existing FK remains an explicit primary annotation.
    weights.setdefault(exercise.knowledge_point_id, 1.0)
    points = {p.id: p for p in db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(weights)).all()}
    total = sum(value for key, value in weights.items() if key in points)
    return [(points[key], value / total) for key, value in weights.items() if key in points] if total else []


def resolve_point(db, name, *, point_id=None, subject="", chapter=""):
    query = db.query(KnowledgePoint)
    if point_id and str(point_id).isdigit():
        query = query.filter(KnowledgePoint.id == int(point_id))
    else:
        # Explicit aliases are catalog-reviewed metadata, not generated labels.
        candidates = [p.id for p in query.all() if p.name.strip().casefold() == name.strip().casefold()
                      or name.strip().casefold() in {str(a).strip().casefold() for a in (p.aliases_json or [])}]
        query = query.filter(KnowledgePoint.id.in_(candidates))
    if subject:
        subjects = db.query(SystemSubject).filter((SystemSubject.name == subject) | (SystemSubject.code == subject)).all()
        if not subjects:
            return None
        query = query.filter(KnowledgePoint.subject_id.in_([item.id for item in subjects]))
    if chapter:
        query = query.filter(KnowledgePoint.chapter == chapter)
    points = query.limit(2).all()
    return points[0] if len(points) == 1 and (points[0].name.strip().casefold() == name.strip().casefold() or name.strip().casefold() in {str(a).strip().casefold() for a in points[0].aliases_json or []}) else None


def load_evidence(db, user_id, *, point=None):
    rows = db.query(AnswerRecord, Exercise).join(Exercise, Exercise.id == AnswerRecord.exercise_id).filter(
        AnswerRecord.user_id == user_id).order_by(AnswerRecord.created_at, AnswerRecord.id).all()
    records = []
    for answer, exercise in rows:
        if not isinstance(answer.is_correct, bool) or not answer.created_at or not str(answer.user_answer or "").strip():
            continue
        meta = answer.evaluation_json if isinstance(answer.evaluation_json, dict) else {}
        if meta.get("scoring_status", "completed") not in {"completed", "graded", "scored"}:
            continue
        if meta.get("evidence_excluded") or meta.get("test_data") or meta.get("evidence_source") in {"demo", "test", "synthetic"}:
            continue
        try:
            exercise_payload = json.loads(exercise.content)
        except (ValueError, TypeError):
            exercise_payload = {}
        if isinstance(exercise_payload, dict) and exercise_payload.get("generated_for_user_id") not in {None, user_id}:
            continue
        for kp, weight in point_memberships(db, exercise):
            if point is not None and kp.id != point.id:
                continue
            row = normalize_answer_row(answer, exercise)
            row.update(user_id=user_id, attempt_id=answer.id, question_id=exercise.id,
                       knowledge_point_id=kp.id, knowledge_point=kp.name, subject_id=kp.subject_id,
                       chapter=kp.chapter, attribution_weight=weight, scoring_status="completed",
                       submitted_at=answer.created_at.isoformat(), correct_answer=exercise.answer,
                       analysis=exercise.analysis, evidence_version=EVIDENCE_VERSION)
            records.append(row)
    return records


def summarize(records):
    # Latest valid attempt per question; repeated submissions add no sample weight.
    unique = {row["exercise_id"]: row for row in records}
    rows = list(unique.values())
    count = len(rows)
    contribution = sum(row["attribution_weight"] for row in rows)
    status = "no_evidence" if not count else "insufficient" if contribution < 3 else "preliminary" if contribution < 8 else "sufficient"
    weights = []
    for row in rows:
        timestamp = datetime.fromisoformat(row["created_at"])
        timestamp = timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
        age = max(0, (datetime.now(UTC) - timestamp).total_seconds() / 86400)
        difficulty = row.get("difficulty_level", row.get("difficulty", 1))
        difficulty = difficulty if isinstance(difficulty, (int, float)) else 1
        weights.append(row["attribution_weight"] * (1 + min(4, max(0, difficulty - 1)) * .15) * 2 ** (-min(age, 365) / 45))
    total = sum(weights)
    rate = sum(float(row["is_correct"]) * w for row, w in zip(rows, weights, strict=True)) / total if total else None
    # Wilson interval is an uncertainty proxy for the effective weighted sample.
    n = min(contribution, total ** 2 / sum(w * w for w in weights)) if total else 0
    interval = None
    if rate is not None:
        z = 1.96
        center = (rate + z*z/(2*n)) / (1 + z*z/n)
        margin = z * math.sqrt(rate*(1-rate)/n + z*z/(4*n*n)) / (1 + z*z/n)
        interval = [round(100 * max(0, center-margin)), round(100 * min(1, center+margin))]
    return {"version": EVIDENCE_VERSION, "status": status, "sample_size": count,
            "attempt_count": len(records), "effective_samples": round(total, 3),
            "mastery_score": round(100*rate) if rate is not None and contribution >= 3 else None,
            "correct_rate": round(100*sum(row["is_correct"] for row in rows)/count) if count else None,
            "uncertainty_interval": interval, "evidence_ids": [row["attempt_id"] for row in rows],
            "question_type_coverage": sorted({row["question_type"] for row in rows}),
            "timing_policy": "recorded_only_no_speed_bonus", "repeat_policy": "latest_valid_attempt_per_question",
            "trend": [row["is_correct"] for row in rows[-5:]]}


def recompute_profile(db, user_id, profile):
    """Rebuild derived scores, retaining original historical data separately."""
    from collections import defaultdict
    grouped = defaultdict(list)
    for row in load_evidence(db, user_id):
        grouped[row["knowledge_point_id"]].append(row)
    previous = dict(profile.mastery_json or {})
    result = {key: value for key, value in previous.items() if not isinstance(value, dict) or "score" not in value}
    stats_by_name = {}
    for point_id, rows in grouped.items():
        stats = summarize(rows)
        stats.update(score=stats["mastery_score"], weak=stats["mastery_score"] is not None and stats["mastery_score"] < 60,
                     knowledge_point_id=point_id, subject_id=rows[-1]["subject_id"])
        stats["history"] = [{"answer_record_id": row["attempt_id"], "exercise_id": row["exercise_id"],
            "is_correct": row["is_correct"], "answered_at": row["submitted_at"],
            "attribution_weight": row["attribution_weight"], "time_spent": row["time_spent"],
            "error_pattern": "none" if row["is_correct"] else "answer_mismatch"} for row in rows[-100:]]
        result[f"kp:{point_id}"] = stats
        stats_by_name.setdefault(rows[-1]["knowledge_point"], []).append(stats)
    for name, entries in stats_by_name.items():
        if len(entries) == 1:
            result[name] = entries[0]
    profile.mastery_json = result
    if isinstance(profile.profile_analysis, dict):
        profile.profile_analysis = {**profile.profile_analysis, "stale": True}
    return result
