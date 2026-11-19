"""Trusted local terminal and DSH decisions. This module is deliberately absent from MCP tools.

Trust root: the local OS session and database owner, not actor labels, TTY alone,
or a caller-provided JSON event. Same-account arbitrary Python/SQL access is
outside this boundary. DSH capture requires its separate private-pipe evidence.
"""
from contextlib import ExitStack
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import uuid

from psycopg.types.json import Jsonb

from .business_adapter import (BusinessAdapter, clean, failure,
                               legacy_domain, resource_for, scope_for)
from .business_artifacts import ArtifactRegistry
from .business_contract import (BusinessContractError, VERSION, request_digest,
                                validate_request, validate_response)
from .business_projection import check_binding, list_pending, require_row
from .business_store import BusinessStore
from .contracts import digest

OPERATIONS = frozenset(('task_decide', 'hand_decide', 'assembly_decide'))


def statement_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def local_principal():
    """Read process-token identity, never USER/USERNAME or actor in a request."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.LocalFree.argtypes = [wintypes.HLOCAL]
        advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise OSError('Unable to read process token')
        try:
            size = wintypes.DWORD()
            advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not size.value:
                raise OSError('Unable to size process identity')
            buf = ctypes.create_string_buffer(size.value)
            if not advapi.GetTokenInformation(token, 1, buf, size.value, ctypes.byref(size)):
                raise OSError('Unable to read process identity')
            sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
            text = wintypes.LPWSTR()
            if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise OSError('Unable to resolve process identity')
            try:
                identity = text.value
            finally:
                kernel.LocalFree(ctypes.cast(text, wintypes.HLOCAL))
        finally:
            kernel.CloseHandle(token)
        kind = 'windows_process_token'
    elif hasattr(os, 'geteuid'):
        identity = str(os.geteuid())
        kind = 'posix_effective_uid'
    else:
        raise BusinessContractError('untrusted_user_event', 'Unsupported local identity source')
    return {'kind': kind, 'subject_sha256': digest({'machine': socket.gethostname(), 'identity': identity})}


def decision_request(item, review, decision, reason, statement, *, channel='trusted_local_cli'):
    """Shared exact request construction; never captures or authorizes an event."""
    if (decision not in item['allowed_decisions'] or not isinstance(reason, str)
            or not isinstance(statement, str) or not reason.strip() or not statement.strip()
            or len(reason) > 2000 or len(statement) > 2000
            or channel not in ('trusted_local_cli', 'trusted_host_ui')):
        raise BusinessContractError('user_input_required', 'Explicit bounded decision, reason and statement required')
    name = item['decision_operation']
    args = {k: v for k, v in item['binding'].items() if k in ('project_id', 'task_id', 'run_id', 'build_id')}
    if name in ('task_decide', 'hand_decide'): args.pop('project_id', None)
    key = 'user-' + uuid.uuid4().hex
    body = {'kind': item['kind'], 'decision': decision, 'actor': 'user', 'reason': reason, 'request_id': key}
    if name == 'task_decide':
        body['version'] = item['binding']['version']
        if item['kind'] == 'model' and decision == 'approve':
            body['defer_execution'] = True
        if item['kind'] == 'result':
            body['result_revision'] = item['binding']['result_revision']
        math = review['dossier'].get('mathematics')
        if math:
            body['math_semantic_sha256'] = math['semantic_sha256']
    else:
        body.update(statement=statement, artifact_sha256=item['binding']['artifact_sha256'])
    if item.get('confirmation_scope')=='manuscript_and_figures':
        if name not in ('hand_decide','assembly_decide') or decision!='approve':raise BusinessContractError('invalid_request','Combined scope requires explicit paper approval')
        body.update(approve_figures=True,**item['components'])
    args['body'] = body
    event_id = 'user-event-' + uuid.uuid4().hex
    request = {'contract_version': VERSION, 'operation': name, 'arguments': args, 'request_id': key,
               'expected_binding': item['binding'], 'user_event': {'event_id': event_id,
               'channel': channel, 'statement_sha256': statement_hash(statement)}}
    validate_request(request)
    return request


class TrustedDecisions:
    def __init__(self, workflow_factory=None, *, root=None, fault=None):
        self.adapter = BusinessAdapter(workflow_factory, root=root)
        self.root = self.adapter.root
        self.fault = fault  # In-process fault injection only; no CLI argument.

    def _locks(self, w, scope):
        stack = ExitStack()
        try:
            stack.enter_context(w.lock('business:' + resource_for(scope)))
            if scope.get('task_id'):
                stack.enter_context(w.lock(scope['task_id']))
            else:
                # Match the native assembly -> sorted chapter task lock order.
                stack.enter_context(w.lock('assembly:' + scope['project_id']))
                row = require_row(w.db.execute('SELECT r.payload FROM mc_assembly_runs r JOIN mc_assembly_builds b ON b.assembly_run_id=r.id WHERE b.project_id=%s AND b.id::text=%s',
                                              (scope['project_id'], scope['build_id'])).fetchone())
                for task in sorted(c['task_id'] for c in row['payload']['chapters']):
                    stack.enter_context(w.lock(task))
            return stack
        except BaseException:
            stack.close()
            raise

    def _review(self, w, name, args, pending_id):
        registry = ArtifactRegistry(w, self.root)
        scope = scope_for(name, args, w)
        query = {k: scope[k] for k in ('project_id', 'task_id', 'run_id', 'build_id') if k in scope}
        items = list_pending(w, registry, query)
        from .combined_paper_review import combined_pending
        items=[*items,*combined_pending(items)]
        item = next((p for p in items if p['pending_id'] == pending_id and p['decision_operation'] == name), None)
        if item is None:
            raise BusinessContractError('stale_binding', 'Pending content is no longer current')
        if name == 'task_decide':
            dossier = w.inspect(scope['task_id'])
            dossier['modeling_runs'] = w.modeling_status(scope['task_id'])
            from .mcp_workflow import evidence
            dossier['reference_evidence'] = evidence(w, scope['task_id'], dossier['task']['current_version'])
            if item['kind']=='result' and (dossier.get('result') or {}).get('review',{}).get('kind')=='hand_runtime_P2':
                from .result_review_documents import result_context
                dossier['result_review_evidence']=result_context(w,scope['task_id'],dossier['execution'])
            owner = {k: item['binding'][k] for k in ('project_id', 'task_id', 'version')}
            for asset in dossier['contract']['content']['inputs']:
                _, sha = registry.resolve_input(asset['path'], owner)
                if sha != asset['sha256']:
                    raise BusinessContractError('artifact_changed', 'Review input bytes changed')
        elif name == 'hand_decide':
            dossier = w.hand_status(scope['task_id'], scope['run_id'])
            if item.get('confirmation_scope')=='manuscript_and_figures':
                from . import hand_runtime as hr
                writer=hr.load(w,scope['task_id'],scope['run_id']);hr.guard(w,writer);wp=writer['payload'];wf=hr.run_folder(writer)
                dossier['writing_review_context']={'manuscript':{'path':wp['manuscript'],'sha256':hr.sha_file(hr.workspace_path(self.root,wp['manuscript']))},
                    'catalog':{'path':hr.rel(wf/'figure-catalog.json'),'sha256':hr.sha_file(wf/'figure-catalog.json')},
                    'outline':{'path':wp['outline'],'sha256':hr.sha_file(hr.workspace_path(self.root,wp['outline']))}}

        else:
            dossier = w.assembly_build_status(scope['project_id'], scope['build_id'])
            if item.get('confirmation_scope')=='manuscript_and_figures':
                from . import assembly_builds as ab
                writer=ab.load(w,scope['project_id'],scope['build_id']);ab.guard(w,scope['project_id'],writer)
                source=ab.source_folder(writer)
                dossier['writing_review_context']={'manuscript':{'path':ab.rel(source/ab.composer.MD_NAME),'sha256':ab.sha_file(source/ab.composer.MD_NAME)},
                    'catalog':{'path':ab.rel(source/'figure-catalog.json'),'sha256':ab.sha_file(source/'figure-catalog.json')},
                    'assembly_id':scope['build_id'],'catalog_evidence':ab.read(source/'figure-catalog.json').get('evidence',{})}

        # Store/display the same review projection; no caller-provided synopsis.
        context = {'pending': item, 'dossier': clean(dossier, self.root)}
        artifacts = (registry.task(scope['task_id'], item['binding']['version'], scope.get('run_id'))
                     if scope.get('task_id') else registry.assembly(scope['project_id'], scope['build_id']))
        context['review_files'] = []
        for artifact in artifacts:
            row = require_row(w.db.execute('SELECT path FROM mc_business_artifacts WHERE artifact_id=%s', (artifact['artifact_id'],)).fetchone())
            # Only this privileged local review projection shows local locations.
            # MCP responses continue to redact them via the ordinary adapter.
            context['review_files'].append({**artifact, 'local_path': str(self.root / row['path'])})
        texts = []
        for artifact_id in item['artifact_ids']:
            record = require_row(w.db.execute('SELECT owner,sha256,bytes,media_type FROM mc_business_artifacts WHERE artifact_id=%s', (artifact_id,)).fetchone())
            data = bytearray()
            for offset in range(0, record['bytes'], 262144):
                import base64
                chunk = registry.read({'owner': record['owner'], 'artifact_id': artifact_id,
                                       'sha256': record['sha256'], 'offset': offset, 'max_bytes': 262144})
                data.extend(base64.b64decode(chunk['content']))
            # These pending artifacts are manuscript Markdown or a JSON catalog.
            texts.append({'artifact_id': artifact_id, 'sha256': record['sha256'], 'text': bytes(data).decode('utf-8-sig')})
        context['review_texts'] = texts
        return context

    def pending(self, scope):
        with self.adapter.workflow() as w:
            return list_pending(w, ArtifactRegistry(w, self.root), scope)

    def capture_interactive(self, scope):
        """Only terminal interaction can mint local evidence. No statement flags."""
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise BusinessContractError('untrusted_user_event', 'A trusted interactive local terminal is required')
        principal = local_principal()
        items = self.pending(scope)
        print(json.dumps({'pending': items}, ensure_ascii=False, indent=2))
        selected = input('请输入完整 pending_id（留空取消）：').strip()
        item = next((p for p in items if p['pending_id'] == selected), None)
        if item is None:
            raise BusinessContractError('user_input_required', 'No current pending item selected')
        name = item['decision_operation']
        args = {k: v for k, v in item['binding'].items() if k in ('project_id', 'task_id', 'run_id', 'build_id')}
        if name in ('task_decide', 'hand_decide'):
            args.pop('project_id', None)
        with self.adapter.workflow() as w:
            bound_scope = scope_for(name, args, w)
            with self._locks(w, bound_scope):
                review = self._review(w, name, args, selected)
        print(json.dumps(review, ensure_ascii=False, indent=2))
        print('请实际审阅上面的契约／结果／正文或图目录及对应文件；本入口不会代替审图和独立质检。')
        decision = input('决定（approve / reject；留空取消）：').strip()
        if decision not in item['allowed_decisions']:
            raise BusinessContractError('user_input_required', 'No explicit decision')
        reason = input('请输入本次审阅理由：').strip()
        statement = input('请输入本次真实用户决定陈述：')
        if not reason or not statement.strip() or len(reason) > 2000 or len(statement) > 2000:
            raise BusinessContractError('invalid_request', 'Explicit bounded statement and reason required')
        request = decision_request(item, review, decision, reason, statement)
        event_id = request['user_event']['event_id']
        challenge = decision + ' ' + selected[-12:] + ' ' + secrets.token_hex(4)
        print(json.dumps({'request': request, 'statement': statement, 'review_sha256': digest(review)}, ensure_ascii=False, indent=2))
        if input('请原样输入以确认本笔决定：' + challenge + '\n').strip() != challenge:
            raise BusinessContractError('user_input_required', 'Local challenge cancelled')
        # Never hold DB locks while a person reviews. Recheck all bytes/state now.
        with self.adapter.workflow() as w:
            with self._locks(w, bound_scope):
                if self._review(w, name, args, selected) != review:
                    raise BusinessContractError('stale_binding', 'Review context changed during user interaction')
                check_binding(w, args, {k: v for k, v in request['expected_binding'].items() if k != 'artifact_sha256'})
                with w.db.transaction():
                    w.db.execute('INSERT INTO mc_trusted_user_events(event_id,channel,principal,pending_id,review_sha256,review,statement,statement_sha256,request_sha256,request) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                 (event_id, 'trusted_local_cli', Jsonb(principal), selected, digest(review), Jsonb(review), statement,
                                  statement_hash(statement), request_digest(request), Jsonb(request)))
        return request

    def submit(self, request):
        """Consume independent capture evidence; caller JSON alone grants nothing."""
        name = request.get('operation', '') if isinstance(request, dict) else ''
        if name not in OPERATIONS:
            raise BusinessContractError('unsupported_operation', 'No generic final/user-operation approval adapter')
        validate_request(request)
        key = request['request_id']; args = request['arguments']; row = None
        try:
            with self.adapter.workflow() as w:
                self.adapter._ensure_targets(w, name, args)
                scope = scope_for(name, args, w)
                with self._locks(w, scope):
                    store = BusinessStore(w.db); registry = ArtifactRegistry(w, self.root)
                    event = require_row_event(w, request)
                    row = store.get(scope, name, key)
                    if row:
                        if row['request_sha256'] != request_digest(request):
                            raise BusinessContractError('idempotency_conflict', 'Decision key payload changed')
                        if row['state'] in ('claimed', 'dispatched', 'outcome_unknown'):
                            reconcile_decision(self.adapter, w, store, registry, row)
                            row = store.get(scope, name, key)
                        return validate_response(store.replay(row) or self.adapter._unknown(row))
                    if w.db.execute('SELECT 1 FROM mc_trusted_user_event_claims WHERE event_id=%s', (event['event_id'],)).fetchone():
                        raise BusinessContractError('untrusted_user_event', 'User event was already claimed')
                    if not event['valid_now']:
                        raise BusinessContractError('untrusted_user_event', 'User event expired')
                    if store.unresolved(resource_for(scope)):
                        raise BusinessContractError('outcome_unknown', 'An unresolved operation fences this target')
                    check_binding(w, args, {k: v for k, v in request['expected_binding'].items() if k != 'artifact_sha256'})
                    # artifact_sha256 is checked against the byte-verified pending
                    # item below; generic binding() has no single artifact field.
                    review = self._review(w, name, args, event['pending_id'])
                    if digest(review) != event['review_sha256'] or review['pending']['binding'] != request['expected_binding']:
                        raise BusinessContractError('stale_binding', 'Confirmed content has changed')
                    body = args['body']
                    if review['pending']['kind'] != body['kind']:
                        raise BusinessContractError('untrusted_user_event', 'Decision targets another pending kind')
                    if name == 'task_decide':
                        if body['actor'] != 'user' or w.task(scope['task_id'])['executor_key'] != 'pending-code':
                            raise BusinessContractError('workflow_conflict', 'G3 handles production pending-code tasks only')
                        if body['kind'] == 'model' and body['decision'] == 'approve' and body.get('defer_execution') is not True:
                            raise BusinessContractError('invalid_request', 'Model approval must defer execution')
                        if w.db.execute('SELECT 1 FROM mc_requests WHERE task_id=%s AND request_id=%s', (scope['task_id'], key)).fetchone():
                            raise BusinessContractError('idempotency_conflict', 'Decision key already used by native service')
                    if name == 'task_decide' and body['decision'] == 'approve':
                        from .mathematics import approval_snapshot
                        approval_snapshot(w, w.task(scope['task_id']), body.get('math_semantic_sha256'), body.get('reason', ''))
                        if body['kind'] == 'model':
                            from .modeling_hand import assert_m1
                            from .mcp_workflow import source_snapshot
                            if assert_m1(w, w.task(scope['task_id'])) is None:
                                raise BusinessContractError('workflow_conflict', 'A current independent M1 receipt is required')
                            source_snapshot(w, scope['task_id'], body['version'])
                    # Authorization claim and business fence are committed together.
                    # Claim means permission spent on one attempt, NOT user approval.
                    with w.db.transaction():
                        row = store.claim(scope, name, key, request_digest(request), request, resource_for(scope),
                                          'actions:' + scope['task_id'] if name == 'task_decide' else legacy_domain(name, scope))
                        claimed = w.db.execute('INSERT INTO mc_trusted_user_event_claims(event_id,scope_sha256,operation,request_id,request_sha256) SELECT event_id,%s,%s,%s,%s FROM mc_trusted_user_events WHERE event_id=%s AND expires_at > clock_timestamp() RETURNING event_id',
                                               (digest(scope), name, key, request_digest(request), event['event_id'])).fetchone()
                        if not claimed:
                            raise BusinessContractError('untrusted_user_event', 'User event expired before claim')
                        row = store.save(row, 'dispatched')
                    try:
                        if self.fault: self.fault('before_core', row)
                        if name == 'task_decide':
                            value = w.action(scope['task_id'], **body)
                        elif name == 'hand_decide':
                            value = w.hand_decision(scope['task_id'], scope['run_id'], **body)
                        else:
                            value = w.assembly_build_decision(scope['project_id'], scope['build_id'], **body)
                        if self.fault: self.fault('after_core', row)
                        response = decision_response(self.adapter, w, registry, request, value)
                        response['receipt'] = {**store.receipt(row), 'state': 'succeeded'}
                        validate_response(response)
                        row = store.save(row, 'succeeded', response)
                        if self.fault: self.fault('after_save', row)
                        response['receipt'] = store.receipt(row)
                        return validate_response(response)
                    except BaseException as exc:
                        if isinstance(exc, (KeyboardInterrupt, SystemExit)): raise
                        current = store.get(scope, name, key)
                        if current['state'] == 'succeeded': return validate_response(store.replay(current))
                        # Native core can commit then fail in checkpoint/filesystem
                        # work. Never infer failure or call it again from exception.
                        row = store.save(current, 'outcome_unknown')
                        reconcile_decision(self.adapter, w, store, registry, row)
                        row = store.get(scope, name, key)
                        return validate_response(store.replay(row) or self.adapter._unknown(row))
        except BusinessContractError as exc:
            return validate_response(failure(name, exc.code, key, unknown=exc.code == 'outcome_unknown'))
        except ValueError:
            return validate_response(failure(name, 'workflow_conflict', key))


def require_row_event(w, request):
    reference = request['user_event']
    event = w.db.execute('SELECT *,expires_at > clock_timestamp() AS valid_now FROM mc_trusted_user_events WHERE event_id=%s', (reference['event_id'],)).fetchone()
    if (not event or reference['channel'] not in ('trusted_local_cli', 'trusted_host_ui') or event['channel'] != reference['channel']
            or event['statement_sha256'] != reference['statement_sha256']
            or statement_hash(event['statement']) != reference['statement_sha256']
            or event['request_sha256'] != request_digest(request) or event['request'] != request
            or digest(event['review']) != event['review_sha256']):
        raise BusinessContractError('untrusted_user_event', 'No independently captured matching event')
    if event['channel'] == 'trusted_host_ui':
        from .dsh_decisions import validate_capture
        validate_capture(w, event)
    # Capture identity is evidence of the local OS boundary, not a public auth token.
    if event['principal'] != local_principal():
        raise BusinessContractError('untrusted_user_event', 'Different local OS principal')
    return event



def decision_response(adapter, w, registry, request, value):
    response = adapter._response(w, registry, request['operation'], request['arguments'], value, request['request_id'])
    event = require_row(w.db.execute('SELECT pending_id,review_sha256 FROM mc_trusted_user_events WHERE event_id=%s', (request['user_event']['event_id'],)).fetchone())
    body = request['arguments']['body']
    response['data']['user_decision'] = {'event_reference': request['user_event'],
        'confirmed_binding': request['expected_binding'], 'pending_id': event['pending_id'],
        'review_sha256': event['review_sha256'], 'kind': body['kind'], 'decision': body['decision'],
        'request_id': request['request_id']}
    if body.get('approve_figures'):
        response['data']['user_decision'].update(confirmation_scope='manuscript_and_figures',
            confirmed_components={k:body[k] for k in ('manuscript_sha256','figure_catalog_sha256')})
    return response


def reconcile_decision(adapter, w, store, registry, row):
    """Read durable core decision evidence; no command, checkpoint or file writes."""
    name = row['operation']; args = row['request']['arguments']; scope = row['scope']; body = args['body']
    if name not in OPERATIONS: return
    claim = w.db.execute('SELECT c.event_id FROM mc_trusted_user_event_claims c JOIN mc_trusted_user_events e ON e.event_id=c.event_id WHERE c.scope_sha256=%s AND c.operation=%s AND c.request_id=%s AND c.request_sha256=%s AND e.request_sha256=c.request_sha256',
                         (row['scope_sha256'], name, row['request_id'], row['request_sha256'])).fetchone()
    if not claim: return
    value = None
    if name == 'task_decide':
        # Immutable business event binds the exact native payload (which adds
        # computed math/M1/reference snapshots); mc_requests proves key commit.
        native = w.db.execute('SELECT payload_sha256 FROM mc_requests WHERE task_id=%s AND request_id=%s', (scope['task_id'], row['request_id'])).fetchone()
        events = w.db.execute('SELECT payload FROM mc_events WHERE task_id=%s AND kind=%s AND actor=%s AND created_at >= %s',
                              (scope['task_id'], body['kind'] + '_' + body['decision'], 'user', row['created_at'])).fetchall()
        expected = {'actor': body['actor'], 'version': body['version'], 'kind': body['kind'],
                    'decision': body['decision'], 'result_revision': body.get('result_revision'),
                    'reason': body.get('reason', ''), 'contract': None}
        if body.get('defer_execution'): expected['defer_execution'] = True
        if body.get('math_semantic_sha256') is not None: expected['math_semantic_sha256'] = body['math_semantic_sha256']
        # The core computes its request hash before appending internal snapshots.
        if native and native['payload_sha256'] == digest(expected) and any(
                all(e['payload'].get(k) == v for k, v in expected.items()) for e in events):
            value = w.inspect(scope['task_id'])
    elif name == 'hand_decide':
        payload = require_row(w.db.execute('SELECT payload FROM mc_hand_runs WHERE task_id=%s AND id::text=%s', (scope['task_id'], scope['run_id'])).fetchone())['payload']
        if payload.get('decisions', {}).get(row['request_id']) == digest({k: v for k, v in body.items() if k != 'request_id'}):
            value = w.hand_status(scope['task_id'], scope['run_id'])
    else:
        payload = require_row(w.db.execute('SELECT payload FROM mc_assembly_builds WHERE project_id=%s AND id::text=%s', (scope['project_id'], scope['build_id'])).fetchone())['payload']
        saved = payload.get('decisions', {}).get(row['request_id'])
        if saved and saved['request_sha256'] == digest(body):
            value = w.assembly_build_status(scope['project_id'], scope['build_id'])
    if value is not None:
        response = decision_response(adapter, w, registry, row['request'], value)
        response['receipt'] = {**store.receipt(row), 'state': 'succeeded'}
        validate_response(response)
        store.save(row, 'succeeded', response)


def main():
    parser = argparse.ArgumentParser(description='枢模可信本地用户决定；不向模型提供批准工具')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('pending', 'review'):
        p = sub.add_parser(command); p.add_argument('--project', required=True); p.add_argument('--task'); p.add_argument('--run'); p.add_argument('--build')
    p = sub.add_parser('status'); p.add_argument('--event-id', required=True)
    args = parser.parse_args(); service = TrustedDecisions()
    try:
        if args.command == 'status':
            with service.adapter.workflow() as w:
                event = w.db.execute('SELECT request,principal FROM mc_trusted_user_events WHERE event_id=%s', (args.event_id,)).fetchone()
                if not event or event['principal'] != local_principal():
                    raise BusinessContractError('untrusted_user_event', 'Unknown event or different local principal')
                request = event['request']; scope = scope_for(request['operation'], request['arguments'], w)
            value = service.adapter.invoke('operation_status', {'contract_version': VERSION, 'operation': 'operation_status', 'arguments': {**scope, 'operation_name': request['operation'], 'request_id': request['request_id']}})
        else:
            if (args.run and not args.task) or (args.build and (args.task or args.run)):
                raise BusinessContractError('invalid_request', 'Choose task[/run] or build')
            scope = {'project_id': args.project, **{k: v for k, v in (('task_id', args.task), ('run_id', args.run), ('build_id', args.build)) if v}}
            value = {'pending': service.pending(scope)} if args.command == 'pending' else service.submit(service.capture_interactive(scope))
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    except (EOFError, KeyboardInterrupt):
        print(json.dumps({'status': 'cancelled', 'user_approval_created': False})); raise SystemExit(1) from None
    except Exception as exc:
        code = exc.code if isinstance(exc, BusinessContractError) else 'service_unavailable'
        print(json.dumps({'status': 'error', 'code': code, 'error_type': type(exc).__name__})); raise SystemExit(1) from None


if __name__ == '__main__': main()
