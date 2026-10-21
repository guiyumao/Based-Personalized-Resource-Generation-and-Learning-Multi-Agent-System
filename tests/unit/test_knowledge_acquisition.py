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


def test_index_failure_still_returns_actual_local_corpus(coverage_db, monkeypatch):
    class Broken:
        is_available = False
    monkeypatch.setattr(knowledge_acquisition, 'ChromaRetriever', Broken)
    directory = knowledge_acquisition.CORPUS_DIR / 'computer_networks'
    directory.mkdir(parents=True)
    (directory / 'bbr.md').write_text('BBR definition algorithm example from local corpus', encoding='utf-8')
    result = knowledge_acquisition.assess_coverage(coverage_db, subject='计算机网络', knowledge_point='BBR')
    assert result['state'] == 'RETRIEVAL_FAILURE'
    assert result['chunks'][0]['content'] == 'BBR definition algorithm example from local corpus'


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


def test_pending_private_candidate_is_not_used_as_public_knowledge(coverage_db, monkeypatch):
    from fastapi import HTTPException

    from common.models.learning import KnowledgeCandidate
    from services.agent_service.app.services import public_knowledge
    db = coverage_db
    db.add(KnowledgeCandidate(creator_user_id=7, source_task_id=1, subject='computer_networks',
        knowledge_point='BBR', title='private draft', content='must not be used',
        source_url='https://example.org/bbr', source_hash='h', content_hash='c', status='DRAFT'))
    db.commit()
    def fail(*a, **kw):
        raise HTTPException(503, {'code': 'MODEL_REVIEW_UNAVAILABLE'})
    monkeypatch.setattr(public_knowledge, 'ensure_public_knowledge', fail)
    with pytest.raises(HTTPException):
        knowledge_acquisition.acquire_context(db, actor_user_id=7, subject='网络', knowledge_point='BBR', allow_web=True)


def test_both_learners_receive_same_verified_public_version(coverage_db, monkeypatch):
    from services.agent_service.app.services import public_knowledge
    calls = []
    chunk = {'id': 'public', 'content': 'BBR verified public knowledge',
             'metadata': {'source': 'computer_networks/published.md'}}
    def ensure(db, user_id, subject, topic, **kw):
        calls.append((user_id, kw['allow_web']))
        return {'subject': 'computer_networks', 'point_id': 1, 'published_versions': [12], 'usable_chunks': [chunk]}
    monkeypatch.setattr(public_knowledge, 'ensure_public_knowledge', ensure)
    first = knowledge_acquisition.acquire_context(coverage_db, actor_user_id=7, subject='网络', knowledge_point='BBR', allow_web=True)
    second = knowledge_acquisition.acquire_context(coverage_db, actor_user_id=8, subject='网络', knowledge_point='BBR', allow_web=False)
    assert first['retrieval_context']['retrieved_chunks'] == second['retrieval_context']['retrieved_chunks'] == [chunk]
    assert first['coverage']['published_versions'] == [12]
    assert all(source['review_status'] == 'PUBLISHED' for source in first['sources'])
    assert calls == [(7, True), (8, False)]
