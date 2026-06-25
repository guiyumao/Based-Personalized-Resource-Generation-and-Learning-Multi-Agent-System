"""Unit tests for tutoring QA enhancements."""

import pytest

from common.schemas.agent import QARequest
from services.agent_service.app.services import qa_service as qa_service_module
from services.agent_service.app.services.qa_service import QAService


@pytest.fixture(autouse=True)
def stub_realtime_qa_llm(monkeypatch):
    """Keep unit tests deterministic while production still calls the configured LLM."""

    def fake_learning_response(self, *, conversation, generated_resource, generated_exercises, **kwargs):
        knowledge_point = str(conversation.get("knowledge_point") or conversation.get("subject") or "当前知识点")
        parts = [f"已围绕{knowledge_point}生成实时学习回答。"]
        if generated_resource is not None:
            parts.append("已生成课件。")
        if generated_exercises is not None:
            parts.append("已生成习题。")
        return "\n".join(parts)

    def fake_study_suggestions(self, **kwargs):
        return ["模型生成：先复盘本轮关键概念。", "模型生成：再用练习检验理解。"]

    monkeypatch.setattr(QAService, "_generate_learning_response_with_llm", fake_learning_response)
    monkeypatch.setattr(QAService, "_generate_study_suggestions_with_llm", fake_study_suggestions)


def test_qa_fallback_includes_context_snippets_and_confidence() -> None:
    """Fallback QA responses should expose grounded snippets and confidence."""

    service = QAService()
    response = service.analyze_question(
        QARequest(
            student_id="1",
            subject="Python",
            grade="freshman",
            question="Python 循环和 while 有什么区别？",
        )
    )

    assert response["context_snippets"]
    assert response["confidence"] is not None
    assert 0 <= response["confidence"] <= 1
    assert "structured_analysis" in response
    assert response["structured_analysis"]["study_suggestions"][0].startswith("模型生成")
    assert "补充更具体的知识点名称后" not in "\n".join(response["structured_analysis"]["study_suggestions"])


def test_qa_generates_resource_and_exercises_when_requested(monkeypatch) -> None:
    """QA should return structured courseware and exercise payloads together."""

    class FakeResourceGenerationService:
        def generate_courseware_with_plan(self, request):
            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "resource_type": "courseware",
                "resource_style": request.resource_style,
                "generation_plan": {
                    "request_summary": request.request_text,
                    "knowledge_point": request.knowledge_point,
                    "resource_type": "courseware",
                    "resource_style": request.resource_style,
                    "title_suggestion": f"{request.knowledge_point} 课件",
                    "suggested_outline": ["概念", "例题", "应用"],
                    "target_word_count": 1200,
                    "difficulty": "intermediate",
                    "personalization_hints": [],
                    "analysis_source": "request",
                },
                "references": [],
                "personalization": {},
                "content": "# 定积分课件\n\n## 概念\n定积分表示累积量。",
                "variants": [],
            }

    class FakeExerciseGenerationService:
        def generate_exercises(self, request):
            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "summary": "已生成 5 道定积分练习题。",
                "personalization": {
                    "mastery_score": 0,
                    "correct_rate": 0,
                    "answered_count": 0,
                    "weak_question_types": [],
                    "basis": [],
                    "recent_mistakes": [],
                },
                "exercises": [
                    {
                        "exercise_id": 1,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "short_answer",
                        "difficulty": "intermediate",
                        "prompt": "说明定积分的几何意义。",
                        "options": [],
                        "answer": "表示带符号面积。",
                        "analysis": "关键在于区分面积和带符号面积。",
                    }
                ],
            }

    monkeypatch.setattr(qa_service_module, "ResourceGenerationService", FakeResourceGenerationService)
    monkeypatch.setattr(qa_service_module, "ExerciseGenerationService", FakeExerciseGenerationService)

    service = QAService()
    response = service.analyze_question(
        QARequest(
            student_id="1",
            subject="高等数学",
            grade="大学",
            question="我要学习定积分，补充说明知识点，再生成课件和习题",
            current_knowledge_points=["定积分"],
        )
    )

    assert response["generated_resource"] is not None
    assert response["generated_exercises"] is not None
    assert "定积分" in response["student_response"]
    assert "已生成课件" in response["structured_analysis"]["learning_state"]
    assert "已生成习题" in response["structured_analysis"]["learning_state"]


