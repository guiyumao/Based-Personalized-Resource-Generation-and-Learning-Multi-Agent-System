"""Read-only learning dashboard computed from the existing learner records."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from common.models.learning import (
    AnswerRecord,
    ChatMessage,
    ChatSession,
    Exercise,
    ReviewCard,
    StudyNote,
)
from services.evaluation_service.app.services.learning_analytics import (
    _LOCAL_TZ,
    build_learning_analytics,
)


def build_learning_insights(db: Session, user_id: int, days: int = 30) -> dict:
    analytics = build_learning_analytics(db, user_id, days)
    since = (
        datetime.combine(
            datetime.fromisoformat(analytics["from_date"]).date(), datetime.min.time(), _LOCAL_TZ
        )
        .astimezone(UTC)
        .replace(tzinfo=None)
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    answers = (
        db.query(
            AnswerRecord.is_correct, AnswerRecord.created_at, Exercise.type, Exercise.difficulty
        )
        .join(Exercise, Exercise.id == AnswerRecord.exercise_id)
        .filter(
            AnswerRecord.user_id == user_id,
            AnswerRecord.created_at >= since,
            AnswerRecord.created_at <= now,
        )
        .all()
    )
    groups = {"question_type": {}, "difficulty": {}}
    hours = [{"hour": hour, "answers": 0, "graded": 0, "correct": 0} for hour in range(24)]
    for correct, when, kind, difficulty in answers:
        for key, value in (
            ("question_type", kind or "未标注"),
            ("difficulty", str(difficulty or "未标注")),
        ):
            item = groups[key].setdefault(
                value, {"label": value, "answers": 0, "graded": 0, "correct": 0}
            )
            item["answers"] += 1
            if correct is not None:
                item["graded"] += 1
                item["correct"] += int(correct)
        hour = (
            when.replace(tzinfo=UTC).astimezone(_LOCAL_TZ).hour
            if when.tzinfo is None
            else when.astimezone(_LOCAL_TZ).hour
        )
        hours[hour]["answers"] += 1
        if correct is not None:
            hours[hour]["graded"] += 1
            hours[hour]["correct"] += int(correct)
    for mapping in groups.values():
        for item in mapping.values():
            item["accuracy_percent"] = (
                round(100 * item["correct"] / item["graded"], 1) if item["graded"] else None
            )
    cards = db.query(ReviewCard).filter_by(user_id=user_id).all()
    flashcards = {
        "total": len(cards),
        "due": sum(card.due_at <= now for card in cards),
        "new": sum(card.review_count == 0 for card in cards),
        "long_interval": sum(card.interval_days >= 21 for card in cards),
        "reviews_in_period": analytics["summary"]["card_reviews"],
    }
    messages = (
        db.query(ChatMessage.created_at, ChatMessage.session_id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .filter(
            ChatSession.user_id == user_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= since,
            ChatMessage.created_at <= now,
        )
        .all()
    )
    sessions = len({session_id for _, session_id in messages})
    conversation = {
        "questions": len(messages),
        "sessions": sessions,
        "questions_per_session": round(len(messages) / sessions, 1) if sessions else None,
    }
    weak = sorted(
        (
            item
            for item in analytics["knowledge_accuracy"]
            if item["accuracy_percent"] is not None and item["accuracy_percent"] < 60
        ),
        key=lambda item: item["accuracy_percent"],
    )
    suggestions = []
    if flashcards["due"]:
        suggestions.append(
            {
                "title": "先复习到期闪卡",
                "description": f"当前有 {flashcards['due']} 张闪卡待复习。",
                "route": "/student/study-tools",
            }
        )
    for item in weak[:3]:
        suggestions.append(
            {
                "title": f"补强{item['name']}",
                "description": f"选定时段内 {item['graded_answers']} 次已判分作答，正确率 {item['accuracy_percent']}%。",
                "route": "/student/exercise",
                "topic": item["name"],
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "title": "继续记录学习证据",
                "description": "阅读资源、完成练习并复习闪卡，这里会更新你的学习趋势。",
                "route": "/student/workspace",
            }
        )
    return {
        **analytics,
        "quiz": {key: list(value.values()) for key, value in groups.items()},
        "answer_hours": hours,
        "flashcards": flashcards,
        "conversation": conversation,
        "notes": db.query(StudyNote.id).filter(StudyNote.user_id == user_id).count(),
        "suggestions": suggestions,
        "suggestion_source": "record_based_rules; no model call",
        "generated_at": datetime.now(UTC).isoformat(),
    }
