"""Account creation and disablement must respect the existing role model."""

from uuid import uuid4

from fastapi.testclient import TestClient

from common.models.learning import User, UserProfile
from services.system_service.app.main import app as system_app
from services.user_service.app.main import app as user_app


def test_public_registration_cannot_choose_privileged_role():
    client = TestClient(user_app)
    for role in ("teacher", "admin"):
        response = client.post(
            "/users/register",
            json={"username": f"denied_{uuid4().hex[:8]}", "password": "a-safe-password", "role": role},
        )
        assert response.status_code == 422


def test_only_admin_can_create_privileged_account(admin_headers, auth_headers, db_session):
    client = TestClient(user_app)
    username = f"managed_{uuid4().hex[:8]}"
    payload = {"username": username, "password": "a-safe-password", "role": "teacher"}
    assert client.post("/users", json=payload).status_code == 401
    assert client.post("/users", json=payload, headers=auth_headers).status_code == 403
    response = client.post("/users", json=payload, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["role"] == "teacher"
    try:
        user = db_session.query(User).filter(User.username == username).one()
        assert user.role == "teacher"
    finally:
        user = db_session.query(User).filter(User.username == username).one_or_none()
        if user:
            profile = db_session.get(UserProfile, user.id)
            if profile:
                db_session.delete(profile)
            db_session.delete(user)
            db_session.commit()


def test_disabled_account_cannot_login_or_use_existing_token(test_user, auth_headers, admin_headers, db_session):
    users = TestClient(user_app)
    system = TestClient(system_app)
    response = system.patch(
        f"/system/users/{test_user.id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 200
    try:
        db_session.expire(test_user)
        assert not test_user.is_active
        assert users.get("/users/me", headers=auth_headers).status_code == 401
        assert users.post(
            "/users/login",
            json={"username": test_user.username, "password": "pytest-password"},
        ).status_code == 401
    finally:
        response = system.patch(
            f"/system/users/{test_user.id}/status",
            json={"is_active": True},
            headers=admin_headers,
        )
        assert response.status_code == 200


def test_admin_cannot_disable_self_or_remove_own_role(admin_user, admin_headers):
    system = TestClient(system_app)
    assert system.patch(
        f"/system/users/{admin_user.id}/status",
        json={"is_active": False},
        headers=admin_headers,
    ).status_code == 422
    assert system.post(
        "/system/roles/assign",
        json={"user_id": admin_user.id, "role": "student"},
        headers=admin_headers,
    ).status_code == 422
