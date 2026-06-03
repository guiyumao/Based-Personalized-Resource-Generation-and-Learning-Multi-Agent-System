"""Evaluation and reporting routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from common.schemas.response import ApiResponse
from services.evaluation_service.app.schemas.report import (
    AnalyticsSuggestion,
    AnswerEvaluationResult,
    AnswerRecordIn,
    AnswerRecordSubmission,
    BatchAnswerSubmission,
    BatchEvaluationResponse,
    MistakeItem,
    MistakeNotebook,
    MonthlyReportResponse,
    PracticeFeedback,
    PracticeSubmission,
    QAMistakeSubmission,
    RemedialExerciseSet,
    ReportDetail,
    ReportSummary,
    StageReportResponse,
)
from services.evaluation_service.app.services.report_service import ReportService

router = APIRouter()


@router.post("/submit", response_model=ApiResponse[AnswerEvaluationResult])
async def submit_answer(payload: AnswerRecordSubmission) -> ApiResponse[AnswerEvaluationResult]:
    """Process one answer submission."""

    service = ReportService()
    try:
        result = await service.submit_answer(payload)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Answer evaluated successfully.")


@router.post("/batch_submit", response_model=ApiResponse[BatchEvaluationResponse])
async def batch_submit(payload: BatchAnswerSubmission) -> ApiResponse[BatchEvaluationResponse]:
    """Process a batch of answer submissions."""

    service = ReportService()
    try:
        result = await service.batch_submit(payload)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Batch evaluation completed successfully.")


@router.get("/stage-report/{user_id}/{chapter_id}", response_model=ApiResponse[StageReportResponse])
async def get_stage_report(user_id: str, chapter_id: str) -> ApiResponse[StageReportResponse]:
    """Generate a chapter-level stage report."""

    service = ReportService()
    try:
        result = await service.generate_stage_report(user_id, chapter_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Stage report generated successfully.")


@router.get("/monthly-report/{user_id}", response_model=ApiResponse[MonthlyReportResponse])
async def get_monthly_report(user_id: str) -> ApiResponse[MonthlyReportResponse]:
    """Generate a rolling 30-day monthly report."""

    service = ReportService()
    try:
        result = await service.generate_monthly_report(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Monthly report generated successfully.")


@router.post("/answers", response_model=ApiResponse[AnswerEvaluationResult])
async def submit_answer_record(payload: AnswerRecordIn) -> ApiResponse[AnswerEvaluationResult]:
    """Compatibility route for legacy raw answer submission."""

    service = ReportService()
    try:
        result = await service.submit_legacy_answer(payload)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Answer record submitted successfully.")


@router.post("/practice/submit", response_model=ApiResponse[PracticeFeedback])
async def submit_practice_answer(payload: PracticeSubmission) -> ApiResponse[PracticeFeedback]:
    """Compatibility route for student practice submissions."""

    service = ReportService()
    try:
        result = await service.evaluate_practice(payload)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Practice answer evaluated successfully.")


@router.post("/mistakes/qa", response_model=ApiResponse[MistakeItem])
async def submit_qa_mistake(payload: QAMistakeSubmission) -> ApiResponse[MistakeItem]:
    """Compatibility route for QA-derived mistakes."""

    service = ReportService()
    try:
        result = await service.record_qa_mistake(payload)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="QA mistake stored successfully.")


@router.get("/reports/stage/{user_id}", response_model=ApiResponse[ReportSummary])
async def get_stage_report_legacy(user_id: int) -> ApiResponse[ReportSummary]:
    """Compatibility route for old stage summary callers."""

    service = ReportService()
    try:
        result = await service.generate_stage_report_summary_legacy(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Stage report generated successfully.")


@router.get("/reports/stage/{user_id}/detail", response_model=ApiResponse[ReportDetail])
async def get_stage_report_detail(user_id: int) -> ApiResponse[ReportDetail]:
    """Compatibility route for old detailed stage report callers."""

    service = ReportService()
    try:
        result = await service.generate_stage_report_detail(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Detailed stage report generated successfully.")


@router.get("/reports/comprehensive/{user_id}", response_model=ApiResponse[ReportSummary])
async def get_comprehensive_report(user_id: int) -> ApiResponse[ReportSummary]:
    """Compatibility route for monthly summary callers."""

    service = ReportService()
    try:
        result = await service.generate_comprehensive_report(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Comprehensive report generated successfully.")


@router.get("/reports/comprehensive/{user_id}/detail", response_model=ApiResponse[ReportDetail])
async def get_comprehensive_report_detail(user_id: int) -> ApiResponse[ReportDetail]:
    """Compatibility route for detailed monthly report callers."""

    service = ReportService()
    try:
        result = await service.generate_comprehensive_report_detail(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Detailed comprehensive report generated successfully.")


@router.get("/mistakes/{user_id}", response_model=ApiResponse[dict[str, object]])
async def get_mistake_statistics(user_id: int) -> ApiResponse[dict[str, object]]:
    """Return mistake statistics."""

    service = ReportService()
    try:
        result = await service.get_mistake_statistics(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Mistake statistics fetched successfully.")


@router.get("/mistakes/{user_id}/detail", response_model=ApiResponse[MistakeNotebook])
async def get_mistake_notebook(user_id: int) -> ApiResponse[MistakeNotebook]:
    """Return the learner mistake notebook."""

    service = ReportService()
    try:
        result = await service.get_mistake_notebook(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Mistake notebook fetched successfully.")


@router.get("/mistakes/{user_id}/remedial", response_model=ApiResponse[RemedialExerciseSet])
async def get_remedial_exercises(user_id: int) -> ApiResponse[RemedialExerciseSet]:
    """Return remedial exercises derived from real mistakes."""

    service = ReportService()
    try:
        result = await service.generate_remedial_exercises(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Remedial exercises generated successfully.")


@router.get("/profiles/{user_id}/snapshot", response_model=ApiResponse[dict[str, object]])
async def get_profile_snapshot(user_id: int) -> ApiResponse[dict[str, object]]:
    """Return a learner profile snapshot."""

    service = ReportService()
    try:
        result = await service.generate_profile_snapshot(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Profile snapshot generated successfully.")


@router.get("/reports/suggestions/{user_id}", response_model=ApiResponse[AnalyticsSuggestion])
async def get_learning_suggestions(user_id: int) -> ApiResponse[AnalyticsSuggestion]:
    """Return personalized suggestions based on real answer data."""

    service = ReportService()
    try:
        result = await service.generate_learning_suggestions(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Learning suggestions generated successfully.")


def _translate_service_error(exc: Exception) -> HTTPException:
    """Map service-layer exceptions into HTTP errors."""

    message = str(exc)
    if "not found" in message.lower():
        return HTTPException(status_code=404, detail=message)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=503, detail=message or "Evaluation service failed.")
