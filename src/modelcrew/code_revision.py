"""Exact Coder source transport; approved fresh runs or already granted repairs.

Initial source uses an all-zero previous hash only on an untouched minimal attempt.
Neither path approves a model, spends/replenishes repair quotas, or skips P1/P2.
"""
import ast
import hashlib
import uuid
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from . import hand_runtime as hr
from .coder_repair import grant,host_policy
from .business_artifacts import read_verified
from .config import ROOT
from .contracts import digest
from .collaboration import sha_file,workspace_path
from .workflow import WorkflowError


class Revision(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    stage:Literal['minimal','full']
    code_path:str=Field(min_length=1,max_length=2000)
    code_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    previous_code_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    rationale:str=Field(min_length=1,max_length=20000)



def prepare(w,task,run_id,value):
    """Read and compile bytes before durable business dispatch. Never execute source."""
    req=Revision(**value)
    if not req.rationale.strip():raise WorkflowError('Coder revision rationale required')
    row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload']
    stage=req.stage
    if (row['hand']!='coding' or row['phase']!=('GENERATE_MINIMAL' if stage=='minimal' else 'GENERATE_FULL')
            or p.get('attached') or w.task(task)['result_revision']):
        raise WorkflowError('Coder revision requires an unclaimed generation stage')
    previous=p.get(stage+'_code_path') or p.get('minimal_code_path')
    initial=(stage=='minimal' and p['attempt']==0 and p.get('retries')==0
             and not previous and not p.get('ops') and not p.get('jobs')
             and not p.get('reviews') and req.previous_code_sha256=='0'*64)
    prepared_full=(stage=='full' and not p.get('full_code_path')
                   and not any(k.startswith('full-') for k in p.get('jobs',{}))
                   and bool(p.get('minimal_code_path')))
    if not initial and not prepared_full:
        permission=grant(row);active=p.get('active_delegated_repair',{})
        if (not permission or active.get('attempt')!=p['attempt'] or active.get('stage')!=stage
                or active.get('authorization_id')!=permission[0]):
            raise WorkflowError('Coder revision requires a claimed delegated repair attempt')
        if permission[1].get('host_policy') and host_policy()!=permission[1]['host_policy']:
            raise WorkflowError('Standing host permission is no longer active')
    if not initial and (not previous or sha_file(workspace_path(ROOT,previous))!=req.previous_code_sha256):
        raise WorkflowError('Coder revision previous code hash differs')
    if 'code-'+stage+'-'+str(p['attempt']) in p.get('ops',{}):
        raise WorkflowError('Generation already claimed; do not replace an in-flight provider operation')
    if stage=='full':
        accepted=p.get('reviews',{}).get(p.get('accepted_reviews',{}).get('P1'))
        if not accepted or accepted['status']!='PASS':raise WorkflowError('Full revision requires accepted independent P1')
        store=hr.CollaborationStore(hr.run_folder(row)/'records')
        receipt=store.load(hr.Receipt,accepted['receipt_sha256'])
        if store.accept_review(receipt,accepted['snapshot_sha256'])!=accepted['receipt_sha256']:
            raise WorkflowError('Full revision P1 receipt differs')
    data,size=read_verified(ROOT,req.code_path,req.code_sha256,limit=256*1024)
    if not 1<=size<=256*1024:raise WorkflowError('Coder revision source must be at most 256 KiB')
    code=data.decode('utf-8')
    if not code.strip():raise WorkflowError('Empty Coder revision')
    try:
        ast.parse(code);compile(code,'<dsh-coder-revision>','exec',dont_inherit=True)
    except (SyntaxError,ValueError) as exc:
        raise WorkflowError('Coder revision is not complete compilable Python') from exc
    return {'revision':req.model_dump(),'code':code,'attempt':p['attempt'],'binding':p['binding'],'initial_prepared_source':initial,'prepared_full_source':prepared_full}


def submit(w,task,run_id,prepared,request_id):
    """Caller holds task lock. Install only the verified preflight snapshot."""
    row=hr.load(w,task,run_id);hr.guard(w,row);p=row['payload']
    req=Revision(**prepared['revision']);key=uuid.uuid5(uuid.UUID(str(row['id'])),request_id).hex
    fingerprint=digest(req.model_dump())
    prior=p.get('coder_code_revisions',{}).get(request_id)
    if prior:
        if prior['request_sha256']!=fingerprint:raise WorkflowError('Coder revision idempotency conflict')
        return hr.status(w,task,run_id)
    if p['attempt']!=prepared['attempt'] or p['binding']!=prepared['binding']:
        raise WorkflowError('Coder revision state changed after preflight')
    initial=prepared.get('initial_prepared_source',False)
    if initial and (req.stage!='minimal' or row['phase']!='GENERATE_MINIMAL'
            or p['attempt']!=0 or p.get('retries')!=0 or p.get('ops') or p.get('jobs')
            or p.get('reviews') or p.get('minimal_code_path') or p.get('full_code_path')
            or p.get('attached') or req.previous_code_sha256!='0'*64):
        raise WorkflowError('Initial prepared source is no longer unclaimed')
    prepared_full=prepared.get('prepared_full_source',False)
    if prepared_full:
        current=prepare(w,task,run_id,req.model_dump())
        if not current['prepared_full_source'] or current['code']!=prepared['code']:
            raise WorkflowError('Prepared full source state changed after preflight')
    exact_source=initial or prepared_full
    code=prepared['code']
    if hashlib.sha256(code.encode('utf-8')).hexdigest()!=req.code_sha256:
        raise WorkflowError('Coder revision snapshot changed')
    stage=req.stage;folder=hr.run_folder(row);target=folder/(stage+'-revision-'+key+'.py')
    if not target.exists():target.write_bytes(code.encode('utf-8'))
    if sha_file(target)!=req.code_sha256:raise WorkflowError('Coder revision artifact differs')
    record={'request':req.model_dump(),'request_sha256':fingerprint,'request_id':request_id,
        'binding':p['binding'],'attempt':p['attempt'],'automatic_retries':p['retries'],
        'code_path':hr.rel(target),'origin':'prepared_coder_source' if exact_source else 'dsh_submitted_coder_revision',
        'call_id':'coder-revision-'+key,'context_id':str(uuid.uuid5(uuid.UUID(key),'coder-context')),
        'delegated_repair':None if exact_source else p['active_delegated_repair'],
        'scope':'Coder revision only; actual Docker execution and new independent P1/P2 required; no user approval'}
    if exact_source:record.update(provider_call=False,content_rewritten=False)
    manifest=folder/('coder-code-revision-'+key+'.json')
    if not manifest.exists():hr.write(manifest,record)
    if hr.read(manifest)!=record:raise WorkflowError('Coder revision manifest differs')
    hr.seal(row,target);hr.seal(row,manifest);hr.author(row,record)
    p.setdefault('coder_code_revisions',{})[request_id]=record
    p[stage+'_code']=code;p[stage+'_code_path']=hr.rel(target)
    p.setdefault('ops',{})['code-'+stage+'-'+str(p['attempt'])]=record
    if stage=='minimal':p['accepted_reviews']={}
    else:
        p['accepted_reviews'].pop('P2',None)
        from .deviation_acceptance import archive_author_visual_evidence
        archive_author_visual_evidence(row,'Full code/export revised; preserve old observations but require fresh actual PDF views.')
        for name in ('full_packet','replica_packet','figure_check','figure_catalog'):p.pop(name,None)
    p['review_pointer_protocol']='exact-v1'
    hr.save(w,row,'EXECUTE_MINIMAL' if stage=='minimal' else 'EXECUTE_FULL')
    return hr.status(w,task,run_id)
