"""Shared pytest fixtures for database-backed tests."""

# ruff: noqa: E402 -- install safety boundary before project imports

from __future__ import annotations

# Must run before importing common.config, session, fixtures, or LLM clients.
from scripts.run_no_cost_tests import bootstrap_pytest

bootstrap_pytest()

from uuid import uuid4
from itertools import count

import pytest

from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import (
    AnswerRecord,
    AssistantAgentExecution,
    AssistantTask,
    ChatMessage,
    ChatSession,
    Exercise,
    LearningReport,
    ResourceInteraction,
    User,
    UserProfile,
)
from common.security.auth import create_access_token, hash_password

# Background analysis is keyed by user ID; reusing a just-deleted SQLite rowid
# can attach a previous fixture's thread/status to a different test account.
_test_user_ids = count(10000)


def _purge_user_chat_data(db, user_id: int) -> None:
    """Delete a test user's chat rows.

    Chat messages reference sessions but there is no ORM cascade from the
    fixture, so leftovers used to survive teardown and leak into later runs.
    """

    session_ids = [
        sid for (sid,) in db.query(ChatSession.id).filter(ChatSession.user_id == user_id).all()
    ]
    if session_ids:
        task_ids = [task_id for (task_id,) in db.query(AssistantTask.id).filter(
            AssistantTask.session_id.in_(session_ids)
        ).all()]
        if task_ids:
            db.query(AssistantAgentExecution).filter(AssistantAgentExecution.task_id.in_(task_ids)).delete(
                synchronize_session=False
            )
            db.query(AssistantTask).filter(AssistantTask.id.in_(task_ids)).delete(
                synchronize_session=False
            )
        db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(
            synchronize_session=False
        )
        db.query(ChatSession).filter(ChatSession.id.in_(session_ids)).delete(
            synchronize_session=False
        )


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
        id=next(_test_user_ids),
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
        for (exercise_id,) in db_session.query(AnswerRecord.exercise_id)
        .filter(AnswerRecord.user_id == user.id)
        .all()
    ]
    db_session.query(AnswerRecord).filter(AnswerRecord.user_id == user.id).delete()
    db_session.query(LearningReport).filter(LearningReport.user_id == user.id).delete()
    db_session.query(ResourceInteraction).filter(ResourceInteraction.user_id == user.id).delete()
    _purge_user_chat_data(db_session, user.id)

    profile = db_session.get(UserProfile, user.id)
    if profile is not None:
        db_session.delete(profile)

    if exercise_ids:
        db_session.query(Exercise).filter(Exercise.id.in_(exercise_ids)).delete(
            synchronize_session=False
        )

    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


@pytest.fixture
def auth_headers(test_user) -> dict[str, str]:
    """Bearer header for ``test_user``.

    The ``/users/{user_id}/...`` endpoints are object-level protected, so tests
    must present the token of the user they operate on.
    """

    return {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}


@pytest.fixture
def other_user(db_session):
    """A second isolated user, used for cross-account authorization tests."""

    username = f"pytest_other_{uuid4().hex[:8]}"
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

    _purge_user_chat_data(db_session, user.id)
    profile = db_session.get(UserProfile, user.id)
    if profile is not None:
        db_session.delete(profile)
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


def _create_role_user(db_session, role: str) -> User:
    """Create a committed user with the requested role plus an empty profile."""

    username = f"pytest_{role}_{uuid4().hex[:8]}"
    user = User(
        username=username,
        password_hash=hash_password("pytest-password"),
        role=role,
        email=f"{username}@example.com",
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserProfile(
            user_id=user.id,
            mastery_json={},
            learning_style="",
            cognitive_abilities={},
            habits={},
        )
    )
    db_session.commit()
    db_session.refresh(user)
    return user


def _teardown_role_user(db_session, user: User) -> None:
    """Remove a role user created by ``_create_role_user``."""

    _purge_user_chat_data(db_session, user.id)
    profile = db_session.get(UserProfile, user.id)
    if profile is not None:
        db_session.delete(profile)
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


@pytest.fixture
def teacher_user(db_session):
    """A committed teacher account scoped to one test."""

    user = _create_role_user(db_session, "teacher")
    yield user
    _teardown_role_user(db_session, user)


@pytest.fixture
def admin_user(db_session):
    """A committed admin account scoped to one test."""

    user = _create_role_user(db_session, "admin")
    yield user
    _teardown_role_user(db_session, user)


@pytest.fixture
def teacher_headers(teacher_user) -> dict[str, str]:
    """Bearer header for ``teacher_user``."""

    return {"Authorization": f"Bearer {create_access_token(str(teacher_user.id))}"}


@pytest.fixture
def admin_headers(admin_user) -> dict[str, str]:
    """Bearer header for ``admin_user``."""

    return {"Authorization": f"Bearer {create_access_token(str(admin_user.id))}"}
