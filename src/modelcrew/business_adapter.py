"""Frozen G1 operations adapted to existing core services with durable dispatch."""
from contextlib import ExitStack
from datetime import date, datetime
from pathlib import Path
import copy
import json
import logging
import re
import uuid

import psycopg
from .business_contract import (VERSION, BusinessContractError, load_contract,
                                request_digest, validate_request, validate_response)
from .business_store import BusinessStore
from .business_artifacts import ArtifactRegistry
from .business_projection import binding, check_binding, list_pending, task_pending, assembly_pending, require_row
from .contracts import digest, validate as validate_model

LOG = logging.getLogger(__name__)
CATALOG = {op['name']:op for op in load_contract()['operations']}
# No trusted_user/local_operator operation is ever callable through this adapter.
IMPLEMENTED = frozenset(op['name'] for op in CATALOG.values()
                        if op['channel']=='model' and op['name']!='figures_select')


def clean(value, root, key=''):
    if any(part in key.lower() for part in ('password','secret','api_key','authorization','database_url','connection_string')) or key in ('executor_config','origin_path'):
        return '[redacted]'
    if isinstance(value, dict):
        return {str(k):clean(v,root,str(k)) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [clean(v,root,key) for v in value]
    if isinstance(value,str):
        value=value.replace(str(root),'[workspace]').replace(Path(root).as_posix(),'[workspace]')
        value=re.sub(r'(?i)postgres(?:ql)?://\S+', '[redacted]', value)
        if re.search(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]',value) or value.startswith(('\\\\','/')) and key.endswith(('path','folder','source')):
            return '[local-path]'
        return value
    if isinstance(value,(uuid.UUID,date,datetime)):
        return str(value)
    return value


def envelope(operation, request_id=None):
    return {'contract_version':VERSION,'operation':operation,'request_id':request_id,
            'status':'ok','binding':{},'phase':None,'replayed':False,'pending':[],
            'artifacts':[],'data':None,'chunk':None,'error':None,'receipt':None}


def failure(operation, code, request_id=None, *, unknown=False):
    response=envelope(operation,request_id)
    policy=load_contract()['errors'][code]
    response.update(status='outcome_unknown' if unknown else 'error',
                    error={'code':code,'message':policy['description'],'recovery':policy['recovery']})
    return response


def scope_for(operation,args,w):
    if operation=='project_create':
        return {'project_id':args['body']['id']}
    if operation=='task_create':
        return {'project_id':args['project_id'],'task_id':args['body']['id']}
    if args.get('task_id'):
        project=w.task(args['task_id'])['project_id']
        if args.get('project_id') and project!=args['project_id']:
            raise BusinessContractError('not_found','Task is outside requested project')
        return {'project_id':project,'task_id':args['task_id'],**{k:args[k] for k in ('run_id',) if k in args}}
    return {k:args[k] for k in ('project_id','run_id','build_id') if k in args}


def resource_for(scope):
    if scope.get('task_id'):
        return 'task:'+scope['task_id']
    return 'project:'+scope['project_id']


def legacy_domain(operation, scope):
    if operation in ('task_revise','task_restore','references_retrieve','references_discuss','mathematics_publish'):
        return 'actions:'+scope['task_id']
    for operations,prefix,key in [
        (('modeling_start','modeling_recheck'),'modeling','task_id'),
        (('hand_start',),'hands','task_id'),
        (('assembly_start','assembly_rebind'),'assembly-inputs','project_id'),
        (('assembly_compose',),'assembly-builds','project_id'),
        (('references_retrieve',),'references','task_id'),
        (('references_discuss',),'discussions','task_id'),
        (('mathematics_publish',),'mathematics','task_id')]:
        if operation in operations:
            return prefix+':'+scope[key]
    return None


class BusinessAdapter:
    def __init__(self, workflow_factory=None, *, root=None, fault=None):
        from .config import ROOT
        self.root=Path(root or ROOT).resolve()
        self.workflow_factory=workflow_factory
        self.fault=fault  # In-process tests only, never a CLI/model-controlled option.

    def workflow(self):
        if self.workflow_factory:
            return self.workflow_factory()
        from .workflow import Workflow
        return Workflow()

    def capabilities(self):
        from .coder_repair import host_policy
        standing=host_policy() is not None
        return {'contract_version':VERSION,'transport':'stdio','sdk_baseline':'mcp==1.30.0',
                'protocol_baseline':'2025-11-25','operations':sorted(IMPLEMENTED),
                'unavailable':{name:('requires_trusted_local_channel' if op['channel']!='model' else 'not_implemented') for name,op in CATALOG.items() if name not in IMPLEMENTED},
                'host_autonomy':{'coder_repairs':'standing' if standing else 'bounded',
                    'entrypoint':'hand_advance','renewal_required':not standing,
                    'modeling_proposal_submission':{'entrypoint':'modeling_start','argument':'proposal_files','source':'workspace path and sha256; current model/math binding; preserved prepared authorship; independent M1 required'},
                    'contract_revision_submission':{'entrypoint':'task_revise','argument':'revision_files','sources':'contract_path/contract_sha256 and math_package_path/math_package_sha256; workspace only'},
                    'code_revision_submission':{'entrypoint':'hand_advance','argument':'code_revision','origin':'dsh_submitted_coder_revision','source':'workspace path and sha256; previous code sha256; rationale','first_full_source':'GENERATE_FULL with accepted P1 and no prior full source/job; previous hash is accepted minimal source; no delegated repair required'},
                    'scope':'coding implementation within approved model; Docker; independent P1/P2; explicit artifact confirmations retained'},
                'authoritative_state':'PostgreSQL and existing Workflow',
                'user_confirmation':'trusted local CLI and DSH native human-command/private-pipe capture; local OS trust boundary',
                'trusted_decision_entrypoint':'python -m modelcrew.trusted_decisions review',
                'trusted_decision_operations':['task_decide','hand_decide','assembly_decide'],
                'trusted_capture_channels':['trusted_local_cli','trusted_host_ui'],
                'host_integration':'DSH 0.2.2-rc.1 local stdio adapter verified; check live connection in host; G5 pending',
                'unknown_outcome':'query original operation; never auto redispatch'}

    def invoke(self, name, request):
        if name not in CATALOG:
            raise BusinessContractError('unsupported_operation','Unknown business operation')
        request_id=request.get('request_id') if isinstance(request,dict) else None
        # Malformed request IDs must not contaminate the stable error envelope.
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}',request_id):
            request_id=None
        row=None
        try:
            validate_request(request)
            if request['operation']!=name:
                raise BusinessContractError('invalid_request','Tool and operation differ')
            if name not in IMPLEMENTED:
                raise BusinessContractError('unsupported_operation','Operation is unavailable in the model channel')
            if name=='capabilities_read':
                response=envelope(name);response['data']=self.capabilities();return validate_response(response)
            with self.workflow() as w:
                store=BusinessStore(w.db);registry=ArtifactRegistry(w,self.root)
                args=request['arguments']
                self._ensure_targets(w,name,args)
                if not CATALOG[name]['mutating']:
                    return validate_response(self._read(w,store,registry,name,args))
                scope=scope_for(name,args,w);resource=resource_for(scope)
                with ExitStack() as locks:
                    locks.enter_context(w.lock('business:'+resource))
                    # Reuse core lock ordering. Project assembly lock precedes any
                    # core sorted task locks; task locks are session-reentrant.
                    locks.enter_context(w.lock(scope['task_id'] if 'task_id' in scope else 'assembly:'+scope['project_id']))
                    row=store.get(scope,name,request['request_id'])
                    if row:
                        if row['request_sha256']!=request_digest(request):
                            raise BusinessContractError('idempotency_conflict','Same request ID has different arguments')
                        replay=store.replay(row)
                        if replay:
                            return validate_response(replay)
                        return validate_response(self._unknown(row))
                    unresolved=store.unresolved(resource)
                    if unresolved:
                        response=failure(name,'outcome_unknown',request_id,unknown=True)
                        response['data']={'blocked_by_operation':unresolved['operation'],'original_request_id':unresolved['request_id']}
                        return validate_response(response)
                    # All safe preflight validation is before a durable claim.
                    if request.get('expected_binding') is not None:
                        check_binding(w,{**args,'_modeling':name=='modeling_recheck'},request['expected_binding'])
                    prepared=self._prepare(w,registry,name,args,scope)
                    if name=='hand_advance' and args.get('code_revision'):prepared['_revision_request_id']=request_id
                    domain=legacy_domain(name,scope)
                    self._check_legacy(w,name,scope,request_id)
                    row=store.claim(scope,name,request_id,request_digest(request),request,resource,domain)
                    if self.fault:
                        self.fault('after_claim',row)
                    row=store.save(row,'dispatched')
                    try:
                        value=self._dispatch(w,name,prepared)
                        if self.fault:
                            self.fault('after_core',row)
                        response=self._response(w,registry,name,prepared,value,request_id)
                        response['receipt']={**store.receipt(row),'state':'succeeded'}
                        validate_response(response)
                        row=store.save(row,'succeeded',response)
                        # Only receipt-free content is hashed; replay regenerates
                        # the receipt deterministically from the stored response.
                        response['receipt']=store.receipt(row)
                        if self.fault:
                            self.fault('after_save',row)
                        return validate_response(response)
                    except BaseException as exc:
                        # A process kill cannot run this handler; the committed
                        # dispatched record still fences every future request.
                        if isinstance(exc,(KeyboardInterrupt,SystemExit)):
                            raise
                        LOG.warning('Business dispatch outcome unresolved (%s)',type(exc).__name__)
                        # A completed immutable receipt is never downgraded if
                        # the response transport fails after save.
                        current=store.get(scope,name,request_id)
                        if current['state']=='succeeded':
                            return validate_response(store.replay(current))
                        # A matching durable terminal rejection is a known failure,
                        # even when the core raises instead of returning a response.
                        if name in ('modeling_start','assembly_compose','assembly_export','assembly_review_w2'):
                            try:
                                self._reconcile(w,store,registry,current)
                            except (BusinessContractError,ValueError,OSError,RuntimeError):
                                pass
                            current=store.get(scope,name,request_id)
                            if current['state'] in ('failed','succeeded'):
                                return validate_response(store.replay(current))
                        row=store.save(current,'outcome_unknown')
                        return validate_response(self._unknown(row))
        except BusinessContractError as exc:
            return validate_response(failure(name,exc.code,request_id,unknown=exc.code=='outcome_unknown'))
        except (psycopg.Error,OSError,RuntimeError):
            return validate_response(failure(name,'service_unavailable',request_id))
        except ValueError:
            return validate_response(failure(name,'workflow_conflict',request_id))
        except Exception as exc:
            LOG.warning('Business adapter failed (%s)',type(exc).__name__)
            return validate_response(failure(name,'internal_error',request_id))

    @staticmethod
    def _unknown(row):
        response=failure(row['operation'],'outcome_unknown',row['request_id'],unknown=True)
        response['binding']=row['scope'];response['receipt']=BusinessStore.receipt(row)
        response['replayed']=True
        return response

    @staticmethod
    def _ensure_targets(w,name,args):
        if name=='operation_status':
            return
        if args.get('project_id') and not w.db.execute('SELECT 1 FROM mc_projects WHERE id=%s',(args['project_id'],)).fetchone():
            raise BusinessContractError('not_found','Unknown project')
        if name=='operation_status':
            return
        if args.get('task_id'):
            task=require_row(w.db.execute('SELECT project_id FROM mc_tasks WHERE id=%s',(args['task_id'],)).fetchone())
            if args.get('project_id') and args['project_id']!=task['project_id']:
                raise BusinessContractError('not_found','Task is outside requested project')
            if args.get('version') is not None and not w.db.execute('SELECT 1 FROM mc_contracts WHERE task_id=%s AND version=%s',(args['task_id'],args['version'])).fetchone():
                raise BusinessContractError('not_found','Unknown contract version')
        if args.get('build_id'):
            require_row(w.db.execute('SELECT 1 FROM mc_assembly_builds WHERE project_id=%s AND id::text=%s',(args['project_id'],args['build_id'])).fetchone())
        if args.get('run_id'):
            if args.get('task_id'):
                table='mc_modeling_runs' if name=='modeling_recheck' else 'mc_hand_runs'
                require_row(w.db.execute(f'SELECT 1 FROM {table} WHERE task_id=%s AND id::text=%s',(args['task_id'],args['run_id'])).fetchone())
            else:
                require_row(w.db.execute('SELECT 1 FROM mc_assembly_runs WHERE project_id=%s AND id::text=%s',(args['project_id'],args['run_id'])).fetchone())

    def _check_legacy(self,w,name,scope,request_id):
        tables={
            'references_retrieve':('mc_requests','task_id','task_id'),
            'references_discuss':('mc_requests','task_id','task_id'),
            'mathematics_publish':('mc_requests','task_id','task_id'),
            'task_revise':('mc_requests','task_id','task_id'),
            'task_restore':('mc_requests','task_id','task_id'),
            'modeling_start':('mc_modeling_runs','task_id','task_id'),
            'hand_start':('mc_hand_runs','task_id','task_id'),
            'assembly_start':('mc_assembly_runs','project_id','project_id'),
            'assembly_compose':('mc_assembly_builds','project_id','project_id')}
        if name in tables:
            table,column,key=tables[name]
            if w.db.execute(f'SELECT 1 FROM {table} WHERE {column}=%s AND request_id=%s',(scope[key],request_id)).fetchone():
                raise BusinessContractError('idempotency_conflict','Request ID is already owned by a pre-existing core request')

    def _prepare(self,w,registry,name,args,scope):
        value=copy.deepcopy(args);body=value.get('body',{})
        if name=='task_revise' and value.get('revision_files'):
            from .revision_files import resolve
            body.update(resolve(self.root,value['revision_files']))
        if name=='project_create':
            old=w.db.execute('SELECT title FROM mc_projects WHERE id=%s',(body['id'],)).fetchone()
            if old and old['title']!=body['title']:
                raise BusinessContractError('workflow_conflict','Project already has different metadata')
        elif name=='task_create':
            w.require_project(scope['project_id'])
            if w.db.execute('SELECT 1 FROM mc_tasks WHERE id=%s',(body['id'],)).fetchone():
                raise BusinessContractError('workflow_conflict','Task already exists outside this request')
            if body['executor_key']!='pending-code' or body.get('executor_config',{}):
                raise BusinessContractError('invalid_request','Production MCP requires pending-code with empty executor configuration')
        if name in ('task_revise','task_restore'):
            if w.task(scope['task_id'])['executor_key']!='pending-code':
                raise BusinessContractError('workflow_conflict','Legacy solver tasks are read-only through MCP')
            if body.get('executor_key') not in (None,'pending-code') or body.get('executor_config'):
                raise BusinessContractError('invalid_request','Model tools cannot replace execution backends')
        if 'contract' in body and body['contract'] is not None:
            contract=body['contract']
            owner={'project_id':scope['project_id'],'task_id':scope['task_id'],
                   'version':1 if name=='task_create' else w.task(scope['task_id'])['current_version']}
            for item in contract.get('inputs',[]):
                path,sha=registry.resolve_input(item['path'],owner)
                if sha!=item['sha256']:
                    raise BusinessContractError('artifact_changed','Input hash differs from registered bytes')
                item['path']=path
            validate_model(contract)
        if name=='task_revise' and body['kind']=='revise_mathematics' and body.get('contract') is not None:
            # File transport includes the unchanged contract as a verified binding,
            # not as an attempted model change. Core math-only actions omit it.
            current=require_row(w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',
                (scope['task_id'],body['version'])).fetchone())
            if not value.get('revision_files') or digest(body['contract'])!=current['sha256']:
                raise BusinessContractError('invalid_request','Math-only revisions must reuse the current contract')
            body.pop('contract')
        if name=='task_revise' and body['kind'] in ('revise_model','revise_mathematics'):
            # The core forbids dropping an existing mathematical baseline.
            # Reject deterministically before a claim can fence the task.
            from .mathematics import latest, validate_package, MathematicsError
            previous=latest(w,scope['task_id'],body['version'])
            package=body.get('math_package')
            if package is None and (previous is not None or body['kind']=='revise_mathematics'):
                raise BusinessContractError('invalid_request','Revision requires math_package; the existing mathematical baseline cannot be dropped')
            if package is not None:
                contract=body.get('contract') or require_row(w.db.execute(
                    'SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s',
                    (scope['task_id'],body['version'])).fetchone())['content']
                try:
                    validate_package(package,contract)
                except MathematicsError as exc:
                    raise BusinessContractError('invalid_request','Invalid revision mathematical package') from exc
                if body['kind']=='revise_mathematics' and previous is not None:
                    from .mathematics import classify_change
                    if classify_change(previous['content'],package)['kind']!='mathematical':
                        raise BusinessContractError('invalid_request','No mathematical semantic change')
        if name=='task_revise' and body['kind']=='revise_model':
            if body.get('contract') is None:
                raise BusinessContractError('invalid_request','Model revisions require a contract')
            current=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',
                (scope['task_id'],body['version'])).fetchone()
            if current and digest(body['contract'])==current['sha256']:
                raise BusinessContractError('invalid_request',
                    'No contract change: use revise_mathematics for a mathematics-only revision')
        if name=='task_restore':
            source=require_row(w.db.execute('SELECT content,executor_key FROM mc_contracts WHERE task_id=%s AND version=%s',(scope['task_id'],body['source_version'])).fetchone())
            if source['executor_key']!='pending-code':
                raise BusinessContractError('workflow_conflict','Cannot restore a legacy backend through MCP')
            if body['source_version']==body['version']:
                raise BusinessContractError('invalid_request','Restoration must select a different historical version')
            for item in source['content']['inputs']:
                _,sha=registry.resolve_input(item['path'],{'project_id':scope['project_id'],'task_id':scope['task_id'],'version':body['source_version']})
                if sha!=item['sha256']:raise BusinessContractError('artifact_changed','Historical input identity changed')
        if name=='hand_advance' and value.get('code_revision'):
            from .code_revision import prepare
            value['_prepared_code_revision']=prepare(w,scope['task_id'],args['run_id'],value['code_revision'])
        if name=='modeling_start' and value.get('proposal_files'):
            from .modeling_submission import prepare
            prepare(w,scope['task_id'],body['version'],value['proposal_files'],root=self.root)
        if name=='modeling_recheck':
            from .modeling_hand import validate_recheck
            from .workflow import WorkflowError
            try:validate_recheck(w,scope['task_id'],run_id=args['run_id'],**body)
            except WorkflowError as exc:
                raise BusinessContractError('workflow_conflict',str(exc)) from exc
        if name=='hand_recheck':
            from . import hand_runtime as hr
            candidate=hr.load(w,scope['task_id'],args['run_id'])
            hr.guard(w,candidate)
            hr.validate_recheck(candidate,body['rationale'])
        if name=='hand_start':
            if value['hand']=='coding':
                from .hand_runtime import assert_coding_run_available
                assert_coding_run_available(w,scope['task_id'],body['version'])
            owner={**{k:scope[k] for k in ('project_id','task_id')},'version':body['version']}
            if value['hand']=='writing':
                from .writing_handoff import prepare as prepare_writing_handoff
                # Discover only the current approved result; no arbitrary new input import.
                from .writing_handoff import resolve_confirmed_reference
                if body.get('figure_catalog'):
                    body['figure_catalog']=resolve_confirmed_reference(w,registry,scope['task_id'],body['figure_catalog'])
                if body.get('result_evidence'):
                    body['result_evidence']=[resolve_confirmed_reference(w,registry,scope['task_id'],v) for v in body['result_evidence']]
                handoff=prepare_writing_handoff(w,scope['task_id'],body['version'],body.get('figure_catalog'),body.get('result_evidence'))
                body['figure_catalog']=handoff['figure_catalog'];body['result_evidence']=handoff['result_evidence']
            else:
                if body.get('result_evidence'):body['result_evidence']=[registry.resolve_input(v,owner)[0] for v in body['result_evidence']]
                if body.get('figure_catalog'):body['figure_catalog']=registry.resolve_input(body['figure_catalog'],owner)[0]
            if body.get('sources'):
                body['sources']=[Path(registry.resolve_input(v,owner)[0]).relative_to(self.root).as_posix() for v in body['sources']]
        if name=='task_resume':
            t=w.task(scope['task_id'])
            if t['model_approved'] and not t['result_revision']:
                event=w.db.execute("SELECT payload FROM mc_events WHERE task_id=%s AND kind='model_approve' AND (payload->>'version')::int=%s ORDER BY id DESC LIMIT 1",(scope['task_id'],t['current_version'])).fetchone()
                if t['executor_key']!='pending-code' or not event or event['payload'].get('defer_execution') is not True:
                    raise BusinessContractError('workflow_conflict','MCP cannot dispatch a legacy solver backend')
        return value

    @staticmethod
    def _dispatch(w,name,args):
        a=args;b=a.get('body',{});t=a.get('task_id');p=a.get('project_id');r=a.get('run_id');build=a.get('build_id')
        if name=='hand_advance' and a.get('code_revision'):
            from .code_revision import submit
            return submit(w,t,r,a['_prepared_code_revision'],a['_revision_request_id'])
        calls={
            'project_create':lambda:w.create_project(b['id'],b['title']),
            'task_create':lambda:w.create(b['id'],b['contract'],project=p,executor_key=b['executor_key'],executor_config=b.get('executor_config',{}),math_package=b.get('math_package')),
            'modeling_start':lambda:w.run_modeling(t,**b,**({'proposal_files':a['proposal_files']} if a.get('proposal_files') else {})),
            'modeling_recheck':lambda:w.recheck_modeling(t,run_id=r,**b),
            'hand_start':lambda:w.start_hand(t,a['hand'],**b),
            'hand_advance':lambda:w.advance_hand(t,r),
            'hand_recheck':lambda:w.recheck_hand(t,r,**b),
            'task_revise':lambda:w.action(t,**b),
            'task_restore':lambda:w.action(t,**b),
            'task_resume':lambda:w.resume(t),
            'references_retrieve':lambda:w.retrieve_references(t,**b),
            'references_discuss':lambda:w.discuss_references(t,**b),
            'mathematics_publish':lambda:w.publish_mathematics(t,version=a['version'],**b),
            'assembly_start':lambda:w.start_assembly(p,**b),
            'assembly_rebind':lambda:w.rebind_assembly(p,r,**b),
            'assembly_compose':lambda:w.compose_assembly(p,r,**b),
            'assembly_export':lambda:w.export_assembly(p,build,**b),
            'assembly_render':lambda:w.render_assembly(p,build,**b),
            'assembly_review_w2':lambda:w.review_assembly_w2(p,build,**b),
            'assembly_recover':lambda:w.recover_assembly(p,build)}
        if name not in calls:
            raise BusinessContractError('unsupported_operation','Core operation is not adapted')
        return calls[name]()

    def _response(self,w,registry,name,args,value,request_id=None):
        response=envelope(name,request_id)
        target={k:args[k] for k in ('project_id','task_id','run_id','build_id') if k in args}
        if name=='project_create':
            target={'project_id':args['body']['id']}
        if name=='task_create':
            target['task_id']=args['body']['id']
        if name=='hand_start' and isinstance(value,dict):
            target['run_id']=value['run_id']
        if name in ('assembly_start','assembly_rebind') and isinstance(value,dict):
            target['run_id']=value['run_id']
        if name=='assembly_compose' and isinstance(value,dict):
            target.pop('run_id',None);target['build_id']=value['build_id']
        # Modeling run IDs are a separate table from coding/writing hand IDs.
        if name in ('modeling_start','modeling_recheck'):
            if isinstance(value,dict) and value.get('run_id'):target['run_id']=value['run_id']
            target['_modeling']=True
        response['binding']=binding(w,target)
        if name in ('task_revise','task_restore','modeling_start','modeling_recheck'):
            current=response['binding']
            current_contract=w.db.execute('SELECT content FROM mc_contracts WHERE task_id=%s AND version=%s',(current['task_id'],current['version'])).fetchone()['content']
            owner={k:current[k] for k in ('project_id','task_id','version')}
            for item in current_contract['inputs']:
                path=Path(item['path']).resolve().relative_to(self.root).as_posix()
                candidates=w.db.execute('SELECT owner FROM mc_business_artifacts WHERE path=%s AND sha256=%s AND is_input=true',(path,item['sha256'])).fetchall()
                if not any(row['owner'].get('project_id')==owner['project_id'] and row['owner'].get('task_id')==owner['task_id'] for row in candidates):
                    raise BusinessContractError('artifact_access_denied','New version references an unregistered input')
                registry.register(owner,item['path'],item['sha256'],'input',is_input=True)
        phase=None
        if isinstance(value,dict):
            phase=value.get('phase') or value.get('status') or value.get('task',{}).get('phase')
        response['phase']=phase
        response['data']=clean(self._input_refs(w,value,response['binding'],args.get('version')),self.root)
        if target.get('task_id') and isinstance(response['data'],dict):
            from .business_projection import host_review_readiness
            response['data']['host_review']=host_review_readiness(w,target['task_id'])
        if target.get('task_id') and name not in ('references_retrieve','references_discuss','mathematics_publish'):
            response['pending']=task_pending(w,registry,target['task_id'],run_id=None if name in ('modeling_start','modeling_recheck') else target.get('run_id'))
        if target.get('build_id'):
            response['pending']=assembly_pending(w,registry,target['project_id'],target['build_id'])
        if response['pending']:
            response['status']='needs_user_input'
        elif phase in ('SOLVING','started','planning','modeling','reviewing','EXPORTING','RENDERING','REVIEWING_W2','GENERATE_MINIMAL','EXECUTE_MINIMAL','REVIEW_P1','GENERATE_FULL','EXECUTE_FULL','REPRODUCE_FULL','REVIEW_P2','READY_TO_ATTACH','PLAN','DRAFT','REVIEW_W1'):
            response['status']='running'
        if phase in ('NEEDS_HUMAN','NEEDS_MODEL_REVISION','NEEDS_WRITING_REVISION','needs_human','blocked','failed','unknown','STALE_BUILD','W2_FAILED','W2_BLOCKED','W2_INVALID_RESPONSE','W2_DELIVERY_BLOCKED','W2_RECOVERY_REQUIRED','EXPORT_FAILED','RENDER_FAILED','COMPOSITION_FAILED','ASSEMBLY_REJECTED'):
            response['status']='blocked'
            policy=load_contract()['errors']['workflow_conflict']
            response['error']={'code':'workflow_conflict','message':policy['description'],'recovery':policy['recovery']}
        if isinstance(value,dict) and name=='references_retrieve' and value.get('envelope',{}).get('status')=='error':
            response['status']='error'
            policy=load_contract()['errors']['retrieval_unavailable']
            response['error']={'code':'retrieval_unavailable','message':policy['description'],'recovery':policy['recovery']}
        if phase in ('W2_FAILED','W2_BLOCKED'):
            code='review_failed' if phase=='W2_FAILED' else 'review_blocked'
            policy=load_contract()['errors'][code]
            response['error']={'code':code,'message':policy['description'],'recovery':policy['recovery']}
        if isinstance(value,dict) and value.get('task',{}).get('executor_key')=='pending-code' and not value.get('execution'):
            response['data']['mode']='pending'
        return response

    def _input_refs(self,w,value,bound,version=None):
        if not bound.get('task_id'):
            return value
        owner={k:bound[k] for k in ('project_id','task_id','version')}
        if version is not None:owner['version']=version
        rows=w.db.execute('SELECT artifact_id,path FROM mc_business_artifacts WHERE owner_sha256=%s AND is_input=true',(digest(owner),)).fetchall()
        aliases={}
        for row in rows:
            for path in (row['path'],str(self.root/row['path']),(self.root/row['path']).as_posix()):
                aliases[path]='artifact:'+row['artifact_id']
        def walk(item):
            if isinstance(item,dict):return {key:walk(child) for key,child in item.items()}
            if isinstance(item,list):return [walk(child) for child in item]
            if isinstance(item,str):return aliases.get(item,item)
            return item
        return walk(value)

    def _read(self,w,store,registry,name,args):
        response=envelope(name)
        if name=='pending_list':
            response['binding']={'project_id':args['project_id']}
            response['pending']=list_pending(w,registry,args)
            if response['pending']:response['status']='needs_user_input'
            return response
        if name=='artifact_read':
            response['binding']=args['owner'];response['chunk']=registry.read(args);return response
        if name=='operation_status':
            return self._operation_status(w,store,registry,args)
        if name in ('artifacts_list','assembly_artifacts_list'):
            if name=='artifacts_list':
                response['artifacts']=registry.task(args['task_id'],args.get('version'))
            else:
                w.require_project(args['project_id']);response['artifacts']=registry.assembly(args['project_id'],args['build_id'])
            response['binding']=binding(w,args);return response
        t=args.get('task_id');p=args.get('project_id')
        reads={
            'projects_list':lambda:w.list_projects(**args),
            'project_read':lambda:w.require_project(p),
            'tasks_list':lambda:w.list_tasks(p,**{k:args[k] for k in ('limit','offset') if k in args}),
            'task_status':lambda:w.inspect(t),
            'versions_list':lambda:w.versions(t),
            'version_read':lambda:w.version_dossier(t,args['version']),
            'proposal_read':lambda:w.inspect(t),
            'result_read':lambda:w.inspect(t),
            'modeling_status':lambda:w.modeling_status(t),
            'hand_status':lambda:w.hand_status(t,args['run_id']),
            'assembly_status':lambda:w.assembly_status(p,args['run_id']),
            'assembly_build_status':lambda:w.assembly_build_status(p,args['build_id']),
            'mathematics_read':lambda:w.mathematical_proposal(t,args['version']),
            'tool_evidence_read':lambda:w.tool_evidence(t,args.get('version'))}
        if name not in reads:
            raise BusinessContractError('unsupported_operation','Read operation is not adapted')
        return self._response(w,registry,name,args,reads[name]())

    def _operation_status(self,w,store,registry,args):
        operation=args['operation_name'];original={k:args[k] for k in ('project_id','task_id','run_id','build_id') if k in args}
        if operation=='project_create':
            scope={'project_id':args['project_id']}
        elif operation=='task_create':
            if not args.get('task_id'):
                raise BusinessContractError('invalid_request','Task creation lookup requires its target task ID')
            scope={k:args[k] for k in ('project_id','task_id')}
        else:
            scope=scope_for(operation,original,w)
        if operation!='project_create':w.require_project(scope['project_id'])
        if 'task_id' in scope and operation!='task_create':
            if w.task(scope['task_id'])['project_id']!=args['project_id']:
                raise BusinessContractError('not_found','Operation is outside requested project')
        resource=resource_for(scope)
        with w.lock('business:'+resource):
            row=require_row(store.get(scope,operation,args['request_id']))
            try:
                current=self._current_status(w,row)
            except (BusinessContractError,ValueError,OSError,RuntimeError):
                current={'status_unavailable':True,'business_stage_advanced':False}
            if row['state'] in ('claimed','dispatched','outcome_unknown'):
                try:
                    self._reconcile(w,store,registry,row,current=current)
                except (BusinessContractError,ValueError,OSError,RuntimeError):
                    current={**current,'reconciliation_blocked':True}
                row=store.get(scope,operation,args['request_id'])
            response=envelope('operation_status',args['request_id']);response['binding']=scope
            response['receipt']=store.receipt(row)
            response['data']={'original_status':row['response']['status'] if row.get('response') else 'outcome_unknown',
                              'response':row.get('response'),'current':current}
            return response

    def _current_status(self,w,row):
        name=row['operation'];scope=row['scope']
        if name in ('modeling_start','modeling_recheck'):
            value={'modeling_runs':w.modeling_status(scope['task_id'])}
        elif scope.get('task_id') and scope.get('run_id'):
            value=w.hand_status(scope['task_id'],scope['run_id'])
            if name=='hand_advance':
                native=require_row(w.db.execute('SELECT payload,phase,version FROM mc_hand_runs WHERE task_id=%s AND id::text=%s',(scope['task_id'],scope['run_id'])).fetchone())
                phase=native['phase'];p=native['payload']
                if phase in ('EXECUTE_MINIMAL','EXECUTE_FULL','REPRODUCE_FULL'):
                    stage='minimal' if phase=='EXECUTE_MINIMAL' else 'full'
                    key=stage+'-'+str(p['attempt'])+('-replica' if phase=='REPRODUCE_FULL' else '')
                    saved=p.get('jobs',{}).get(key)
                    if saved and saved.get('dispatched'):
                        job_id='hand-'+scope['run_id'].replace('-','')+'-'+key
                        # Append a read-only status trace. This path can never
                        # invoke code_execute or advance a hand to another stage.
                        from .mcp_workflow import trace_call
                        try:
                            _,receipt=trace_call(w,scope['task_id'],native['version'],'code-executor','code_execution_status',{'run_id':job_id},'business-status:'+row['request_sha256'])
                            value={**value,'execution_status':receipt,'business_stage_advanced':False}
                        except Exception:
                            value={**value,'execution_status_unavailable':True,'business_stage_advanced':False}
        elif scope.get('task_id'):
            value=w.inspect(scope['task_id']) if w.db.execute('SELECT 1 FROM mc_tasks WHERE id=%s',(scope['task_id'],)).fetchone() else {'exists':False}
        elif scope.get('build_id'):
            value=w.assembly_build_status(scope['project_id'],scope['build_id'])
        elif scope.get('run_id'):
            value=w.assembly_status(scope['project_id'],scope['run_id'])
        else:
            value=w.db.execute('SELECT id,title FROM mc_projects WHERE id=%s',(scope['project_id'],)).fetchone() or {'exists':False}
        return clean(value,self.root)

    def _reconcile(self,w,store,registry,row,*,current=None):
        # Reconciliation only reads durable core facts. It never calls a command,
        # resumes a graph or resends a provider/executor request.
        name=row['operation'];args=row['request']['arguments'];scope=row['scope'];value=None
        if name in ('task_decide','hand_decide','assembly_decide'):
            from .trusted_decisions import reconcile_decision
            reconcile_decision(self,w,store,registry,row)
            return
        if name=='modeling_start':
            with w.lock(scope['task_id']):
                self._reconcile_planning_failure(w,store,row)
                current_row=store.get(scope,name,row['request_id'])
                if current_row['state'] in ('claimed','dispatched','outcome_unknown'):
                    self._reconcile_completed_review(w,store,registry,current_row)
            return
        if name=='assembly_review_w2':
            self._reconcile_w2_failure(w,store,row)
            return
        if name=='assembly_export':
            self._reconcile_export(w,store,registry,row)
            return
        if name=='assembly_compose':
            self._reconcile_composition(w,store,registry,row)
            return
        if name=='project_create':
            p=w.db.execute('SELECT id,title FROM mc_projects WHERE id=%s',(scope['project_id'],)).fetchone()
            if p and p['title']==args['body']['title']:value=p
        elif name=='task_create':
            t=w.db.execute('SELECT * FROM mc_tasks WHERE id=%s AND project_id=%s',(scope['task_id'],scope['project_id'])).fetchone()
            if t:
                prepared=self._prepare_existing_contract(registry,args,scope)
                c=w.db.execute('SELECT sha256,executor_key,executor_config FROM mc_contracts WHERE task_id=%s AND version=1',(scope['task_id'],)).fetchone()
                if c and c['sha256']==digest(prepared['body']['contract']) and c['executor_key']=='pending-code' and not c['executor_config']:
                    value=w.inspect(scope['task_id'])
        elif name in ('task_revise','task_restore'):
            saved=w.db.execute('SELECT response FROM mc_requests WHERE task_id=%s AND request_id=%s',(scope['task_id'],row['request_id'])).fetchone()
            if saved:value=w.inspect(scope['task_id'])
            elif name=='task_revise':
                from .business_recovery import recover_unchanged_contract
                try:recover_unchanged_contract(w,scope['task_id'],row['request_id'],apply=True,root=self.root)
                except (ValueError,BusinessContractError,OSError):pass
                return
        elif name=='hand_start':
            saved=w.db.execute('SELECT id FROM mc_hand_runs WHERE task_id=%s AND request_id=%s',(scope['task_id'],row['request_id'])).fetchone()
            if saved:value=w.hand_status(scope['task_id'],str(saved['id']))
        elif name=='hand_advance':
            # An immutable core phase transition after our durable claim proves
            # the bounded stage completed. Merely seeing a new checkpoint or a
            # cached provider filename never suffices.
            before=w.db.execute('SELECT id,phase,payload FROM mc_hand_events WHERE run_id=%s AND created_at<%s ORDER BY id DESC LIMIT 1',(scope['run_id'],row['created_at'])).fetchone()
            after=w.db.execute('SELECT id,phase,payload FROM mc_hand_events WHERE run_id=%s AND created_at>=%s ORDER BY id DESC LIMIT 1',(scope['run_id'],row['created_at'])).fetchone()
            if before and after and current and current.get('phase')==after['phase'] and after['phase']!='PROVIDER_UNKNOWN':
                if before['phase']!=after['phase'] or before['payload'].get('attempt')!=after['payload'].get('attempt'):
                    value=current
            # A known executor response on an already dispatched job also makes
            # the call outcome inspectable. A future advance still uses the
            # core's status-only branch for this same frozen job.
            execution=(current or {}).get('execution_status',{})
            if execution.get('status')=='ok' and execution.get('data',{}).get('status') in ('running','succeeded','code_error','timeout','memory_limit','output_limit','unsafe_artifact'):
                value=current
        if value is not None:
            response=self._response(w,registry,name,args,value,row['request_id'])
            response['receipt']={**store.receipt(row),'state':'succeeded'}
            validate_response(response)
            store.save(row,'succeeded',response)

    def _reconcile_w2_failure(self,w,store,row):
        """Settle a completed invalid answer, preserving its verdict and raw bytes."""
        from .assembly_w2 import W2Request
        from .collaboration import workspace_path,sha_file
        req=row['request'];args=req['arguments'];scope=row['scope']
        if (req['operation']!='assembly_review_w2' or req['request_id']!=args['body']['request_id']
                or row['request_sha256']!=request_digest(req) or row['scope_sha256']!=digest(scope)
                or scope!={k:args[k] for k in ('project_id','build_id')}
                or row['resource_key']!='project:'+scope['project_id']):return
        normalized=W2Request.model_validate(args['body']).model_dump(exclude_none=True)
        with w.lock('assembly:'+scope['project_id']):
            native=w.db.execute('SELECT * FROM mc_assembly_builds WHERE project_id=%s AND id=%s',
                (scope['project_id'],scope['build_id'])).fetchone()
            if not native or native['phase']!='W2_INVALID_RESPONSE':return
            p=native['payload'];op=p.get('w2_reviews',{}).get(req['request_id'],{})
            if (op.get('phase')!='INVALID_RESPONSE' or op.get('request')!=normalized
                    or op.get('request_sha256')!=digest(normalized) or not op.get('validation_error')):return
            event=w.db.execute('SELECT * FROM mc_assembly_build_events WHERE build_id=%s ORDER BY id DESC LIMIT 1',
                (native['id'],)).fetchone()
            if (not event or event['created_at']<row['created_at'] or event['phase']!=native['phase']
                    or event['payload']!=p):return
            base=workspace_path(self.root,op['folder']);meta=op.get('provider_metadata',{})
            if (meta.get('status')!='completed' or meta.get('http_status')!=200
                    or meta.get('finish_reason')!='stop'):return
            paths={'answer':base/'answer.json','packet':base/'packet.json',
                   'response':base/('W2-'+meta['call_id']+'-response.json'),
                   'metadata':base/('W2-'+meta['call_id']+'-metadata.json')}
            hashes={}
            for key,path in paths.items():
                relative=path.relative_to(self.root).as_posix()
                if not path.is_file() or sha_file(path)!=p.get('sealed',{}).get(relative):return
                hashes[key]=sha_file(path)
            if hashes['answer']!=op.get('answer_sha256') or hashes['packet']!=op.get('packet_sha256') or hashes['response']!=meta.get('response_sha256'):return
            read=lambda path:json.loads(path.read_text(encoding='utf-8'))
            raw=read(paths['response']);answer=read(paths['answer'])
            if (read(paths['metadata'])!=meta or raw['choices'][0].get('finish_reason')!='stop'
                    or json.loads(raw['choices'][0]['message']['content'])!=answer
                    or answer.get('status')!=op.get('reviewer_reported_status')):return
            response=failure('assembly_review_w2','workflow_conflict',req['request_id'])
            response.update(binding=scope,phase='W2_INVALID_RESPONSE',data={
                'recovery_kind':'persisted_w2_invalid_response','terminal_event_id':event['id'],
                'validation_error':clean(op['validation_error'],self.root),
                'reviewer_reported_status':op.get('reviewer_reported_status'),
                'evidence_hashes':hashes,'original_request_sha256':row['request_sha256'],
                'no_redispatch':True,'recheck_consumed':False})
            response['receipt']={**store.receipt(row),'state':'failed'}
            validate_response(response);store.save(row,'failed',response)

    def _reconcile_export(self,w,store,registry,row):
        """Resolve only an exact, durable failed export; never rerun the exporter."""
        from .assembly_builds import ExportRequest
        req=row['request'];args=req['arguments'];scope=row['scope']
        if (req['operation']!='assembly_export' or req['request_id']!=args['body']['request_id']
                or row['request_sha256']!=request_digest(req) or row['scope_sha256']!=digest(scope)
                or scope!={k:args[k] for k in ('project_id','build_id')}
                or row['resource_key']!='project:'+scope['project_id']):return
        normalized=ExportRequest.model_validate(args['body']).model_dump(mode='json')
        with w.lock('assembly:'+scope['project_id']):
            native=w.db.execute('SELECT * FROM mc_assembly_builds WHERE project_id=%s AND id=%s',
                (scope['project_id'],scope['build_id'])).fetchone()
            if not native or native['phase']!='EXPORT_FAILED':return
            entry=native['payload'].get('exports',{}).get(req['request_id'],{})
            if (entry.get('phase')!='EXPORT_FAILED' or entry.get('request_sha256')!=digest(normalized)
                    or not isinstance(entry.get('error'),str) or not entry['error']):return
            event=w.db.execute('SELECT * FROM mc_assembly_build_events WHERE build_id=%s ORDER BY id DESC LIMIT 1',
                (native['id'],)).fetchone()
            if (not event or event['created_at']<row['created_at'] or event['phase']!=native['phase']
                    or event['payload']!=native['payload']):return
            response=failure('assembly_export','workflow_conflict',req['request_id'])
            response.update(binding=scope,phase='EXPORT_FAILED',data={
                'failure':{'message':clean(entry['error'],self.root)},'output':entry.get('output'),
                'recovery_kind':'persisted_export_failure','terminal_event_id':event['id'],
                'original_request_sha256':row['request_sha256'],'no_redispatch':True})
            response['receipt']={**store.receipt(row),'state':'failed'}
            validate_response(response);store.save(row,'failed',response)

    def _reconcile_composition(self,w,store,registry,row):
        """Only a matching immutable terminal build event can resolve composition."""
        from .assembly_builds import ComposeRequest
        req=row['request'];args=req['arguments'];scope=row['scope']
        if (req['operation']!='assembly_compose' or req['request_id']!=args['body']['request_id']
                or row['request_sha256']!=request_digest(req) or row['scope_sha256']!=digest(scope)
                or scope!={k:args[k] for k in ('project_id','run_id')}
                or row['resource_key']!='project:'+scope['project_id']):return
        with w.lock('assembly:'+scope['project_id']):
            native=w.db.execute('SELECT * FROM mc_assembly_builds WHERE project_id=%s AND request_id=%s',
                (scope['project_id'],req['request_id'])).fetchone()
            normalized=ComposeRequest.model_validate(args['body']).model_dump(mode='json')
            if (not native or str(native['assembly_run_id'])!=scope['run_id'] or native['created_at']<row['created_at']
                    or native['payload'].get('request')!=normalized
                    or native['request_sha256']!=digest({'assembly_run_id':scope['run_id'],'request':normalized})):return
            event=w.db.execute('SELECT * FROM mc_assembly_build_events WHERE build_id=%s ORDER BY id DESC LIMIT 1',
                (native['id'],)).fetchone()
            if (not event or event['created_at']<row['created_at'] or event['phase']!=native['phase']
                    or event['payload']!=native['payload']):return
            if native['phase']=='COMPOSITION_FAILED':
                problem=native['payload'].get('failure',{})
                if native['payload'].get('source_ready') or not all(isinstance(problem.get(k),str) and problem[k] for k in ('kind','message')):return
                response=failure('assembly_compose','workflow_conflict',req['request_id'])
                response.update(binding={**scope,'build_id':str(native['id'])},phase='COMPOSITION_FAILED',data={
                    'build_id':str(native['id']),'failure':clean(problem,self.root),'recovery_kind':'persisted_composition_failure',
                    'terminal_event_id':event['id'],'original_request_sha256':row['request_sha256'],'no_redispatch':True})
                state='failed'
            elif native['phase']=='WAITING_ASSEMBLY_REVIEW' and native['payload'].get('source_ready'):
                value=w.assembly_build_status(scope['project_id'],str(native['id']))
                if value.get('issues') or value['phase']!='WAITING_ASSEMBLY_REVIEW':return
                response=self._response(w,registry,'assembly_compose',args,value,req['request_id']);state='succeeded'
            else:return
            response['receipt']={**store.receipt(row),'state':state}
            validate_response(response);store.save(row,state,response)

    def _reconcile_planning_failure(self,w,store,row):
        """Prove a terminal planning rejection, without resending or deleting history."""
        request=row['request'];args=request['arguments'];body=args['body'];scope=row['scope']
        if (row['request_sha256']!=request_digest(request) or args['task_id']!=scope['task_id']
                or request['request_id']!=body['request_id']):
            return
        saved=w.db.execute('SELECT * FROM mc_modeling_runs WHERE task_id=%s AND request_id=%s',
            (scope['task_id'],row['request_id'])).fetchone()
        if saved is None or saved['status']!='failed' or saved['created_at']<row['created_at']:
            return
        p=saved['payload']
        if (saved['base_version']!=body['version'] or saved['version']!=body['version']
                or saved['actor']!=body['actor'] or saved['guidance']!=body['guidance']
                or p.get('failure_domain')!='model_output_or_validation'
                or p.get('attempts') or p.get('snapshot_sha256') or p.get('receipt_sha256')
                or not p.get('calls') or any(c.get('stage')!='planning' or c.get('status')!='completed' for c in p['calls'])
                or any(c.get('stage')!='planning' or c.get('status')!='completed' for c in p.get('call_attempts',[]))):
            return
        fingerprint=digest({'version':body['version'],'actor':body['actor'],
            'guidance':body['guidance'],'auto_correct':body.get('auto_correct',True)})
        if body.get('question_reference') is not None:
            references=w.question_context(**body['question_reference'])
            fingerprint=digest({'base':fingerprint,'question_references':references})
        if saved['request_sha256']!=fingerprint:
            return
        event=w.db.execute('SELECT status,payload FROM mc_modeling_events WHERE run_id=%s ORDER BY sequence DESC LIMIT 1',
            (saved['id'],)).fetchone()
        if not event or event['status']!='failed' or digest(event['payload'])!=digest(p):
            return
        response=failure('modeling_start','workflow_conflict',row['request_id'])
        response['binding']={**scope,'version':body['version']}
        response['data']={'recovery_kind':'terminal_planning_validation_failure',
            'run_id':str(saved['id']),'status':'failed','failure_type':p.get('failure_type'),
            'failure_domain':p['failure_domain'],'payload_sha256':digest(p),
            'original_request_sha256':row['request_sha256'],
            'independent_M1_started':False,'user_approval':'not_granted',
            'next_action':'Correct planning output and use a new modeling_start request ID.'}
        response['receipt']={**store.receipt(row),'state':'failed'}
        validate_response(response)
        store.save(row,'failed',response)

    def _reconcile_completed_review(self,w,store,registry,row):
        """A terminal validation failure with a delivered review is not unknown."""
        request=row['request'];args=request['arguments'];body=args['body'];scope=row['scope']
        if (row['request_sha256']!=request_digest(request) or args['task_id']!=scope['task_id']
                or request['request_id']!=body['request_id']):return
        saved=w.db.execute('SELECT * FROM mc_modeling_runs WHERE task_id=%s AND request_id=%s',
            (scope['task_id'],row['request_id'])).fetchone()
        if saved is None or saved['status']!='failed' or saved['created_at']<row['created_at']:return
        p=saved['payload']
        if (saved['base_version']!=body['version'] or saved['version']!=body['version']
                or saved['actor']!=body['actor'] or saved['guidance']!=body['guidance']
                or p.get('failure_domain')!='model_output_or_validation'
                or p.get('failure_type') not in ('ValueError','ValidationError','KeyError','TypeError')
                or not p.get('snapshot_sha256') or p.get('receipt_sha256')):return
        recorded_attempts=p.get('call_attempts',[])
        if (not any(c.get('stage')=='M1' and c.get('status')=='completed' and c.get('http_status')==200
                    and c.get('finish_reason')=='stop' and c.get('response_sha256') for c in recorded_attempts)
                or any(c.get('status')!='completed' for c in recorded_attempts)):return
        fingerprint=digest({'version':body['version'],'actor':body['actor'],
            'guidance':body['guidance'],'auto_correct':body.get('auto_correct',True)})
        if body.get('question_reference') is not None:
            fingerprint=digest({'base':fingerprint,'question_references':w.question_context(**body['question_reference'])})
        if fingerprint!=saved['request_sha256']:return
        event=w.db.execute('SELECT status,payload FROM mc_modeling_events WHERE run_id=%s ORDER BY sequence DESC LIMIT 1',
            (saved['id'],)).fetchone()
        if not event or event['status']!='failed' or digest(event['payload'])!=digest(p):return
        from .modeling_hand import recover_completed_modeling_review
        try:
            value=recover_completed_modeling_review(w,scope['task_id'],str(saved['id']))
        except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
            response=failure('modeling_start','workflow_conflict',row['request_id'])
            response['binding']={**scope,'version':body['version']}
            response['data']={'recovery_kind':'terminal_delivered_review_validation_failure',
                'run_id':str(saved['id']),'status':'failed','failure_type':p['failure_type'],
                'independent_M1_started':True,'validation_error':clean(str(exc)[:2000],self.root),
                'user_approval':'not_granted','no_model_call':True}
            response['receipt']={**store.receipt(row),'state':'failed'}
            validate_response(response);store.save(row,'failed',response)
        else:
            response=self._response(w,registry,'modeling_start',args,value,row['request_id'])
            response['receipt']={**store.receipt(row),'state':'succeeded'}
            validate_response(response);store.save(row,'succeeded',response)

    @staticmethod
    def _prepare_existing_contract(registry,args,scope):
        result=copy.deepcopy(args)
        for item in result['body']['contract'].get('inputs',[]):
            item['path'],sha=registry.resolve_input(item['path'],{**scope,'version':1})
            if sha!=item['sha256']:
                raise BusinessContractError('artifact_changed','Original input changed')
        return result
