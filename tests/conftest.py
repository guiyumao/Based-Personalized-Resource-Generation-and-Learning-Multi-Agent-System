"""Shared pytest fixtures for database-backed tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import AnswerRecord, Exercise, LearningReport, User, UserProfile
from common.security.auth import hash_password


@pytest.fixture(scope="session", autouse=True)
def initialize_database_schema():
    """Ensure the shared local test database schema exists before any test runs."""

    ensure_database_schema()


@pytest.fixture
def db_session():
    """Yield a real project database session for one test."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user(db_session):
    """Create an isolated user so report tests do not interfere with real records."""

    username = f"pytest_user_{uuid4().hex[:8]}"
    user = User(
        username=username,
        password_hash=hash_password("pytest-password"),
        role="student",
        email=f"{username}@example.com",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    yield user

    exercise_ids = [
        exercise_id
        for (exercise_id,) in db_session.query(AnswerRecord.exercise_id).filter(AnswerRecord.user_id == user.id).all()
    ]
    db_session.query(AnswerRecord).filter(AnswerRecord.user_id == user.id).delete()
    db_session.query(LearningReport).filter(LearningReport.user_id == user.id).delete()

    profile = db_session.get(UserProfile, user.id)
    if profile is not None:
        db_session.delete(profile)

    if exercise_ids:
        db_session.query(Exercise).filter(Exercise.id.in_(exercise_ids)).delete(synchronize_session=False)

    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()
