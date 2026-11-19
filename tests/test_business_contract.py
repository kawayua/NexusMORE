"""G1 wire contract tests use no database, model request or business decision."""
import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from modelcrew.business_contract import (
    BusinessContractError, audit_contract, load_contract, pending_id, request_digest,
    request_schema, response_schema, validate_request, validate_response,
)

ROOT = Path(__file__).resolve().parents[1]
H = 'a' * 64
BINDING = {'project_id': 'demo', 'task_id': 'q1', 'version': 1,
           'contract_sha256': H, 'run_id': 'run-1', 'build_id': 'build-1',
           'execution_id': 'execution-1', 'result_revision': 1,
           'artifact_sha256': H, 'source_sha256': H}


def command(operation='hand_advance', **args):
    value = {'contract_version': '1.0.0', 'operation': operation,
             'arguments': args or {'task_id': 'q1', 'run_id': 'run-1'},
             'request_id': 'request-1', 'expected_binding': copy.deepcopy(BINDING)}
    return value


def result(status='ok', operation='hand_advance'):
    return {'contract_version': '1.0.0', 'operation': operation,
            'request_id': 'request-1', 'status': status, 'binding': {},
            'phase': None, 'replayed': False, 'pending': [], 'artifacts': [],
            'data': None, 'chunk': None, 'error': None, 'receipt': ({'operation_name': operation, 'request_id': 'request-1', 'request_sha256': H, 'scope': {}, 'state': 'succeeded', 'result_sha256': H} if operation == 'hand_advance' and status == 'ok' else None)}


def test_catalog_covers_complete_business_families_and_reports_gaps():
    audit = audit_contract()
    assert audit['operations'] == 50
    assert audit['core_status'] == {'mapped': 39, 'partial': 5, 'missing': 6}
    operations = {op['name']: op for op in load_contract()['operations']}
    assert {'question_import', 'task_decide', 'task_revise', 'task_restore',
            'pending_list', 'operation_status', 'artifact_read', 'figures_select',
            'manuscript_register_revision', 'final_decide', 'assembly_export'} <= operations.keys()
    assert all(op['adapter_status'] == 'not_implemented' for op in operations.values())
    assert all(op['core']['service'] is None and op['core']['http'] is None
               for op in operations.values() if op['core']['status'] == 'missing')
    assert operations['task_create']['idempotency'] == 'adapter_ledger_required'
    assert operations['project_create']['idempotency'] == 'natural_key_project_id_title'
    assert operations['hand_advance']['idempotency'] == 'adapter_ledger_required'
    assert operations['task_decide']['channel'] == 'trusted_user'
    assert operations['hand_repair']['channel'] == 'local_operator'
    assert load_contract() is not load_contract()


def test_core_service_and_all_business_http_routes_are_mapped_read_only():
    # Parse source only: no DB connection or optional runtime import needed.
    tree = ast.parse((ROOT/'src/modelcrew/workflow.py').read_text(encoding='utf-8-sig'))
    methods = {node.name for cls in tree.body if isinstance(cls, ast.ClassDef)
               and cls.name == 'Workflow' for node in cls.body if isinstance(node, ast.FunctionDef)}
    api = ast.parse((ROOT/'src/modelcrew/api.py').read_text(encoding='utf-8-sig'))
    routes = set()
    for node in ast.walk(api):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ('get', 'post'):
                    path = ast.literal_eval(dec.args[0])
                    if path not in ('/search', '/health'):
                        routes.add((dec.func.attr.upper(), path))
    mapped = set()
    for op in load_contract()['operations']:
        service = op['core']['service']
        if service and service.startswith('Workflow.'):
            assert service.removeprefix('Workflow.') in methods
        if op['core']['http']:
            mapped.add(tuple(op['core']['http'][key] for key in ('method', 'path')))
    assert mapped == routes


