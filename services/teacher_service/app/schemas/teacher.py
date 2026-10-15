"""Schemas for teacher APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ClassCreate(BaseModel):
    """Payload to create a class."""

    name: str = Field(min_length=2, max_length=100)
    subject: str
    teacher_name: str


class ClassItem(ClassCreate):
    """Class response model."""

    id: int
    course_id: int | None = None
    student_count: int = 0


class HomeworkAssign(BaseModel):
    """Homework assignment payload."""

    class_id: int
    title: str
    description: str
    due_at: datetime | None = None


class ReviewPayload(BaseModel):
    """Homework review payload."""

    score: float = Field(ge=0, le=100)
    comment: str


class EnrollmentCreate(BaseModel):
    student_user_id: int = Field(gt=0)


class AssignmentItem(HomeworkAssign):
    id: int
    status: str
    created_at: datetime
    submission_count: int = 0


class SubmissionCreate(BaseModel):
    content: str = Field(min_length=1)
    attachment_url: str | None = None


class SubmissionItem(BaseModel):
    id: int
    assignment_id: int
    student_user_id: int
    student_name: str
    content: str
    attachment_url: str | None = None
    status: str
    submitted_at: datetime
    score: float | None = None
    teacher_comment: str = ""
    reviewed_at: datetime | None = None


class DiscussionCreate(BaseModel):
    class_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=2, max_length=160)
    content: str = Field(min_length=1)


class DiscussionReplyCreate(BaseModel):
    content: str = Field(min_length=1)


class DiscussionReplyItem(BaseModel):
    id: int
    author_user_id: int
    author_name: str
    content: str
    created_at: datetime


class DiscussionItem(BaseModel):
    id: int
    class_id: int | None
    author_user_id: int
    author_name: str
    title: str
    content: str
    status: str
    created_at: datetime
    replies: list[DiscussionReplyItem] = Field(default_factory=list)


class NotificationItem(BaseModel):
    id: int
    title: str
    content: str
    type: str
    related_type: str
    related_id: int | None
    is_read: bool
    created_at: datetime


class TeachingScopeCreate(BaseModel):
    """Teacher-defined learning scope and direction for a class or learner."""

    class_id: int = Field(gt=0)
    student_user_id: int | None = Field(default=None, gt=0)
    knowledge_points: list[str] = Field(min_length=1)
    learning_direction: str = Field(min_length=2, max_length=200)
    courseware_title: str = Field(min_length=2, max_length=120)
    courseware_content: str = Field(min_length=2)
    teaching_goal: str = Field(default="", max_length=300)


class TeachingScopeItem(TeachingScopeCreate):
    """Saved teacher scope returned to the teacher workspace."""

    id: int


class KnowledgePointMistakeStat(BaseModel):
    """Mistake aggregation for one knowledge point."""

    knowledge_point: str
    mistake_count: int
    affected_students: int
    suggested_direction: str


class TeacherTeachingAnalytics(BaseModel):
    """Class-level analytics for teaching decisions."""

    class_id: int
    student_count: int
    answered_students: int
    total_answers: int
    correct_rate: int | None
    total_mistakes: int
    weak_knowledge_points: list[KnowledgePointMistakeStat]
    teaching_suggestions: list[str]


class StudentInsight(BaseModel):
    """Teacher-facing student insight summary."""

    user_id: int
    student_name: str
    mastery: int
    recent_focus: str
    mistake_count: int
    report_summary: str


class MistakeNotebookItem(BaseModel):
    """One mistake entry shown to teachers."""

    exercise_id: int
    knowledge_point: str
    question_type: str
    user_answer: str
    correct_answer: str
    analysis: str
    suggested_action: str


class TeacherReportDetail(BaseModel):
    """Teacher-facing detailed report payload."""

    report_type: str
    user_id: int
    title: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    next_actions: list[str]


class StudentLearningDetail(BaseModel):
    """Aggregated learner detail for the teacher workspace."""

    user_id: int
    student_name: str
    mastery: int
    recent_focus: str
    mistake_count: int
    report_summary: str
    mistake_notebook: list[MistakeNotebookItem]
    stage_report: TeacherReportDetail
    comprehensive_report: TeacherReportDetail
