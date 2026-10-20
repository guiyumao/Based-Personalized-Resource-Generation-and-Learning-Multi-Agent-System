"""Evidence-based learning activity summary for the existing report service."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from common.models.learning import (
    AnswerRecord,
    CardReviewEvent,
    ChatMessage,
    ChatSession,
    Exercise,
    KnowledgePoint,
    LearningPath,
    LearningTask,
    Resource,
    ResourceInteraction,
    ReviewCard,
)
from services.evaluation_service.app.services.study_activity import (
    activity_schema_ready,
    measured_daily_seconds,
)

_LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def build_learning_analytics(db: Session, user_id: int, days: int = 30) -> dict[str, object]:
    """Count recorded activity only; question time is not total study time."""

    now = datetime.now(UTC)
    today = now.astimezone(_LOCAL_TZ).date()
    start_day = today - timedelta(days=days - 1)
    start_utc = datetime.combine(start_day, datetime.min.time(), _LOCAL_TZ).astimezone(UTC).replace(tzinfo=None)
    end_utc = now.replace(tzinfo=None)
    buckets = {
        (start_day + timedelta(days=offset)).isoformat(): {
            "date": (start_day + timedelta(days=offset)).isoformat(),
            "answers": 0,
            "graded_answers": 0,
            "correct_answers": 0,
            "question_seconds": 0,
            "resource_events": 0,
            "questions_asked": 0,
            "card_reviews": 0,
        }
        for offset in range(days)
    }

    def bucket_for(when: datetime | None) -> dict[str, object] | None:
        if when is None:
            return None
        stamped = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
        return buckets.get(stamped.astimezone(_LOCAL_TZ).date().isoformat())

    answers = db.query(AnswerRecord.created_at, AnswerRecord.is_correct, AnswerRecord.time_spent).filter(
        AnswerRecord.user_id == user_id,
        AnswerRecord.created_at >= start_utc,
        AnswerRecord.created_at <= end_utc,
    ).all()
    for when, correct, seconds in answers:
        bucket = bucket_for(when)
        if bucket is None:
            continue
        bucket["answers"] += 1
        if correct is not None:
            bucket["graded_answers"] += 1
            bucket["correct_answers"] += int(correct)
        bucket["question_seconds"] += max(0, seconds or 0)

    interactions = db.query(ResourceInteraction.created_at).filter(
        ResourceInteraction.user_id == user_id,
        ResourceInteraction.created_at >= start_utc,
        ResourceInteraction.created_at <= end_utc,
    ).all()
    for (when,) in interactions:
        bucket = bucket_for(when)
        if bucket is not None:
            bucket["resource_events"] += 1

    questions = db.query(ChatMessage.created_at).join(ChatSession).filter(
        ChatSession.user_id == user_id,
        ChatMessage.role == "user",
        ChatMessage.created_at >= start_utc,
        ChatMessage.created_at <= end_utc,
    ).all()
    for (when,) in questions:
        bucket = bucket_for(when)
        if bucket is not None:
            bucket["questions_asked"] += 1

    reviews = db.query(CardReviewEvent.reviewed_at).filter(
        CardReviewEvent.user_id == user_id,
        CardReviewEvent.reviewed_at >= start_utc,
        CardReviewEvent.reviewed_at <= end_utc,
    ).all()
    for (when,) in reviews:
        bucket = bucket_for(when)
        if bucket is not None:
            bucket["card_reviews"] += 1

    daily = list(buckets.values())
    activity_ready = activity_schema_ready(db)
    measured = measured_daily_seconds(db, user_id, start_utc, end_utc, _LOCAL_TZ) if activity_ready else {}
    for day in daily:
        day["study_seconds"] = round(measured.get(day["date"], 0), 3) if activity_ready else None
    totals: dict[str, int] = defaultdict(int)
    for day in daily:
        for key in ("answers", "graded_answers", "correct_answers", "question_seconds", "resource_events", "questions_asked", "card_reviews"):
            totals[key] += int(day[key])
    active_days = sum(bool(day["answers"] or day["resource_events"] or day["questions_asked"] or day["card_reviews"] or day["study_seconds"]) for day in daily)
    accuracy = round(100 * totals["correct_answers"] / totals["graded_answers"], 1) if totals["graded_answers"] else None
    last_seven = sum(int(day["answers"]) for day in daily[-7:])
    previous_seven = sum(int(day["answers"]) for day in daily[-14:-7]) if days >= 14 else None

    point_counts: dict[int, dict[str, object]] = {}
    point_answers = db.query(KnowledgePoint.id, KnowledgePoint.name, AnswerRecord.is_correct).join(
        Exercise, Exercise.knowledge_point_id == KnowledgePoint.id
    ).join(AnswerRecord, AnswerRecord.exercise_id == Exercise.id).filter(
        AnswerRecord.user_id == user_id,
        AnswerRecord.created_at >= start_utc,
        AnswerRecord.created_at <= end_utc,
    ).all()
    for point_id, name, correct in point_answers:
        item = point_counts.setdefault(point_id, {
            "knowledge_point_id": point_id, "name": name,
            "answers": 0, "graded_answers": 0, "correct_answers": 0,
        })
        item["answers"] += 1
        if correct is not None:
            item["graded_answers"] += 1
            item["correct_answers"] += int(correct)
    knowledge_accuracy = [
        {**item, "accuracy_percent": round(100 * item["correct_answers"] / item["graded_answers"], 1)
         if item["graded_answers"] else None}
        for item in point_counts.values()
    ]
    knowledge_accuracy.sort(key=lambda item: (-item["graded_answers"], -item["answers"], item["name"]))

    latest_path = db.query(LearningPath).filter(
        LearningPath.user_id == user_id, LearningPath.status == "active"
    ).order_by(LearningPath.created_at.desc(), LearningPath.id.desc()).first()
    path_progress = None
    if latest_path is not None:
        path_progress = summarize_path(db, latest_path)

    current_week_start = today - timedelta(days=today.weekday())
    week_seconds = sum(float(day["study_seconds"] or 0) for day in daily if day["date"] >= current_week_start.isoformat())
    previous_start = current_week_start - timedelta(days=7)
    previous_seconds = sum(float(day["study_seconds"] or 0) for day in daily
                           if previous_start.isoformat() <= day["date"] < current_week_start.isoformat())
    streak = 0
    for day in reversed(daily):
        active = any(day[key] for key in ("answers", "resource_events", "questions_asked", "card_reviews", "study_seconds"))
        if not active:
            if day["date"] == today.isoformat():
                continue
            break
        streak += 1

    return {
        "days": days,
        "timezone": "Asia/Shanghai",
        "from_date": start_day.isoformat(),
        "to_date": today.isoformat(),
        "summary": {**totals, "active_days": active_days, "accuracy_percent": accuracy,
                    "study_seconds": round(sum(measured.values()), 3) if activity_ready else None,
                    "current_streak_days": streak, "streak_window_days": days},
        "week_comparison": {"last_seven_answers": last_seven, "previous_seven_answers": previous_seven,
                            "this_week_study_seconds": round(week_seconds, 3) if activity_ready else None,
                            "previous_week_study_seconds": round(previous_seconds, 3) if activity_ready and start_day <= previous_start else None},
        "knowledge_accuracy": knowledge_accuracy,
        "path_progress": path_progress,
        "daily": daily,
        "evidence": {
            "answers": "answer_records",
            "resource_events": "resource_interactions",
            "questions_asked": "chat_messages(role=user)",
            "card_reviews": "card_review_events",
            "question_seconds": "answer_records.time_spent; not total study duration",
            "knowledge_accuracy": "graded answer_records joined through exercises to knowledge_points; not overall mastery",
            "path_progress": "learning_paths.path_data_json.stages.tasks (authoritative); legacy learning_tasks only when stages absent",
            "study_seconds": "study_activities server-time intervals; visible, focused, recent input; shared per-user CAS cursor; no historical backfill" if activity_ready else "unavailable: activity migration required",
        },
    }


def summarize_path(db: Session, path: LearningPath) -> dict:
    """Use the same JSON tasks that LearningPathService updates; avoid double counting."""
    data = path.path_data_json if isinstance(path.path_data_json, dict) else {}
    tasks = None
    if isinstance(data.get("stages"), list):
        tasks = []
        for stage in data["stages"]:
            if isinstance(stage, dict) and isinstance(stage.get("tasks"), list):
                tasks.extend(task for task in stage["tasks"] if isinstance(task, dict))
    if tasks is None:
        legacy = db.query(LearningTask).filter(LearningTask.path_id == path.id).all()
        tasks = [{"task_id": str(task.id), "completed": task.completed, "task_type": task.task_type} for task in legacy]
    completed = sum(task.get("completed") is True for task in tasks)
    pending = [task for task in tasks if task.get("completed") is not True]
    return {
        "path_id": path.id, "subject": data.get("subject", ""), "knowledge_point": data.get("knowledge_point", ""),
        "overview": data.get("overview", ""), "total_tasks": len(tasks), "completed_tasks": completed,
        "completion_percent": round(100 * completed / len(tasks), 1) if tasks else None,
        "pending_tasks": [{key: task.get(key) for key in ("task_id", "title", "task_type", "knowledge_point", "estimated_minutes", "depends_on")} for task in pending[:8]],
    }


def build_learning_overview(db: Session, user_id: int) -> dict:
    """Read existing business rows; this endpoint never calls a model."""
    analytics = build_learning_analytics(db, user_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    due_count = db.query(ReviewCard).filter(ReviewCard.user_id == user_id, ReviewCard.due_at <= now).count()
    plans = db.query(LearningPath).filter(LearningPath.user_id == user_id, LearningPath.status == "active").order_by(LearningPath.id.desc()).all()
    resources = db.query(Resource).filter(Resource.generated_for_user_id == user_id).order_by(Resource.created_at.desc(), Resource.id.desc()).limit(6).all()
    weak = [dict(item, confidence="low" if item["graded_answers"] < 5 else "moderate")
            for item in analytics["knowledge_accuracy"] if item["accuracy_percent"] is not None and item["accuracy_percent"] < 60]
    weak.sort(key=lambda item: (item["accuracy_percent"], -item["graded_answers"]))
    suggestions = []
    if due_count:
        suggestions.append(f"有 {due_count} 张闪卡到期，建议先完成复习。")
    suggestions.extend(f"{item['name']}近期练习正确率 {item['accuracy_percent']}%（{item['graded_answers']} 次判分），建议复习并重练。" for item in weak[:3])
    if not suggestions and not analytics["summary"].get("answers"):
        suggestions.append("完成一次练习后，可依据作答证据查看薄弱项。")
    return {"analytics": analytics, "active_plans": [summarize_path(db, path) for path in plans],
            "due_cards": due_count, "weak_points": weak[:8], "suggestions": suggestions,
            "recent_resources": [{"id": row.id, "title": row.title, "type": row.type,
                                  "knowledge_point_id": row.knowledge_point_id, "generation_status": row.generation_status,
                                  "created_at": row.created_at.isoformat()} for row in resources],
            "evidence": "existing learning_paths, answer_records, review_cards, resources and study_activities; no model calls"}
