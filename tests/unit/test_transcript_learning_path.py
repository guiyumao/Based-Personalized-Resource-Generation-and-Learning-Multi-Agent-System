"""A transcript can seed only its owner's existing persisted path workflow."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from common.db.base import Base
from common.models.learning import LearningPath, TranscriptAnalysis, TranscriptImport, User
from common.schemas.agent import LearningPathRequest
from services.agent_service.app.services.learning_path import LearningPathService
from services.agent_service.app.services.personalization import PersonalizationService


def test_transcript_path_uses_owned_scores_and_reuses_active_path(monkeypatch) -> None:
    # Isolate transcript evidence/reuse from the separately tested catalog gate.
    from services.agent_service.app.services import plan_knowledge
    monkeypatch.setattr(plan_knowledge, "require_plan_knowledge", lambda *_: {
        "knowledge_point": "数学", "subject_id": 1, "point_id": 1,
        "published_versions": [1], "usable_chunks": [],
    })
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="path_owner", password_hash="x", role="student")
        outsider = User(username="path_outsider", password_hash="x", role="student")
        db.add_all([owner, outsider])
        db.flush()
        imported = TranscriptImport(
            owner_user_id=owner.id, file_name="grades.csv", file_type="csv",
            content_hash="1" * 64, quality_score=1.0,
            field_mapping_json={}, normalized_rows_json=[], warnings_json=[],
        )
        db.add(imported)
        db.flush()
        analysis = TranscriptAnalysis(
            import_id=imported.id, owner_user_id=owner.id, scope="student",
            cache_key="2" * 64, status="completed", data_quality="sufficient",
            result_json={"score_statistics": {"subject_statistics": {
                "数学": {"average": 52.0}, "英语": {"average": 83.0},
            }}}, report_text="",
        )
        db.add(analysis)
        db.commit()

        captured = []

        def fake_generate(request, teacher_scope):
            captured.append(request.learner_profile)
            return {
                "user_id": request.user_id, "subject": request.subject,
                "knowledge_point": request.knowledge_point, "overview": "先复习数学基础",
                "estimated_days": 1, "stages": [{
                    "stage_id": "s1", "title": "复习", "description": "按成绩诊断安排",
                    "tasks": [{"task_id": "t1", "title": "基础练习", "task_type": "exercise",
                               "knowledge_point": "数学", "objective": "检查基础概念",
                               "estimated_minutes": 20, "difficulty": "foundation",
                               "completed": False, "status": "pending", "depends_on": []}],
                }],
            }

        service = LearningPathService(db)
        snapshot = PersonalizationService(db).build_snapshot(
            owner.id, "数学", {"transcript_analysis_id": analysis.id}
        )
        assert snapshot.learner_profile["transcript_analysis_id"] == analysis.id
        monkeypatch.setattr(service, "_generate_path_with_llm", fake_generate)
        request = LearningPathRequest(
            user_id=owner.id, subject="数学", knowledge_point="数学",
            learner_profile={"transcript_analysis_id": analysis.id,
                             "transcript_evidence": {"subject_averages": {"数学": 100}}},
        )
        first = service.generate_path(request)
        second = service.generate_path(request)
        assert first["source_transcript_analysis_id"] == analysis.id
        assert second == first
        assert len(captured) == 1
        assert captured[0]["transcript_evidence"]["subject_averages"]["数学"] == 52.0
        assert db.query(LearningPath).count() == 1

        for invalid in (
            request.model_copy(update={"user_id": outsider.id}),
            request.model_copy(update={"subject": "物理"}),
        ):
            try:
                service.generate_path(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError("an unrelated transcript or subject must be rejected")
        assert db.query(LearningPath).count() == 1
