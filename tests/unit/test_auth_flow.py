"""Tests for password hashing and login flow."""

from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.learning import User
from common.security.auth import hash_password, verify_password
from services.user_service.app.main import app


def test_bcrypt_hash_and_verify() -> None:
    """Password hashing should be verifiable."""

    password_hash = hash_password("12345678")
    assert verify_password("12345678", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_login_and_me_flow() -> None:
    """User should be able to login and fetch `/users/me`."""

    db = SessionLocal()
    existing = db.query(User).filter(User.username == "test_login_user").first()
    if existing is None:
        user = User(
            username="test_login_user",
            password_hash=hash_password("12345678"),
            role="student",
            email="test_login_user@example.com",
        )
        db.add(user)
        db.commit()
    db.close()

    client = TestClient(app)
    login_response = client.post(
        "/users/login",
        json={"username": "test_login_user", "password": "12345678"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "test_login_user"