def test_qa_recognizes_generate_practice_wording(monkeypatch) -> None:
    """Common wording like '生成配套练习' should trigger exercise generation."""

    class FakeExerciseGenerationService:
        def generate_exercises(self, request):
            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "summary": "已生成 3 道配套练习。",
                "personalization": {},
                "exercises": [
                    {
                        "exercise_id": 1,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "short_answer",
                        "difficulty": "intermediate",
                        "prompt": "说明极限的定义。",
                        "options": [],
                        "answer": "描述函数值或数列项的逼近趋势。",
                        "analysis": "抓住逼近过程和目标值两个核心要素。",
                    }
                ],
            }

    monkeypatch.setattr(qa_service_module, "ExerciseGenerationService", FakeExerciseGenerationService)

    service = QAService()
    response = service.analyze_question(
        QARequest(
            student_id="1",
            subject="高等数学",
            grade="大学",
            question="生成配套练习",
            current_knowledge_points=["极限"],
        )
    )

    assert response["generated_exercises"] is not None
    assert "已生成" in response["student_response"]
    assert "已生成习题" in response["structured_analysis"]["learning_state"]
    assert response["structured_analysis"]["study_suggestions"][0].startswith("模型生成")
    assert "知识点补充" not in response["student_response"]


def test_qa_follow_up_continues_previous_context(db_session, test_user) -> None:
    """Short follow-up turns should inherit the previous knowledge point."""

    service = QAService(db_session)

    first = service.analyze_question(
        QARequest(
            student_id=str(test_user.id),
            subject="高等数学",
            grade="大学",
            question="我要学习高等数学的定积分，补充说明知识点",
            current_knowledge_points=["定积分"],
        )
    )
    second = service.analyze_question(
        QARequest(
            student_id=str(test_user.id),
            subject="",
            grade="大学",
            question="好的继续",
            session_id=first["session_id"],
            current_knowledge_points=[],
        )
    )

    assert second["message_history"][-1]["created_at"].endswith("+00:00")
    assert "定积分" in second["student_response"]
    assert "承接上一轮上下文" in second["structured_analysis"]["learning_state"]


def test_qa_message_history_timestamps_are_timezone_aware(db_session, test_user) -> None:
    """Persisted QA history should serialize timestamps with explicit timezone info."""

    service = QAService(db_session)
    response = service.analyze_question(
        QARequest(
            student_id=str(test_user.id),
            subject="Python",
            grade="freshman",
            question="解释一下 Python 循环",
        )
    )

    assert response["message_history"]
    assert all(item["created_at"].endswith("+00:00") for item in response["message_history"])


def test_qa_refreshes_broken_session_title() -> None:
    """Broken or garbled titles should still trigger QA title refresh."""

    service = QAService()

    assert service._should_refresh_session_title("????????????")
    assert service._should_refresh_session_title("？？？？？")


def test_detect_intent_mode_distinguishes_general_and_learning() -> None:
    """Intent detection should separate open-domain questions from learning tasks."""

    general_intent = QAService.detect_intent_mode_from_request(
        QARequest(
            student_id="1",
            subject="",
            grade="大学",
            question="今天星期几？",
            current_knowledge_points=[],
        )
    )
    learning_intent = QAService.detect_intent_mode_from_request(
        QARequest(
            student_id="1",
            subject="",
            grade="大学",
            question="帮我讲解定积分，并生成配套习题",
            current_knowledge_points=[],
        )
    )

    assert general_intent["mode"] == "general"
    assert learning_intent["mode"] == "learning"


def test_infer_route_knowledge_point_from_question_text() -> None:
    """Route knowledge point inference should pick explicit topics from the question."""

    knowledge_point = QAService.infer_route_knowledge_point_from_request(
        QARequest(
            student_id="1",
            subject="",
            grade="大学",
            question="大学物理的练习题",
            current_knowledge_points=[],
        )
    )

    assert knowledge_point == "大学物理"
