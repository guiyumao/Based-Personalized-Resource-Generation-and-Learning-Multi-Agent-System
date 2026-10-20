"""Administrator inventory and secret write boundaries, using isolated fixtures."""
import pytest
from fastapi.testclient import TestClient
from services.resource_service.app.main import app as resource_app
from services.system_service.app.main import app as system_app


@pytest.mark.parametrize('identity,expected', [('anonymous', 401), ('auth_headers', 403), ('teacher_headers', 403), ('admin_headers', 200)])
def test_managed_inventory_roles(identity, expected, request):
    headers = {} if identity == 'anonymous' else request.getfixturevalue(identity)
    assert TestClient(resource_app).get('/resources/managed', headers=headers).status_code == expected


def test_admin_inventory_contains_private_draft(db_session, test_user, admin_headers):
    from common.models.learning import Resource
    item = Resource(title='admin-inventory-private-test', type='article', content='draft', generated_for_user_id=test_user.id, publish_status='draft')
    db_session.add(item)
    db_session.commit()
    try:
        client = TestClient(resource_app)
        assert item.id in [row['id'] for row in client.get('/resources/managed', headers=admin_headers).json()['data']]
        assert item.id not in [row['id'] for row in client.get('/resources').json()['data']]
        assert client.get(f'/resources/{item.id}').status_code == 404
        assert client.get(f'/resources/{item.id}', headers=admin_headers).status_code == 200
    finally:
        db_session.delete(item)
        db_session.commit()


def test_sensitive_config_write_is_rejected_without_echo(monkeypatch, admin_headers):
    from services.system_service.app.services.system_persistence import SystemManager
    def forbidden(*args, **kwargs):
        raise AssertionError('Secret write must never reach persistence')
    monkeypatch.setattr(SystemManager, 'update_config', forbidden)
    response = TestClient(system_app).put('/system/configs/deepseek_api_key', json={'value': 'sentinel-secret'}, headers=admin_headers)
    assert response.status_code == 422
    assert 'sentinel-secret' not in response.text
