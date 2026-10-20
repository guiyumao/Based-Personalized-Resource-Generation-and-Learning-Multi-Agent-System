"""Tests for learner exercise favorites."""

from __future__ import annotations

import json

from common.models.learning import Exercise, KnowledgePoint
from services.evaluation_service.app.services.report_service import ReportService


def test_favorite_notebook_persists_a_real_exercise_snapshot(db_session, test_user) -> None:
    knowledge_point = KnowledgePoint(
        name=f"favorite-kp-{test_user.id}",
        description="favorite test knowledge point",
        difficulty=1,
        importance=1,
        subject_id=1,
    )
    db_session.add(knowledge_point)
    db_session.flush()
    exercise = Exercise(
        knowledge_point_id=knowledge_point.id,
        type="choice",
        difficulty=1,
        content=json.dumps(
            {
                "knowledge_point": knowledge_point.name,
                "question_type": "choice",
                "difficulty": "foundation",
                "prompt": "TCP 建立连接需要几次握手？",
                "options": ["A. 两次", "B. 三次"],
            },
            ensure_ascii=False,
        ),
        answer="B",
        analysis="通过三次报文完成连接确认。",
    )
    db_session.add(exercise)
    db_session.commit()

    service = ReportService()
    saved = service._add_exercise_favorite(test_user.id, exercise.id)
    notebook = service._get_exercise_favorites(test_user.id)
    service._remove_exercise_favorite(test_user.id, exercise.id)

    assert saved.exercise_id == exercise.id
    assert saved.prompt == "TCP 建立连接需要几次握手？"
    assert saved.options == ["A. 两次", "B. 三次"]
    assert notebook.favorite_count == 1
    assert notebook.items[0].answer == "B"

    db_session.delete(exercise)
    db_session.delete(knowledge_point)
    db_session.commit()
