"""Schemas for weekly classroom schedules and one-off schedule changes."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ClassSessionPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    topic: str = Field(min_length=1, max_length=160)
    weekday: int = Field(ge=1, le=7)
    start_time: str
    end_time: str
    week_start: str
    week_end: str
    location: str = Field(default="", max_length=160)
    mode: Literal["offline", "online"] = "offline"

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not TIME_PATTERN.match(value):
            raise ValueError("时间格式必须为 HH:MM")
        return value

    @field_validator("week_start", "week_end")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if not DATE_PATTERN.match(value):
            raise ValueError("日期格式必须为 YYYY-MM-DD")
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.start_time >= self.end_time:
            raise ValueError("上课开始时间必须早于结束时间")
        if self.week_start > self.week_end:
            raise ValueError("教学周开始日期不能晚于结束日期")
        return self


class ClassSessionItem(BaseModel):
    id: int
    class_id: int
    class_name: str = ""
    teacher_name: str = ""
    topic: str
    weekday: int
    start_time: str
    end_time: str
    week_start: str
    week_end: str
    location: str = ""
    mode: str = "offline"
    status: str = "active"
    created_at: datetime


class ScheduleExceptionPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    date: str
    kind: Literal["cancel", "reschedule", "makeup"]
    new_date: str | None = None
    new_start_time: str | None = None
    new_end_time: str | None = None
    location: str | None = Field(default=None, max_length=160)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("date", "new_date")
    @classmethod
    def valid_date(cls, value):
        if value is not None and not DATE_PATTERN.match(value):
            raise ValueError("日期格式必须为 YYYY-MM-DD")
        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator("new_start_time", "new_end_time")
    @classmethod
    def valid_time(cls, value):
        if value is not None and not TIME_PATTERN.match(value):
            raise ValueError("时间格式必须为 HH:MM")
        return value

    @model_validator(mode="after")
    def validate_change(self):
        if self.kind == "cancel" and (
            self.new_date or self.new_start_time or self.new_end_time
        ):
            raise ValueError("停课不能同时设置新的时间")
        if self.kind == "reschedule" and not (
            self.new_date or self.new_start_time or self.new_end_time
        ):
            raise ValueError("调课必须提供新的日期或时间")
        if self.kind == "makeup" and not (self.new_date and self.new_start_time and self.new_end_time):
            raise ValueError("补课必须提供新的日期和起止时间")
        if self.new_start_time and self.new_end_time and self.new_start_time >= self.new_end_time:
            raise ValueError("调课开始时间必须早于结束时间")
        return self


class ScheduleExceptionItem(BaseModel):
    id: int
    session_id: int
    class_id: int
    class_name: str = ""
    date: str
    kind: str
    new_date: str | None = None
    new_start_time: str | None = None
    new_end_time: str | None = None
    location: str | None = None
    reason: str = ""
    created_at: datetime


class TeacherSchedule(BaseModel):
    class_id: int
    class_name: str
    sessions: list[ClassSessionItem] = Field(default_factory=list)
    exceptions: list[ScheduleExceptionItem] = Field(default_factory=list)


class StudentScheduleEntry(BaseModel):
    date: str
    weekday: int
    start_time: str
    end_time: str
    topic: str
    location: str = ""
    mode: str = "offline"
    class_id: int
    class_name: str
    teacher_name: str = ""
    status: str = "normal"
    session_id: int
    personal_id: int | None = None
    source: str = "classroom"
    source_date: str | None = None


class StudentSchedule(BaseModel):
    week_start: str
    week_end: str
    today: str
    entries: list[StudentScheduleEntry] = Field(default_factory=list)
    classrooms: list[ImportedClassroom] = Field(default_factory=list)
    personal: list[PersonalScheduleItem] = Field(default_factory=list)


class ImportedClassroom(BaseModel):
    class_id: int
    class_name: str
    teacher_name: str
    scheduled: bool


class PersonalSchedulePayload(ClassSessionPayload):
    class_id: int | None = None
    source_session_id: int | None = None
    source_date: str | None = None
    hidden: bool = False

    @model_validator(mode="after")
    def valid_override(self):
        if bool(self.source_session_id) != bool(self.source_date):
            raise ValueError("个人调整需要原课程和原日期")
        if self.source_date:
            date.fromisoformat(self.source_date)
        if self.hidden and not self.source_session_id:
            raise ValueError("仅课堂课程可隐藏")
        if self.source_session_id and self.week_start != self.week_end:
            raise ValueError("课堂课程个人调整仅限当次，起止日期应相同")
        first = date.fromisoformat(self.week_start)
        if first + timedelta(days=(self.weekday - first.isoweekday()) % 7) > date.fromisoformat(self.week_end):
            raise ValueError("日期范围内没有所选上课日，请调整星期或日期")
        return self


class PersonalScheduleItem(PersonalSchedulePayload):
    model_config = ConfigDict(from_attributes=True)
    id: int


StudentSchedule.model_rebuild()
