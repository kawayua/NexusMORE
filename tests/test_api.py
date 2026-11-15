"""HTTP boundary checks without database or model calls."""
import pytest
from fastapi.testclient import TestClient
from modelcrew.api import create_app


def test_health_and_openapi_do_not_connect():
    def unavailable():
        raise AssertionError('Must not connect')
    with TestClient(create_app(unavailable)) as client:
        assert client.get('/health').json()['scope'] == 'http_process'
        schema = client.get('/openapi.json').json()
        assert '/tasks/{task_id}/actions' in schema['paths']


@pytest.mark.parametrize('body', [
    {'kind': 'result', 'decision': 'approve'},
    {'kind': 'revise_model', 'reason': 'change'},
    {'kind': 'restore_version', 'reason': 'restore'},
    {'kind': 'model', 'decision': 'approve', 'crash_after_commit': True},
    {'kind': 'model', 'decision': 'approve', 'version': True},
])
def test_invalid_action_never_reaches_workflow(body):
    class Guard:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def action(self, *args, **kwargs): raise AssertionError('Invalid action reached workflow')
    with TestClient(create_app(Guard)) as client:
        response = client.post('/tasks/test/actions', json={
            'actor': 'TEST_SIMULATED_USER', 'request_id': 'test', 'version': 1, **body})
        assert response.status_code == 422


def test_backend_failure_hides_connection_details():
    def unavailable():
        raise RuntimeError('postgresql://secret-user:secret-password@localhost/test')
    with TestClient(create_app(unavailable)) as client:
        response = client.get('/tasks/test')
        assert response.status_code == 503
        assert 'secret' not in response.text
