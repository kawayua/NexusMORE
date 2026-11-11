"""Real PostgreSQL + HTTP workflow using new fixed evidence and simulated actors."""
import copy
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from modelcrew.api import create_app
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.inputs import file_hash


def test_http_workflow_preserves_gates_and_versions():
    key = uuid.uuid4().hex
    project = 'test-api-' + key
    task = 'test-api-task-' + key
    contract = json.loads((ROOT/'contracts/examples/valid-2024-a-q1.json').read_text(encoding='utf-8-sig'))
    folder = ROOT/'stage-c/runs'/key
    folder.mkdir(parents=True)
    artifact = folder/'fixed.json'
    artifact.write_text('{"TEST_ONLY":true}', encoding='utf-8')
    manifest = folder/'manifest.json'
    manifest.write_text(json.dumps({'contract_sha256': digest(contract), 'description': 'TEST_ONLY new fixed evidence', 'artifacts': [
        {'path': str(artifact), 'sha256': file_hash(artifact), 'role': 'fixed_fixture'}]}), encoding='utf-8')
    config = {'manifest_path': str(manifest), 'manifest_sha256': file_hash(manifest)}
    prefix = '/tasks/' + task
    with TestClient(create_app()) as client:
        p = {'id': project, 'title': 'TEST_ONLY HTTP integration'}
        assert client.post('/projects', json=p).status_code == 200
        assert client.post('/projects', json=p).json() == p
        assert client.post('/projects', json={**p, 'title': 'different'}).status_code == 409
        assert client.get('/projects?limit=200').status_code == 200
        assert client.get('/projects?limit=201').status_code == 422
        body = {'id': task, 'contract': contract, 'executor_key': 'manifest-fixture', 'executor_config': config}
        assert client.post('/projects/missing-project/tasks', json=body).status_code == 404
        response = client.post(f'/projects/{project}/tasks', json=body)
        assert response.status_code == 201, response.text
        state = response.json()
        assert state['task']['phase'] == 'WAITING_MODEL_APPROVAL'
        assert state['execution'] is None
        assert client.post(f'/projects/{project}/tasks', json=body).status_code == 409
        assert len(client.get(f'/projects/{project}/tasks').json()) == 1
        assert client.post(prefix+'/resume').json()['execution'] is None
        assert client.get(prefix+'/proposal').json()['model_approved'] is False
        assert client.get(prefix+'/result').json()['result'] is None
        action = {'actor': 'TEST_SIMULATED_USER', 'request_id': 'model-1', 'version': 1,
                  'kind': 'model', 'decision': 'approve'}
        first = client.post(prefix+'/actions', json=action)
        assert first.status_code == 200, first.text
        execution_id = first.json()['execution']['id']
        assert first.json()['task']['phase'] == 'WAITING_RESULT_APPROVAL'
        repeated = client.post(prefix+'/actions', json=action)
        assert repeated.status_code == 200 and repeated.json()['execution']['id'] == execution_id
        assert client.post(prefix+'/actions', json={**action, 'decision': 'reject', 'reason': 'TEST_ONLY reject'}).status_code == 409
        stale = {**action, 'kind': 'result', 'request_id': 'stale-result', 'result_revision': 2}
        assert client.post(prefix+'/actions', json=stale).status_code == 409
        approved = client.post(prefix+'/actions', json={**stale, 'request_id': 'result-1', 'result_revision': 1})
        assert approved.status_code == 200 and approved.json()['task']['phase'] == 'COMPLETED'
        artifacts = client.get(prefix+'/artifacts?version=1').json()
        assert len(artifacts['executions']) == 1
        assert artifacts['executions'][0]['artifacts'][0]['integrity'] == 'verified'
        changed = copy.deepcopy(contract)
        changed['risks'].append('TEST_ONLY API revision')
        revised = client.post(prefix+'/actions', json={
            'actor': 'TEST_SIMULATED_USER', 'request_id': 'revise', 'version': 1,
            'kind': 'revise_model', 'reason': 'TEST_ONLY change model', 'contract': changed})
        assert revised.status_code == 200, revised.text
        assert revised.json()['task']['current_version'] == 2
        assert not revised.json()['task']['model_approved'] and revised.json()['execution'] is None
        assert client.post(prefix+'/actions', json={**action, 'request_id': 'stale-model'}).status_code == 409
        assert len(client.get(prefix+'/versions').json()) == 2
        assert client.get(prefix+'/versions/1').json()['is_current'] is False
        assert client.get('/tasks/unknown-api-task').status_code == 404

