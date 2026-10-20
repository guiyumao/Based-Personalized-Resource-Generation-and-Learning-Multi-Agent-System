"""Contracts for transcript parsing, analysis orchestration and follow-up chat."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TranscriptRow(BaseModel):
    student_no: str = ""
    student_name: str = ""
    class_name: str = ""
    subject: str = ""
    score: float | None = None
    max_score: float = Field(default=100, gt=0)
    exam_date: str | None = None
    chapter: str = ""
    question_scores: dict[str, float] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class TranscriptParseResponse(BaseModel):
    import_id: int | None = None
    file_name: str
    file_type: str
    headers: list[str]
    rows: list[TranscriptRow]
    field_mapping: dict[str, str | None]
    warnings: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0, le=1)
    ocr_mode: bool = False
    low_confidence_cells: list[dict[str, Any]] = Field(default_factory=list)


class TranscriptAnalyzeRequest(BaseModel):
    import_id: int | None = None
    file_name: str = "manual-entry"
    file_type: str = "manual"
    headers: list[str] = Field(default_factory=list)
    rows: list[TranscriptRow] = Field(min_length=1)
    field_mapping: dict[str, str | None] = Field(default_factory=dict)
    scope: Literal["student", "class"] = "student"
    target_student_no: str | None = None
    target_student_name: str | None = None
    class_name: str | None = None
    exam_date: str | None = None


class TranscriptChatRequest(BaseModel):
    analysis_id: int
    question: str = Field(min_length=1, max_length=2000)


class TranscriptHistoryItem(BaseModel):
    id: int
    import_id: int
    file_name: str
    scope: str
    status: str
    data_quality: str
    created_at: str
    summary: str

