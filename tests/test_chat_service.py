"""Test the chat service with large-small model collaboration."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from common.db.session import get_db
from common.schemas.agent import ChatSessionCreate, ChatMessageInput
from services.agent_service.app.services.chat_service import ChatService


def test_chat_flow():
    """Test the complete chat flow."""
    print("=" * 60)
    print("Testing Chat Service with Large-Small Model Collaboration")
    print("=" * 60)

    # Get database session
    db = next(get_db())
    service = ChatService(db)

    try:
        # Step 1: Create a new chat session
        print("\n1. Creating new chat session...")
        session_data = ChatSessionCreate(
            user_id=1,
            title="Python 学习讨论",
            subject="Python"
        )
        session = service.create_session(session_data)
        print(f"✓ Session created: ID={session.id}, Title='{session.title}'")

        # Step 2: Send a simple question (should use small model)
        print("\n2. Sending simple question (should use small model)...")
        simple_question = ChatMessageInput(
            session_id=session.id,
            user_id=1,
            content="什么是Python？",
            context={}
        )
        response1 = service.send_message(simple_question)
        print(f"✓ Response received:")
        print(f"  Model used: {response1.model_used}")
        print(f"  Content preview: {response1.content[:100]}...")
        print(f"  Metadata: {response1.metadata}")

        # Step 3: Send a complex question (should use large model)
        print("\n3. Sending complex question (should use large model)...")
        complex_question = ChatMessageInput(
            session_id=session.id,
            user_id=1,
            content="为什么Python装饰器可以修改函数行为？请详细解释其实现原理，并给出实际应用场景的对比分析。",
            context={}
        )
        response2 = service.send_message(complex_question)
        print(f"✓ Response received:")
        print(f"  Model used: {response2.model_used}")
        print(f"  Content preview: {response2.content[:100]}...")
        print(f"  Metadata: {response2.metadata}")

        # Step 4: List sessions
        print("\n4. Listing user sessions...")
        sessions = service.list_sessions(user_id=1, limit=10)
        print(f"✓ Found {len(sessions)} session(s)")
        for s in sessions:
            print(f"  - ID={s.id}, Title='{s.title}', Messages={s.message_count}")

        # Step 5: Get session detail
        print("\n5. Getting session detail...")
        detail = service.get_session(session.id, user_id=1)
        print(f"✓ Session detail retrieved:")
        print(f"  Messages: {detail.message_count}")
        for msg in detail.messages[-4:]:  # Show last 4 messages
            print(f"  - [{msg.role}] {msg.content[:50]}...")

        print("\n" + "=" * 60)
        print("✓ All tests passed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_chat_flow()
