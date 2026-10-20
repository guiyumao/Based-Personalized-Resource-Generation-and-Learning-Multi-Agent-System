"""Private note and flashcard persistence, authorization and review progression."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from common.db.base import Base
from common.db.session import get_db
from common.models.learning import CardReviewEvent, ReviewCard, User
from common.security.auth import create_access_token
from services.agent_service.app.services.llm_factory import LLMFactory
from services.user_service.app.main import app


def test_note_card_workflow_is_private_and_persistent(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([User(username="owner", password_hash="hash", role="student"), User(username="other", password_hash="hash", role="student")])
        db.commit()
        owner_id = db.query(User.id).filter(User.username == "owner").scalar()
        other_id = db.query(User.id).filter(User.username == "other").scalar()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        owner = {"Authorization": f"Bearer {create_access_token(str(owner_id))}"}
        other = {"Authorization": f"Bearer {create_access_token(str(other_id))}"}
        assert client.get("/study/notes").status_code == 401
        note_response = client.post("/study/notes", headers=owner, json={"title": "分数", "body": "先通分"})
        assert note_response.status_code == 201
        note_id = note_response.json()["id"]
        assert client.get("/study/notes", headers=other).json()["total"] == 0
        assert client.put(f"/study/notes/{note_id}", headers=other, json={"title": "x", "body": "y"}).status_code == 404
        assert client.post("/study/cards", headers=other, json={"front": "Q", "back": "A", "source_note_id": note_id}).status_code == 404

        class FakeModel:
            def invoke(self, _messages):
                return type("Result", (), {"content": '{"organized_note":"通分步骤：找公分母。","cards":[{"front":"通分先做什么？","back":"找公分母"}]}'} )()

        monkeypatch.setattr(LLMFactory, "build_for_task", lambda self, task, temperature=0.2: FakeModel())
        organized = client.post(f"/study/notes/{note_id}/organize", headers=owner)
        assert organized.status_code == 200
        assert organized.json()["cards"][0]["front"] == "通分先做什么？"
        assert client.post(f"/study/notes/{note_id}/organize", headers=other).status_code == 404

        card_response = client.post("/study/cards", headers=owner, json={"front": "如何通分？", "back": "找公分母", "source_note_id": note_id})
        assert card_response.status_code == 201
        card_id = card_response.json()["id"]
        assert client.get("/study/cards?due_only=true", headers=owner).json()["due_count"] == 1
        assert client.post(f"/study/cards/{card_id}/review", headers=other, json={"grade": 4}).status_code == 404
        assert client.post(f"/study/cards/{card_id}/review", headers=owner, json={"grade": 7}).status_code == 422

        reviewed = client.post(f"/study/cards/{card_id}/review", headers=owner, json={"grade": 4})
        assert reviewed.status_code == 200
        assert reviewed.json()["interval_days"] == 1
        assert reviewed.json()["review_count"] == 1
        history = client.get(f"/study/cards/{card_id}/reviews", headers=owner)
        assert history.status_code == 200
        assert len(history.json()) == 1
        assert history.json()[0]["grade"] == 4
        assert client.get(f"/study/cards/{card_id}/reviews", headers=other).status_code == 404
        assert client.post(f"/study/cards/{card_id}/review", headers=owner, json={"grade": 4}).status_code == 409
        assert client.get("/study/cards?due_only=true", headers=owner).json()["due_count"] == 0

        assert client.delete(f"/study/notes/{note_id}", headers=owner).status_code == 204
        with factory() as db:
            assert db.get(ReviewCard, card_id).source_note_id is None
        assert client.delete(f"/study/cards/{card_id}", headers=owner).status_code == 204
        with factory() as db:
            assert db.query(CardReviewEvent).filter(CardReviewEvent.card_id == card_id).count() == 0
    finally:
        app.dependency_overrides.clear()
