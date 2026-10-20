from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from common.db.base import Base
from common.models.learning import TranscriptAnalysis, TranscriptScore, User, UserProfile
from services.evaluation_service.app.schemas.transcript import (
    TranscriptAnalyzeRequest,
    TranscriptRow,
)
from services.evaluation_service.app.services.transcript_analysis import (
    TranscriptAnalysisOrchestrator,
    TranscriptAnalysisService,
)
from services.evaluation_service.app.services.transcript_parser import parse_transcript


def test_csv_parser_maps_fields_and_filters_invalid_rows() -> None:
    parsed = parse_transcript(
        "scores.csv",
        "姓名,学号,科目,分数,满分\n张三,S001,数学,88,100\n李四,S002,数学,120,100\n张三,S001,数学,88,100\n".encode(),
    )

    assert len(parsed["rows"]) == 1
    assert parsed["rows"][0].student_name == "张三"
    assert parsed["field_mapping"]["score"] == "分数"
    assert any("超出" in warning for warning in parsed["warnings"])
    assert any("重复" in warning for warning in parsed["warnings"])


def test_orchestrator_returns_serial_and_parallel_agent_contract() -> None:
    rows = [
        TranscriptRow(student_name="张三", student_no="S001", subject="数学", score=55, max_score=100),
        TranscriptRow(student_name="张三", student_no="S001", subject="英语", score=86, max_score=100),
    ]
    result = TranscriptAnalysisOrchestrator().run(rows, scope="student", quality=1.0, owner_user_id=1)

    assert result["orchestration"]["serial_agents"] == [
        "score_statistics_agent",
        "student_profile_agent",
        "weakness_diagnosis_agent",
    ]
    assert len(result["orchestration"]["parallel_agents"]) == 2
    assert result["student_profile"]["weak_subjects"] == ["数学", "英语"]
    assert result["resource_recommendations"]["seven_day_plan"][0]["day"] == 1
    assert result["exercise_recommendations"]["distribution"]["foundation"] == 0.6


def test_service_persists_report_and_updates_profile() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="student", password_hash="x", role="student")
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, mastery_json={}, learning_style="视觉型", cognitive_abilities={}, habits={}))
        db.commit()
        result = TranscriptAnalysisService(db).persist_and_analyze(
            user.id,
            TranscriptAnalyzeRequest(
                file_name="scores.csv",
                file_type="csv",
                rows=[
                    TranscriptRow(student_name="张三", student_no="S001", subject="数学", score=62),
                    TranscriptRow(student_name="张三", student_no="S001", subject="语文", score=91),
                ],
            ),
        )

        assert result["analysis_id"] > 0
        assert result["report"]["title"] == "个性化学情分析与学习方案报告"
        profile = db.get(UserProfile, user.id)
        assert profile is not None
        assert profile.profile_analysis["transcript_learning_style"]
        assert profile.profile_analysis["stale"] is True
        assert profile.learning_style == "视觉型"
        assert profile.mastery_json["transcript"]["analysis_id"] == result["analysis_id"]


def test_identical_transcript_cache_is_private_to_each_owner() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        users = [User(username=f"student{index}", password_hash="x", role="student") for index in (1, 2)]
        db.add_all(users)
        db.commit()
        payload = TranscriptAnalyzeRequest(rows=[TranscriptRow(student_no="S001", student_name="张三", subject="数学", score=70)])
        service = TranscriptAnalysisService(db)
        first = service.persist_and_analyze(users[0].id, payload)
        second = service.persist_and_analyze(users[1].id, payload)
        repeat = service.persist_and_analyze(users[0].id, payload)

        assert first["analysis_id"] != second["analysis_id"]
        assert second["cache_hit"] is False
        assert repeat["cache_hit"] is True
        assert repeat["analysis_id"] == first["analysis_id"]
        assert {item.owner_user_id for item in db.query(TranscriptAnalysis).all()} == {users[0].id, users[1].id}
        assert db.get(UserProfile, users[1].id).mastery_json["transcript"]["analysis_id"] == second["analysis_id"]


def test_personal_analysis_requires_selection_and_only_links_selected_scores() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="student", password_hash="x", role="student")
        db.add(user)
        db.commit()
        rows = [
            TranscriptRow(student_no="S001", student_name="张三", subject="数学", score=55),
            TranscriptRow(student_no="S002", student_name="李四", subject="数学", score=95),
        ]
        service = TranscriptAnalysisService(db)
        try:
            service.persist_and_analyze(user.id, TranscriptAnalyzeRequest(rows=rows))
        except ValueError as exc:
            assert "选择" in str(exc)
        else:
            raise AssertionError("multiple students must require a selection")
        assert db.query(TranscriptAnalysis).count() == 0
        assert db.query(TranscriptScore).count() == 0

        result = service.persist_and_analyze(user.id, TranscriptAnalyzeRequest(rows=rows, target_student_no="S001"))
        assert result["score_statistics"]["record_count"] == 1
        scores = db.query(TranscriptScore).all()
        assert [(row.student_no, row.student_user_id) for row in scores] == [("S001", user.id)]

        try:
            service.persist_and_analyze(user.id, TranscriptAnalyzeRequest(rows=rows, target_student_no="missing"))
        except ValueError as exc:
            assert "没有有效成绩" in str(exc)
        else:
            raise AssertionError("an unknown student must not fall back to another")


def test_class_analysis_contains_one_personal_report_per_student() -> None:
    rows = [
        TranscriptRow(student_name="张三", student_no="S001", subject="数学", score=62),
        TranscriptRow(student_name="李四", student_no="S002", subject="数学", score=91),
    ]
    result = TranscriptAnalysisOrchestrator().run(rows, scope="class", quality=1.0, owner_user_id=7)

    assert len(result["student_reports"]) == 2
    assert all("report" in report and "score_statistics" in report for report in result["student_reports"])
