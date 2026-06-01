"""Schemas for evaluation and report APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnswerRecordIn(BaseModel):
    """Input answer record for evaluation service."""

    user_id: int
    exercise_id: int
    answer: str
    is_correct: bool | None = None
    time_spent: int = Field(ge=0, default=0)


class ReportSummary(BaseModel):
    """Report summary payload."""

    report_type: Literal["stage", "comprehensive", "mistakes"]
    user_id: int
    title: str
    summary: str


class PracticeSubmission(BaseModel):
    """A learner answer submitted from the student workspace."""

    user_id: int
    exercise_id: int
    knowledge_point: str
    question_type: Literal["choice", "blank", "judge", "short_answer", "programming"]
    user_answer: str
    correct_answer: str
    analysis: str
    time_spent: int = Field(ge=0, default=0)


class PracticeFeedback(BaseModel):
    """Immediate evaluation feedback for one submitted answer."""

    user_id: int
    exercise_id: int
    is_correct: bool
    score: int = Field(ge=0, le=100)
    feedback: str
    suggested_action: str
    analysis: str
    mastery_after_update: int | None = Field(default=None, ge=0, le=100)


class MistakeItem(BaseModel):
    """One item in the learner's mistake notebook."""

    user_id: int
    exercise_id: int
    knowledge_point: str
    question_type: Literal["choice", "blank", "judge", "short_answer", "programming"]
    user_answer: str
    correct_answer: str
    analysis: str
    suggested_action: str


class RemedialExerciseItem(BaseModel):
    """One variant exercise generated from a mistake item."""

    exercise_id: int
    knowledge_point: str
    question_type: Literal["choice", "blank", "judge", "short_answer", "programming"]
    prompt: str
    options: list[str]
    answer: str
    analysis: str
    source_exercise_id: int


class RemedialExerciseSet(BaseModel):
    """Variant exercise collection for mistake review."""

    user_id: int
    generated_from_mistakes: int
    summary: str
    exercises: list[RemedialExerciseItem]


class MistakeNotebook(BaseModel):
    """Collection of mistake items for one learner."""

    user_id: int
    mistake_count: int
    items: list[MistakeItem]


class LatestMistakeEvidence(BaseModel):
    """Most recent mistake used as concrete reporting evidence."""

    knowledge_point: str
    question_type: Literal["choice", "blank", "judge", "short_answer", "programming"]
    user_answer: str
    correct_answer: str
    analysis: str


class ReportEvidence(BaseModel):
    """Structured evidence that explains why the report reached its conclusions."""

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
    """Detailed learning report payload for student display."""

    report_type: Literal["stage", "comprehensive"]
    user_id: int
    title: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    next_actions: list[str]
    evidence: ReportEvidence


class AnalyticsSuggestion(BaseModel):
    """Personalized learning suggestions distilled from practice evidence."""

    user_id: int
    suggestions: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    recommended_action: str
