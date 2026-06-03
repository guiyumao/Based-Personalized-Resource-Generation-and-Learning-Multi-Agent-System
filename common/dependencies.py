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
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.models.learning import User
from common.security.auth import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the JWT bearer token, returning the authenticated User.

    Returns 401 if the token is missing, expired, or the user does not exist.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
        )

    token = credentials.credentials
    payload = decode_access_token(token)
    user_id: int = int(payload["sub"])

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


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
