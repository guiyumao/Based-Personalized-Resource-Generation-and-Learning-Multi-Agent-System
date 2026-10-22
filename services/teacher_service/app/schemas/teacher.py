"""Schemas for teacher APIs."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClassCreate(BaseModel):
    """Payload to create a class."""

    name: str = Field(min_length=2, max_length=100)
    model_config = ConfigDict(str_strip_whitespace=True)
    subject: str = Field(min_length=1, max_length=100)
    teacher_name: str = Field(default="", max_length=100)
    join_mode: str = Field(default="invite", pattern="^(invite|open)$")
    description: str = Field(default="", max_length=4000)
    objective: str = Field(default="", max_length=4000)
    syllabus: str = Field(default="", max_length=8000)
    semester: str = Field(default="", max_length=40)
    is_public: bool = True
    capacity: int = Field(default=0, ge=0, le=100000)


class ClassUpdate(ClassCreate):
    status: str = Field(default="active", pattern="^(active|inactive)$")


class ClassJoin(BaseModel):
    invite_code: str = Field(min_length=4, max_length=32)


class ClassMember(BaseModel):
    user_id: int
    username: str
    joined_at: datetime


class ClassItem(ClassCreate):
    """Class response model."""

    id: int
    course_id: int | None = None
    student_count: int = 0
    assignment_count: int = 0
    invite_code: str | None = None
    status: str = "active"


class PlazaClassItem(BaseModel):
    """Read-only classroom card shown in the student classroom plaza."""

    id: int
    name: str
    subject: str
    teacher_name: str
    course_title: str = ""
    course_description: str = ""
    description: str = ""
    objective: str = ""
    syllabus: str = ""
    semester: str = ""
    student_count: int = 0
    capacity: int = 0
    is_public: bool = True
    status: str = "active"
    join_mode: str = "invite"
    joined: bool = False
    invite_matched: bool = False
    open_task_count: int = 0
    latest_scope_title: str = ""


class HomeworkAssign(BaseModel):
    """Homework assignment payload."""

    model_config = ConfigDict(str_strip_whitespace=True)
    class_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def utc_deadline(cls, value):
        return value.astimezone(UTC).replace(tzinfo=None) if value and value.tzinfo else value


class ReviewPayload(BaseModel):
    """Homework review payload."""

    score: float = Field(ge=0, le=100)
    comment: str


class EnrollmentCreate(BaseModel):
    student_user_id: int = Field(gt=0)


class AssignmentItem(HomeworkAssign):
    target_student_id: int | None = None
    practice_questions: list[dict] = Field(default_factory=list)
    id: int
    status: str
    created_at: datetime
    submission_count: int = 0
    class_name: str = ""
    student_count: int = 0
    pending_count: int = 0
    reviewed_count: int = 0
    my_submission: SubmissionItem | None = None
    pending_attachments: list[HomeworkFileItem] = Field(default_factory=list)


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    content: str = ""
    attachment_url: str | None = None
    attachment_ids: list[int] | None = Field(default=None, max_length=10)
    answers: list[str] | None = Field(default=None, min_length=1, max_length=10)
    time_spent: int | None = Field(default=None, ge=0, le=86400)

    @model_validator(mode="after")
    def require_answer(self):
        if not self.content and not self.attachment_ids and not self.answers:
            raise ValueError("请填写作业内容或选择至少一个附件")
        return self


class HomeworkFileItem(BaseModel):
    is_pending: bool = False
    id: int
    file_name: str
    content_type: str
    size_bytes: int


class SubmissionItem(BaseModel):
    practice_result: dict | None = None
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
    history: list[dict] = Field(default_factory=list)
    attachments: list[HomeworkFileItem] = Field(default_factory=list)


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
    homework_submissions: int = 0
    homework_reviewed: int = 0
    homework_average_score: float | None = None


class StudentInsight(BaseModel):
    """Teacher-facing student insight summary."""

    user_id: int
    student_name: str
    mastery: int | None
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
    mastery: int | None
    recent_focus: str
    mistake_count: int
    report_summary: str
    mistake_notebook: list[MistakeNotebookItem]
    stage_report: TeacherReportDetail
    comprehensive_report: TeacherReportDetail
