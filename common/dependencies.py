"""Shared FastAPI dependencies for authentication and authorization.

Provides:
- get_current_user  – JWT bearer token → User ORM instance
- require_role(*roles) – role-based access control dependency factory

Usage::

    from common.dependencies import get_current_user, require_role

    @router.get("/protected")
    def protected_route(current_user: User = Depends(get_current_user)):
        ...

    @router.post("/admin-only")
    def admin_only(current_user: User = Depends(require_role("admin"))):
        ...
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, object_session

from common.db.session import get_db
from common.models.learning import ClassEnrollment, Classroom, User
from common.security.auth import TokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the JWT bearer token, returning the authenticated User.

    Returns 401 if the token is missing, malformed, expired, signed with the wrong
    key, or refers to a user that no longer exists. Token problems are never
    allowed to surface as 500 responses.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        subject = payload.get("sub")
        if subject is None:
            raise TokenError("Token is missing the 'sub' claim")
        user_id = int(subject)
    except (TokenError, TypeError, ValueError):
        raise _UNAUTHORIZED from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    from common.performance import set_trace_context
    set_trace_context(user_id=user.id)
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Keep public reads open while validating a supplied bearer token."""
    if credentials is None:
        return None
    return get_current_user(credentials, db)


def require_self_or_admin(requested_user_id: int, current_user: User) -> None:
    """Raise 403 unless the caller is the requested user or an administrator.

    Object-level guard for every ``/users/{user_id}/...`` resource so a learner
    token cannot read or mutate another learner's data.
    """

    if current_user.role == "admin" or current_user.id == requested_user_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You may only access your own account",
    )


def require_self_or_staff(requested_user_id: int, current_user: User) -> None:
    """Raise 403 unless the caller is the requested user, a teacher, or an admin.

    Used by the teaching-side reporting endpoints: a learner may read their own
    data and a teacher may read the data of a learner they teach, but an
    unrelated learner token must not read someone else's records.
    """

    if current_user.role == "admin" or current_user.id == requested_user_id:
        return
    if current_user.role == "teacher":
        db = object_session(current_user) if isinstance(current_user, User) else None
        if db is not None and db.query(ClassEnrollment.id).join(
            Classroom, Classroom.id == ClassEnrollment.class_id,
        ).filter(
            Classroom.teacher_user_id == current_user.id,
            ClassEnrollment.student_user_id == requested_user_id,
        ).first() is not None:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You may only access your own records",
    )


def require_role(*roles: str):
    """Return a FastAPI dependency that requires the current user to have one of
    the specified roles.

    Must be used **after** ``get_current_user`` (or a dependency that calls it).
    """

    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return current_user

    return role_dependency
