"""Shared transactional notification primitives and live recipient authorization."""

from sqlalchemy import and_, or_, select

from common.models.checkin import AttendanceSession, CheckinTask
from common.models.learning import (
    Assignment,
    AssistantTask,
    ClassEnrollment,
    Classroom,
    Course,
    DiscussionThread,
    KnowledgeBuildTask,
    LearningPath,
    Notification,
    NotificationDispatch,
    User,
)


def emit(
    db,
    *,
    user_id,
    event_key,
    title,
    content,
    type="system",
    related_type="",
    related_id=None,
    sender_id=None,
):
    values = dict(
        user_id=user_id,
        event_key=event_key,
        title=title[:160],
        content=content,
        type=type,
        related_type=related_type,
        related_id=related_id,
        sender_id=sender_id,
        is_read=False,
    )
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        raise RuntimeError("Notification delivery requires SQLite or PostgreSQL")
    db.flush()
    db.execute(
        insert(Notification)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["user_id", "event_key"])
    )


def visible(db, user):
    if user.role == "student":
        class_access = Classroom.id.in_(
            select(ClassEnrollment.class_id).where(ClassEnrollment.student_user_id == user.id)
        )
    else:
        class_access = and_(Classroom.teacher_user_id == user.id, user.role == "teacher")
    classes = select(Classroom.id).where(class_access)
    assignments = select(Assignment.id).where(Assignment.class_id.in_(classes))
    if user.role == "student":
        from common.assignment_access import student_assignment_clause
        assignments = assignments.where(student_assignment_clause(user.id))
    courses = select(Classroom.course_id).where(Classroom.id.in_(classes))
    discussions = select(DiscussionThread.id).where(DiscussionThread.class_id.in_(classes))
    checkin_tasks = select(CheckinTask.id).where(CheckinTask.class_id.in_(classes))
    attendance_sessions = select(AttendanceSession.id).where(
        AttendanceSession.class_id.in_(classes)
    )
    return db.query(Notification).filter(
        Notification.user_id == user.id,
        or_(
            Notification.related_type.in_(["", "announcement"]),
            and_(
                Notification.related_type == "knowledge_task",
                Notification.related_id.in_(
                    select(KnowledgeBuildTask.id).where(KnowledgeBuildTask.actor_user_id == user.id)
                ),
            ),
            and_(
                Notification.related_type == "plan",
                Notification.related_id.in_(
                    select(LearningPath.id).where(LearningPath.user_id == user.id)
                ),
            ),
            and_(Notification.related_type == "class", Notification.related_id.in_(classes)),
            and_(Notification.related_type == "course", Notification.related_id.in_(courses)),
            and_(
                Notification.related_type == "assignment", Notification.related_id.in_(assignments)
            ),
            and_(
                Notification.related_type == "discussion", Notification.related_id.in_(discussions)
            ),
            and_(
                Notification.related_type == "checkin_task",
                Notification.related_id.in_(checkin_tasks),
            ),
            and_(
                Notification.related_type == "attendance",
                Notification.related_id.in_(attendance_sessions),
            ),
            and_(
                Notification.related_type == "task",
                Notification.related_id.in_(
                    select(AssistantTask.id).where(AssistantTask.user_id == user.id)
                ),
            ),
        ),
    )


def serialize(db, item):
    sender = db.get(User, item.sender_id) if item.sender_id else None
    return dict(
        id=item.id,
        title=item.title,
        content=item.content,
        type=item.type,
        related_type=item.related_type,
        related_id=item.related_id,
        is_read=item.is_read,
        read_at=item.read_at,
        created_at=item.created_at,
        sender_name=sender.username if sender else "系统通知",
    )


