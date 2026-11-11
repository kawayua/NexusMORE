"""D1 invariants: these fixture reviews exercise admission, not mathematical quality."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from modelcrew.collaboration import (Artifact, Binding, Call, Check, CollaborationStore,
    Evidence, Handoff, Issue, Receipt, Snapshot, Ticket, REQUIRED_CHECKS,
    collaboration_policy, require_tool, sha_file, workspace_path)
from modelcrew.collaboration_retrieval import algorithm_context
from modelcrew.contracts import digest


@pytest.fixture
def package(tmp_path):
    binding = Binding(task_id='d1-fixture', contract_version=1, contract_sha256=digest({'fixture':'contract'}))
    store = CollaborationStore(tmp_path / 'records', root=tmp_path)
    for call_id, context, role in [('author', 'author-context', 'modeling'),
                                   ('review', 'review-context', 'quality'),
                                   ('coder', 'coding-context', 'coding')]:
        store.register_call(Call(call_id=call_id, context_id=context, role=role, binding=binding))
    artifacts = []
    for kind in ['contract', 'mathematics', 'input', 'source']:
        path = tmp_path / (kind + '.txt'); path.write_text(json.dumps({'fixture':kind}), encoding='utf-8')
        artifacts.append(Artifact(artifact_id=kind, kind=kind, path=path.name,
                                  sha256=sha_file(path), author_call_ids=['author']))
    snapshot = Snapshot(binding=binding, hand='modeling', artifacts=artifacts, lineage_call_ids=['author'])
    key = store.freeze(snapshot)
    ticket_key = store.dispatch_review(key, 'M1', 'review')
    return store, snapshot, key, ticket_key


def receipt_for(store, ticket_key):
    ticket = store.load(Ticket, ticket_key)
    return Receipt(ticket_sha256=ticket_key, reviewer_call_id=ticket.reviewer_call_id,
                   status='PASS', checks=[Check(check_id=c, status='PASS', explanation='fixture assertion',
                    evidence=[Evidence(artifact_id='contract', selector='line 1')]) for c in ticket.required_checks])


def altered(model, **changes):
    return type(model).model_validate({**model.model_dump(mode='json'), **changes})


def test_immutable_records_and_restart_admit_same_receipt(package):
    store, snapshot, key, ticket_key = package
    receipt = receipt_for(store, ticket_key)
    accepted = store.accept_review(receipt, key)
    restarted = CollaborationStore(store.directory, root=store.root)
    assert restarted.load(Snapshot, key) == snapshot
    assert restarted.accept_review(receipt, key) == accepted
    assert restarted.load(Receipt, accepted).status == 'PASS'


def test_handoff_minimum_context_does_not_forward_source_or_math(package):
    store, snapshot, key, _ = package
    packet = store.handoff(key, 'coding', ['contract', 'input'])
    context = store.context(packet, 'coder')
    assert [a['artifact_id'] for a in context['artifacts']] == ['contract', 'input']
    assert context['requires_authoritative_user_approval'] is True
    assert 'code_execute' in context['tools'] and 'confirm_result' not in context['tools']
    with pytest.raises(ValueError, match='recipient'):
        store.context(packet, 'author')


@pytest.mark.parametrize('recipient,ids', [('writing', ['contract', 'input']), ('coding', ['contract']),
    ('coding', []), ('coding', ['contract', 'input', 'missing']), ('coding', ['contract', 'input', 'input'])])
def test_bad_handoff_routes_or_inputs(package, recipient, ids):
    store, _, key, _ = package
    with pytest.raises(ValueError): store.handoff(key, recipient, ids)


@pytest.mark.parametrize('role,tool', [('quality', 'code_execute'), ('quality', 'draft_markdown'),
    ('modeling', 'code_execute'), ('coding', 'propose_contract'), ('writing', 'code_execute'),
    ('writing', 'confirm_result'), ('modeling', 'confirm_model')])
def test_capability_denial(package, role, tool):
    store, snapshot, _, _ = package
    call = Call(call_id='test', context_id='test', role=role, binding=snapshot.binding)
    with pytest.raises(ValueError, match='forbidden'): require_tool(call, tool)


def test_context_reuse_under_new_call_id_is_not_independent(package):
    store, snapshot, key, _ = package
    store.register_call(Call(call_id='alias', context_id='author-context', role='quality', binding=snapshot.binding))
    with pytest.raises(ValueError, match='authorship'): store.dispatch_review(key, 'M1', 'alias')


def test_call_id_cannot_change_identity(package):
    store, snapshot, _, _ = package
    with pytest.raises(ValueError, match='already registered'):
        store.register_call(Call(call_id='author', context_id='new', role='quality', binding=snapshot.binding))


@pytest.mark.parametrize('field,value', [('task_id', 'another'), ('contract_version', 2),
    ('contract_sha256', 'b' * 64), ('execution_id', 'different-run')])
def test_wrong_reviewer_scope(package, field, value):
    store, snapshot, key, _ = package
    binding = altered(snapshot.binding, **{field: value})
    store.register_call(Call(call_id='wrong', context_id='fresh', role='quality', binding=binding))
    with pytest.raises(ValueError, match='binding'): store.dispatch_review(key, 'M1', 'wrong')


def test_reviewer_role_and_gate_cannot_be_impersonated(package):
    store, _, key, _ = package
    with pytest.raises(ValueError, match='role'): store.dispatch_review(key, 'M1', 'author')
    with pytest.raises(ValueError, match='another hand'): store.dispatch_review(key, 'P1', 'review')


def test_all_previous_editors_remain_in_lineage(package):
    store, snapshot, _, _ = package
    store.register_call(Call(call_id='previous-editor', context_id='review-context', role='modeling', binding=snapshot.binding))
    revised = altered(snapshot, lineage_call_ids=['author', 'previous-editor'])
    key = store.freeze(revised)
    with pytest.raises(ValueError, match='authorship'): store.dispatch_review(key, 'M1', 'review')


def test_artifact_change_invalidates_outstanding_review(package):
    store, snapshot, key, ticket_key = package
    (store.root / 'contract.txt').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='changed'): store.accept_review(receipt_for(store, ticket_key), key)


def test_revision_snapshot_rejects_old_ticket(package):
    store, snapshot, _, ticket_key = package
    path = store.root / 'source.txt'; path.write_text('new source', encoding='utf-8')
    data = snapshot.model_dump(mode='json'); data['artifacts'][-1]['sha256'] = sha_file(path)
    key = store.freeze(Snapshot.model_validate(data))
    with pytest.raises(ValueError, match='Stale'): store.accept_review(receipt_for(store, ticket_key), key)


@pytest.mark.parametrize('mutation', ['empty', 'missing', 'duplicate', 'unknown_evidence', 'no_evidence', 'wrong_reviewer', 'false_status'])
def test_invalid_review_cannot_pass(package, mutation):
    store, _, key, ticket_key = package
    data = receipt_for(store, ticket_key).model_dump(mode='json')
    if mutation == 'empty': data['checks'] = []
    elif mutation == 'missing': data['checks'].pop()
    elif mutation == 'duplicate': data['checks'].append(data['checks'][0])
    elif mutation == 'unknown_evidence': data['checks'][0]['evidence'][0]['artifact_id'] = 'unknown'
    elif mutation == 'no_evidence': data['checks'][0]['evidence'] = []
    elif mutation == 'wrong_reviewer': data['reviewer_call_id'] = 'author'
    elif mutation == 'false_status': data['checks'][0]['status'] = 'FAIL'
    with pytest.raises((ValueError, ValidationError)):
        store.accept_review(Receipt.model_validate(data), key)


@pytest.mark.parametrize('status,domain,target', [('FAIL', 'model', 'modeling'),
    ('FAIL', 'implementation', 'coding'), ('BLOCKED', 'infrastructure', 'recovery')])
def test_failure_records_route_without_advancing(package, status, domain, target):
    store, _, key, ticket_key = package
    data = receipt_for(store, ticket_key).model_dump(mode='json')
    data['status'] = status; data['checks'][0]['status'] = status
    data['issues'] = [Issue(check_id=data['checks'][0]['check_id'], severity='blocking', domain=domain,
                            target=target, reason='injected defect', recheck='repeat M1').model_dump(mode='json')]
    saved = store.accept_review(Receipt.model_validate(data), key)
    assert store.load(Receipt, saved).status == status
    assert len(list(store.directory.glob('Receipt/*.json'))) == 1


def test_failed_review_without_rework_entry_rejected(package):
    store, _, key, ticket_key = package
    data = receipt_for(store, ticket_key).model_dump(mode='json')
    data['status'] = 'BLOCKED'; data['checks'][0]['status'] = 'BLOCKED'
    with pytest.raises(ValueError, match='recheck'): store.accept_review(Receipt.model_validate(data), key)


@pytest.mark.parametrize('relative', ['../secret', '/secret', 'C:/secret', 'a\\b'])
def test_paths_cannot_escape_context(tmp_path, relative):
    with pytest.raises(ValueError): workspace_path(tmp_path, relative)


def test_corrupt_record_rejected_on_reload(package):
    store, _, key, _ = package
    path = store.directory / 'Snapshot' / (key + '.json')
    data = json.loads(path.read_text(encoding='utf-8')); data['hand'] = 'writing'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='hash'): store.load(Snapshot, key)


def test_source_only_snapshot_cannot_request_model_pass(package):
    store, snapshot, _, _ = package
    key = store.freeze(altered(snapshot, artifacts=[snapshot.artifacts[-1].model_dump(mode='json')]))
    with pytest.raises(ValueError, match='incomplete'): store.dispatch_review(key, 'M1', 'review')


def test_wrong_author_output_role_rejected(package):
    store, snapshot, _, _ = package
    data = snapshot.model_dump(mode='json'); data['artifacts'][0]['author_call_ids'] = ['coder']; data['lineage_call_ids'].append('coder')
    with pytest.raises(ValueError, match='responsibility'): store.freeze(Snapshot.model_validate(data))


def test_algorithm_context_preserves_conditions_locations_and_citations():
    result = algorithm_context('geometry', card_ids=['bracketed-root'],
        facts={'scalar_equation': True, 'continuous_on_bracket': True, 'opposite_endpoint_signs': True})
    card = result['cards'][0]
    assert result['status'] == 'ok' and result['index']['sha256'] == result['index']['read_sha256']
    assert card['applicability']['status'] == 'premises_satisfied'
    assert card['source_sections'][0]['line_start'] >= 1 and card['citation_id'].startswith('algorithm:')
    assert card['adoption'] == 'pending_modeling_hand_decision'
    assert any('不保证唯一' in s['text'] for s in card['source_sections'])


def test_uncovered_excluded_and_unknown_are_distinct():
    assert algorithm_context('prediction')['status'] == 'uncovered'
    assert algorithm_context('geometry', card_ids=['bracketed-root'], facts={'continuous_on_bracket': False})['status'] == 'no_applicable_cards'
    unknown = algorithm_context('geometry', card_ids=['bracketed-root'])
    assert unknown['cards'][0]['applicability']['status'] == 'needs_review'
    with pytest.raises(ValueError): algorithm_context('unknown')
    with pytest.raises(ValueError): algorithm_context('geometry', card_ids=['continuous-lp'])


def test_policy_matches_three_hands_and_read_only_quality():
    policy = collaboration_policy()
    assert set(policy['outputs']) == {'modeling', 'coding', 'writing'}
    assert policy['tools']['quality'] == ['read_snapshot', 'submit_review']

@pytest.mark.parametrize('gate', ['P1', 'P2', 'W1', 'W2'])
def test_each_downstream_gate_accepts_complete_versioned_package(tmp_path, gate):
    store = CollaborationStore(tmp_path / 'records', root=tmp_path)
    binding = Binding(task_id='q', contract_version=2, contract_sha256=digest({'fixture':'contract'}), execution_id='exec-1', result_revision=1)
    roles = {'modeling': 'm', 'coding': 'c', 'writing': 'w', 'quality': 'q'}
    for role, call_id in roles.items():
        store.register_call(Call(call_id=call_id, context_id=call_id, role=role, binding=binding))
    artifact_roles = {'contract': 'm', 'input': 'm', 'code': 'c', 'execution': 'c', 'result': 'c',
                      'figure': 'c', 'reproduction': 'c', 'outline': 'w', 'manuscript': 'w', 'render': 'w'}
    artifacts = []
    for kind, author in artifact_roles.items():
        path = tmp_path / (kind + '.txt'); path.write_text(json.dumps({'fixture':kind}), encoding='utf-8')
        artifacts.append(Artifact(artifact_id=kind, kind=kind, path=path.name, sha256=sha_file(path), author_call_ids=[author]))
    snapshot = Snapshot(binding=binding, hand='coding' if gate.startswith('P') else 'writing',
                        artifacts=artifacts, lineage_call_ids=['m', 'c', 'w'])
    key = store.freeze(snapshot)
    ticket = store.dispatch_review(key, gate, 'q')
    assert store.accept_review(receipt_for(store, ticket), key)
    if gate.startswith('P'):
        handoff = store.handoff(key, 'writing', ['contract', 'execution', 'result'])
        assert len(store.context(handoff, 'w')['artifacts']) == 3


def test_same_reviewer_can_recheck_but_cannot_edit(package):
    store, snapshot, key, ticket = package
    assert store.dispatch_review(key, 'M1', 'review') == ticket
    data = snapshot.model_dump(mode='json'); data['artifacts'][0]['author_call_ids'] = ['review']; data['lineage_call_ids'].append('review')
    with pytest.raises(ValueError, match='Read-only'): store.freeze(Snapshot.model_validate(data))


def test_author_identity_race_has_only_one_winner(package):
    from concurrent.futures import ThreadPoolExecutor
    store, snapshot, _, _ = package
    def register(index):
        try:
            store.register_call(Call(call_id='same-id', context_id='context-'+str(index), role='modeling', binding=snapshot.binding))
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(register, range(4))) == 1
    assert store.call('same-id').role == 'modeling'


def test_unresolved_error_and_wrong_rework_cannot_be_passed(package):
    store, _, key, ticket = package
    data = receipt_for(store, ticket).model_dump(mode='json')
    data['issues'] = [Issue(check_id='model', severity='error', domain='model', target='modeling',
                            reason='unresolved', recheck='M1').model_dump(mode='json')]
    with pytest.raises(ValueError, match='unresolved'): store.accept_review(Receipt.model_validate(data), key)
    data['status'] = 'FAIL'; data['checks'][0]['status'] = 'FAIL'; data['issues'][0]['target'] = 'coding'
    with pytest.raises(ValueError, match='target'): store.accept_review(Receipt.model_validate(data), key)


def test_record_keys_cannot_traverse(package):
    store, _, _, _ = package
    with pytest.raises(ValueError): store.load(Snapshot, '../anything')


def test_schema_strictness_and_no_empty_identities():
    with pytest.raises(ValidationError): Binding(task_id=' ', contract_version=1, contract_sha256='a'*64)
    with pytest.raises(ValidationError): Binding(task_id='q', contract_version=True, contract_sha256='a'*64)
    with pytest.raises(ValidationError): Binding(task_id='q', contract_version=1, contract_sha256='a'*64, result_revision=1)


def test_workflow_change_invalidates_pending_ticket(package, monkeypatch):
    import modelcrew.collaboration as module
    store, _, key, ticket = package
    policy = collaboration_policy(); policy['workflow_sha256'] = 'f'*64
    monkeypatch.setattr(module, 'collaboration_policy', lambda: policy)
    with pytest.raises(ValueError, match='ticket mismatch'):
        store.accept_review(receipt_for(store, ticket), key)


def test_all_published_schemas_match_runtime_contracts():
    from modelcrew.config import ROOT
    for model in [Artifact, Binding, Call, Handoff, Snapshot, Ticket, Receipt]:
        schema = json.loads((ROOT / 'contracts' / ('collaboration-'+model.__name__.lower()+'-1.0.0.schema.json')).read_text(encoding='utf-8'))
        assert schema == model.model_json_schema()


def test_card_profiles_are_versioned_and_include_operational_limits():
    for category in ['geometry', 'optimization', 'simulation']:
        context = algorithm_context(category)
        for card in context['cards']:
            profile = card['profile']
            assert profile['version'] == '1.0.0' and profile['base_card_sha256'] == card['card_sha256']
            assert profile['inputs_units'] and profile['steps'] and profile['stopping_conditions'] and profile['failure_states']
            assert profile['validation'] and profile['minimal_example']
            assert profile['verification'] == 'profile_reviewed_not_executed_in_D1'

@pytest.mark.parametrize('change', [{'task_id':'another'}, {'contract_version':2}, {'execution_id':'new-run'}, {'execution_id':'run','result_revision':2}])
def test_context_is_scoped_to_one_task_and_version(package, change):
    store, snapshot, _, _ = package
    binding = altered(snapshot.binding, **change)
    with pytest.raises(ValueError, match='Context already bound'):
        store.register_call(Call(call_id='another-call', context_id='author-context', role='modeling', binding=binding))


def test_contract_bytes_cannot_be_bound_to_another_contract(package):
    store, snapshot, _, _ = package
    binding = altered(snapshot.binding, contract_sha256='f'*64)
    for role in ['modeling']:
        store.register_call(Call(call_id='bad-hash-author', context_id='bad-hash-context', role=role, binding=binding))
    data = snapshot.model_dump(mode='json'); data['binding'] = binding.model_dump(mode='json')
    data['lineage_call_ids'] = ['bad-hash-author']
    for item in data['artifacts']: item['author_call_ids'] = ['bad-hash-author']
    with pytest.raises(ValueError, match='Contract content'): store.freeze(Snapshot.model_validate(data))

def test_historical_receipt_validation_is_read_only_and_does_not_relax_current_gate(package,monkeypatch):
    import modelcrew.collaboration as module
    store,snapshot,key,ticket_key=package
    receipt=receipt_for(store,ticket_key)
    accepted=store.accept_review(receipt,key)
    old_policy=store.load(Ticket,ticket_key).policy_sha256
    original=module.collaboration_policy()
    monkeypatch.setattr(module,'collaboration_policy',lambda:{**original,'workflow_sha256':'f'*64})
    before={p.relative_to(store.directory).as_posix():p.read_bytes() for p in store.directory.rglob('*.json')}
    with pytest.raises(ValueError,match='ticket mismatch'):store.accept_review(receipt,key)
    with module.historical_review_context(old_policy):
        assert store.accept_review(receipt,key)==accepted
        wrong=receipt.model_copy(update={'reviewer_call_id':'author'})
        with pytest.raises(ValueError,match='Wrong reviewer'):store.accept_review(wrong,key)
    after={p.relative_to(store.directory).as_posix():p.read_bytes() for p in store.directory.rglob('*.json')}
    assert before==after
    with pytest.raises(ValueError,match='ticket mismatch'):store.accept_review(receipt,key)
