"""Explicit immutable E input rebinding for editorial context changes only.

Historical W1 and user decisions are checked under their sealed original policy;
current composition/export still require current policy and separate user decisions.
"""
from contextlib import ExitStack
import hashlib
import json
import uuid
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb
from . import assembly_runtime as ar
from . import hand_runtime as hands
from .collaboration import sha_file, workspace_path
from .contracts import digest
from .modeling_paper import writing_context
from .workflow import WorkflowError
from .writing_reviews import review_status


class RebindRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)
    expected_previous_context: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_current_context: str = Field(pattern=r'^[0-9a-f]{64}$')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def context_delta(old, new):
    """Reject scientific/procedural changes; allow the bounded editorial schema."""
    left = {d['path']:d for d in old['documents']}
    right = {d['path']:d for d in new['documents']}
    changed = sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))
    editorial = {'resources/paper/writer-instructions.md',
                 'resources/paper/chinese-modeling-policy.json'}
    for name in changed:
        if name not in editorial and not name.startswith('resources/paper/reference/'):
            raise WorkflowError('Non-editorial context change requires upstream review: '+name)
        if name not in right:
            raise WorkflowError('Context removal is not an editorial rebind: '+name)
    # Only the global notation rule was added to the policy. Figure, language,
    # evidence and review requirements must remain identical.
    policy = 'resources/paper/chinese-modeling-policy.json'
    a = json.loads(left[policy]['text']); b = json.loads(right[policy]['text'])
    for value in (a,b):
        value.pop('policy_version',None); value.pop('symbol_table',None)
    if a != b:
        raise WorkflowError('Substantive paper policy changed; upstream review required')
    a = dict(old['workflow']); b = dict(new['workflow'])
    for value in (a,b):
        for key in ('workflow_version','must_load','layout_requirements'):value.pop(key,None)
    if a != b:
        raise WorkflowError('Workflow gates or scientific requirements changed')
    return [{'path':k,'previous_sha256':left.get(k,{}).get('sha256'),
             'current_sha256':right.get(k,{}).get('sha256')} for k in changed]


def chapter_context(payload, chapter):
    """Resolve only original context documents through the sealed E snapshot."""
    indexed = {i['source']:i for i in payload['files'] if i['question_id']==chapter['question_id']}
    name = f"stage-d/runs/runtime/{chapter['run_id']}/writer-context.json"
    item = indexed.get(name)
    if item is None:raise WorkflowError('Frozen Writer context is missing')
    path = workspace_path(ar.ROOT,item['snapshot'])
    if sha_file(path)!=item['sha256']:raise WorkflowError('Historical writer context changed')
    context = read(path)
    allowed = {}
    for doc in context['documents']:
        item = indexed.get(doc['path'])
        if item is None:raise WorkflowError('Frozen context document is missing: '+doc['path'])
        source = workspace_path(ar.ROOT,item['snapshot'])
        if (item['sha256']!=doc['sha256'] or sha_file(source)!=doc['sha256'] or
                source.read_text(encoding='utf-8')!=doc['text']):
            raise WorkflowError('Historical document identity mismatch')
        allowed[doc['path']] = item
    return {'context':context,'files':allowed}


def historical_state(w, chapter, evidence):
    row = hands.load(w,chapter.task_id,chapter.run_id)
    hands.guard(w,row,historical_context=evidence)
    p = row['payload']; base = hands.run_folder(row)
    # The context supplied by the caller must be this run's sealed context.
    original = read(base/'writer-context.json')
    if original != evidence['context']:raise WorkflowError('Wrong historical Writer context')
    policy = next(d['sha256'] for d in original['documents']
                  if d['path']=='resources/paper/chinese-modeling-policy.json')
    rs = review_status(ar.ROOT/p['manuscript'],base/'figure-catalog.json',
                       p.get('manuscript_review'),p.get('figure_review'),
                       historical_policy_sha256=policy)
    return {'hand':row['hand'],'phase':row['phase'],'binding':p['binding'],'reviews':rs,
            'manuscript_sha256':sha_file(ar.ROOT/p['manuscript']),
            'figure_catalog_sha256':sha_file(base/'figure-catalog.json')}