def publish(db, user, payload):
    data = payload.model_dump()
    receipt = (
        db.query(NotificationDispatch)
        .filter_by(sender_id=user.id, request_key=payload.request_key)
        .first()
    )
    if receipt:
        if receipt.payload_json != data:
            raise ValueError("同一发送标识不能用于不同消息")
        return dict(id=receipt.id, recipient_count=receipt.recipient_count)
    scope, target = payload.scope, payload.target_id
    recipients = db.query(User.id).filter(
        User.is_active.is_(True), User.role.in_(["student", "teacher"])
    )
    kind, related = "announcement", None
    if user.role == "teacher" and scope not in ("class", "course", "student"):
        raise PermissionError("教师仅可向本人课程、班级及学生发送通知")
    if scope in ("students", "teachers"):
        recipients = recipients.filter(
            User.role == ("student" if scope == "students" else "teacher")
        )
    elif scope in ("student", "teacher"):
        recipients = recipients.filter(User.id == target, User.role == scope)
        if user.role == "teacher":
            recipients = recipients.filter(
                User.id.in_(
                    select(ClassEnrollment.student_user_id)
                    .join(Classroom, Classroom.id == ClassEnrollment.class_id)
                    .where(Classroom.teacher_user_id == user.id)
                )
            )
    elif scope in ("class", "course"):
        model = Classroom if scope == "class" else Course
        resource = db.get(model, target)
        if resource is None:
            raise ValueError("班级或课程不存在")
        if user.role == "teacher" and resource.teacher_user_id != user.id:
            raise PermissionError("无权向此班级或课程发送通知")
        class_query = (
            select(Classroom.id).where(Classroom.id == target)
            if scope == "class"
            else select(Classroom.id).where(Classroom.course_id == target)
        )
        teacher_query = select(Classroom.teacher_user_id).where(Classroom.id.in_(class_query))
        recipients = recipients.filter(
            or_(
                User.id.in_(
                    select(ClassEnrollment.student_user_id).where(
                        ClassEnrollment.class_id.in_(class_query)
                    )
                ),
                User.id.in_(teacher_query),
            )
        )
        kind, related = scope, target
    else:
        raise ValueError("不支持的接收范围")
    if scope == "student" and user.role == "teacher":
        enrollment = (
            db.query(ClassEnrollment)
            .join(Classroom, Classroom.id == ClassEnrollment.class_id)
            .filter(Classroom.teacher_user_id == user.id, ClassEnrollment.student_user_id == target)
            .order_by(ClassEnrollment.id)
            .first()
        )
        if enrollment:
            kind, related = "class", enrollment.class_id
    ids = [row[0] for row in recipients.order_by(User.id).limit(5001)]
    if len(ids) > 5000:
        raise ValueError("单次最多发送5000人，请按班级或课程拆分发送")
    if not ids:
        raise ValueError("没有符合权限的有效接收人")
    receipt = NotificationDispatch(
        sender_id=user.id,
        request_key=payload.request_key,
        payload_json=data,
        recipient_count=len(ids),
    )
    db.add(receipt)
    db.flush()
    for uid in ids:
        emit(
            db,
            user_id=uid,
            event_key=f"dispatch:{receipt.id}",
            title=payload.title,
            content=payload.content,
            type=payload.type,
            related_type=kind,
            related_id=related,
            sender_id=user.id,
        )
    db.commit()
    return dict(id=receipt.id, recipient_count=len(ids))


def target_path(db, item, user):
    # Called only after visible() has rechecked current membership and ownership.
    if item.related_type == "assignment":
        return (
            f"/teacher/homework?assignment={item.related_id}"
            if user.role == "teacher"
            else f"/student/classroom?assignment={item.related_id}"
        )
    if item.related_type == "checkin_task":
        return (
            f"/teacher/checkin?task={item.related_id}"
            if user.role == "teacher"
            else f"/student/checkin?task={item.related_id}"
        )
    if item.related_type == "attendance":
        return (
            f"/teacher/checkin?attendance={item.related_id}"
            if user.role == "teacher"
            else f"/student/checkin?attendance={item.related_id}"
        )
    if item.related_type == "discussion":
        return None
    if item.related_type in ("class", "course"):
        return (
            "/teacher/classes"
            if user.role == "teacher"
            else f"/student/classroom?{item.related_type}={item.related_id}"
        )
    if item.related_type == "plan":
        return "/student/learning-path"
    if item.related_type == "knowledge_task":
        return "/admin/tasks" if user.role == "admin" else None
    if item.related_type == "task":
        return (
            f"/student/notifications?assistant_task={item.related_id}"
            if user.role == "student"
            else None
        )
    return None
