"""Tests for conversational learner-profile building."""

from fastapi.testclient import TestClient

from services.user_service.app.main import app


def test_profile_chat_updates_dimensions_and_profile_read(test_user) -> None:
    """Profile chat should extract dimensions and persist them into the learner profile."""

    client = TestClient(app)

    response = client.post(
        f"/users/{test_user.id}/profile/chat",
        json={
            "message": "我学过 Python 基础，比较喜欢动手实践，最近目标是找后端实习。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_updates"]["knowledgeBase"]
    assert payload["profile_updates"]["cognitiveStyle"] == "动手实践型"
    assert payload["estimated_remaining_rounds"] >= 0

    profile_response = client.get(f"/users/{test_user.id}/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["profile_dimensions"]["knowledgeBase"]
    assert profile["profile_dimensions"]["goalOrientation"]


def test_manual_profile_update_allows_dimension_patch(test_user) -> None:
    """Manual profile updates should merge dimension fields into the stored profile."""

    client = TestClient(app)
    response = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "visual",
            "profile_dimensions": {
                "interestDirection": "更偏向后端开发和数据库方向",
                "learningSpeed": "适中",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["learning_style"] == "visual"
    assert payload["profile_dimensions"]["interestDirection"] == "更偏向后端开发和数据库方向"
