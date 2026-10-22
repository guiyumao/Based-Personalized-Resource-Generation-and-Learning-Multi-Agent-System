"""Membership operations on the existing shared class and enrollment tables."""

import secrets

from sqlalchemy.exc import IntegrityError

from common.db.session import SessionLocal
from common.models.checkin import CheckinTask
from common.models.learning import (
    ClassEnrollment,
    Classroom,
    Course,
    LearningPath,
    TeachingScope,
    User,
)
from common.notifications import emit
from services.teacher_service.app.schemas.teacher import ClassMember, PlazaClassItem


class ClassroomMembership:
    def list_my_classes(self, student_id):
        with SessionLocal() as db:
            rows = (
                db.query(Classroom)
                .join(ClassEnrollment, ClassEnrollment.class_id == Classroom.id)
                .filter(ClassEnrollment.student_user_id == student_id)
                .all()
            )
            return [
                self._class_to_item(db, row).model_copy(update={"invite_code": None})
                for row in rows
            ]

    def lookup_invite(self, code):
        with SessionLocal() as db:
            row = self._invited_class(db, code)
            return self._class_to_item(db, row).model_copy(update={"invite_code": None})

    def list_plaza(self, student_id: int, query: str = "", subject: str = "") -> list[PlazaClassItem]:
        """Return joinable classroom cards without exposing invitation codes."""

        with SessionLocal() as db:
            normalized_query = query.strip()
            invite_match = (
                Classroom.invite_code == normalized_query.upper()
                if normalized_query else False
            )
            rooms = db.query(Classroom).filter(
                Classroom.status == "active", Classroom.is_public.is_(True) | invite_match
            )
            if subject.strip():
                rooms = rooms.filter((Classroom.subject == subject.strip()) | invite_match)
            if normalized_query:
                pattern = f"%{normalized_query}%"
                rooms = rooms.filter(
                    Classroom.name.like(pattern)
                    | Classroom.subject.like(pattern)
                    | Classroom.teacher_name.like(pattern)
                    | invite_match
                )
            rows = rooms.order_by(Classroom.id.desc()).limit(100).all()
            joined = {
                row[0]
                for row in db.query(ClassEnrollment.class_id)
                .filter(ClassEnrollment.student_user_id == student_id)
                .all()
            }
            items = []
            for room in rows:
                course = db.get(Course, room.course_id) if room.course_id else None
                scope = (
                    db.query(TeachingScope)
                    .filter_by(class_id=room.id, student_user_id=None)
                    .order_by(TeachingScope.id.desc())
                    .first()
                )
                items.append(
                    PlazaClassItem(
                        id=room.id,
                        name=room.name,
                        subject=room.subject,
                        teacher_name=room.teacher_name,
                        course_title=course.title if course else room.name,
                        course_description=course.description if course else "",
                        description=room.description,
                        objective=room.objective,
                        syllabus=room.syllabus,
                        semester=room.semester,
                        capacity=room.capacity,
                        is_public=room.is_public,
                        student_count=db.query(ClassEnrollment)
                        .filter_by(class_id=room.id)
                        .count(),
                        status=room.status,
                        join_mode=room.join_mode,
                        joined=room.id in joined,
                        invite_matched=bool(normalized_query and room.invite_code == normalized_query.upper()),
                        open_task_count=db.query(CheckinTask)
                        .filter_by(class_id=room.id, status="published")
                        .count(),
                        latest_scope_title=scope.courseware_title if scope else "",
                    )
                )
            return items

    def join_plaza_class(self, class_id: int, student_id: int):
        """Self-enroll in an open class chosen from the plaza."""

        with SessionLocal() as db:
            self._lock_write(db)
            room = db.get(Classroom, class_id)
            if room is None:
                raise ValueError("班级不存在")
            if room.status != "active":
                raise RuntimeError("该班级已停用，无法加入")
            if room.join_mode != "open":
                raise PermissionError("该班级仅支持邀请码加入，请向教师获取邀请码")
            student = db.get(User, student_id)
            if not student or student.role != "student" or not student.is_active:
                raise PermissionError("仅有效学生账号可以加入班级")
            existing = (
                db.query(ClassEnrollment)
                .filter_by(class_id=room.id, student_user_id=student_id)
                .first()
            )
            if existing is None:
                self._ensure_capacity(db, room)
                try:
                    with db.begin_nested():
                        db.add(
                            ClassEnrollment(class_id=room.id, student_user_id=student_id)
                        )
                        db.flush()
                    emit(
                        db,
                        user_id=room.teacher_user_id,
                        sender_id=student_id,
                        event_key=f"joined:{room.id}:{student_id}",
                        title="学生通过课堂广场加入班级",
                        content=f"{student.username} 通过课堂广场加入了 {room.name}",
                        type="class",
                        related_type="class",
                        related_id=room.id,
                    )
                    latest_scope = (
                        db.query(TeachingScope)
                        .filter_by(class_id=room.id, student_user_id=None)
                        .order_by(TeachingScope.id.desc())
                        .first()
                    )
                    if latest_scope:
                        self._publish_scope_to_students(db, latest_scope, only_student=student)
                    else:
                        db.commit()
                except IntegrityError:
                    db.rollback()
                    if (
                        not db.query(ClassEnrollment)
                        .filter_by(class_id=room.id, student_user_id=student_id)
                        .first()
                    ):
                        raise
            return self._class_to_item(db, room).model_copy(update={"invite_code": None})

    def _ensure_capacity(self, db, room: Classroom) -> None:
        if room.capacity and room.capacity > 0:
            members = db.query(ClassEnrollment).filter_by(class_id=room.id).count()
            if members >= room.capacity:
                raise RuntimeError("该课堂人数已满，暂时无法加入")

    def get_public_class(self, class_id: int, student_id: int) -> PlazaClassItem:
        with SessionLocal() as db:
            room = db.get(Classroom, class_id)
            if room is None or room.status != "active":
                raise ValueError("课堂不存在或已停用")
            joined = (
                db.query(ClassEnrollment.id)
                .filter_by(class_id=room.id, student_user_id=student_id)
                .first()
                is not None
            )
            if not room.is_public and not joined:
                raise PermissionError("该课堂未公开，无法查看")
            course = db.get(Course, room.course_id) if room.course_id else None
            scope = (
                db.query(TeachingScope)
                .filter_by(class_id=room.id, student_user_id=None)
                .order_by(TeachingScope.id.desc())
                .first()
            )
            return PlazaClassItem(
                id=room.id,
                name=room.name,
                subject=room.subject,
                teacher_name=room.teacher_name,
                course_title=course.title if course else room.name,
                course_description=course.description if course else "",
                description=room.description,
                objective=room.objective,
                syllabus=room.syllabus,
                semester=room.semester,
                capacity=room.capacity,
                is_public=room.is_public,
                student_count=db.query(ClassEnrollment).filter_by(class_id=room.id).count(),
                status=room.status,
                join_mode=room.join_mode,
                joined=joined,
                open_task_count=db.query(CheckinTask)
                .filter_by(class_id=room.id, status="published")
                .count(),
                latest_scope_title=scope.courseware_title if scope else "",
            )

    def _invited_class(self, db, code):
        row = db.query(Classroom).filter_by(invite_code=code.strip().upper()).first()
        if row is None:
            raise ValueError("邀请码无效或已失效")
        if row.status != "active":
            raise RuntimeError("该班级已停用，无法加入")
        return row

    def join_class(self, code, student_id):
        with SessionLocal() as db:
            self._lock_write(db)
            row = self._invited_class(db, code)
            student = db.get(User, student_id)
            if not student or student.role != "student" or not student.is_active:
                raise PermissionError("仅有效学生账号可以加入班级")
            existing = (
                db.query(ClassEnrollment)
                .filter_by(class_id=row.id, student_user_id=student_id)
                .first()
            )
            if not existing:
                self._ensure_capacity(db, row)
                # Savepoint + the existing unique constraint handle concurrent joins.
                try:
                    with db.begin_nested():
                        db.add(ClassEnrollment(class_id=row.id, student_user_id=student_id))
                        db.flush()
                    emit(
                        db,
                        user_id=row.teacher_user_id,
                        sender_id=student_id,
                        event_key=f"joined:{row.id}:{student_id}",
                        title="学生加入班级",
                        content=f"{student.username} 已加入 {row.name}",
                        type="class",
                        related_type="class",
                        related_id=row.id,
                    )
                    latest_scope = (
                        db.query(TeachingScope)
                        .filter_by(class_id=row.id, student_user_id=None)
                        .order_by(TeachingScope.id.desc())
                        .first()
                    )
                    if latest_scope:
                        self._publish_scope_to_students(db, latest_scope, only_student=student)
                    else:
                        db.commit()
                except IntegrityError:
                    db.rollback()
                    if (
                        not db.query(ClassEnrollment)
                        .filter_by(class_id=row.id, student_user_id=student_id)
                        .first()
                    ):
                        raise
            return self._class_to_item(db, row).model_copy(update={"invite_code": None})

    def list_members(self, class_id, teacher_id, role):
        self.ensure_teacher_class_access(class_id, teacher_id, role)
        with SessionLocal() as db:
            rows = (
                db.query(User, ClassEnrollment)
                .join(ClassEnrollment, ClassEnrollment.student_user_id == User.id)
                .filter(ClassEnrollment.class_id == class_id)
                .order_by(User.id)
                .all()
            )
            return [
                ClassMember(user_id=u.id, username=u.username, joined_at=e.created_at)
                for u, e in rows
            ]

    def update_class(self, class_id, payload, teacher_id):
        with SessionLocal() as db:
            self._lock_write(db)
            row = self._teacher_class(db, class_id, teacher_id)
            row.name, row.subject = payload.name, payload.subject
            row.teacher_name, row.status = (
                payload.teacher_name or db.get(User, teacher_id).username,
                payload.status,
            )
            row.join_mode = payload.join_mode
            row.description = payload.description
            row.objective = payload.objective
            row.syllabus = payload.syllabus
            row.semester = payload.semester
            row.is_public = payload.is_public
            if payload.capacity:
                members = db.query(ClassEnrollment).filter_by(class_id=row.id).count()
                if payload.capacity < members:
                    raise RuntimeError("人数上限不能小于当前成员数")
            row.capacity = payload.capacity
            course = db.get(Course, row.course_id) if row.course_id else None
            if course:
                course.title, course.subject, course.status = row.name, row.subject, row.status
                course.description = row.description or f"{row.name}课程"
            db.commit()
            return self._class_to_item(db, row)

    def rotate_invite(self, class_id, teacher_id):
        with SessionLocal() as db:
            self._lock_write(db)
            row = self._teacher_class(db, class_id, teacher_id)
            row.invite_code = secrets.token_hex(8).upper()
            db.commit()
            return self._class_to_item(db, row)

    def remove_member(self, class_id, student_id, teacher_id):
        with SessionLocal() as db:
            self._lock_write(db)
            self._teacher_class(db, class_id, teacher_id)
            db.query(ClassEnrollment).filter_by(
                class_id=class_id, student_user_id=student_id
            ).delete()
            for path in db.query(LearningPath).filter_by(user_id=student_id, status="active").all():
                scope = (path.path_data_json or {}).get("teacher_scope", {})
                if scope.get("class_id") == class_id:
                    path.status = "archived"
            db.commit()
        return self.list_members(class_id, teacher_id, "teacher")

    def leave_class(self, class_id, student_id):
        """Student leaves a classroom; past submissions remain, future schedule stops."""

        with SessionLocal() as db:
            self._lock_write(db)
            room = db.get(Classroom, class_id)
            if room is None:
                raise ValueError("课堂不存在")
            enrollment = (
                db.query(ClassEnrollment)
                .filter_by(class_id=class_id, student_user_id=student_id)
                .first()
            )
            if enrollment is not None:
                db.delete(enrollment)
                for path in (
                    db.query(LearningPath)
                    .filter_by(user_id=student_id, status="active")
                    .all()
                ):
                    scope = (path.path_data_json or {}).get("teacher_scope", {})
                    if scope.get("class_id") == class_id:
                        path.status = "archived"
                emit(
                    db,
                    user_id=room.teacher_user_id,
                    sender_id=student_id,
                    event_key=f"left:{class_id}:{student_id}",
                    title="学生退出课堂",
                    content=f"{db.get(User, student_id).username} 退出了 {room.name}",
                    type="class",
                    related_type="class",
                    related_id=class_id,
                )
                db.commit()
            return self._class_to_item(db, room).model_copy(update={"invite_code": None})
