"""Cross-topic contamination regression with real isolated SQL rows."""
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from common.db.base import Base
from common.learning_evidence import load_evidence, point_memberships, recompute_profile, summarize
from common.models.learning import (
    AnswerRecord,
    Exercise,
    ExerciseKnowledgePoint,
    KnowledgePoint,
    SystemSubject,
    User,
    UserProfile,
)
from services.agent_service.app.services.personalization import PersonalizationService


@pytest.fixture
def evidence_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([User(id=1, username="alice", password_hash="unused"), User(id=2, username="bob", password_hash="unused"),
                    SystemSubject(id=1, name="算法", code="algorithms", description="test"), SystemSubject(id=2, name="计算机网络", code="networks", description="test")])
        db.flush()
        db.add_all([KnowledgePoint(id=1, name="冒泡排序", subject_id=1), KnowledgePoint(id=2, name="TCP协议", subject_id=2),
                    KnowledgePoint(id=3, name="排序稳定性", subject_id=1)])
        db.add(UserProfile(user_id=1, mastery_json={"冒泡排序": {"score": 60}}, profile_analysis={"summaries": {"cognitiveStyle": "偏好样例"}}))
        db.commit()
        yield db
    engine.dispose()


def add_answers(db, point, count, user=1, start=1):
    for i in range(start, start+count):
        db.add(Exercise(id=i, knowledge_point_id=point, type="choice", content=json.dumps({"prompt": "TCP在哪一层？" if point == 2 else "冒泡排序的交换过程？"}), answer="B"))
        db.flush()
        db.add(AnswerRecord(user_id=user, exercise_id=i, user_answer="B" if i % 2 else "A", is_correct=bool(i % 2), created_at=datetime.utcnow()))
    db.commit()


def test_five_tcp_answers_never_become_bubble_sort_evidence(evidence_db):
    db = evidence_db
    add_answers(db, 2, 5)
    snapshot = PersonalizationService(db).build_snapshot(1, "冒泡排序", {}, subject="算法")
    assert snapshot.answered_count == 0 and snapshot.mastery_score is None and snapshot.correct_rate is None
    assert snapshot.recent_mistakes == []
    assert snapshot.learner_profile["evidence"]["status"] == "no_evidence"
    assert snapshot.learner_profile["profile_analysis_summaries"] == {}
    tcp = PersonalizationService(db).build_snapshot(1, "TCP协议", {}, subject="计算机网络")
    assert tcp.answered_count == 5 and tcp.correct_rate == 60
    assert len(tcp.learner_profile["evidence"]["evidence_ids"]) == 5


def test_mixed_points_users_and_repeats_are_independent(evidence_db):
    db = evidence_db
    add_answers(db, 2, 5)
    add_answers(db, 1, 3, start=6)
    add_answers(db, 1, 4, user=2, start=20)
    for _ in range(10):
        db.add(AnswerRecord(user_id=1, exercise_id=6, user_answer="B", is_correct=True, created_at=datetime.utcnow()))
    db.commit()
    snapshot = PersonalizationService(db).build_snapshot(1, "冒泡排序", {})
    assert snapshot.answered_count == 3
    assert snapshot.learner_profile["evidence"]["attempt_count"] == 13
    assert PersonalizationService(db).build_snapshot(2, "冒泡排序", {}).answered_count == 4
    assert PersonalizationService(db).build_snapshot(1, "TCP协议", {}).answered_count == 5


def test_unknown_and_low_sample_are_not_precise_scores(evidence_db):
    db = evidence_db
    assert PersonalizationService(db).build_snapshot(1, "冒泡排序", {}).mastery_score is None
    add_answers(db, 1, 1)
    snapshot = PersonalizationService(db).build_snapshot(1, "冒泡排序", {})
    assert snapshot.mastery_score is None and snapshot.answered_count == 1
    assert snapshot.learner_profile["evidence"]["status"] == "insufficient"


def test_confirmed_multi_point_weights_and_candidate_exclusion(evidence_db):
    db = evidence_db
    add_answers(db, 1, 3)
    for i in (1, 2, 3):
        db.add(ExerciseKnowledgePoint(exercise_id=i, knowledge_point_id=3, weight=1, confirmed=True))
        db.add(ExerciseKnowledgePoint(exercise_id=i, knowledge_point_id=2, weight=1, confirmed=False))
    db.commit()
    stats = summarize(load_evidence(db, 1, point=db.get(KnowledgePoint, 1)))
    assert stats["sample_size"] == 3 and stats["effective_samples"] < 1.51
    assert stats["mastery_score"] is None
    assert load_evidence(db, 1, point=db.get(KnowledgePoint, 2)) == []
    assert sum(weight for _, weight in point_memberships(db, db.get(Exercise, 1))) == 1


def test_stale_profile_is_recomputed_without_deleting_answers(evidence_db):
    db = evidence_db
    add_answers(db, 2, 5)
    profile = db.get(UserProfile, 1)
    recompute_profile(db, 1, profile)
    db.commit()
    assert "冒泡排序" not in profile.mastery_json
    assert profile.profile_analysis["stale"] is True
    assert profile.mastery_json["TCP协议"]["score"] == 60
    assert db.query(AnswerRecord).count() == 5


def test_subject_ambiguity_invalid_grading_and_missing_fk_fail_closed(evidence_db):
    db = evidence_db
    add_answers(db, 1, 3)
    db.add(KnowledgePoint(id=4, name="冒泡排序", subject_id=2))
    db.commit()
    assert PersonalizationService(db).build_snapshot(1, "冒泡排序", {}).answered_count == 0
    assert PersonalizationService(db).build_snapshot(1, "冒泡排序", {}, subject="算法").answered_count == 3
    row = db.query(AnswerRecord).first()
    row.evaluation_json = {"scoring_status": "pending", "knowledge_point_ids": ["TCP协议"]}
    db.commit()
    assert len(load_evidence(db, 1, point=db.get(KnowledgePoint, 1))) == 2
    assert load_evidence(db, 1, point=db.get(KnowledgePoint, 2)) == []


def test_unconfirmed_imports_remain_raw_without_becoming_evidence(evidence_db):
    db = evidence_db
    add_answers(db, 1, 1)
    exercise = db.get(Exercise, 1)
    exercise.content = json.dumps({"classification_status": "pending", "knowledge_point": "冒泡排序"})
    db.commit()
    assert load_evidence(db, 1) == [] and db.query(AnswerRecord).count() == 1
