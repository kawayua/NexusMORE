"""Frozen business wire contracts, not a business/MCP dispatcher.

This module needs only base dependencies. Validation neither opens a database nor
executes a model, approves a decision, or makes a missing adapter available.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from .package_resources import resource

VERSION = '1.0.0'


class BusinessContractError(ValueError):
    """A wire contract violation with a stable, non-secret error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _read(name: str) -> dict:
    return json.loads(resource('contracts/' + name).read_text(encoding='utf-8'))


def load_contract() -> dict:
    """Return a fresh catalog; listed operations are not executable tools."""
    return _read(f'business-tools-{VERSION}.json')


def request_schema() -> dict:
    schema=_read(f'business-request-{VERSION}.schema.json')
    # Backward-compatible runtime extension; frozen G1 resource bytes stay unchanged.
    schema['$defs']['request_hand_advance']['properties']['arguments']['properties']['code_revision']=_code_revision_schema()
    # File references are an adapter transport extension, not a change to core Action schemas.
    import copy
    branch=schema['$defs']['request_task_revise']['properties']['arguments']
    inline=copy.deepcopy(branch)
    file_body=copy.deepcopy(schema['$defs']['Action_task_revise'])
    file_body['properties']['kind']={'enum':['revise_model','revise_mathematics']}
    for name in ('contract','math_package'):file_body['properties'].pop(name,None)
    file_body['allOf']=[rule for rule in file_body.get('allOf',[]) if rule.get('if',{}).get('properties',{}).get('kind',{}).get('const') not in ('revise_model','revise_mathematics')]
    schema['$defs']['RevisionFileBody']=file_body
    files=copy.deepcopy(branch)
    files['properties']['body']={'$ref':'#/$defs/RevisionFileBody'}
    files['properties']['revision_files']={'type':'object','additionalProperties':False,
        'required':['contract_path','contract_sha256','math_package_path','math_package_sha256'],
        'properties':{name:({'type':'string','pattern':'^[0-9a-f]{64}$'} if name.endswith('sha256') else
            {'type':'string','minLength':1,'maxLength':2000}) for name in
            ('contract_path','contract_sha256','math_package_path','math_package_sha256')}}
    files['required']=[*files['required'],'revision_files']
    schema['$defs']['request_task_revise']['properties']['arguments']={'oneOf':[inline,files]}
    schema['$defs']['request_modeling_start']['properties']['arguments']['properties']['proposal_files']={
        'type':'object','additionalProperties':False,'required':['path','sha256'],
        'properties':{'path':{'type':'string','minLength':1,'maxLength':2000},
                      'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'}}}
    for name in ('HandDecision','Decision'):
        decision=schema['$defs'][name]
        decision['properties'].update({'approve_figures':{'type':'boolean'},
            'manuscript_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
            'figure_catalog_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'}})
        decision.setdefault('allOf',[]).append({'if':{'properties':{'approve_figures':{'const':True}},'required':['approve_figures']},
            'then':{'required':['manuscript_sha256','figure_catalog_sha256'],'properties':{'kind':{'const':'manuscript'},'decision':{'const':'approve'}}}})
    return schema


def _code_revision_schema():
    return {'type':'object','additionalProperties':False,'required':['stage','code_path','code_sha256','previous_code_sha256','rationale'],
        'properties':{'stage':{'enum':['minimal','full']},
            'code_path':{'type':'string','minLength':1,'maxLength':2000},
            'code_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
            'previous_code_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
            'rationale':{'type':'string','minLength':1,'maxLength':20000}}}


def response_schema() -> dict:
    return _read(f'business-response-{VERSION}.schema.json')


