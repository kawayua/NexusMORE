"""G3 trust boundary probes. All terminal input is explicitly TEST_SIMULATED_USER.

No real user approval, provider call, independent M1/P2/W1/W2 or paper export.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from psycopg.types.json import Jsonb
import pytest

from modelcrew.business_adapter import BusinessAdapter
from modelcrew.business_contract import BusinessContractError, request_digest, validate_response
from modelcrew.business_store import BusinessStore
from modelcrew.contracts import digest
from modelcrew.trusted_decisions import TrustedDecisions, local_principal, statement_hash
from modelcrew.workflow import Workflow
from modelcrew.workflow_mcp import definitions
from test_business_mcp import request, task


@pytest.fixture(scope='module')
def url():
    value = os.environ.get('MODELCREW_USER_EVENTS_TEST_URL')
    if not value: pytest.skip('Run the explicit isolated trusted-user-decisions probe')
    with Workflow(value) as w: w.setup()
    return value


@pytest.fixture
def adapter(url):
    return BusinessAdapter(lambda: Workflow(url))


@pytest.fixture
def service(url, monkeypatch):
    # Not actual terminal evidence. Label every synthetic DB capture accordingly.
    monkeypatch.setattr('modelcrew.trusted_decisions.local_principal', lambda: {'kind': 'test_simulated_terminal', 'subject_sha256': 'a' * 64})
    return TrustedDecisions(lambda: Workflow(url))


class Terminal(io.StringIO):
    def isatty(self): return True


def capture(service, scope, monkeypatch, *, decision='reject', kind='model', during=None, cancel=False, statement='TEST_SIMULATED_USER: this is not a real user approval'):
    pending = next(p for p in service.pending(scope) if p['kind'] == kind)
    def user_input(prompt):
        if prompt.startswith('请输入完整 pending_id'): return pending['pending_id']
        if prompt.startswith('决定'): return decision
        if prompt.startswith('请输入本次审阅理由'): return 'TEST_SIMULATED_USER: isolated boundary probe only'
        if prompt.startswith('请输入本次真实用户决定'): return statement
        if prompt.startswith('请原样输入'):
            if during: during()
            return '' if cancel else prompt.split('：', 1)[1].strip()
        raise AssertionError('Unexpected terminal prompt')
    output = Terminal()
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'stdin', Terminal()); patch.setattr(sys, 'stdout', output)
        patch.setattr('builtins.input', user_input)
        command = service.capture_interactive(scope)
    assert 'TEST_SIMULATED_USER' in output.getvalue()
    return command


def counts(url, task_id):
    with Workflow(url) as w:
        return {'core': w.db.execute("SELECT count(*) AS n FROM mc_events WHERE task_id=%s AND kind IN ('model_approve','model_reject','result_approve','result_reject')", (task_id,)).fetchone()['n'],
                'claims': w.db.execute('SELECT count(*) AS n FROM mc_trusted_user_event_claims c JOIN mc_business_operations o USING(scope_sha256,operation,request_id) WHERE o.scope->>\'task_id\'=%s', (task_id,)).fetchone()['n']}


def test_local_identity_uses_os_token_not_actor_or_environment(monkeypatch):
    before = local_principal()
    monkeypatch.setenv('USERNAME', 'forged_actor'); monkeypatch.setenv('USER', 'forged_actor')
    assert local_principal() == before
    assert before['kind'] in ('windows_process_token', 'posix_effective_uid')
    assert len(before['subject_sha256']) == 64
    assert 'forged_actor' not in json.dumps(before)


def test_no_capture_or_approval_tool_is_model_discoverable():
    names = {t.name for t in definitions()}
    assert len(names) == 40
    assert not names & {'task_decide', 'hand_decide', 'assembly_decide', 'capture_user_event', 'trusted_user_event'}


def test_piped_terminal_cannot_mint_event(service, monkeypatch):
    monkeypatch.setattr(sys, 'stdin', io.StringIO('approve\n'))
    with pytest.raises(BusinessContractError, match='interactive') as exc:
        service.capture_interactive({'project_id': 'unused'})
    assert exc.value.code == 'untrusted_user_event'


def test_real_cli_rejects_pipe_without_database_or_secret(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith('MODELCREW_')}
    env['PYTHONIOENCODING'] = 'utf-8'
    probe = subprocess.run([sys.executable, '-m', 'modelcrew.trusted_decisions', 'review', '--project', 'not-connected'],
                           input='approve\n', capture_output=True, text=True, encoding='utf-8', env=env)
    assert probe.returncode == 1
    assert json.loads(probe.stdout)['code'] == 'untrusted_user_event'
    assert 'Traceback' not in probe.stderr


def test_independent_capture_and_exact_replay(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    command = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    with Workflow(url) as w:
        event = w.db.execute('SELECT * FROM mc_trusted_user_events WHERE event_id=%s', (command['user_event']['event_id'],)).fetchone()
        assert event['statement'].startswith('TEST_SIMULATED_USER')
        assert event['principal']['kind'] == 'test_simulated_terminal'
        assert event['request_sha256'] == request_digest(command)
        assert event['review_sha256'] == digest(event['review'])
    response = validate_response(service.submit(command))
    assert response['receipt']['state'] == 'succeeded', response
    assert service.submit(command)['replayed'] is True
    assert counts(url, t) == {'core': 1, 'claims': 1}
    with Workflow(url) as w: assert not w.task(t)['model_approved']


@pytest.mark.parametrize('change', ['actor', 'decision', 'reason', 'key', 'statement', 'channel', 'event_id', 'target'])
def test_reference_and_decision_tampering_cannot_grant_authority(service, adapter, url, tmp_path, monkeypatch, change):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    original = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    cmd = copy.deepcopy(original)
    if change == 'actor': cmd['arguments']['body']['actor'] = 'model'
    elif change == 'decision': cmd['arguments']['body']['decision'] = 'approve'
    elif change == 'reason': cmd['arguments']['body']['reason'] = 'altered'
    elif change == 'key': cmd['request_id'] = cmd['arguments']['body']['request_id'] = 'another-key'
    elif change == 'statement': cmd['user_event']['statement_sha256'] = 'b' * 64
    elif change == 'channel': cmd['user_event']['channel'] = 'trusted_host_ui'
    elif change == 'event_id': cmd['user_event']['event_id'] = 'invented-event'
    else:
        _, other, _, _, state = task(adapter, url, tmp_path)
        cmd['arguments']['task_id'] = other; cmd['expected_binding'] = state['binding']
    response = service.submit(cmd)
    assert response['error']['code'] == 'untrusted_user_event', response
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_model_adapter_rejects_even_genuine_local_capture(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    assert adapter.invoke('task_decide', cmd)['error']['code'] == 'unsupported_operation'
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_cancel_does_not_register_event(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    with pytest.raises(BusinessContractError) as exc:
        capture(service, {'project_id': p, 'task_id': t}, monkeypatch, cancel=True)
    assert exc.value.code == 'user_input_required'
    with Workflow(url) as w:
        assert not w.db.execute("SELECT 1 FROM mc_trusted_user_events WHERE request->'arguments'->>'task_id'=%s", (t,)).fetchone()


def revise(adapter, t, created, state):
    content = copy.deepcopy(created['arguments']['body']['contract']); content['risks'].append('G3 version change')
    return adapter.invoke('task_revise', request('task_revise', {'task_id': t, 'body': {'kind': 'revise_model', 'version': 1,
        'actor': 'model', 'request_id': 'revise-g3', 'reason': 'synthetic changed contract', 'contract': content}}, key='revise-g3', bound=state['binding']))


def test_change_while_user_is_reading_never_captures_stale_decision(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, created, state = task(adapter, url, tmp_path)
    with pytest.raises(BusinessContractError) as exc:
        capture(service, {'project_id': p, 'task_id': t}, monkeypatch, during=lambda: revise(adapter, t, created, state))
    assert exc.value.code == 'stale_binding'
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_revision_after_capture_invalidates_event_without_spending_it(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, created, state = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    assert revise(adapter, t, created, state)['binding']['version'] == 2
    assert service.submit(cmd)['error']['code'] == 'stale_binding'
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_review_snapshot_change_without_contract_revision_is_stale(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    with Workflow(url) as w:
        w.record_entry(t, version=1, kind='proposal', text='Additional review context', actor='model', request_id='new-context')
    assert service.submit(cmd)['error']['code'] == 'stale_binding'
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_event_expiry_and_immutability(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    # Synthetic expired capture, explicitly inserted by fixture DB owner.
    old_id = cmd['user_event']['event_id']; cmd['user_event']['event_id'] = 'expired-' + uuid.uuid4().hex
    with Workflow(url) as w:
        w.db.execute("INSERT INTO mc_trusted_user_events SELECT %s,channel,principal,pending_id,review_sha256,review,statement,statement_sha256,%s,%s,clock_timestamp()-interval '2 hours',clock_timestamp()-interval '1 hour' FROM mc_trusted_user_events WHERE event_id=%s", (cmd['user_event']['event_id'], request_digest(cmd), Jsonb(cmd), old_id))
        for sql in ('UPDATE mc_trusted_user_events SET statement=\'forged\' WHERE event_id=%s', 'DELETE FROM mc_trusted_user_events WHERE event_id=%s'):
            with pytest.raises(Exception): w.db.execute(sql, (old_id,))
    assert service.submit(cmd)['error']['code'] == 'untrusted_user_event'
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_different_os_principal_is_rejected(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    monkeypatch.setattr('modelcrew.trusted_decisions.local_principal', lambda: {'kind': 'test_simulated_terminal', 'subject_sha256': 'b' * 64})
    assert service.submit(cmd)['error']['code'] == 'untrusted_user_event'
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_concurrent_exact_retry_consumes_one_event_once(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: service.submit(cmd), range(2)))
    assert all(r['receipt']['state'] == 'succeeded' for r in responses), responses
    assert sum(bool(r['replayed']) for r in responses) == 1
    assert counts(url, t) == {'core': 1, 'claims': 1}
    with Workflow(url) as w:
        with pytest.raises(Exception): w.db.execute('DELETE FROM mc_trusted_user_event_claims WHERE event_id=%s', (cmd['user_event']['event_id'],))


def test_two_captures_of_same_snapshot_do_not_both_dispatch(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    first = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    second = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    assert service.submit(first)['receipt']['state'] == 'succeeded'
    assert service.submit(second)['error']['code'] == 'stale_binding'
    assert counts(url, t) == {'core': 1, 'claims': 1}


@pytest.mark.parametrize('stage', ['before_core', 'after_core', 'after_save'])
def test_process_kill_never_reissues_decision(service, adapter, url, tmp_path, monkeypatch, stage):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    path = tmp_path / 'synthetic-command.json'; path.write_text(json.dumps(cmd), encoding='utf-8')
    child = '''import json,os,sys
import modelcrew.trusted_decisions as trusted
from modelcrew.workflow import Workflow
trusted.local_principal=lambda:{'kind':'test_simulated_terminal','subject_sha256':'a'*64}
def fault(stage,row):
    if stage==sys.argv[2]:os._exit(37)
service=trusted.TrustedDecisions(lambda:Workflow(os.environ['MODELCREW_USER_EVENTS_TEST_URL']),fault=fault)
service.submit(json.load(open(sys.argv[1],encoding='utf-8')))
'''
    probe = subprocess.run([sys.executable, '-c', child, str(path), stage], capture_output=True, text=True)
    assert probe.returncode == 37, probe.stderr
    query = request('operation_status', {'project_id': p, 'task_id': t, 'operation_name': 'task_decide', 'request_id': cmd['request_id']})
    response = adapter.invoke('operation_status', query)
    assert response['status'] == 'ok', response
    retry = service.submit(cmd)
    if stage == 'before_core':
        assert response['receipt']['state'] == 'dispatched'
        assert retry['status'] == 'outcome_unknown'
        assert counts(url, t) == {'core': 0, 'claims': 1}
        other = request('task_resume', {'task_id': t}, key='must-not-replace', bound=cmd['expected_binding'])
        assert adapter.invoke('task_resume', other)['status'] == 'outcome_unknown'
    else:
        assert response['receipt']['state'] == retry['receipt']['state'] == 'succeeded'
        assert retry['replayed'] is True
        assert counts(url, t) == {'core': 1, 'claims': 1}


def test_model_approval_still_requires_independent_m1(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch, decision='approve')
    response = service.submit(cmd)
    assert response['error']['code'] == 'workflow_conflict', response
    assert counts(url, t) == {'core': 0, 'claims': 0}


def test_simulated_m1_model_approval_defers_all_execution(service, adapter, url, tmp_path, monkeypatch):
    # Test-double M1 only: this does not create a genuine independent receipt.
    monkeypatch.setattr('modelcrew.modeling_hand.assert_m1', lambda *a, **k: {'TEST_SIMULATED_M1': True})
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch, decision='approve')
    assert cmd['arguments']['body']['defer_execution'] is True
    response = service.submit(cmd)
    assert response['receipt']['state'] == 'succeeded', response
    with Workflow(url) as w:
        assert w.task(t)['model_approved'] and not w.task(t)['execution_id']
        assert not w.db.execute('SELECT 1 FROM mc_executions WHERE task_id=%s', (t,)).fetchone()
    assert counts(url, t) == {'core': 1, 'claims': 1}


def test_final_decision_is_not_invented_to_fill_contract_gap(service):
    with pytest.raises(BusinessContractError) as exc: service.submit({'operation': 'final_decide'})
    assert exc.value.code == 'unsupported_operation'

@pytest.mark.parametrize('path,body', [
    ('/tasks/task/actions', {'actor': 'user', 'request_id': 'forged', 'version': 1, 'kind': 'model', 'decision': 'approve'}),
    ('/tasks/task/actions/', {'actor': 'user', 'request_id': 'forged', 'version': 1, 'kind': 'result', 'decision': 'reject', 'result_revision': 1}),
    ('/tasks/task/hand-runs/run/decisions', {}),
    ('/projects/project/assembly-builds/build/decisions', {}),
])
def test_http_decisions_rejected_before_database_or_actor_validation(path, body):
    from fastapi.testclient import TestClient
    from modelcrew.api import create_app
    def forbidden(): pytest.fail('An unauthenticated HTTP decision must not open Workflow')
    with TestClient(create_app(forbidden)) as client:
        response = client.post(path, json=body)
        assert response.status_code == 403, response.text
        assert response.json()['error']['code'] == 'untrusted_user_event'


def test_legacy_cli_actor_arguments_cannot_approve():
    probe = subprocess.run([sys.executable, '-m', 'modelcrew', 'act', 'not-connected', '--kind', 'model',
                            '--version', '1', '--actor', 'user', '--request-id', 'forged', '--decision', 'approve'],
                           capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=60)
    assert probe.returncode == 2
    assert 'trusted_decisions review' in probe.stderr
    assert 'Traceback' not in probe.stderr


@pytest.mark.parametrize('assembly', [False, True])
def test_manuscript_and_figures_need_separate_captured_events(service, adapter, url, tmp_path, monkeypatch, assembly):
    """Real DB/event/hash boundary; native hand/build status and decisions are doubles.

    Existing writing_reviews/assembly tests cover native acceptance requirements;
    this fixture does not create real W1, render checks, or manuscript approval.
    """
    from modelcrew.config import ROOT
    p, t, _, _, _ = task(adapter, url, tmp_path)
    run = str(uuid.uuid4()); build = str(uuid.uuid4()); source = tmp_path/'source'; source.mkdir()
    md = source/'manuscript.md'; cat = source/'figure-catalog.json'
    md.write_text('TEST_SIMULATED_MANUSCRIPT: trust boundary only', encoding='utf-8')
    cat.write_text('{"TEST_SIMULATED_FIGURES":true}', encoding='utf-8')
    rel = lambda path: path.relative_to(ROOT).as_posix()
    sha = lambda path: __import__('hashlib').sha256(path.read_bytes()).hexdigest()
    sealed = {rel(md): sha(md), rel(cat): sha(cat)}
    payload = {'manuscript': rel(md), 'sealed': sealed, 'decisions': {}}
    table = 'mc_assembly_builds' if assembly else 'mc_hand_runs'; identifier = build if assembly else run
    with Workflow(url) as w:
        if assembly:
            w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',
                         (run, p, 'synthetic-inputs', 'a'*64, Jsonb({'chapters': [{'task_id': t}]})))
            w.db.execute("INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,'WAITING_ASSEMBLY_REVIEW',%s)",
                         (build, run, p, 'synthetic-build', 'a'*64, Jsonb(payload)))
        else:
            w.db.execute("INSERT INTO mc_hand_runs(id,task_id,version,hand,request_id,request_sha256,phase,payload) VALUES(%s,%s,1,'writing',%s,%s,'WAITING_MANUSCRIPT_AND_FIGURES',%s)",
                         (run, t, 'synthetic-writing', 'a'*64, Jsonb(payload)))
    def status(self, parent, identifier):
        data = self.db.execute(f'SELECT payload FROM {table} WHERE id::text=%s', (identifier,)).fetchone()['payload']
        if assembly:
            return {'phase': 'WAITING_ASSEMBLY_REVIEW', 'source': rel(source), 'manuscript': rel(md), 'issues': [], 'TEST_SIMULATED': True}
        return {'hand': 'writing', 'phase': 'WAITING_MANUSCRIPT_AND_FIGURES', 'manuscript_sha256': sha(md), 'figure_catalog_sha256': sha(cat), 'TEST_SIMULATED': True}
    def decision(self, parent, identifier, **body):
        data = self.db.execute(f'SELECT payload FROM {table} WHERE id::text=%s', (identifier,)).fetchone()['payload']
        data['decisions'][body['request_id']] = {'request_sha256': digest(body)} if assembly else digest({k: v for k, v in body.items() if k != 'request_id'})
        data['manuscript_review' if body['kind']=='manuscript' else 'figure_review'] = {'TEST_SIMULATED_USER': True, 'decision': body['decision']}
        self.db.execute(f'UPDATE {table} SET payload=%s WHERE id::text=%s', (Jsonb(data), identifier))
        return status(self, parent, identifier)
    monkeypatch.setattr(Workflow, 'assembly_build_status' if assembly else 'hand_status', status)
    monkeypatch.setattr(Workflow, 'assembly_build_decision' if assembly else 'hand_decision', decision)
    scope = {'project_id': p, **({'build_id': build} if assembly else {'task_id': t, 'run_id': run})}
    first = capture(service, scope, monkeypatch, kind='manuscript', decision='approve')
    original = md.read_bytes()
    md.write_bytes(original + b' CHANGED AFTER CAPTURE')
    assert service.submit(first)['error']['code'] == 'artifact_changed'
    with Workflow(url) as w:
        assert not w.db.execute('SELECT 1 FROM mc_trusted_user_event_claims WHERE event_id=%s', (first['user_event']['event_id'],)).fetchone()
    md.write_bytes(original)
    assert service.submit(first)['receipt']['state'] == 'succeeded'
    assert [p['kind'] for p in service.pending(scope)] == ['figures']
    second = capture(service, scope, monkeypatch, kind='figures', decision='reject')
    assert first['user_event']['event_id'] != second['user_event']['event_id']
    assert first['expected_binding']['artifact_sha256'] != second['expected_binding']['artifact_sha256']
    assert service.submit(second)['receipt']['state'] == 'succeeded'
    assert service.pending(scope) == []
    with Workflow(url) as w:
        assert w.db.execute('SELECT count(*) AS n FROM mc_trusted_user_event_claims WHERE event_id=ANY(%s)',
                            ([first['user_event']['event_id'], second['user_event']['event_id']],)).fetchone()['n'] == 2

@pytest.mark.parametrize('changed', [False, True])
def test_result_decision_binds_execution_and_revision(service, adapter, url, tmp_path, monkeypatch, changed):
    p, t, _, _, initial = task(adapter, url, tmp_path)
    execution = str(uuid.uuid4())
    with Workflow(url) as w:
        w.db.execute("INSERT INTO mc_executions(id,task_id,version,contract_sha256,mode,artifacts) VALUES(%s,%s,1,%s,'fixture','[]')", (execution, t, initial['binding']['contract_sha256']))
        w.db.execute("INSERT INTO mc_results(task_id,version,revision,execution_id,interpretation,review) VALUES(%s,1,1,%s,'TEST_SIMULATED_RESULT',%s)", (t, execution, Jsonb({'status': 'passed', 'mode': 'fixture', 'TEST_SIMULATED_P2': True})))
        w.db.execute("UPDATE mc_tasks SET model_approved=true,execution_id=%s,result_revision=1,phase='WAITING_RESULT_APPROVAL' WHERE id=%s", (execution, t))
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch, kind='result')
    assert cmd['expected_binding']['execution_id'] == execution
    assert cmd['expected_binding']['result_revision'] == cmd['arguments']['body']['result_revision'] == 1
    # The DB fixture has no actual graph execution lineage; test only the native
    # rejection transaction, not graph recovery/solver/quality-gate acceptance.
    monkeypatch.setattr(Workflow, '_resume_locked', lambda self, task: None)
    if changed:
        with Workflow(url) as w: w.db.execute('UPDATE mc_tasks SET result_revision=2 WHERE id=%s', (t,))
        assert service.submit(cmd)['error']['code'] == 'stale_binding'
        assert counts(url, t) == {'core': 0, 'claims': 0}
    else:
        response = service.submit(cmd)
        assert response['receipt']['state'] == 'succeeded', response
        assert response['data']['user_decision']['confirmed_binding']['execution_id'] == execution
        assert counts(url, t) == {'core': 1, 'claims': 1}
        with Workflow(url) as w: assert not w.task(t)['result_approved']


def test_other_native_event_with_same_key_does_not_prove_this_decision(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch)
    def interruption(stage, row):
        if stage == 'before_core': raise SystemExit(37)
    service.fault = interruption
    with pytest.raises(SystemExit): service.submit(cmd)
    with Workflow(url) as w:
        w.action(t, **{**cmd['arguments']['body'], 'reason': 'TEST_SIMULATED unrelated payload with same native key'})
    query = request('operation_status', {'project_id': p, 'task_id': t, 'operation_name': 'task_decide', 'request_id': cmd['request_id']})
    response = adapter.invoke('operation_status', query)
    assert response['receipt']['state'] == 'dispatched', response
    assert service.submit(cmd)['status'] == 'outcome_unknown'


def test_statement_bytes_are_preserved_without_unicode_or_whitespace_normalization(service, adapter, url, tmp_path, monkeypatch):
    p, t, _, _, _ = task(adapter, url, tmp_path)
    statement = 'TEST_SIMULATED_USER: 原始表达 e\u0301 ≠ é，保留尾部空格  '
    cmd = capture(service, {'project_id': p, 'task_id': t}, monkeypatch, statement=statement)
    with Workflow(url) as w:
        row = w.db.execute('SELECT statement,statement_sha256 FROM mc_trusted_user_events WHERE event_id=%s', (cmd['user_event']['event_id'],)).fetchone()
        assert row['statement'] == statement
        assert row['statement_sha256'] == statement_hash(statement)
        assert row['statement_sha256'] != statement_hash(statement.strip())
    assert service.submit(cmd)['receipt']['state'] == 'succeeded'
