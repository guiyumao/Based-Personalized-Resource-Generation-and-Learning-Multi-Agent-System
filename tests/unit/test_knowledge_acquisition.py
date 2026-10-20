import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.models.learning import KnowledgePoint, SystemSubject
from services.agent_service.app.services import knowledge_acquisition


@pytest.fixture
def coverage_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'coverage.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(knowledge_acquisition, "CORPUS_DIR", tmp_path / "corpus")
    with sessionmaker(bind=engine)() as db:
        subject = SystemSubject(name="计算机网络", code="computer_networks", description="network")
        db.add(subject); db.flush()
        db.add(KnowledgePoint(name="BBR", aliases_json=["BBR拥塞控制"], subject_id=subject.id))
        db.commit()
        yield db
    engine.dispose()


def test_index_failure_is_not_missing(coverage_db, monkeypatch):
    class Broken:
        is_available = False
    monkeypatch.setattr(knowledge_acquisition, "ChromaRetriever", Broken)
    result = knowledge_acquisition.assess_coverage(coverage_db, subject="计算机网络", knowledge_point="BBR")
    assert result["state"] == "RETRIEVAL_FAILURE"


def test_alias_and_actual_content_contribute_to_coverage(coverage_db, monkeypatch):
    class Indexed:
        is_available = True
        def retrieve_with_metadata(self, *args, **kwargs):
            return [{"id": "bbr", "content": "BBR definition algorithm example", "metadata": {"subject": "computer_networks"}}]
    monkeypatch.setattr(knowledge_acquisition, "ChromaRetriever", Indexed)
    result = knowledge_acquisition.assess_coverage(coverage_db, subject="计算机网络", knowledge_point="BBR拥塞控制")
    assert result["state"] == "COMPLETE"
    assert result["point_id"] is not None


def test_absence_needs_known_catalog_and_available_index(coverage_db, monkeypatch):
    class Empty:
        is_available = True
        def retrieve_with_metadata(self, *args, **kwargs): return []
    monkeypatch.setattr(knowledge_acquisition, "ChromaRetriever", Empty)
    assert knowledge_acquisition.assess_coverage(coverage_db, subject="计算机网络", knowledge_point="BBR")["state"] == "MISSING"
    assert knowledge_acquisition.assess_coverage(coverage_db, subject="计算机网络", knowledge_point="unknown")["state"] == "UNCERTAIN"
