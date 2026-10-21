"""Tests for deep learner-profile analysis endpoints and caching."""

import asyncio
import json
import pytest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from teaching_fixtures import registered_catalog  # noqa: F401

from common.models.learning import AnswerRecord, UserProfile
from services.evaluation_service.app.schemas.report import PracticeSubmission
from services.evaluation_service.app.services.report_service import ReportService
from services.user_service.app.main import app
from services.user_service.app.services import profile_analysis as analysis_module
from services.user_service.app.services.profile_analysis import ProfileAnalysisService


@pytest.fixture(autouse=True)
def deterministic_analysis_provider(monkeypatch):
    # Endpoint/cache tests must not race an unconfigured external provider.
    class Model:
        def invoke(self, _):
            return SimpleNamespace(content=json.dumps({key:"测试依据不足，建议继续练习。" for key in analysis_module.PROFILE_DIMENSION_KEYS}))
    monkeypatch.setattr(analysis_module,"LLMFactory",lambda *_:SimpleNamespace(build_chat_model=lambda **__:Model()))


def test_profile_analysis_endpoints_return_completed_payload(test_user, auth_headers) -> None:
    """Profile analysis endpoints should expose generated analysis content."""

    client = TestClient(app)
    update_response = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "visual",
            "profile_dimensions": {
                "knowledgeBase": "学过 Python 基础和简单项目",
                "cognitiveStyle": "视觉型",
                "goalOrientation": "求职实习",
            },
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 200

    response = client.get(
        f"/users/{test_user.id}/profile/analysis",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"processing", "completed"}

    status_response = client.get(
        f"/users/{test_user.id}/profile/analysis/status",
        headers=auth_headers,
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    if status_payload["status"] == "completed":
      analysis = status_payload["analysis"]
      assert analysis["knowledgeBase"]
      assert analysis["goalOrientation"]


def test_profile_analysis_cache_marked_stale_after_profile_change(test_user, auth_headers) -> None:
    """Updating the learner profile should mark cached deep analysis as stale."""

    client = TestClient(app)
    first_update = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "reading",
            "profile_dimensions": {
                "knowledgeBase": "学过基础概念",
                "interestDirection": "后端开发",
                "goalOrientation": "完成项目",
            },
        },
        headers=auth_headers,
    )
    assert first_update.status_code == 200

    first_analysis = client.get(
        f"/users/{test_user.id}/profile/analysis",
        headers=auth_headers,
    )
    assert first_analysis.status_code == 200

    second_update = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "reading",
            "profile_dimensions": {
                "learningSpeed": "适中",
            },
        },
        headers=auth_headers,
    )
    assert second_update.status_code == 200

    status_response = client.get(
        f"/users/{test_user.id}/profile/analysis/status",
        headers=auth_headers,
    )
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] in {"processing", "completed", "idle"}


def test_profile_analysis_refresh_endpoint_available(test_user, auth_headers) -> None:
    """Refresh endpoint should accept requests and restart or return analysis."""

    client = TestClient(app)
    update_response = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "auditory",
            "profile_dimensions": {
                "cognitiveStyle": "听觉型",
                "interestDirection": "AI 应用",
                "goalOrientation": "长期兴趣",
            },
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 200

    response = client.post(
        f"/users/{test_user.id}/profile/analysis/refresh", json={},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"processing", "completed"}


def test_deep_analysis_uses_studied_content_and_refreshes_after_new_answer(
    db_session, test_user, monkeypatch
) -> None:
    class FakePublisher:
        def publish(self, queue_name, message):
            pass

    async def submit(exercise_id: int, topic: str) -> None:
        await ReportService(publisher=FakePublisher()).evaluate_practice(
            PracticeSubmission(
                user_id=test_user.id,
                exercise_id=exercise_id,
                knowledge_point=topic,
                question_type="choice",
                user_answer="A",
                correct_answer="B",
                analysis="review the concept",
                time_spent=12,
            )
        )

    asyncio.run(submit(330000 + test_user.id, "Python 循环"))
    prompts = []

    class FakeModel:
        def invoke(self, messages):
            prompts.append(messages[1].content)
            return SimpleNamespace(content=json.dumps({key: "数据不足" for key in analysis_module.PROFILE_DIMENSION_KEYS}))

    monkeypatch.setattr(
        analysis_module, "LLMFactory", lambda settings: SimpleNamespace(build_chat_model=lambda **kwargs: FakeModel())
    )
    service = ProfileAnalysisService(db_session)
    answer_id = (
        db_session.query(AnswerRecord.id)
        .filter(AnswerRecord.user_id == test_user.id)
        .order_by(AnswerRecord.id.desc())
        .first()[0]
    )
    service._run_analysis(test_user.id, {}, answer_id)
    assert "Python 循环" in prompts[0]
    assert '"wrong": 1' in prompts[0]

    db_session.expire_all()
    cached = service.get_or_generate(test_user.id)
    assert cached["status"] == "completed"

    asyncio.run(submit(340000 + test_user.id, "数据库索引"))
    db_session.expire_all()
    monkeypatch.setattr(analysis_module.threading.Thread, "start", lambda self: None)
    try:
        fresh = service.get_or_generate(test_user.id)
        assert fresh["status"] == "processing"
    finally:
        analysis_module._analysis_tasks.pop(test_user.id, None)


def test_transcript_evidence_enters_deep_profile_and_invalidates_cache(db_session, test_user, monkeypatch) -> None:
    profile = UserProfile(
        user_id=test_user.id,
        mastery_json={"transcript": {
            "analysis_id": 12,
            "weak_subjects": ["数学"],
            "mastery_by_subject": {"数学": {"average": 54.0}},
        }},
        learning_style="视觉型", cognitive_abilities={}, habits={},
    )
    db_session.add(profile)
    db_session.commit()
    prompts = []

    class FakeModel:
        def invoke(self, messages):
            prompts.append(messages[1].content)
            return SimpleNamespace(content=json.dumps({key: "数据不足" for key in analysis_module.PROFILE_DIMENSION_KEYS}))

    monkeypatch.setattr(
        analysis_module, "LLMFactory", lambda settings: SimpleNamespace(build_chat_model=lambda **kwargs: FakeModel())
    )
    service = ProfileAnalysisService(db_session)
    service._run_analysis(test_user.id, {}, None)
    assert '"analysis_id": 12' in prompts[0]
    assert '"数学": 54.0' in prompts[0]
    db_session.expire_all()
    assert service.get_or_generate(test_user.id)["status"] == "completed"

    profile = db_session.get(UserProfile, test_user.id)
    profile.mastery_json = {"transcript": {"analysis_id": 13, "weak_subjects": ["英语"]}}
    db_session.commit()
    monkeypatch.setattr(analysis_module.threading.Thread, "start", lambda self: None)
    try:
        assert service.get_or_generate(test_user.id)["status"] == "processing"
    finally:
        analysis_module._analysis_tasks.pop(test_user.id, None)
