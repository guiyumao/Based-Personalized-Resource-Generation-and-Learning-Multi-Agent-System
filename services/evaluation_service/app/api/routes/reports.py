"""Evaluation and report routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.schemas.response import ApiResponse
from services.evaluation_service.app.schemas.report import (
    AnalyticsSuggestion,
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


@router.post("/answers", response_model=ApiResponse[AnswerRecordIn])
def submit_answer_record(payload: AnswerRecordIn, db: Session = Depends(get_db)) -> ApiResponse[AnswerRecordIn]:
    """Submit one answer record for evaluation."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.submit_answer(payload),
        message="Answer record submitted successfully.",
    )


@router.post("/practice/submit", response_model=ApiResponse[PracticeFeedback])
def submit_practice_answer(payload: PracticeSubmission, db: Session = Depends(get_db)) -> ApiResponse[PracticeFeedback]:
    """Evaluate one practice answer and return immediate feedback."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.evaluate_practice(payload),
        message="Practice answer evaluated successfully.",
    )


@router.get("/reports/stage/{user_id}", response_model=ApiResponse[ReportSummary])
def get_stage_report(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[ReportSummary]:
    """Generate a stage report."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.generate_stage_report(user_id),
        message="Stage report generated successfully.",
    )


@router.get("/reports/stage/{user_id}/detail", response_model=ApiResponse[ReportDetail])
def get_stage_report_detail(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[ReportDetail]:
    """Generate a detailed stage report for the student workspace."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.generate_stage_report_detail(user_id),
        message="Detailed stage report generated successfully.",
    )


@router.get("/reports/comprehensive/{user_id}", response_model=ApiResponse[ReportSummary])
def get_comprehensive_report(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[ReportSummary]:
    """Generate a comprehensive report."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.generate_comprehensive_report(user_id),
        message="Comprehensive report generated successfully.",
    )


@router.get("/reports/comprehensive/{user_id}/detail", response_model=ApiResponse[ReportDetail])
def get_comprehensive_report_detail(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[ReportDetail]:
    """Generate a detailed comprehensive report for the student workspace."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.generate_comprehensive_report_detail(user_id),
        message="Detailed comprehensive report generated successfully.",
    )


@router.get("/mistakes/{user_id}", response_model=ApiResponse[dict[str, object]])
def get_mistake_statistics(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[dict[str, object]]:
    """Return mistake statistics."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.get_mistake_statistics(user_id),
        message="Mistake statistics fetched successfully.",
    )


@router.get("/mistakes/{user_id}/detail", response_model=ApiResponse[MistakeNotebook])
def get_mistake_notebook(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[MistakeNotebook]:
    """Return the learner mistake notebook."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.get_mistake_notebook(user_id),
        message="Mistake notebook fetched successfully.",
    )


@router.get("/mistakes/{user_id}/remedial", response_model=ApiResponse[RemedialExerciseSet])
def get_remedial_exercises(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[RemedialExerciseSet]:
    """Generate remedial exercises from the learner's mistake notebook."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.generate_remedial_exercises(user_id),
        message="Remedial exercises generated successfully.",
    )


@router.get("/profiles/{user_id}/snapshot", response_model=ApiResponse[dict[str, object]])
def get_profile_snapshot(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[dict[str, object]]:
    """Return a learner profile dashboard snapshot derived from recent practice."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.generate_profile_snapshot(user_id),
        message="Profile snapshot generated successfully.",
    )


@router.get("/reports/suggestions/{user_id}", response_model=ApiResponse[AnalyticsSuggestion])
def get_learning_suggestions(user_id: int, db: Session = Depends(get_db)) -> ApiResponse[AnalyticsSuggestion]:
    """Return personalized learning suggestions distilled from practice history."""

    report_service = ReportService(db)
    return ApiResponse(
        data=report_service.generate_learning_suggestions(user_id),
        message="Learning suggestions generated successfully.",
    )
