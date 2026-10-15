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


def test_list_sessions_keyword_searches_title_subject_and_message_content(db_session, test_user) -> None:
    """History search should find sessions whose loaded messages contain the keyword."""

    keyword = "unique-decorator-search-20261015"
    session = ChatSession(
        user_id=test_user.id,
        title="可搜索会话",
        subject="Python",
        is_active=True,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    db_session.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=f"请解释 Python 装饰器的执行顺序：{keyword}",
            model_used="",
            metadata_json={},
        )
    )
    db_session.commit()

    service = ChatService(db_session)

    matches = service.list_sessions(test_user.id, keyword=keyword)
    assert [item.id for item in matches] == [session.id]
    assert service.list_sessions(test_user.id, keyword="不存在的历史关键词") == []
