"""Locally authorized Coder repair through ordinary hand_advance, with separate budget.

Models can consume a sealed grant, never create/extend one or approve results.
Generated source still executes only in Docker and passes independent P1/P2.
"""
import uuid
from pydantic import BaseModel,ConfigDict,Field
from . import hand_runtime as hr
from .contracts import digest
from .collaboration import sha_file,workspace_path
from .config import ROOT
from .workflow import WorkflowError


class Authorization(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    version:int=Field(ge=1)
    actor:str=Field(min_length=1,max_length=200)
    request_id:str=Field(min_length=1,max_length=200,pattern=r'^[A-Za-z0-9_.-]+$')
    statement:str=Field(min_length=1,max_length=2000)
    max_repairs:int|None=Field(default=3,ge=1,le=3)



def failure_stage(p):
    if p.get('coding_failure_stage') in ('minimal','full'):return p['coding_failure_stage']
    last=p.get('last_review',{})
    if last.get('attempt')==p['attempt'] and last.get('gate') in ('P1','P2'):
        return 'minimal' if last['gate']=='P1' else 'full'
    return 'full' if any(k.startswith('full-') for k in p.get('jobs',{})) else 'minimal'

def authorize(w,task,run_id,**kwargs):
    """Trusted local only. Exact current user permission is captured by the host."""
    req=Authorization(**kwargs)
    if req.max_repairs is None:raise WorkflowError('Standing permission must come from host configuration')
    if not req.actor.strip() or not req.statement.strip():raise WorkflowError('Explicit local user permission required')
    with w.lock('business:task:'+task),w.lock(task):
        from .business_store import BusinessStore
        if BusinessStore(w.db).unresolved('task:'+task):raise WorkflowError('Resolve unknown business operation before authorization')
        row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload'];fingerprint=digest(req.model_dump())
        prior=p.get('coder_repair_authorizations',{}).get(req.request_id)
        if prior:
            if prior['request_sha256']!=fingerprint:raise WorkflowError('Authorization idempotency key conflict')
            return hr.status(w,task,run_id)
        if (req.version!=row['version'] or row['hand']!='coding' or row['phase']!='NEEDS_HUMAN'
                or p.get('retries')!=3 or p.get('failure_domain')!='implementation'
                or p.get('rework_target')!='coding' or p.get('attached') or w.task(task)['result_revision']):
            raise WorkflowError('Authorization requires current exhausted coding implementation failure')
        if p.get('active_coder_repair_authorization'):
            raise WorkflowError('Preserve current authorization; extending the repair budget requires separate review')
        return _register(w,row,req)


def _register(w,row,req,policy=None):
    """Caller holds task lock; immutable old grants and uses are retained."""
    p=row['payload'];fingerprint=digest(req.model_dump())
    stage=failure_stage(p)
    previous=p.get(stage+'_code_path') or p.get('minimal_code_path')
    math=(hr.read(hr.run_folder(row)/'mathematics.json') or {}).get('content') or {}
    planned=len(math.get('figures',[]))
    contract=hr.read(hr.run_folder(row)/'contract.json')
    # Account for every frozen candidate's PNG/PDF/SVG plus declared outputs/catalog.
    full_max_files=full_file_capacity(p['request']['limits'],planned,len(contract['outputs']))
    record=dict(request=req.model_dump(),request_sha256=fingerprint,task_id=row['task_id'],run_id=str(row['id']),
                binding=p['binding'],source_attempt=p['attempt'],source_sha256=sha_file(workspace_path(ROOT,previous)),
                allowed_stages=['minimal','full'],full_max_files=full_max_files,planned_figures=planned,origin='host_standing_authorization' if policy else 'trusted_local_user_authorization',
                scope='Coder generation and sandbox execution only; preserve contract/tolerances and automatic retries; new independent P1/P2 required; no user approval')
    if policy:record['host_policy']=policy
    path=hr.run_folder(row)/('coder-repair-authorization-'+uuid.uuid5(uuid.UUID(str(row['id'])),req.request_id).hex+'.json')
    if not path.exists():hr.write(path,record)
    if hr.read(path)!=record:raise WorkflowError('Authorization evidence differs')
    hr.seal(row,path)
    p.setdefault('coder_repair_authorizations',{})[req.request_id]=dict(path=hr.rel(path),sha256=sha_file(path),request_sha256=fingerprint)
    p['active_coder_repair_authorization']=req.request_id
    p.setdefault('coder_repair_uses',[])
    hr.save(w,row)
    return hr.status(w,row['task_id'],str(row['id']))

def grant(row):
    p=row['payload'];key=p.get('active_coder_repair_authorization')
    if not key:return None
    entry=p.get('coder_repair_authorizations',{}).get(key)
    if not entry:raise WorkflowError('Missing Coder authorization evidence')
    path=workspace_path(ROOT,entry['path'])
    if sha_file(path)!=entry['sha256']:raise WorkflowError('Coder authorization bytes changed')
    record=hr.read(path)
    if (record['request_sha256']!=entry['request_sha256'] or digest(record['request'])!=entry['request_sha256']
            or record['task_id']!=row['task_id'] or record['run_id']!=str(row['id'])
            or record['binding']!=p['binding']):raise WorkflowError('Coder authorization binding changed')
    Authorization(**record['request'])
    return key,record


def host_policy():
    """Trusted local settings, never model-supplied tool arguments; read on every step."""
    from .config import load_settings
    policy=load_settings()['autonomy']
    if policy['coder_repairs']!='standing':return None
    if not policy['statement'].strip():raise WorkflowError('Standing host permission requires user statement')
    return dict(mode='standing',statement=policy['statement'],scope='coding_implementation_only')


def ensure_host_grant(w,row):
    p=row['payload']
    if (row['hand']!='coding' or row['phase']!='NEEDS_HUMAN' or p.get('retries')!=3
            or p.get('failure_domain')!='implementation' or p.get('rework_target')!='coding'
            or p.get('attached') or w.task(row['task_id'])['result_revision']):return
    policy=host_policy()
    if not policy:return
    value=grant(row)
    if value and value[1].get('host_policy')==policy:return
    from .business_store import BusinessStore
    # The caller's own dispatched hand_advance is not an unresolved earlier operation.
    fence=BusinessStore(w.db).unresolved('task:'+row['task_id'])
    if fence and (fence.get('state')!='dispatched' or fence.get('operation')!='hand_advance'):raise WorkflowError('Resolve unknown business operation before repair')
    req=Authorization(version=row['version'],actor='trusted-host-standing-policy',
        request_id='host-standing-'+digest(policy)[:20]+'-'+str(p['attempt']),
        statement=policy['statement'],max_repairs=None)
    _register(w,row,req,policy)


def summary(row):
    value=grant(row)
    if not value:return None
    key,record=value;used=sum(x['authorization_id']==key for x in row['payload'].get('coder_repair_uses',[]))
    return dict(authorization_id=key,max_repairs=record['request']['max_repairs'],used=used,
                remaining=None if record['request']['max_repairs'] is None else max(0,record['request']['max_repairs']-used),
                mode='standing' if record.get('host_policy') else 'bounded',channel='hand_advance',
                author='Coder',execution='Docker',independent_review_required=True)


def begin(w,row):
    """Caller holds task lock. Claim one repair before any provider operation."""
    ensure_host_grant(w,row)
    p=row['payload'];value=grant(row)
    if not value or row['phase']!='NEEDS_HUMAN' or row['hand']!='coding':return False
    key,record=value
    if (p.get('retries')!=3 or p.get('failure_domain')!='implementation' or p.get('rework_target')!='coding'
            or p.get('attached') or w.task(row['task_id'])['result_revision']):return False
    uses=p.get('coder_repair_uses',[]);used=sum(x['authorization_id']==key for x in uses)
    if record.get('host_policy') and host_policy()!=record['host_policy']:return False
    if record['request']['max_repairs'] is not None and used>=record['request']['max_repairs']:return False
    stage=failure_stage(p)
    if stage not in record['allowed_stages']:raise WorkflowError('Coder stage not authorized')
    if not used:
        source=p.get(stage+'_code_path') or p.get('minimal_code_path')
        if p['attempt']!=record['source_attempt'] or sha_file(workspace_path(ROOT,source))!=record['source_sha256']:
            raise WorkflowError('Coder repair source changed since authorization')
    if stage=='full':
        accepted=p.get('reviews',{}).get(p.get('accepted_reviews',{}).get('P1'))
        if not accepted or accepted['status']!='PASS':raise WorkflowError('Full repair requires accepted independent P1')
        store=hr.CollaborationStore(hr.run_folder(row)/'records')
        receipt=store.load(hr.Receipt,accepted['receipt_sha256'])
        if store.accept_review(receipt,accepted['snapshot_sha256'])!=accepted['receipt_sha256']:
            raise WorkflowError('Full repair P1 binding differs')
    use=dict(authorization_id=key,authorization_sha256=p['coder_repair_authorizations'][key]['sha256'],
             ordinal=used+1,stage=stage,previous_attempt=p['attempt'],attempt=p['attempt']+1,automatic_retries=p['retries'],
             origin='delegated_coder_repair',previous_feedback=p.get('feedback'),
             scope='New Coder operation, actual Docker execution, independent P1/P2; no acceptance or user approval')
    path=hr.run_folder(row)/('coder-repair-use-'+str(use['attempt'])+'.json')
    if not path.exists():hr.write(path,use)
    if hr.read(path)!=use:raise WorkflowError('Coder repair claim differs')
    hr.seal(row,path);p.setdefault('coder_repair_uses',[]).append(use)
    p['active_delegated_repair']=dict(authorization_id=key,ordinal=used+1,stage=stage,attempt=use['attempt'])
    p['attempt']=use['attempt']
    if stage=='minimal':p['accepted_reviews']={}
    else:
        p['accepted_reviews'].pop('P2',None)
        for name in ('full_packet','replica_packet','figure_check','figure_catalog'):p.pop(name,None)
    for name in ('review_suffix','recheck_rationale','failure_domain','rework_target','error_type'):p.pop(name,None)
    p['review_pointer_protocol']='exact-v1'
    hr.save(w,row,'GENERATE_FULL' if stage=='full' else 'GENERATE_MINIMAL')
    return True


def execution_limits(row,full):
    limits=dict(row['payload']['request']['limits'])
    value=grant(row)
    if full and value:
        limits['max_files']=value[1]['full_max_files']
    return hr.Limits.model_validate(limits).model_dump()


def full_file_capacity(limits,planned_figures,declared_outputs):
    required=planned_figures*3+declared_outputs+2 if planned_figures else limits['max_files']
    value=hr.Limits.model_validate({**limits,'max_files':max(limits['max_files'],required)})
    return value.max_files
