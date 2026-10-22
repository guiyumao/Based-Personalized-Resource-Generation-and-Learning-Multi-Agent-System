"""Schemas for the learning check-in and classroom attendance APIs."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class DailyCheckinPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    goal: str = Field(default="", max_length=500)
    reflection: str = Field(default="", max_length=2000)


class DailyCheckinItem(BaseModel):
    id: int
    checkin_date: str
    checkin_at: datetime
    goal: str = ""
    reflection: str = ""


class PlatformCheckinStatus(BaseModel):
    today: str
    checked_in: bool = False
    today_checkin: DailyCheckinItem | None = None
    current_streak: int = 0
    total_days: int = 0
    week_days: int = 0
    week_goal: int = 7
    month_days: int = 0


class PlatformCalendarDay(BaseModel):
    date: str
    checked_in: bool = True
    goal: str = ""
    reflection: str = ""


class PlatformCheckinCalendar(BaseModel):
    month: str
    days: list[PlatformCalendarDay] = Field(default_factory=list)
    streak: int = 0
    total_days: int = 0


class CheckinTaskCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    class_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    goal: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=4000)
    frequency: Literal["once", "daily", "weekly"] = "once"
    weekly_days: list[int] = Field(default_factory=list, max_length=7)
    start_at: datetime
    end_at: datetime
    due_time: str = "23:59"
    allow_late: bool = False
    review_mode: Literal["auto", "manual"] = "manual"
    require_attachment: bool = False
    knowledge_points: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("start_at", "end_at")
    @classmethod
    def utc_datetime(cls, value: datetime) -> datetime:
        return _naive_utc(value) or value

    @field_validator("due_time")
    @classmethod
    def valid_due_time(cls, value: str) -> str:
        if not _TIME_PATTERN.match(value):
            raise ValueError("截止时间格式必须为 HH:MM")
        return value

    @field_validator("weekly_days")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        days = sorted({int(day) for day in value})
        if any(day < 1 or day > 7 for day in days):
            raise ValueError("每周重复日必须为 1-7（周一至周日）")
        return days

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.end_at <= self.start_at:
            raise ValueError("结束时间必须晚于开始时间")
        if self.frequency == "weekly" and not self.weekly_days:
            raise ValueError("每周任务必须选择重复的星期")
        return self


class CheckinTaskUpdate(CheckinTaskCreate):
    pass


class CheckinSubmissionItem(BaseModel):
    id: int
    task_id: int
    task_title: str = ""
    class_name: str = ""
    student_user_id: int
    student_name: str = ""
    period_key: str
    period_due_at: datetime
    content: str = ""
    attachment_ids: list[int] = Field(default_factory=list)
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None = None
    review_comment: str = ""
    score: float | None = None
    version: int = 1
    late: bool = False
    history: list[dict] = Field(default_factory=list)


class CheckinTaskItem(BaseModel):
    id: int
    class_id: int
    class_name: str = ""
    course_id: int | None = None
    title: str
    goal: str = ""
    description: str = ""
    frequency: str
    weekly_days: list[int] = Field(default_factory=list)
    start_at: datetime
    end_at: datetime
    due_time: str
    allow_late: bool = False
    review_mode: str = "manual"
    require_attachment: bool = False
    knowledge_points: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    published_at: datetime | None = None
    closed_at: datetime | None = None
    student_count: int = 0
    submitted_count: int = 0
    approved_count: int = 0
    pending_review_count: int = 0
    expected_count: int = 0
    completion_rate: float | None = None
    today_period: str | None = None
    my_state: str | None = None
    can_submit: bool = False
    my_submission: CheckinSubmissionItem | None = None


class CheckinPeriodItem(BaseModel):
    period_key: str
    due_at: datetime
    state: str = "pending"


class CheckinTaskDetail(CheckinTaskItem):
    teacher_name: str = ""
    periods: list[CheckinPeriodItem] = Field(default_factory=list)


class CheckinSubmitPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    content: str = Field(default="", max_length=8000)
    attachment_ids: list[int] = Field(default_factory=list, max_length=10)
    period_key: str | None = None

    @field_validator("period_key")
    @classmethod
    def valid_period(cls, value):
        if value is not None and not _DATE_PATTERN.match(value):
            raise ValueError("周期格式必须为 YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def require_evidence(self):
        if not self.content and not self.attachment_ids:
            raise ValueError("请填写学习成果或上传附件")
        return self


class CheckinReviewPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    verdict: Literal["approve", "return"]
    comment: str = Field(default="", max_length=2000)
    score: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def require_return_reason(self):
        if self.verdict == "return" and not self.comment:
            raise ValueError("退回补交必须填写原因")
        return self


class CheckinReviewBatch(CheckinReviewPayload):
    submission_ids: list[int] = Field(min_length=1, max_length=100)


class CheckinRemindPayload(BaseModel):
    period_key: str | None = None


class StudentTaskSummary(BaseModel):
    task_id: int
    title: str
    class_name: str
    task_type: str
    period_key: str | None = None
    due_at: datetime | None = None
    state: str
    can_submit: bool = False


class CheckinHome(BaseModel):
    today: str
    due_today: int = 0
    completed_today: int = 0
    current_streak: int = 0
    total_days: int = 0
    week_completion_rate: float | None = None
    week_expected: int = 0
    week_approved: int = 0
    pending_tasks: list[StudentTaskSummary] = Field(default_factory=list)
    upcoming_tasks: list[StudentTaskSummary] = Field(default_factory=list)
    available_attendance: list[AttendanceSessionItem] = Field(default_factory=list)
    latest_feedback: list[CheckinSubmissionItem] = Field(default_factory=list)
    recent_checkins: list[DailyCheckinItem] = Field(default_factory=list)
    today_checked_in: bool = False


class AttendanceSessionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    class_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    start_at: datetime
    end_at: datetime
    late_after_at: datetime | None = None

    @field_validator("start_at", "end_at", "late_after_at")
    @classmethod
    def utc_datetime(cls, value):
        return _naive_utc(value)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("签到结束时间必须晚于开始时间")
        if self.late_after_at and (
            self.late_after_at < self.start_at or self.late_after_at > self.end_at
        ):
            raise ValueError("迟到判定时间必须位于签到时段内")
        return self


class AttendanceRecordBrief(BaseModel):
    id: int
    status: str
    checked_in_at: datetime | None = None
    source: str = ""
    note: str = ""


class AttendanceSessionItem(BaseModel):
    id: int
    class_id: int
    class_name: str = ""
    title: str
    start_at: datetime
    end_at: datetime
    late_after_at: datetime | None = None
    status: str
    code: str | None = None
    token: str | None = None
    my_record: AttendanceRecordBrief | None = None
    checked_in_count: int = 0
    late_count: int = 0
    leave_count: int = 0
    absent_count: int = 0
    missing_count: int = 0
    student_count: int = 0


class AttendanceCheckinPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str | None = Field(default=None, max_length=32)
    token: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def require_code(self):
        if not self.code and not self.token:
            raise ValueError("请填写签到码或扫描签到二维码")
        return self


class AttendanceStudentRow(BaseModel):
    student_user_id: int
    student_name: str
    status: str
    checked_in_at: datetime | None = None
    source: str = ""
    note: str = ""
    record_id: int | None = None


class AttendanceLive(BaseModel):
    session: AttendanceSessionItem
    rows: list[AttendanceStudentRow] = Field(default_factory=list)


class AttendanceUpdatePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    status: Literal["present", "late", "leave", "absent", "pending"]
    reason: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=500)


class ClassCheckinStat(BaseModel):
    class_id: int
    class_name: str
    student_count: int
    task_completion_rate: float | None = None
    attendance_rate: float | None = None
    pending_review: int = 0
    low_participation: int = 0


class CheckinTrendPoint(BaseModel):
    date: str
    approved: int = 0
    submitted: int = 0
    attendance: int = 0


class TeacherCheckinOverview(BaseModel):
    class_count: int = 0
    active_task_count: int = 0
    pending_review_count: int = 0
    today_attendance_count: int = 0
    overdue_student_count: int = 0
    classes: list[ClassCheckinStat] = Field(default_factory=list)
    trend: list[CheckinTrendPoint] = Field(default_factory=list)
    recent_tasks: list[CheckinTaskItem] = Field(default_factory=list)


class AdminCheckinOverview(BaseModel):
    task_count: int = 0
    published_task_count: int = 0
    submission_count: int = 0
    pending_review_count: int = 0
    attendance_session_count: int = 0
    attendance_record_count: int = 0
    self_checkin_count: int = 0
    recent_audits: list[dict] = Field(default_factory=list)


class CheckinTaskCompletion(BaseModel):
    task: CheckinTaskItem
    period_key: str
    periods: list[CheckinPeriodItem] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)


CheckinHome.model_rebuild()
