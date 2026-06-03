"""Unit tests for tutoring QA enhancements."""

from common.schemas.agent import QARequest
from services.agent_service.app.services.qa_service import QAService


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
    assert response["confidence"] == 0.8
    assert "structured_analysis" in response