def test_frozen_core_body_schemas_have_not_drifted():
    from modelcrew.api import app
    components = app.openapi()['components']['schemas']
    frozen = request_schema()['$defs']
    def rewrite(value):
        if isinstance(value, dict):
            return {k: (v.replace('#/components/schemas/', '#/$defs/') if k == '$ref' else rewrite(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        return value
    for name, schema in components.items():
        if name in ('HandDecision','Decision'):
            # Native chat adds an opt-in combined scope; the frozen HTTP body stays unchanged.
            import json
            from modelcrew.business_contract import _read
            original=_read('business-request-1.0.0.schema.json')
            assert original['$defs'][name]==rewrite(schema),name
        else:assert frozen[name] == rewrite(schema), name


def test_valid_step_is_schema_validation_only():
    request = command()
    assert validate_request(request) is request
    digest = request_digest(request)
    assert len(digest) == 64
    reordered = dict(reversed(list(request.items())))
    assert request_digest(reordered) == digest
    changed = copy.deepcopy(request); changed['expected_binding']['version'] = 2
    assert request_digest(changed) != digest


@pytest.mark.parametrize('field,value,code', [
    ('contract_version', '0.1.0', 'unsupported_contract_version'),
    ('operation', 'auto_approve_everything', 'unsupported_operation'),
    ('operation', [], 'unsupported_operation'),
    ('arguments', {'task_id': '../secret', 'run_id': 'run-1'}, 'invalid_request'),
    ('arguments', {'task_id': 'q1', 'run_id': 'run-1', 'path': 'secret'}, 'invalid_request'),
    ('expected_binding', {}, 'invalid_request'),
    ('expected_binding', {'task_id': 'other', 'version': 1, 'contract_sha256': H, 'run_id': 'run-1'}, 'stale_binding'),
])
def test_invalid_envelope_and_drift_are_rejected(field, value, code):
    request = command(); request[field] = value
    with pytest.raises(BusinessContractError) as error:
        validate_request(request)
    assert error.value.code == code


@pytest.mark.parametrize('version', [True, 0, 1.5, '1', float('nan')])
def test_versions_are_finite_positive_integers(version):
    request = command(); request['expected_binding']['version'] = version
    with pytest.raises(BusinessContractError):
        validate_request(request)


def test_mutation_requires_original_request_id_and_body_identity():
    request = command('hand_start', task_id='q1', hand='coding', body={
        'version': 1, 'actor': 'host', 'request_id': 'different', 'guidance': 'bounded test'})
    with pytest.raises(BusinessContractError) as error:
        validate_request(request)
    assert error.value.code == 'idempotency_conflict'
    request['arguments']['body']['request_id'] = request['request_id']
    validate_request(request)
    request.pop('request_id')
    with pytest.raises(BusinessContractError):
        validate_request(request)


def decision(kind='model'):
    value = command('task_decide', task_id='q1', body={
        'actor': 'user', 'request_id': 'request-1', 'version': 1, 'kind': kind,
        'decision': 'approve', 'reason': 'synthetic contract example only'})
    value['user_event'] = {'event_id': 'event-1', 'channel': 'trusted_local_cli', 'statement_sha256': H}
    return value


def test_decision_requires_event_reference_but_reference_is_not_authentication():
    value = decision(); validate_request(value)
    value.pop('user_event')
    with pytest.raises(BusinessContractError):
        validate_request(value)
    value['arguments']['body']['actor'] = 'trusted-admin'
    with pytest.raises(BusinessContractError):
        validate_request(value)


def test_result_decision_and_manuscript_decision_bind_exact_target():
    value = decision('result')
    with pytest.raises(BusinessContractError): validate_request(value)
    value['arguments']['body']['result_revision'] = 1
    validate_request(value)
    value['expected_binding']['result_revision'] = 2
    with pytest.raises(BusinessContractError) as error: validate_request(value)
    assert error.value.code == 'stale_binding'
    value = command('hand_decide', task_id='q1', run_id='run-1', body={
        'actor': 'user', 'request_id': 'request-1', 'kind': 'manuscript', 'decision': 'approve',
        'statement': 'synthetic', 'reason': 'synthetic', 'artifact_sha256': H})
    value['user_event'] = decision()['user_event']; validate_request(value)
    value['expected_binding'].pop('artifact_sha256')
    with pytest.raises(BusinessContractError): validate_request(value)


@pytest.mark.parametrize('kind,extra', [
    ('revise_model', {}), ('revise_mathematics', {}),
    ('revise_interpretation', {}), ('restore_version', {})])
def test_revision_conditional_fields_are_required(kind, extra):
    op = 'task_restore' if kind == 'restore_version' else 'task_revise'
    value = command(op, task_id='q1', body={
        'actor': 'host', 'request_id': 'request-1', 'version': 1,
        'kind': kind, 'reason': 'explicit guidance', **extra})
    with pytest.raises(BusinessContractError): validate_request(value)


def test_missing_operation_may_be_described_but_never_claimed_as_executable():
    value = {'contract_version': '1.0.0', 'operation': 'artifact_read', 'arguments': {
        'owner': {'project_id': 'demo', 'task_id': 'q1', 'version': 1},
        'artifact_id': 'artifact-1', 'sha256': H, 'offset': 0, 'max_bytes': 1024}}
    validate_request(value)
    for change in ({'path': 'C:/secret'}, {'url': 'https://example.invalid'}, {'max_bytes': 262145}):
        bad = copy.deepcopy(value); bad['arguments'].update(change)
        with pytest.raises(BusinessContractError): validate_request(bad)
    value['arguments']['owner'].pop('version')
    with pytest.raises(BusinessContractError): validate_request(value)


def test_unknown_mutation_outcome_cannot_suggest_automatic_retry():
    value = result('outcome_unknown')
    with pytest.raises(BusinessContractError): validate_response(value)
    value['error'] = {'code': 'outcome_unknown', 'message': 'Query original request', 'recovery': 'query_operation_status'}
    validate_response(value)
    value['error']['recovery'] = 'fix_request'
    with pytest.raises(BusinessContractError): validate_response(value)


def test_pending_user_input_contains_separate_version_bound_scopes():
    value = result('needs_user_input', 'pending_list')
    with pytest.raises(BusinessContractError): validate_response(value)
    value['pending'] = [{'pending_id': 'pending-'+kind, 'kind': kind,
                         'binding': {'project_id': 'demo', 'task_id': 'q1', 'version': 1, 'contract_sha256': H,
                                     'run_id': 'run-1', 'artifact_sha256': H},
                         'artifact_ids': [kind+'-1'], 'prompt': '合成示例，尚待真实用户决定',
                         'allowed_decisions': ['approve', 'reject'], 'decision_operation': 'hand_decide'}
                        for kind in ('manuscript', 'figures')]
    for item in value['pending']:
        item['pending_id'] = pending_id(item['kind'], item['binding'], item['artifact_ids'])
    validate_response(value)
    assert len(value['pending']) == 2
    value['pending'][0]['binding']['version'] = 2
    with pytest.raises(BusinessContractError): validate_response(value)


def test_artifact_chunk_bounds_and_encoding_are_checked():
    value = result(operation='artifact_read')
    value['chunk'] = {'artifact_id': 'artifact-1', 'sha256': H, 'offset': 0,
                      'bytes_returned': 3, 'total_bytes': 3, 'encoding': 'base64',
                      'content': base64.b64encode(b'abc').decode(), 'eof': True}
    validate_response(value)
    for changes in ({'bytes_returned': 2}, {'offset': 2}, {'content': '***'}, {'eof': False}):
        bad = copy.deepcopy(value); bad['chunk'].update(changes)
        with pytest.raises(BusinessContractError): validate_response(bad)


def test_error_recovery_is_fixed_for_all_error_codes():
    for code, policy in load_contract()['errors'].items():
        value = result('error')
        value['error'] = {'code': code, 'message': 'Synthetic diagnostic', 'recovery': policy['recovery']}
        validate_response(value)
        value['error']['recovery'] = 'not_a_registered_policy'
        with pytest.raises(BusinessContractError): validate_response(value)


def test_contract_resources_are_available_outside_checkout_from_zip(tmp_path):
    package = ROOT/'src/modelcrew'; archive = tmp_path/'contract.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        for name in ('__init__.py', 'business_contract.py', 'package_resources.py'):
            zipped.write(package/name, 'modelcrew/'+name)
        for name in ('business-tools-1.0.0.json', 'business-request-1.0.0.schema.json', 'business-response-1.0.0.schema.json'):
            zipped.write(package/'resources/contracts'/name, 'modelcrew/resources/contracts/'+name)
    dependency_root = str(Path(__import__('jsonschema').__file__).parent.parent)
    assert not Path(dependency_root).is_relative_to(ROOT)
    code = "import sys,json; sys.path.insert(0,sys.argv[1]); sys.path.insert(1,sys.argv[2]); from modelcrew.business_contract import audit_contract; print(json.dumps(audit_contract()))"
    response = subprocess.run([sys.executable, '-I', '-c', code, str(archive), dependency_root], cwd=tmp_path,
                              capture_output=True, text=True, timeout=60)
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout)['operations'] == 50


def test_all_frozen_examples_are_contract_valid_and_explicitly_unexecuted():
    from modelcrew.package_resources import resource
    samples = json.loads(resource('contracts/business-examples-1.0.0.json').read_text(encoding='utf-8'))
    assert 'No request executed' in samples['scope']
    for value in samples['requests']:
        validate_request(value)
    for value in samples['responses']:
        validate_response(value)


def test_successful_mutation_requires_durable_receipt():
    value = result()
    validate_response(value)
    value['receipt'] = None
    with pytest.raises(BusinessContractError): validate_response(value)


def test_operation_lookup_is_scoped_and_requires_original_operation():
    value = {'contract_version': '1.0.0', 'operation': 'operation_status',
             'arguments': {'project_id': 'demo', 'task_id': 'q1',
                           'operation_name': 'hand_advance', 'request_id': 'request-1'}}
    validate_request(value)
    value['arguments'].pop('project_id')
    with pytest.raises(BusinessContractError): validate_request(value)


def test_hand_advance_additive_coder_revision_schema_keeps_old_requests_and_no_approval_fields():
    from modelcrew.workflow_mcp import input_schema
    old=command();assert validate_request(old) is old
    revised=copy.deepcopy(old)
    revised['arguments']['code_revision']={'stage':'minimal','code_path':'runs/repairs/patched.py',
        'code_sha256':H,'previous_code_sha256':H,'rationale':'targeted implementation change'}
    assert validate_request(revised) is revised
    assert 'code_revision' in input_schema('hand_advance')['properties']['arguments']['properties']
    for key,value in [('actor','user'),('approved',True),('max_repairs',100)]:
        bad=copy.deepcopy(revised);bad['arguments']['code_revision'][key]=value
        with pytest.raises(BusinessContractError):validate_request(bad)


def test_revision_file_transport_preserves_inline_schema_and_rejects_ambiguous_payload():
    command={'contract_version':'1.0.0','operation':'task_revise','request_id':'revision-1',
        'arguments':{'task_id':'q1','body':{'actor':'modeling-hand','request_id':'revision-1','version':1,'kind':'revise_model','reason':'revision'},
        'revision_files':{'contract_path':'runs/c.json','contract_sha256':H,'math_package_path':'runs/m.json','math_package_sha256':H}},
        'expected_binding':{'task_id':'q1','version':1,'contract_sha256':H}}
    assert validate_request(command) is command
    bad=copy.deepcopy(command);bad['arguments']['body']['contract']={}
    with pytest.raises(BusinessContractError):validate_request(bad)
    bad=copy.deepcopy(command);bad['arguments']['revision_files'].pop('math_package_sha256')
    with pytest.raises(BusinessContractError):validate_request(bad)


def test_prepared_proposal_file_transport_is_small_and_hash_bound():
    value=command('modeling_start',task_id='q1',body={'version':1,'actor':'editor','request_id':'request-1','guidance':'Submit full prepared draft'},
                  proposal_files={'path':'runs/prepared/submission.json','sha256':H})
    validate_request(value)
    value['arguments']['proposal_files']['sha256']='not-a-hash'
    with pytest.raises(BusinessContractError):validate_request(value)
