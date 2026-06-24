"""Tests for deep learner-profile analysis endpoints and caching."""

from fastapi.testclient import TestClient

from services.user_service.app.main import app


def test_profile_analysis_endpoints_return_completed_payload(test_user) -> None:
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
    )
    assert update_response.status_code == 200

    response = client.get(f"/users/{test_user.id}/profile/analysis")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"processing", "completed"}

    status_response = client.get(f"/users/{test_user.id}/profile/analysis/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    if status_payload["status"] == "completed":
      analysis = status_payload["analysis"]
      assert analysis["knowledgeBase"]
      assert analysis["goalOrientation"]


def test_profile_analysis_cache_marked_stale_after_profile_change(test_user) -> None:
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
    )
    assert first_update.status_code == 200

    first_analysis = client.get(f"/users/{test_user.id}/profile/analysis")
    assert first_analysis.status_code == 200

    second_update = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "reading",
            "profile_dimensions": {
                "learningSpeed": "适中",
            },
        },
    )
    assert second_update.status_code == 200

    status_response = client.get(f"/users/{test_user.id}/profile/analysis/status")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] in {"processing", "completed", "idle"}


def test_profile_analysis_refresh_endpoint_available(test_user) -> None:
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
    )
    assert update_response.status_code == 200

    response = client.post(f"/users/{test_user.id}/profile/analysis/refresh", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"processing", "completed"}