def rebind(w, project, previous_run_id, **kwargs):
    req = RebindRequest.model_validate(kwargs)
    with ExitStack() as locks:
        locks.enter_context(w.lock('assembly:'+project)); w.require_project(project)
        previous = ar.load(w,project,previous_run_id); old = previous['payload']
        for task in sorted(c['task_id'] for c in old['chapters']):locks.enter_context(w.lock(task))
        identity = digest({'previous_run_id':str(previous['id']),'request':req.model_dump()})
        existing = w.db.execute('SELECT * FROM mc_assembly_runs WHERE project_id=%s AND request_id=%s',
                                (project,req.request_id)).fetchone()
        if existing:
            if existing['request_sha256']!=identity:raise WorkflowError('Rebind request ID reused with different inputs')
            return ar.status(w,project,str(existing['id']))
        base = ar.folder(previous_run_id)
        for name,key in [('input-manifest.json','manifest_sha256'),('writer-context.json','context_sha256')]:
            if sha_file(base/name)!=old[key]:raise WorkflowError('Previous binding evidence changed')
        before = read(base/'writer-context.json'); current = writing_context()
        if digest(before)!=req.expected_previous_context or digest(current)!=req.expected_current_context:
            raise WorkflowError('Explicit context hashes do not match; inspect new context before rebinding')
        delta = context_delta(before,current)
        for item in old['files']:
            if sha_file(workspace_path(ar.ROOT,item['snapshot']))!=item['sha256']:
                raise WorkflowError('Frozen source changed: '+item['source'])
        for chapter in old['chapters']:
            spec = ar.ChapterInput.model_validate({k:chapter[k] for k in ('question_id','task_id','run_id','source_project_id')})
            now = ar.approved_chapter(w,spec,project,historical_context=chapter_context(old,chapter))
            if now!=chapter:raise WorkflowError('Scientific source or historical approval identity changed: '+chapter['question_id'])
        run_id = str(uuid.uuid4()); target = ar.folder(run_id); target.mkdir(parents=True,exist_ok=False)
        ar.write_once(target/'writer-context.json',current)
        frozen = []
        for item in old['files']:
            data = workspace_path(ar.ROOT,item['snapshot']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=item['sha256']:raise WorkflowError('Source changed during rebind')
            dest = (target/'snapshot'/item['question_id']/item['source']) if old.get('snapshot_layout')=='per_question' else (target/'snapshot'/item['source']); dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():dest.write_bytes(data)
            elif sha_file(dest)!=item['sha256']:raise WorkflowError('Conflicting shared evidence')
            frozen.append({**item,'snapshot':ar.relative(dest)})
        payload = {**old,'run_id':run_id,'request':req.model_dump(),'files':frozen,
                   'context_sha256':sha_file(target/'writer-context.json'),'context_identity':digest(current),
                   'workflow_sha256':current['workflow_sha256'],'combined_manuscript_approved':False,'W2':'NOT_RUN',
                   'context_rebinding':{'previous_run_id':str(previous['id']),
                      'previous_manifest_sha256':old['manifest_sha256'],
                      'previous_context_identity':digest(before),'current_context_identity':digest(current),
                      'actor':req.actor,'reason':req.reason,'document_changes':delta,
                      'scientific_inputs_unchanged':True,'current_approvals_inherited':False},
                   'scope':'Editorial context rebind; historical W1 only, no new scientific, manuscript, figure or W2 approval.'}
        payload.pop('manifest_sha256',None)
        payload['update_impact']={'changed_questions':[],'preserved_questions':sorted(c['question_id'] for c in old['chapters']),
                                 'invalidated_products':['build','W2'],'solver_rerun_started':False}
        ar.write_once(target/'input-manifest.json',payload); payload['manifest_sha256']=sha_file(target/'input-manifest.json')
        w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',
                     (run_id,project,req.request_id,identity,Jsonb(payload)))
        return ar.status(w,project,run_id)
