"""Regression tests for QA knowledge-point inference priority."""

from common.schemas.agent import QARequest
from services.agent_service.app.services.qa_service import QAService


def test_infer_route_knowledge_point_prefers_question_over_subject(monkeypatch) -> None:
    """Explicit topics in the latest question should override stale subject context."""

    monkeypatch.setattr(
        QAService,
        "_extract_explicit_topic_from_question",
        lambda self, question: "University Physics" if "physics" in question.lower() else "",
    )

    knowledge_point = QAService.infer_route_knowledge_point_from_request(
        QARequest(
            student_id="1",
            subject="Python",
            grade="freshman",
            question="Please generate physics exercises",
            current_knowledge_points=[],
        )
    )

    assert knowledge_point == "University Physics"


def test_infer_route_knowledge_point_handles_real_chinese_text() -> None:
    """Real Chinese prompts should infer the explicit knowledge point before stale subject fallback."""

    knowledge_point = QAService.infer_route_knowledge_point_from_request(
        QARequest(
            student_id="1",
            subject="Python",
            grade="freshman",
            question="\u5927\u5b66\u7269\u7406\u7684\u7ec3\u4e60\u9898",
            current_knowledge_points=[],
        )
    )

    assert knowledge_point == "\u5927\u5b66\u7269\u7406"


def test_infer_route_knowledge_point_handles_chinese_subtopic_without_kb_entry() -> None:
    """A concrete Chinese subtopic should still beat stale subject fallback even without a KB article."""

    knowledge_point = QAService.infer_route_knowledge_point_from_request(
        QARequest(
            student_id="1",
            subject="Python",
            grade="freshman",
            question="\u751f\u6210\u5927\u5b66\u7269\u7406\u7535\u78c1\u573a\u7684\u7ec3\u4e60\u9898",
            current_knowledge_points=[],
        )
    )

    assert knowledge_point == "\u5927\u5b66\u7269\u7406\u7535\u78c1\u573a"


def test_detect_intent_mode_prefers_learning_for_chinese_generation_request() -> None:
    """Chinese exercise-generation wording should be classified as learning intent."""

    intent = QAService.detect_intent_mode_from_request(
        QARequest(
            student_id="1",
            subject="Python",
            grade="freshman",
            question="\u751f\u6210\u5927\u5b66\u7269\u7406\u7535\u78c1\u573a\u7684\u7ec3\u4e60\u9898",
            current_knowledge_points=[],
        )
    )

    assert intent["mode"] == "learning"
