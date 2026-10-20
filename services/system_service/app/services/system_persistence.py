"""Database-backed system administration manager."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from common.db.session import SessionLocal
from common.models.learning import AnswerRecord, AuditLog, LearningPath, Resource, SystemConfig, SystemSubject, User
from services.system_service.app.schemas.system import (
    AuditLogItem,
    AdminDashboard,
    AdminUserItem,
    AdminUserPage,
    RoleAssignment,
    SubjectCreate,
    SubjectItem,
    SystemConfigItem,
)


class SystemManager:
    def dashboard(self) -> AdminDashboard:
        """Return counts sourced from persisted tables; no fabricated token usage."""

        since = (datetime.now(UTC) - timedelta(days=7)).replace(tzinfo=None)
        with SessionLocal() as db:
            return AdminDashboard(
                total_users=db.query(func.count(User.id)).scalar() or 0,
                active_users=db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0,
                total_learning_paths=db.query(func.count(LearningPath.id)).scalar() or 0,
                total_resources=db.query(func.count(Resource.id)).scalar() or 0,
                answers_last_7_days=db.query(func.count(AnswerRecord.id)).filter(AnswerRecord.created_at >= since).scalar() or 0,
            )

    def list_users(self, page: int, size: int, keyword: str | None = None, role: str | None = None) -> AdminUserPage:
        with SessionLocal() as db:
            query = db.query(User)
            if keyword:
                literal = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                pattern = f"%{literal}%"
                query = query.filter(or_(
                    User.username.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                ))
            if role:
                query = query.filter(User.role == role)
            total = query.count()
            users = query.order_by(User.id.desc()).offset((page - 1) * size).limit(size).all()
            return AdminUserPage(
                total=total,
                page=page,
                size=size,
                items=[
                    AdminUserItem(
                        id=user.id,
                        username=user.username,
                        email=user.email,
                        role=user.role,
                        is_active=bool(user.is_active),
                        created_at=user.created_at.isoformat() if user.created_at else "",
                    )
                    for user in users
                ],
            )

    def assign_role(self, payload: RoleAssignment, actor_user_id: int | None = None) -> dict[str, object]:
        role = payload.role.strip().lower()
        if role not in {"student", "teacher", "admin"}:
            raise ValueError("Role must be student, teacher, or admin.")
        with SessionLocal() as db:
            user = db.get(User, payload.user_id)
            if user is None:
                raise LookupError("User not found.")
            if user.id == actor_user_id and role != "admin":
                raise ValueError("You cannot remove your own administrator role.")
            user.role = role
            self._log(db, "INFO", "role_assigned", f"Assigned role `{role}` to user {user.id}.", actor_user_id)
            db.commit()
            return {"user_id": user.id, "role": role, "status": "updated"}

    def set_user_status(self, user_id: int, is_active: bool, actor_user_id: int) -> dict[str, object]:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is None:
                raise LookupError("User not found.")
            if user.id == actor_user_id and not is_active:
                raise ValueError("You cannot disable your own account.")
            if user.role == "admin" and not is_active:
                active_admins = db.query(func.count(User.id)).filter(
                    User.role == "admin", User.is_active.is_(True)
                ).scalar() or 0
                if active_admins <= 1:
                    raise ValueError("The last active administrator cannot be disabled.")
            user.is_active = is_active
            self._log(db, "WARN", "user_status_changed", f"Set user {user.id} active={is_active}.", actor_user_id)
            db.commit()
            return {"user_id": user.id, "is_active": bool(user.is_active)}

    def list_subjects(self) -> list[SubjectItem]:
        with SessionLocal() as db:
            return [SubjectItem(id=x.id, name=x.name, description=x.description) for x in db.query(SystemSubject).order_by(SystemSubject.name).all()]

    def create_subject(self, payload: SubjectCreate, actor_user_id: int | None = None) -> SubjectItem:
        with SessionLocal() as db:
            record = SystemSubject(name=payload.name.strip(), description=payload.description.strip())
            db.add(record)
            self._log(db, "INFO", "subject_created", f"Created subject `{record.name}`.", actor_user_id)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ValueError("Subject name already exists.") from exc
            db.refresh(record)
            return SubjectItem(id=record.id, name=record.name, description=record.description)

    def list_configs(self) -> list[SystemConfigItem]:
        with SessionLocal() as db:
            return [SystemConfigItem(key=x.key, value=x.value) for x in db.query(SystemConfig).order_by(SystemConfig.key).all()]

    def update_config(self, key: str, value: str, actor_user_id: int | None = None) -> SystemConfigItem:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("Config key cannot be empty.")
        with SessionLocal() as db:
            record = db.get(SystemConfig, normalized_key)
            event = "config_updated"
            if record is None:
                record = SystemConfig(key=normalized_key, value=value)
                db.add(record)
                event = "config_created"
            else:
                record.value = value
            self._log(db, "WARN", event, f"Stored config `{normalized_key}`.", actor_user_id)
            db.commit()
            return SystemConfigItem(key=record.key, value=record.value)

    def list_logs(self, level: str | None = None) -> list[AuditLogItem]:
        with SessionLocal() as db:
            query = db.query(AuditLog)
            if level:
                query = query.filter(AuditLog.level == level.strip().upper())
            return [AuditLogItem(level=x.level, event=x.event, message=x.message) for x in query.order_by(AuditLog.id.desc()).limit(500).all()]

    def _log(self, db, level: str, event: str, message: str, actor_user_id: int | None) -> None:
        db.add(AuditLog(level=level, event=event, message=message, actor_user_id=actor_user_id))
