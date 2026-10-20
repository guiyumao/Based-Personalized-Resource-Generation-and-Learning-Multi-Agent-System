"""Persistence tests for the class, homework, discussion and notification loop."""

from uuid import uuid4

import pytest

from common.db.session import SessionLocal
from common.models.learning import (
    Assignment,
    AssignmentSubmission,
    ClassEnrollment,
    Classroom,
    Course,
    DiscussionReply,
    DiscussionThread,
    Notification,
    User,
)
from common.security.auth import hash_password
from services.teacher_service.app.schemas.teacher import (
    ClassCreate,
    DiscussionCreate,
    DiscussionReplyCreate,
    HomeworkAssign,
    ReviewPayload,
    SubmissionCreate,
)
from services.teacher_service.app.services.teacher_manager import TeacherManager


def test_learning_community_persists_end_to_end() -> None:
    suffix = uuid4().hex[:8]
    with SessionLocal() as db:
        teacher = User(username=f"teacher_{suffix}", password_hash=hash_password("pw"), role="teacher")
        student = User(username=f"student_{suffix}", password_hash=hash_password("pw"), role="student")
        db.add_all([teacher, student])
        db.commit()
        teacher_id, student_id = teacher.id, student.id

    manager = TeacherManager()
    classroom = manager.create_class(ClassCreate(name="操作系统实验班", subject="操作系统", teacher_name="测试教师"), teacher_id)
    manager.enroll_student(classroom.id, student_id, teacher_id)
    with pytest.raises(PermissionError):
        manager.ensure_teacher_class_access(classroom.id, student_id, "teacher")
    assignment = manager.create_assignment(
        HomeworkAssign(class_id=classroom.id, title="进程调度实验", description="提交调度算法分析"),
        teacher_id,
    )
    submission = manager.submit_assignment(assignment.id, SubmissionCreate(content="完成 FIFO 与 RR 对比"), student_id)
    reviewed = manager.review_submission(submission.id, ReviewPayload(score=92, comment="分析完整"), teacher_id)
    topic = manager.create_discussion(
        DiscussionCreate(class_id=classroom.id, title="时间片选择", content="时间片如何影响响应时间？"),
        student_id,
        "student",
    )
    topic = manager.reply_discussion(
        topic.id,
        DiscussionReplyCreate(content="需要结合上下文切换开销。"),
        teacher_id,
        "teacher",
    )

    assert reviewed.status == "reviewed"
    assert reviewed.score == 92
    assert topic.replies[0].author_name.startswith("teacher_")
    assert any(item.type == "review" for item in manager.list_notifications(student_id))
    assert manager.list_student_assignments(student_id)[0].id == assignment.id

    with SessionLocal() as db:
        db.query(DiscussionReply).filter(DiscussionReply.thread_id == topic.id).delete()
        db.query(DiscussionThread).filter(DiscussionThread.id == topic.id).delete()
        db.query(Notification).filter(Notification.user_id.in_([teacher_id, student_id])).delete(synchronize_session=False)
        db.query(AssignmentSubmission).filter(AssignmentSubmission.assignment_id == assignment.id).delete()
        db.query(Assignment).filter(Assignment.id == assignment.id).delete()
        db.query(ClassEnrollment).filter(ClassEnrollment.class_id == classroom.id).delete()
        db.query(Classroom).filter(Classroom.id == classroom.id).delete()
        if classroom.course_id:
            db.query(Course).filter(Course.id == classroom.course_id).delete()
        db.query(User).filter(User.id.in_([teacher_id, student_id])).delete(synchronize_session=False)
        db.commit()
