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


def test_profile_chat_accepts_multi_dimension_quick_choices(test_user) -> None:
    """Profile chat should persist grouped quick-choice answers across dimensions."""

    client = TestClient(app)

    response = client.post(
        f"/users/{test_user.id}/profile/chat",
        json={
            "message": "\n".join(
                [
                    "我想一次补充画像多维度：",
                    "知识基础：学过基础概念、做过小项目",
                    "认知风格：视觉型、动手实践型",
                    "易错偏好：概念理解容易混淆、代码调试容易卡",
                    "学习节奏：慢一点分步讲",
                    "兴趣方向：后端开发、AI 应用",
                    "目标导向：求职实习、完成项目",
                ]
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_completeness"] == {
        "knowledgeBase": "已获取",
        "cognitiveStyle": "已获取",
        "errorPreference": "已获取",
        "learningSpeed": "已获取",
        "interestDirection": "已获取",
        "goalOrientation": "已获取",
    }
    assert payload["estimated_remaining_rounds"] == 0

    profile_response = client.get(f"/users/{test_user.id}/profile")
    assert profile_response.status_code == 200
    dimensions = profile_response.json()["profile_dimensions"]
    assert dimensions["knowledgeBase"] == "学过基础概念、做过小项目"
    assert dimensions["cognitiveStyle"] == "视觉型、动手实践型"
    assert dimensions["errorPreference"] == "概念理解容易混淆、代码调试容易卡"
    assert dimensions["learningSpeed"] == "慢一点分步讲"
    assert dimensions["interestDirection"] == "后端开发、AI 应用"
    assert dimensions["goalOrientation"] == "求职实习、完成项目"


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
    context = payload["habits"]["agent_collaboration_context"]
    assert context["source"] == "learner_profile_agent"
    assert context["agent_handoff"]["resource_generation_agent"]


def test_profile_dimension_delete_updates_status_and_agent_context(test_user) -> None:
    """Deleting a profile record should remove it from status and downstream agent context."""

    client = TestClient(app)
    update_response = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "visual",
            "profile_dimensions": {
                "knowledgeBase": "已经学过基础语法",
                "cognitiveStyle": "视觉型",
                "learningSpeed": "适中",
            },
        },
    )
    assert update_response.status_code == 200

    response = client.delete(f"/users/{test_user.id}/profile/dimensions/cognitiveStyle")

    assert response.status_code == 200
    payload = response.json()
    assert "cognitiveStyle" not in payload["profile_dimensions"]
    assert payload["learning_style"] == ""
    context = payload["habits"]["agent_collaboration_context"]
    assert "cognitiveStyle" not in context["profile_dimensions"]
    assert context["learning_style"] == ""
    assert context["preferred_resource_modes"] == ["worked_example", "guided_practice"]
    assert not context["agent_handoff"]["resource_generation_agent"]

    status_response = client.get(f"/users/{test_user.id}/profile/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["dimensions_filled"] == 2
    assert status_payload["completed"] is False
    assert status_payload["dimensions"]["cognitiveStyle"] is False


def test_profile_status_and_read_ignore_bulk_dump_values(test_user) -> None:
    """Malformed bulk-dump values should not be treated as completed profile dimensions."""

    client = TestClient(app)
    response = client.put(
        f"/users/{test_user.id}/profile",
        json={
            "learning_style": "reading",
            "profile_dimensions": {
                "knowledgeBase": "我想一次补充画像多维度：\n知识基础：有系统学习经历\n认知风格：文本型",
                "cognitiveStyle": "文本型",
                "goalOrientation": "我想一次补充画像多维度：\n目标导向：通过认证\n兴趣方向：真实业务案例",
            },
        },
    )
    assert response.status_code == 200

    profile_payload = client.get(f"/users/{test_user.id}/profile").json()
    assert "knowledgeBase" not in profile_payload["profile_dimensions"]
    assert "goalOrientation" not in profile_payload["profile_dimensions"]
    assert profile_payload["profile_dimensions"]["cognitiveStyle"] == "文本型"

    status_payload = client.get(f"/users/{test_user.id}/profile/status").json()
    assert status_payload["dimensions_filled"] == 1
    assert status_payload["dimensions"]["knowledgeBase"] is False
    assert status_payload["dimensions"]["goalOrientation"] is False
    assert status_payload["dimensions"]["cognitiveStyle"] is True


def test_profile_chat_analyzes_generic_short_answers_and_builds_agent_context(test_user) -> None:
    """Profile chat should analyze short answers by the active dimension, without subject-specific rules."""

    client = TestClient(app)

    opening = client.post(f"/users/{test_user.id}/profile/chat", json={"message": ""})
    assert opening.status_code == 200

    replies: list[str] = []
    payload = None
    for answer in ["入门基础", "图形化说明", "慢一点", "抽象概念总是卡住"]:
        response = client.post(f"/users/{test_user.id}/profile/chat", json={"message": answer})
        assert response.status_code == 200
        payload = response.json()
        replies.append(payload["reply"])

    assert payload is not None
    assert payload["profile_completeness"]["knowledgeBase"] == "已获取"
    assert payload["profile_completeness"]["cognitiveStyle"] == "已获取"
    assert payload["profile_completeness"]["errorPreference"] == "已获取"
    assert "我已分析并记录" in replies[0]
    assert "哪类题目或知识点" not in replies[2]

    profile_response = client.get(f"/users/{test_user.id}/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    dimensions = profile["profile_dimensions"]
    assert dimensions["knowledgeBase"] == "入门基础"
    assert dimensions["cognitiveStyle"] == "视觉型"
    assert dimensions["learningSpeed"] == "较慢"
    assert "抽象概念总是卡住" in dimensions["errorPreference"]

    context = profile["habits"]["agent_collaboration_context"]
    assert context["source"] == "learner_profile_agent"
    assert context["learning_style"] == "visual"
    assert context["agent_handoff"]["resource_generation_agent"]
    assert context["agent_handoff"]["exercise_generation_agent"]
