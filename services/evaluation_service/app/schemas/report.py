"""Schemas for the evaluation service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ExerciseType = Literal["choice", "fill", "judge", "short_answer", "code", "blank", "programming"]
DifficultyLevel = Literal["basic", "intermediate", "advanced"]


class AnswerRecordSubmission(BaseModel):
    """One answer submission pushed from the frontend or user-service."""

    user_id: str
    exercise_id: str
    user_answer: str
    is_correct: bool | None = None
    time_spent: float = Field(ge=0)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    exercise_type: ExerciseType
    difficulty: DifficultyLevel
    standard_answer: str | None = None
    reference_answer: str | None = None
    max_score: float | None = Field(default=None, ge=0)
    exercise_content: str | None = None
    explanation: str | None = None
    chapter_id: str | None = None
    chapter_name: str | None = None
    student_name: str | None = None

    @model_validator(mode="after")
    def validate_subjective_requirements(self) -> "AnswerRecordSubmission":
        normalized_type = normalize_exercise_type(self.exercise_type)
        if normalized_type in {"short_answer", "code"}:
            if not self.reference_answer:
                raise ValueError("reference_answer is required for short_answer and code submissions.")
            if self.max_score is None:
                raise ValueError("max_score is required for short_answer and code submissions.")
        return self


class BatchAnswerSubmission(BaseModel):
    """Batch submission payload."""

    records: list[AnswerRecordSubmission] = Field(min_length=1)


class KnowledgePointFeedback(BaseModel):
    """One knowledge point update after evaluation."""

    knowledge_point_id: str
    mastery_score: float = Field(ge=0, le=100)
    recent_accuracy: float = Field(ge=0, le=100)
    consecutive_incorrect: int = Field(ge=0)
    weak: bool = False
    error_pattern: str


class AnswerEvaluationResult(BaseModel):
    """Structured evaluation result for one submitted answer."""

    user_id: str
    exercise_id: str
    answer_record_id: int
    is_correct: bool
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    ratio: float = Field(ge=0, le=1)
    comment: str
    suggestion: str
    encouragement: str
    explanation: str | None = None
    error_pattern: str
    weak_knowledge_points: list[str] = Field(default_factory=list)
    knowledge_points: list[KnowledgePointFeedback] = Field(default_factory=list)
    created_at: datetime


class BatchEvaluationResponse(BaseModel):
    """Batch evaluation result."""

    results: list[AnswerEvaluationResult]
    total_submissions: int = Field(ge=0)
    correct_submissions: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=100)


class KnowledgePointStageStatus(BaseModel):
    """Aggregated chapter status for one knowledge point."""

    knowledge_point_id: str
    mastery_score: float = Field(ge=0, le=100)
    accuracy: float = Field(ge=0, le=100)
    attempts: int = Field(ge=0)
    weak: bool = False
    dominant_error_pattern: str


class StageReportResponse(BaseModel):
    """Chapter-level learning report."""

    user_id: str
    chapter_id: str
    chapter_name: str
    generated_at: datetime
    overall_accuracy: float = Field(ge=0, le=100)
    total_answers: int = Field(ge=0)
    total_time_spent: float = Field(ge=0)
    top_weak_points: list[str] = Field(default_factory=list)
    knowledge_points: list[KnowledgePointStageStatus] = Field(default_factory=list)
    report_text: str
    suggested_next_focus: list[str] = Field(default_factory=list)


class MonthlyReportResponse(BaseModel):
    """Monthly comprehensive report."""

    user_id: str
    generated_at: datetime
    start_date: datetime
    end_date: datetime
    chapters_completed: int = Field(ge=0)
    overall_accuracy: float = Field(ge=0, le=100)
    avg_daily_time: float = Field(ge=0)
    most_improved: str | None = None
    still_weak: list[str] = Field(default_factory=list)
    summary_text: str


class ReportSummary(BaseModel):
    """Compatibility summary payload."""

    report_type: Literal["stage", "comprehensive", "monthly"]
    user_id: int
    title: str
    summary: str


class LatestMistakeEvidence(BaseModel):
    """Most recent mistake evidence."""

    knowledge_point: str
    question_type: str
    user_answer: str
    correct_answer: str
    analysis: str


class ReportEvidence(BaseModel):
    """Compatibility evidence payload."""

    total_answers: int = Field(ge=0, default=0)
    correct_answers: int = Field(ge=0, default=0)
    accuracy: int = Field(ge=0, le=100, default=0)
    average_time_spent: int = Field(ge=0, default=0)
    average_score: int = Field(ge=0, le=100, default=0)
    mistake_count: int = Field(ge=0, default=0)
    strongest_question_types: list[str] = Field(default_factory=list)
    weakest_question_types: list[str] = Field(default_factory=list)
    weakest_knowledge_point: str | None = None
    weakest_knowledge_accuracy: int | None = Field(default=None, ge=0, le=100)
    latest_mistake: LatestMistakeEvidence | None = None


class ReportDetail(BaseModel):
    """Compatibility detail payload used by existing frontends."""

    report_type: Literal["stage", "comprehensive"]
    user_id: int
    title: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    next_actions: list[str]
    evidence: ReportEvidence


class PracticeSubmission(BaseModel):
    """Legacy practice submission payload."""

    user_id: int
    exercise_id: int
    knowledge_point: str
    question_type: ExerciseType
    user_answer: str
    correct_answer: str
    analysis: str
    time_spent: int = Field(ge=0, default=0)
    difficulty: DifficultyLevel = "intermediate"
    chapter_id: str | None = None
    chapter_name: str | None = None


class PracticeFeedback(BaseModel):
    """Legacy immediate feedback payload."""

    user_id: int
    exercise_id: int
    is_correct: bool
    score: int = Field(ge=0, le=100)
    feedback: str
    suggested_action: str
    analysis: str
    mastery_after_update: int | None = Field(default=None, ge=0, le=100)


class QAMistakeSubmission(BaseModel):
    """Legacy QA mistake submission payload."""

    user_id: int
    exercise_id: int
    knowledge_point: str
    question_type: ExerciseType = "short_answer"
    question_summary: str
    wrong_answer: str
    correct_answer: str
    analysis: str
    suggested_action: str
    time_spent: int = Field(ge=0, default=0)
    difficulty: DifficultyLevel = "intermediate"
    chapter_id: str | None = None
    chapter_name: str | None = None


class MistakeItem(BaseModel):
    """One mistake notebook entry."""

    user_id: int
    exercise_id: int
    knowledge_point: str
    question_type: str
    user_answer: str
    correct_answer: str
    analysis: str
    suggested_action: str


class MistakeNotebook(BaseModel):
    """Collection of mistakes for one learner."""

    user_id: int
    mistake_count: int
    items: list[MistakeItem]


class MistakeNotebookClearResult(BaseModel):
    """Result returned after clearing the visible mistake notebook."""

    user_id: int
    cleared_count: int = Field(ge=0)
    cleared_at: datetime


class RemedialExerciseItem(BaseModel):
    """One remedial exercise synthesized from a real weak point."""

    exercise_id: int
    knowledge_point: str
    question_type: str
    prompt: str
    options: list[str]
    answer: str
    analysis: str
    source_exercise_id: int


class RemedialExerciseSet(BaseModel):
    """Remedial exercise collection."""

    user_id: int
    generated_from_mistakes: int
    summary: str
    exercises: list[RemedialExerciseItem]


class AnalyticsSuggestion(BaseModel):
    """Compatibility learner suggestions payload."""

    user_id: int
    suggestions: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    recommended_action: str


class AnswerRecordIn(BaseModel):
    """Legacy raw answer payload kept for compatibility."""

    user_id: int
    exercise_id: int
    answer: str
    is_correct: bool | None = None
    time_spent: int = Field(ge=0, default=0)


def normalize_exercise_type(exercise_type: str) -> str:
    """Normalize legacy exercise type aliases."""

    return {
        "blank": "fill",
        "programming": "code",
    }.get(exercise_type, exercise_type)


def compatibility_question_type(exercise_type: str) -> str:
    """Return the legacy question-type label expected by existing UI code."""

    return {
        "fill": "blank",
        "code": "programming",
    }.get(exercise_type, exercise_type)


def normalize_difficulty(difficulty: str) -> str:
    """Normalize difficulty aliases."""

    return difficulty.lower()


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Serialize a pydantic model across v2-compatible callers."""

    return model.model_dump()