def _canonical(value: Any) -> str:
    def keys(item):
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError('Non-string JSON key')
            for child in item.values():
                keys(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                keys(child)
    try:
        keys(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise BusinessContractError('invalid_request', 'Expected finite JSON data') from exc


def request_digest(request: dict) -> str:
    """Canonical payload hash; does not reserve an idempotency key."""
    validate_request(request)
    return hashlib.sha256(_canonical(request).encode('utf-8')).hexdigest()


def _validate(schema: dict, value: Any) -> None:
    _canonical(value)
    if next(Draft202012Validator(schema).iter_errors(value), None) is not None:
        # jsonschema messages can contain full payloads or private paths.
        raise BusinessContractError('invalid_request', 'Business contract schema mismatch')


def validate_request(request: dict) -> dict:
    """Validate structure and internal binding consistency, never authority.

    G2/G3 still must resolve ownership, check authoritative state under its lock,
    reserve durable claims, and verify the independently captured user event.
    """
    if not isinstance(request, dict):
        raise BusinessContractError('invalid_request', 'Expected a request object')
    if request.get('contract_version') != VERSION:
        raise BusinessContractError('unsupported_contract_version', 'Unsupported business contract version')
    operations = {o['name']: o for o in load_contract()['operations']}
    name = request.get('operation')
    if not isinstance(name, str) or name not in operations:
        raise BusinessContractError('unsupported_operation', 'Unregistered business operation')
    _validate(request_schema(), request)
    args = request['arguments']
    body = args.get('body', {})
    binding = request.get('expected_binding', {})
    if 'request_id' in body and body['request_id'] != request['request_id']:
        raise BusinessContractError('idempotency_conflict', 'Envelope and body request IDs differ')
    for key in ('project_id', 'task_id', 'version', 'run_id', 'build_id'):
        values = [value[key] for value in (args, body, binding) if key in value]
        if values and any(v != values[0] for v in values[1:]):
            raise BusinessContractError('stale_binding', 'Request contains inconsistent binding fields')
    if name in ('manuscript_register_revision', 'figures_select'):
        # A single target is required; a run and a build are different scopes.
        if (bool(args.get('run_id')) == bool(args.get('build_id'))
                or bool(args.get('run_id')) != bool(args.get('task_id'))):
            raise BusinessContractError('invalid_request', 'Choose a task run or an assembly build')
        target = 'run_id' if 'run_id' in args else 'build_id'
        if binding.get(target) != args[target]:
            raise BusinessContractError('stale_binding', 'Revision target must be bound')
    if name == 'pending_list':
        if ('run_id' in args and 'task_id' not in args) or ('build_id' in args and 'task_id' in args):
            raise BusinessContractError('invalid_request', 'Incompatible pending scope')
    if name == 'artifact_read':
        owner = args['owner']
        if ('task_id' in owner) == ('build_id' in owner) or ('run_id' in owner and 'task_id' not in owner):
            raise BusinessContractError('invalid_request', 'Artifact requires a task or build owner')
        if 'task_id' in owner and 'version' not in owner:
            raise BusinessContractError('invalid_request', 'Task artifacts require an explicit version')
    if name == 'assembly_review_w2':
        if bool(body.get('recheck_of')) != bool(body.get('rationale')):
            raise BusinessContractError('invalid_request', 'Recheck requires original request and rationale')
    if name in ('hand_decide', 'assembly_decide'):
        if binding.get('artifact_sha256') != body['artifact_sha256']:
            raise BusinessContractError('stale_binding', 'User decision artifact must be bound')
    if name == 'task_decide' and body['kind'] == 'result':
        if binding.get('result_revision') != body['result_revision'] or not binding.get('execution_id'):
            raise BusinessContractError('stale_binding', 'Result decision requires execution and revision binding')
    if name == 'manuscript_register_revision' and binding['source_sha256'] != args['previous_sha256']:
        raise BusinessContractError('stale_binding', 'Previous manuscript must be bound')
    if name == 'figures_select' and binding['source_sha256'] != args['catalog_sha256']:
        raise BusinessContractError('stale_binding', 'Selection catalog must be bound')
    return request


def pending_id(kind: str, binding: dict, artifact_ids: list[str]) -> str:
    """Stable presentation identity, never an approval token or authentication."""
    value = {'kind': kind, 'binding': binding, 'artifact_ids': sorted(artifact_ids)}
    return 'pending_' + hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def validate_response(response: dict) -> dict:
    _validate(response_schema(), response)
    error = response['error']
    if error and error['recovery'] != load_contract()['errors'][error['code']]['recovery']:
        raise BusinessContractError('invalid_request', 'Error recovery contradicts frozen policy')
    receipt = response['receipt']
    if receipt is not None:
        if response['request_id'] != receipt['request_id']:
            raise BusinessContractError('invalid_request', 'Response receipt request ID differs')
        if response['operation'] != 'operation_status' and response['operation'] != receipt['operation_name']:
            raise BusinessContractError('invalid_request', 'Response receipt operation differs')
    seen = set()
    for item in response['pending']:
        if item['pending_id'] != pending_id(item['kind'], item['binding'], item['artifact_ids']):
            raise BusinessContractError('invalid_request', 'Pending identity differs from current snapshot')
        if item['pending_id'] in seen:
            raise BusinessContractError('invalid_request', 'Duplicate pending item')
        seen.add(item['pending_id'])
        target = item['binding']
        op = item['decision_operation']
        if op == 'hand_decide' and not all(k in target for k in ('task_id', 'version', 'contract_sha256', 'run_id')):
            raise BusinessContractError('invalid_request', 'Pending hand decision requires a bound run')
        if op == 'assembly_decide' and 'build_id' not in target:
            raise BusinessContractError('invalid_request', 'Pending assembly decision requires a bound build')
    chunk = response['chunk']
    if chunk is not None:
        try:
            data = base64.b64decode(chunk['content'], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise BusinessContractError('invalid_request', 'Invalid artifact chunk encoding') from exc
        end = chunk['offset'] + len(data)
        if (len(data) != chunk['bytes_returned'] or end > chunk['total_bytes']
                or chunk['eof'] != (end == chunk['total_bytes'])):
            raise BusinessContractError('invalid_request', 'Inconsistent artifact chunk bounds')
    return response


def audit_contract() -> dict:
    catalog = load_contract()
    request = request_schema()
    response = response_schema()
    Draft202012Validator.check_schema(request)
    Draft202012Validator.check_schema(response)
    names = [op['name'] for op in catalog['operations']]
    branches = [ref['$ref'].rsplit('/', 1)[-1].removeprefix('request_') for ref in request['oneOf']]
    if len(names) != len(set(names)) or names != branches:
        raise BusinessContractError('invalid_request', 'Catalog and request schemas differ')
    if response['properties']['operation']['enum'] != names:
        raise BusinessContractError('invalid_request', 'Response operations differ from catalog')
    return {'contract_version': VERSION, 'status': 'passed', 'operations': len(names),
            'core_status': {status: sum(op['core']['status'] == status for op in catalog['operations'])
                            for status in ('mapped', 'partial', 'missing')},
            'scope': 'contract validation only; no business/MCP/host execution',
            'adapter_implemented': False, 'user_approval_created': False}


if __name__ == '__main__':
    print(json.dumps(audit_contract(), ensure_ascii=False))
