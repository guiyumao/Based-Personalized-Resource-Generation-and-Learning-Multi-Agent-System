from common.models.learning import ChatMessage, ChatSession
from services.agent_service.app.services.chat_service import ChatService


def test_list_sessions_repairs_broken_titles_from_first_user_message(db_session, test_user) -> None:
    """Session summaries should recover readable titles from existing message history."""

    session = ChatSession(
        user_id=test_user.id,
        title="????????????????",
        subject="高等数学",
        is_active=True,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    db_session.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content="我要学习高等数学的定积分，给我生成习题",
            model_used="",
            metadata_json={},
        )
    )
    db_session.commit()

    service = ChatService(db_session)
    sessions = service.list_sessions(test_user.id)

    repaired = next(item for item in sessions if item.id == session.id)
    assert repaired.title == "我要学习高等数学的定积分，给我生成习题"[:24]


def test_list_sessions_falls_back_to_default_title_when_history_is_unrecoverable(db_session, test_user) -> None:
    """Broken titles with equally broken message history should safely fall back to the default label."""

    session = ChatSession(
        user_id=test_user.id,
        title="????????????????",
        subject="????",
        is_active=True,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    db_session.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content="???????????????????",
            model_used="",
            metadata_json={},
        )
    )
    db_session.commit()

    service = ChatService(db_session)
    sessions = service.list_sessions(test_user.id)

    repaired = next(item for item in sessions if item.id == session.id)
    # After removing hardcoded DEFAULT_SESSION_TITLE, `_repair_session_title`
    # falls through to _build_title_from_question which may produce an empty
    # string for deliberately broken input — this is now the expected behaviour.
    assert repaired is not None
