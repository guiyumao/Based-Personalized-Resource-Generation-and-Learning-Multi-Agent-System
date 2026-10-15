"""Evaluation and reporting routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from common.config import get_settings
from common.dependencies import get_current_user, require_self_or_staff
from common.models.learning import User
from common.performance import set_trace_context
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
    MistakeNotebookClearResult,
    MonthlyReportResponse,
    PracticeFeedback,
    PracticeSubmission,
    QAMistakeSubmission,
    RemedialExerciseSet,
    ReportDashboardResponse,
    ReportDetail,
    ReportSummary,
    StageReportResponse,
)
from services.evaluation_service.app.services.report_service import ReportService

router = APIRouter()


def _set_report_trace(user_id: str | int, task_type: str, **attributes: object) -> None:
    settings = get_settings()
    set_trace_context(
        user_id=user_id,
        task_type=task_type,
        deadline_seconds=settings.report_deadline_seconds,
        retry_budget=settings.max_total_retries,
        **attributes,
    )


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

    _set_report_trace(user_id, "stage_report_generation", chapter_id=chapter_id)
    service = ReportService()
    try:
        result = await service.generate_stage_report(user_id, chapter_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Stage report generated successfully.")


@router.get("/monthly-report/{user_id}", response_model=ApiResponse[MonthlyReportResponse])
async def get_monthly_report(user_id: str) -> ApiResponse[MonthlyReportResponse]:
    """Generate a rolling 30-day monthly report."""

    _set_report_trace(user_id, "monthly_report_generation")
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
async def get_stage_report_legacy(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[ReportSummary]:
    """Compatibility route for old stage summary callers."""

    require_self_or_staff(user_id, current_user)

    _set_report_trace(user_id, "stage_report_summary")
    service = ReportService()
    try:
        result = await service.generate_stage_report_summary_legacy(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Stage report generated successfully.")


@router.get("/reports/stage/{user_id}/detail", response_model=ApiResponse[ReportDetail])
async def get_stage_report_detail(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[ReportDetail]:
    """Compatibility route for old detailed stage report callers."""

    require_self_or_staff(user_id, current_user)

    _set_report_trace(user_id, "stage_report_detail")
    service = ReportService()
    try:
        result = await service.generate_stage_report_detail(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Detailed stage report generated successfully.")


@router.get("/reports/comprehensive/{user_id}", response_model=ApiResponse[ReportSummary])
async def get_comprehensive_report(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[ReportSummary]:
    """Compatibility route for monthly summary callers."""

    require_self_or_staff(user_id, current_user)

    _set_report_trace(user_id, "comprehensive_report_summary")
    service = ReportService()
    try:
        result = await service.generate_comprehensive_report(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Comprehensive report generated successfully.")


@router.get("/reports/comprehensive/{user_id}/detail", response_model=ApiResponse[ReportDetail])
async def get_comprehensive_report_detail(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[ReportDetail]:
    """Compatibility route for detailed monthly report callers."""

    require_self_or_staff(user_id, current_user)

    _set_report_trace(user_id, "comprehensive_report_detail")
    service = ReportService()
    try:
        result = await service.generate_comprehensive_report_detail(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Detailed comprehensive report generated successfully.")


@router.get("/reports/dashboard/{user_id}", response_model=ApiResponse[ReportDashboardResponse])
async def get_report_dashboard(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[ReportDashboardResponse]:
    """Return all student report-page data from one database snapshot."""

    require_self_or_staff(user_id, current_user)

    _set_report_trace(user_id, "report_dashboard")
    service = ReportService()
    try:
        result = await service.generate_dashboard(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Report dashboard generated successfully.")


@router.get("/mistakes/{user_id}", response_model=ApiResponse[dict[str, object]])
async def get_mistake_statistics(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[dict[str, object]]:
    """Return mistake statistics."""

    require_self_or_staff(user_id, current_user)

    service = ReportService()
    try:
        result = await service.get_mistake_statistics(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Mistake statistics fetched successfully.")


@router.get("/mistakes/{user_id}/detail", response_model=ApiResponse[MistakeNotebook])
async def get_mistake_notebook(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[MistakeNotebook]:
    """Return the learner mistake notebook."""

    require_self_or_staff(user_id, current_user)

    service = ReportService()
    try:
        result = await service.get_mistake_notebook(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Mistake notebook fetched successfully.")


@router.get("/mistakes/{user_id}/teacher-detail", response_model=ApiResponse[MistakeNotebook])
async def get_teacher_mistake_notebook(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[MistakeNotebook]:
    """Return all real mistakes for teacher-side detail views."""

    if current_user.role not in {"teacher", "admin"}:
        raise HTTPException(status_code=403, detail="Teacher access required")

    service = ReportService()
    try:
        result = await service.get_teacher_mistake_notebook(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Teacher mistake notebook fetched successfully.")


@router.delete("/mistakes/{user_id}", response_model=ApiResponse[MistakeNotebookClearResult])
async def clear_mistake_notebook(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[MistakeNotebookClearResult]:
    """Clear the learner's visible mistake notebook entries."""

    require_self_or_staff(user_id, current_user)

    service = ReportService()
    try:
        result = await service.clear_mistake_notebook(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Mistake notebook cleared successfully.")


@router.get("/mistakes/{user_id}/remedial", response_model=ApiResponse[RemedialExerciseSet])
async def get_remedial_exercises(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[RemedialExerciseSet]:
    """Return remedial exercises derived from real mistakes."""

    require_self_or_staff(user_id, current_user)

    service = ReportService()
    try:
        result = await service.generate_remedial_exercises(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Remedial exercises generated successfully.")


@router.get("/profiles/{user_id}/snapshot", response_model=ApiResponse[dict[str, object]])
async def get_profile_snapshot(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[dict[str, object]]:
    """Return a learner profile snapshot."""

    require_self_or_staff(user_id, current_user)

    service = ReportService()
    try:
        result = await service.generate_profile_snapshot(user_id)
    except Exception as exc:  # pragma: no cover - route translation
        raise _translate_service_error(exc) from exc
    return ApiResponse(data=result, message="Profile snapshot generated successfully.")


@router.get("/reports/suggestions/{user_id}", response_model=ApiResponse[AnalyticsSuggestion])
async def get_learning_suggestions(
    user_id: int, current_user: User = Depends(get_current_user)
) -> ApiResponse[AnalyticsSuggestion]:
    """Return personalized suggestions based on real answer data."""

    require_self_or_staff(user_id, current_user)

    _set_report_trace(user_id, "learning_suggestions")
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
