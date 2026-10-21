"""Dashboard statistics are checked against isolated durable records, never a Provider."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.dependencies import get_current_user
from common.models.learning import AssistantTask, KnowledgeBudgetCounter, KnowledgeBuildTask
from common.models.operations import ModelCall, WorkerInstance
from services.agent_service.app.main import app


@pytest.fixture
def ledger(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard.sqlite'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


def admin():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role='admin')
    return TestClient(app)


def call(db, when, model='requested-model', **kwargs):
    row = ModelCall(id=str(uuid4()), mode='LIVE', provider='test', model=model,
        feature='assistant:courseware', status='SUCCEEDED', usage_status='KNOWN',
        input_tokens=10, output_tokens=5, started_at=when)
    for key, value in kwargs.items():
        setattr(row, key, value)
    db.add(row)
    return row


def task(db, status, when, kind='assistant', operation='courseware', attempt=1):
    if kind == 'assistant':
        row = AssistantTask(user_id=1, session_id=1, client_request_id=str(uuid4()), task_type=operation,
                            status=status, created_at=when, execution_attempt=attempt)
    else:
        row = KnowledgeBuildTask(actor_user_id=1, client_request_id=str(uuid4()), request_hash='test',
            trigger_source='test', operation_type=operation, status=status, created_at=when, execution_attempt=attempt)
    db.add(row)
    return row


RANGE = 'start=2020-01-02&end=2020-01-04'


def test_calendar_bounds_zero_fill_and_model_identity(ledger):
    with ledger() as db:
        call(db, datetime(2020, 1, 1, 23, 59, 59))
        call(db, datetime(2020, 1, 2), response_model='billing-unknown')
        call(db, datetime(2020, 1, 4, 23, 59, 59), model='second-model')
        call(db, datetime(2020, 1, 5))
        call(db, datetime(2020, 1, 3), mode='TEST')
        db.commit()
    client = admin()
    result = client.get('/admin/dashboard?' + RANGE).json()
    assert result['summary']['calls'] == 2
    assert [row['calls'] for row in result['daily']] == [1, 0, 1]
    assert {row['name'] for row in result['distribution']} == {'requested-model', 'second-model'}
    assert sum(row['value'] for row in result['distribution']) == result['summary']['calls']
    assert client.get('/admin/usage?' + RANGE).json()['total'] == 2
    assert client.get('/admin/dashboard?' + RANGE + '&mode=TEST').json()['summary']['calls'] == 1


def test_unknown_tokens_failed_consumption_and_cache_not_added(ledger):
    with ledger() as db:
        call(db, datetime(2020, 1, 2), input_tokens=100, cached_input_tokens=30)
        call(db, datetime(2020, 1, 3), status='FAILED', output_tokens=20, input_tokens=None, usage_status='PARTIAL')
        db.commit()
    result = admin().get('/admin/dashboard?' + RANGE).json()
    assert result['summary']['input_tokens'] is None
    assert result['summary']['known_input_subtotal'] == 100
    assert result['summary']['known_output_subtotal'] == 25
    assert result['summary']['cost'] is None
    assert result['summary']['unknown_or_partial_calls'] == 1


def test_success_denominator_attempt_dedup_and_same_length_comparison(ledger):
    with ledger() as db:
        for status in ['SUCCEEDED', 'FAILED', 'RUNNING', 'PENDING', 'CANCELLED', 'CANCEL_REQUESTED']:
            task(db, status, datetime(2020, 1, 2), attempt=3)
        task(db, 'COMPLETED', datetime(2020, 1, 3), kind='knowledge', operation='BUILD_POINT')
        task(db, 'FAILED', datetime(2020, 1, 1))
        db.commit()
    client = admin()
    result = client.get('/admin/dashboard?' + RANGE).json()
    assert result['completion']['denominator'] == 3
    assert result['completion']['rate'] == 2 / 3 * 100
    assert result['completion']['change_points'] == 2 / 3 * 100
    assert sum(r['count'] for r in result['tasks']) == 7
    tasks = client.get('/admin/operations/tasks?' + RANGE + '&kind=assistant&operation=courseware&state=running').json()
    assert tasks['total'] == 2
    assert {r['status'] for r in tasks['items']} == {'RUNNING', 'CANCEL_REQUESTED'}


def test_validation_and_empty_not_unknown(ledger):
    client = admin()
    for query in ['start=2020-01-01', 'start=2020-01-02&end=2020-01-01',
                  'start=2020-01-01&end=2020-04-01', 'start=2099-01-01&end=2099-01-02']:
        assert client.get('/admin/dashboard?' + query).status_code == 422
    result = client.get('/admin/dashboard?' + RANGE).json()
    assert result['summary']['calls'] == 0
    assert result['completion']['rate'] is None
    assert len(result['daily']) == 3


def test_budget_unconfigured_zero_and_tools_kept_separate(ledger, monkeypatch):
    monkeypatch.delenv('AI_PROVIDER_DAY_CALL_LIMIT', raising=False)
    with ledger() as db:
        db.add(KnowledgeBudgetCounter(scope_key='day:20200102', search_calls=3, fetch_calls=2, model_calls=7))
        db.commit()
    client = admin()
    assert client.get('/admin/model-budget').json()['day_call_budget']['limit'] is None
    result = client.get('/admin/dashboard?' + RANGE).json()
    assert result['summary']['calls'] == 0
    assert result['tool_reservations'][0]['search'] == 3
    assert result['tool_reservations'][0]['fetch'] == 2
    assert client.put('/admin/model-budget', json={'day_call_limit': 0}).json()['day_call_budget']['limit'] == 0


def test_actual_tools_are_classified_by_provider_and_drilldown_is_consistent(ledger):
    with ledger() as db:
        call(db, datetime(2020, 1, 2), provider='deepseek-tools', model='search', input_tokens=None, output_tokens=None, usage_status='UNKNOWN')
        call(db, datetime(2020, 1, 3), provider='deepseek-tools', model='fetch', status='FAILED')
        call(db, datetime(2020, 1, 3), provider='real-model-provider', model='search')
        db.commit()
    client = admin()
    result = client.get('/admin/dashboard?' + RANGE).json()
    assert result['summary']['calls'] == 3
    assert result['model_summary']['calls'] == 1
    assert result['tool_summary']['calls'] == 2
    assert result['distribution'] == [{'name': 'search', 'value': 1}]
    assert {r['name']: r['value'] for r in result['tool_distribution']} == {'search': 1, 'fetch': 1}
    query = RANGE + '&call_type=tools&model=search'
    assert client.get('/admin/usage?' + query).json()['total'] == 1
    assert len(client.get('/admin/usage/export?' + query).text.strip().splitlines()) == 2


def test_worker_full_registry_and_effective_denominator(ledger):
    now = datetime.utcnow()
    with ledger() as db:
        for index in range(102):
            db.add(WorkerInstance(id=str(uuid4()), kind='test', pid=index, capabilities=[],
                status='STOPPED' if index < 100 else 'RUNNING', started_at=now-timedelta(days=1),
                heartbeat_at=now-timedelta(seconds=100 if index == 100 else 0), heartbeat_interval=5))
        db.commit()
    result = admin().get('/admin/workers').json()
    assert result['registered'] == 102
    assert result['active_registered'] == 2
    assert result['online'] == 1
    assert result['distribution'] == {'ONLINE': 1, 'STALE': 1, 'STOPPED': 100}


def test_filters_pagination_export_and_csv_formula_guard(ledger):
    with ledger() as db:
        for index in range(23):
            call(db, datetime(2020, 1, 2), model='=unsafe', feature='assistant:exercise', request_id=f'q-{index}')
        call(db, datetime(2020, 1, 2), model='other')
        db.commit()
    client = admin()
    query = RANGE + '&model=%3Dunsafe&feature=assistant:exercise&status=SUCCEEDED'
    assert client.get('/admin/usage?' + query + '&page=2').json()['total'] == 23
    assert len(client.get('/admin/usage?' + query + '&page=2').json()['items']) == 3
    export = client.get('/admin/usage/export?' + query)
    assert export.status_code == 200
    assert len(export.text.strip().splitlines()) == 24
    assert "'=unsafe" in export.text
    assert client.get('/admin/usage?' + RANGE + '&search=q-1').json()['total'] == 11
    assert client.get('/admin/usage?' + RANGE + '&search=%25').json()['total'] == 0


def test_dashboard_admin_permission_boundaries(ledger):
    client = TestClient(app)
    paths = ['/admin/dashboard', '/admin/operations/tasks', '/admin/usage/export?' + RANGE]
    for path in paths:
        assert client.get(path).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role='teacher')
    for path in paths:
        assert client.get(path).status_code == 403


def test_query_count_does_not_scale_with_number_of_days(ledger):
    client = admin()
    with ledger() as db:
        engine = db.get_bind()
    counts = []
    def count(*_):
        counts.append(1)
    event.listen(engine, 'before_cursor_execute', count)
    try:
        assert client.get('/admin/dashboard?days=7').status_code == 200
        first = len(counts)
        counts.clear()
        assert client.get('/admin/dashboard?days=90').status_code == 200
        assert len(counts) == first
        assert first < 25
    finally:
        event.remove(engine, 'before_cursor_execute', count)
