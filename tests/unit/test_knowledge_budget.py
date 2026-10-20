import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.models.learning import KnowledgeBudgetCounter
from services.agent_service.app.services import knowledge_budget


def test_budget_reservations_are_atomic_and_task_bound(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(knowledge_budget, "SessionLocal", factory)
    monkeypatch.setenv("KNOWLEDGE_SEARCH_DAY_LIMIT", "1")
    token = knowledge_budget.current_knowledge_task.set(10)
    try:
        knowledge_budget.reserve_usage("search")
        with pytest.raises(knowledge_budget.KnowledgeBudgetExceeded):
            knowledge_budget.reserve_usage("search")
        assert knowledge_budget.task_usage(10)["search_calls"] == 1
        with factory() as db:
            assert db.get(KnowledgeBudgetCounter, "task:10").search_calls == 1
    finally:
        knowledge_budget.current_knowledge_task.reset(token)
        engine.dispose()
