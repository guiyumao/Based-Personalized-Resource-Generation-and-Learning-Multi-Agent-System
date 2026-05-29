"""Evaluation and report routes."""

from fastapi import APIRouter

from common.schemas.response import ApiResponse
from services.evaluation_service.app.schemas.report import (
    AnswerRecordIn,
    MistakeNotebook,
    PracticeFeedback,
    PracticeSubmission,
    RemedialExerciseSet,
    ReportDetail,
    ReportSummary,
)
from services.evaluation_service.app.services.report_service import ReportService

router = APIRouter()
report_service = ReportService()


@router.post("/answers", response_model=ApiResponse[AnswerRecordIn])
def submit_answer_record(payload: AnswerRecordIn) -> ApiResponse[AnswerRecordIn]:
    """Submit one answer record for evaluation."""

    return ApiResponse(
        data=report_service.submit_answer(payload),
        message="Answer record submitted successfully.",
    )


@router.post("/practice/submit", response_model=ApiResponse[PracticeFeedback])
def submit_practice_answer(payload: PracticeSubmission) -> ApiResponse[PracticeFeedback]:
    """Evaluate one practice answer and return immediate feedback."""

    return ApiResponse(
        data=report_service.evaluate_practice(payload),
        message="Practice answer evaluated successfully.",
    )


@router.get("/reports/stage/{user_id}", response_model=ApiResponse[ReportSummary])
def get_stage_report(user_id: int) -> ApiResponse[ReportSummary]:
    """Generate a stage report."""

    return ApiResponse(
        data=report_service.generate_stage_report(user_id),
        message="Stage report generated successfully.",
    )


@router.get("/reports/stage/{user_id}/detail", response_model=ApiResponse[ReportDetail])
def get_stage_report_detail(user_id: int) -> ApiResponse[ReportDetail]:
    """Generate a detailed stage report for the student workspace."""

    return ApiResponse(
        data=report_service.generate_stage_report_detail(user_id),
        message="Detailed stage report generated successfully.",
    )


@router.get("/reports/comprehensive/{user_id}", response_model=ApiResponse[ReportSummary])
def get_comprehensive_report(user_id: int) -> ApiResponse[ReportSummary]:
    """Generate a comprehensive report."""

    return ApiResponse(
        data=report_service.generate_comprehensive_report(user_id),
        message="Comprehensive report generated successfully.",
    )


@router.get("/reports/comprehensive/{user_id}/detail", response_model=ApiResponse[ReportDetail])
def get_comprehensive_report_detail(user_id: int) -> ApiResponse[ReportDetail]:
    """Generate a detailed comprehensive report for the student workspace."""

    return ApiResponse(
        data=report_service.generate_comprehensive_report_detail(user_id),
        message="Detailed comprehensive report generated successfully.",
    )


@router.get("/mistakes/{user_id}", response_model=ApiResponse[dict[str, object]])
def get_mistake_statistics(user_id: int) -> ApiResponse[dict[str, object]]:
    """Return mistake statistics."""

    return ApiResponse(
        data=report_service.get_mistake_statistics(user_id),
        message="Mistake statistics fetched successfully.",
    )


@router.get("/mistakes/{user_id}/detail", response_model=ApiResponse[MistakeNotebook])
def get_mistake_notebook(user_id: int) -> ApiResponse[MistakeNotebook]:
    """Return the learner mistake notebook."""

    return ApiResponse(
        data=report_service.get_mistake_notebook(user_id),
        message="Mistake notebook fetched successfully.",
    )


@router.get("/mistakes/{user_id}/remedial", response_model=ApiResponse[RemedialExerciseSet])
def get_remedial_exercises(user_id: int) -> ApiResponse[RemedialExerciseSet]:
    """Generate remedial exercises from the learner's mistake notebook."""

    return ApiResponse(
        data=report_service.generate_remedial_exercises(user_id),
        message="Remedial exercises generated successfully.",
    )


@router.get("/profiles/{user_id}/snapshot", response_model=ApiResponse[dict[str, object]])
def get_profile_snapshot(user_id: int) -> ApiResponse[dict[str, object]]:
    """Return a learner profile dashboard snapshot derived from recent practice."""

    return ApiResponse(
        data=report_service.generate_profile_snapshot(user_id),
        message="Profile snapshot generated successfully.",
    )
