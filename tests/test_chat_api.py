"""Simple test to verify chat service setup."""

import requests
import json

BASE_URL = "http://localhost:8002"

def test_chat_api():
    """Test chat API endpoints."""
    print("=" * 60)
    print("Testing Chat API")
    print("=" * 60)

    # Test 1: Create session
    print("\n1. Creating new chat session...")
    try:
        response = requests.post(
            f"{BASE_URL}/chat/sessions/new",
            json={
                "user_id": 1,
                "title": "Python 学习讨论",
                "subject": "Python"
            }
        )
        response.raise_for_status()
        session = response.json()
        session_id = session["id"]
        print(f"✓ Session created: ID={session_id}")
    except Exception as e:
        print(f"✗ Failed to create session: {e}")
        return

    # Test 2: Send simple message
    print("\n2. Sending simple question...")
    try:
        response = requests.post(
            f"{BASE_URL}/chat/chat",
            json={
                "session_id": session_id,
                "user_id": 1,
                "content": "什么是Python？"
            }
        )
        response.raise_for_status()
        result = response.json()
        print(f"✓ Response received:")
        print(f"  Model: {result['model_used']}")
        print(f"  Content: {result['content'][:100]}...")
    except Exception as e:
        print(f"✗ Failed to send message: {e}")
        return

    # Test 3: List sessions
    print("\n3. Listing sessions...")
    try:
        response = requests.get(
            f"{BASE_URL}/chat/sessions",
            params={"user_id": 1}
        )
        response.raise_for_status()
        sessions = response.json()
        print(f"✓ Found {len(sessions)} session(s)")
    except Exception as e:
        print(f"✗ Failed to list sessions: {e}")

    print("\n" + "=" * 60)
    print("✓ Basic tests completed")
    print("=" * 60)


if __name__ == "__main__":
    print("\nMake sure the service is running:")
    print("cd services/agent_service")
    print("uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload\n")

    input("Press Enter to start testing...")
    test_chat_api()
