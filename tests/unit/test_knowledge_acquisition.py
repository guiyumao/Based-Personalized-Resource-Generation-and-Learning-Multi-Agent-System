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


def test_owned_saved_supplement_reused_without_new_search(coverage_db, monkeypatch):
    from common.models.learning import KnowledgeCandidate
    from services.agent_service.app.services import knowledge_tasks
    db = coverage_db
    monkeypatch.setattr(knowledge_acquisition, 'assess_coverage', lambda *a, **kw: {
        'chunks': [], 'state': 'MISSING', 'point_id': 1, 'subject': 'computer_networks',
        'knowledge_point': 'BBR', 'missing_facets': ['definition']})
    db.add(KnowledgeCandidate(creator_user_id=7, source_task_id=1, subject='computer_networks',
        knowledge_point='BBR', title='Saved BBR source', content='BBR reliable source text',
        source_url='https://example.org/bbr', source_hash='h', content_hash='c', status='DRAFT'))
    db.commit()
    monkeypatch.setattr(knowledge_tasks, 'create_task', lambda *a, **kw: pytest.fail('Repeated external search'))
    result = knowledge_acquisition.acquire_context(db, actor_user_id=7, subject='网络', knowledge_point='BBR', allow_web=True)
    assert result['supplementation']['reused'] is True
    assert result['supplementation']['candidate_ids']
    assert result['retrieval_context']['retrieved_chunks'][0]['content'] == 'BBR reliable source text'
    disabled = knowledge_acquisition.acquire_context(db, actor_user_id=8, subject='网络', knowledge_point='BBR', allow_web=False)
    assert disabled['retrieval_context']['retrieved_chunks'] == []


def test_search_fetch_persists_candidate_then_next_request_reuses_it(coverage_db, monkeypatch):
    from common.models.learning import KnowledgeBuildTask, KnowledgeCandidate
    from services.agent_service.app.services import knowledge_tasks
    db = coverage_db
    monkeypatch.setattr(knowledge_acquisition, 'assess_coverage', lambda *a, **kw: {
        'chunks': [], 'state': 'MISSING', 'point_id': 1, 'subject': 'computer_networks',
        'knowledge_point': 'BBR', 'missing_facets': ['definition']})
    operations = []
    def create(db, **kwargs):
        operation = kwargs['operation_type']; operations.append(operation)
        row = KnowledgeBuildTask(actor_user_id=7, client_request_id=kwargs['client_request_id'],
            request_hash=operation, trigger_source='test',
            operation_type=operation, subject=kwargs['subject'], status='COMPLETED',
            result_json={'sources': [{'url': 'https://source.example/bbr'}]} if operation == 'SEARCH_SOURCES' else
                {'source': {'url': 'https://source.example/bbr', 'title': 'BBR source', 'content': 'Reliable BBR source text for a saved candidate.'}})
        db.add(row); db.commit()
        return row
    monkeypatch.setattr(knowledge_tasks, 'create_task', create)
    monkeypatch.setattr(knowledge_tasks, 'execute_task', lambda task_id: None)
    first = knowledge_acquisition.acquire_context(db, actor_user_id=7, subject='网络', knowledge_point='BBR', allow_web=True)
    second = knowledge_acquisition.acquire_context(db, actor_user_id=7, subject='网络', knowledge_point='BBR', allow_web=True)
    assert operations == ['SEARCH_SOURCES', 'FETCH_SOURCE']
    assert db.query(KnowledgeCandidate).count() == 1
    assert first['supplementation']['reused'] is False
    assert second['supplementation']['reused'] is True
    assert first['supplementation']['candidate_ids'] == second['supplementation']['candidate_ids']
    assert first['retrieval_context']['retrieved_chunks'] == second['retrieval_context']['retrieved_chunks']
