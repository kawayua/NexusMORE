"""D5 writing-hand lifecycle: immutable W1 plan, separate reviews and durable resume.

The caller supplies authored plans/Markdown; no autonomous provider/API is claimed.
"""
import json
import os
import uuid
from pathlib import Path
from .config import ROOT
from .collaboration import (Artifact, Binding, Call, CollaborationStore, Snapshot, Receipt,
                            Ticket, REQUIRED_CHECKS, sha_file, require_tool)
from .modeling_hand import M1Answer, pointer
from .modeling_paper import writing_context, validate_draft, sha
from .writing_reviews import selection_record, manuscript_record, review_status, write_record_new


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def new(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def state_write(folder,value):
    temp=folder/('state-'+uuid.uuid4().hex+'.tmp')
    new(temp,value);os.replace(temp,folder/'state.json')
def rel(p):return Path(p).resolve().relative_to(ROOT.resolve()).as_posix()
def frozen_manifest(paths):return [{'path':rel(p),'sha256':sha_file(p)} for p in paths]
def verify_files(items):
    for item in items:
        path=(ROOT/item['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()) or sha_file(path)!=item['sha256']:raise ValueError('Writing evidence missing/changed: '+item['path'])


def assert_upstream(w,binding):
    t=w.task(binding['task_id'])
    if (t['current_version']!=binding['contract_version'] or not t['model_approved'] or not t['result_approved']
            or t['result_revision']!=binding['result_revision'] or str(t['execution_id'])!=binding['execution_id']):
        raise ValueError('Current confirmed model/result required; writing binding is stale')
    c=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(t['id'],t['current_version'])).fetchone()
    if c['sha256']!=binding['contract_sha256']:raise ValueError('Writing contract is stale')
    from .mathematics import assert_gate_binding
    assert_gate_binding(w,t,'model');assert_gate_binding(w,t,'result')


def guard(folder,w=None):
    folder=Path(folder);meta=read(folder/'run.json');verify_files(meta['inputs'])
    if meta.get('source_run'):
        from .full_result import verify_frozen_files
        source=ROOT/meta['source_run']
        if read(source/'contract.json').get('problem',{}).get('subproblem_id')=='Q2':
            from .q2_full_result import verify_q2_frozen_files
            verify_q2_frozen_files(source)
        else:verify_frozen_files(source)
        for item in read(source/'contract.json')['inputs']:
            if sha_file(item['path'])!=item['sha256']:raise ValueError('Approved original input changed')
    if writing_context()['workflow_sha256']!=meta['workflow_sha256']:raise ValueError('Writing workflow changed')
    if w is not None:assert_upstream(w,meta['binding'])
    store=CollaborationStore(folder/'records')
    store.validate_snapshot(store.load(Snapshot,meta['W1_snapshot_sha256']))
    return meta,store


def prepare(w,folder,source_run,plan,citations,*,context_id):
    """Read live approvals, hand off exact D4 evidence and freeze the pre-prose W1 plan."""
    import shutil
    from .full_result import validate_full_run,verify_frozen_files
    folder=Path(folder).resolve();source_run=Path(source_run).resolve()
    if not folder.is_relative_to(ROOT.resolve()):raise ValueError('Writing run outside workspace')
    if folder.exists():raise ValueError('Use a new writing run directory')
    # Resolve all supplied evidence before creating any new run artifacts.
    if not plan.get('claims') or not plan.get('sections'):raise ValueError('Claim-evidence plan required')
    for claim in plan['claims']:
        for proof in claim['evidence']:
            pointer(read(ROOT/proof['path']),proof['selector'])
            verify_files(proof.get('support_files',[]))
    for cite in citations['references']:
        for proof in cite['sources']:
            if sha_file(ROOT/proof['path'])!=proof['sha256']:raise ValueError('Citation source hash mismatch')
    upstream=read(source_run/'run.json')
    binding={k:upstream[k] for k in ['task_id','contract_version','contract_sha256','execution_id','result_revision']}
    assert_upstream(w,binding);validate_full_run(w,binding['task_id'],binding['contract_version'],source_run)
    source_state=read(ROOT/'stage-d/d4/current-solve.json')
    if source_state['run_dir']!=rel(source_run) or source_state['figure_selection']!='user_approved_all_nine':raise ValueError('Confirmed figure source differs')
    figure_approval_path=ROOT/source_state['figure_selection_approval'];approval=read(figure_approval_path)
    registration_path=ROOT/source_state['confirmation_registration'];registration=read(registration_path)
    if registration['approval_files']['figure-selection-approval.json']!=sha_file(figure_approval_path):raise ValueError('Figure consent receipt mismatch')
    figs=read(source_run/'figure-manifest.json')['figures']
    if sorted(approval['selected_figure_ids'])!=sorted(f['figure_id'] for f in figs):raise ValueError('Figure selection mismatch')
    if approval['binding']['execution_id']!=binding['execution_id'] or approval['binding']['result_revision']!=binding['result_revision']:raise ValueError('Figure approval binding mismatch')
    if approval['figure_manifest_sha256']!=sha_file(source_run/'figure-manifest.json'):raise ValueError('Approved figure semantics changed')
    for f in figs:
        prior=next(x for x in approval['selected_figures'] if x['figure_id']==f['figure_id'])
        if prior['file_hashes']!=f['file_hashes']:raise ValueError('Approved figure content changed')
    if not plan.get('claims') or not plan.get('sections'):raise ValueError('Claim-evidence plan required')
    folder.mkdir(parents=True);(folder/'figures').mkdir()
    context=writing_context();new(folder/'writer-context.json',context)
    new(folder/'outline.json',plan);new(folder/'citations.json',citations)
    store=CollaborationStore(folder/'records');oldstore=CollaborationStore(source_run/'records')
    for path in (oldstore.directory/'Call').glob('*.json'):store.register_call(Call.model_validate(read(path)))
    previous=None
    if plan.get('revision_of'):
        previous=ROOT/plan['revision_of'];prior_meta,prior_store=guard(previous,w)
        if read(previous/'W1-admission.json')['status'] not in ['FAIL','BLOCKED']:raise ValueError('Rework needs a failed/blocked prior W1')
        for p in (prior_store.directory/'Call').glob('*.json'):store.register_call(Call.model_validate(read(p)))
    coder=Call.model_validate(upstream['author'])
    modeler=next(Call.model_validate(read(p)) for p in (oldstore.directory/'Call').glob('*.json') if read(p)['role']=='modeling')
    author=Call(call_id=str(uuid.uuid4()),context_id=context_id,role='writing',binding=Binding.model_validate(binding))
    store.register_call(author);require_tool(author,'load_writing_context');require_tool(author,'request_W1')
    def artifact(name,kind,p,owner):return Artifact(artifact_id=name,kind=kind,path=rel(p),sha256=sha_file(p),author_call_ids=[owner.call_id])
    coding_artifacts=[artifact('contract','contract',source_run/'contract.json',modeler),artifact('execution','execution',source_run/'execution-evidence.json',coder),artifact('result','result',source_run/'result-evidence.json',coder),artifact('mathematics','mathematics',source_run/'mathematics.json',modeler),artifact('figures','figure',source_run/'figure-manifest.json',coder),artifact('numeric','input',source_run/'independent-numerics.json',coder)]
    lineage=list(dict.fromkeys(upstream['lineage_call_ids']+[modeler.call_id]+(prior_store.load(Snapshot,prior_meta['W1_snapshot_sha256']).lineage_call_ids if previous else [])))
    coding_key=store.freeze(Snapshot(binding=author.binding,hand='coding',artifacts=coding_artifacts,lineage_call_ids=lineage))
    handoff=store.handoff(coding_key,'writing',[a.artifact_id for a in coding_artifacts]);new(folder/'handoff.json',store.context(handoff,author.call_id))
    catalog=[]
    for i,f in enumerate(figs,1):
        files={}
        for fmt,path in f['files'].items():
            target=folder/'figures'/f"{f['figure_id']}.{fmt}";shutil.copyfile(ROOT/path,target)
            if sha_file(target)!=f['file_hashes'][fmt]:raise ValueError('Figure copy changed')
            files[fmt]={'path':target.relative_to(folder).as_posix(),'sha256':sha_file(target)}
        catalog.append({'id':f['figure_id'],'category':f['category'],'question_ids':['q1'],'title':f['title'],'purpose':f['evidence'],'statistics':f['statistics'],'source_kind':'confirmed_D4_'+f['category'],'formal':True,'number':i,'files':files,'limitation':'轮廓不是碰撞检验；确定性数值，不虚构置信区间。'})
    new(folder/'figure-catalog.json',{'question_ids':['q1'],'evidence':binding,'figures':catalog,'approval_origin':rel(figure_approval_path)})
    selection=selection_record(folder/'figure-catalog.json',[f['id'] for f in catalog],decision='approve',actor='user',statement=approval['user_statement'],reason='继承用户已明确通过的同一9幅图；文件与图意来自已批准清单，未更改。')
    selection['origin']={'path':rel(figure_approval_path),'sha256':sha_file(figure_approval_path),'registration_path':rel(registration_path),'registration_sha256':sha_file(registration_path)}
    new(folder/'figure-selection-review.json',selection)
    artifacts=coding_artifacts+[artifact('outline','outline',folder/'outline.json',author),artifact('citations','source',folder/'citations.json',author),artifact('writer_context','input',folder/'writer-context.json',author),artifact('figure_catalog','figure_selection',folder/'figure-catalog.json',author),artifact('figure_approval','input',figure_approval_path,author)]
    key=store.freeze(Snapshot(binding=author.binding,hand='writing',artifacts=artifacts,lineage_call_ids=lineage+[author.call_id]))
    paths=[source_run/'frozen-artifacts.json',source_run/'P2-admission.json',figure_approval_path,registration_path,ROOT/source_state['result_review_approval'],folder/'writer-context.json',folder/'figure-catalog.json',folder/'figure-selection-review.json']
    paths += [folder/asset['path'] for f in catalog for asset in f['files'].values()]
    paths += [ROOT/d['path'] for d in context['documents']]+[ROOT/'resources/paper/workflow.json']
    for cite in citations['references']:
        for proof in cite['sources']:
            path=ROOT/proof['path']
            if sha_file(path)!=proof['sha256']:raise ValueError('Citation source hash mismatch')
            paths.append(path)
    for claim in plan['claims']:
        for proof in claim['evidence']:
            path=ROOT/proof['path'];pointer(read(path),proof['selector']);paths.append(path)
            paths += [ROOT/x['path'] for x in proof.get('support_files',[])]
    if previous:paths += [previous/'W1-response.json',previous/'W1-admission.json',previous/'outline.json']
    meta={'binding':binding,'author':author.model_dump(mode='json'),'source_run':rel(source_run),'workflow_sha256':context['workflow_sha256'],'W1_snapshot_sha256':key,'inputs':frozen_manifest(sorted(set(paths))),'implementation':'Codex writing-hand author with programmatic lifecycle, no new model API calls'}
    new(folder/'run.json',meta)
    new(folder/'W1-context.json',{'snapshot_sha256':key,'binding':binding,'required_checks':REQUIRED_CHECKS['W1'],'evidence':{a.artifact_id:a.path for a in artifacts},'response_schema':M1Answer.model_json_schema(),'read_only':True,'gate_scope':'Claims/evidence/citations/outline BEFORE long prose, not W2 final layout','source_files':[{'path':x['path'],'sha256':x['sha256']} for x in meta['inputs']]})
    state_write(folder,{'phase':'WAITING_W1','manuscript_review':'pending','figure_selection':'approved_from_D4','paper_exported':False})
    return status(folder,w)


def dispatch(folder,reviewer_id,w=None):
    folder=Path(folder);meta,store=guard(folder,w)
    if (folder/'W1-dispatch.json').exists():raise ValueError('W1 already dispatched')
    reviewer=Call(call_id='W1-agent-'+reviewer_id,context_id='independent-agent-'+reviewer_id,role='quality',binding=Binding.model_validate(meta['binding']))
    store.register_call(reviewer);ticket=store.dispatch_review(meta['W1_snapshot_sha256'],'W1',reviewer.call_id)
    new(folder/'W1-dispatch.json',{'reviewer_agent_id':reviewer_id,'reviewer_call_id':reviewer.call_id,'ticket_sha256':ticket,'snapshot_sha256':meta['W1_snapshot_sha256'],'fork_turns':'none','read_only':True})
    return ticket


def admit(folder,w=None):
    folder=Path(folder);meta,store=guard(folder,w);packet=read(folder/'W1-dispatch.json')
    raw=read(folder/'W1-response.json');answer=M1Answer.model_validate(raw)
    context=read(folder/'W1-context.json')
    for check in answer.checks:
        for proof in check.evidence:
            if proof.artifact_id not in context['evidence']:raise ValueError('Unknown W1 evidence')
            pointer(read(ROOT/context['evidence'][proof.artifact_id]),proof.selector)
    status_value='FAIL' if any(c.status=='FAIL' for c in answer.checks) else ('BLOCKED' if any(c.status=='BLOCKED' for c in answer.checks) else 'PASS')
    if answer.status is not None and answer.status!=status_value:raise ValueError('Reported W1 status contradicts checks')
    receipt=Receipt(ticket_sha256=packet['ticket_sha256'],reviewer_call_id=packet['reviewer_call_id'],status=status_value,checks=answer.checks,issues=answer.issues)
    key=store.accept_review(receipt,meta['W1_snapshot_sha256'])
    admission={'status':status_value,'receipt_sha256':key,'snapshot_sha256':meta['W1_snapshot_sha256'],'reviewer_agent_id':packet['reviewer_agent_id'],'raw_response_sha256':sha_file(folder/'W1-response.json'),'independent_context':True,'semantic_findings_modified':False,'issues':[i.model_dump(mode='json') for i in answer.issues]}
    new(folder/'W1-admission.json',admission)
    current=read(folder/'state.json');current.update({'phase':'READY_TO_DRAFT' if status_value=='PASS' else 'W1_REWORK_REQUIRED','W1':status_value,'W1_receipt_sha256':key,'rework_targets':sorted(set(i.target for i in answer.issues))})
    state_write(folder,current);return admission


def require_W1(folder,w=None):
    folder=Path(folder);meta,store=guard(folder,w)
    if not (folder/'W1-admission.json').exists():raise ValueError('W1 must PASS before long prose')
    admission=read(folder/'W1-admission.json');receipt=store.load(Receipt,admission['receipt_sha256'])
    if receipt.status!='PASS' or store.accept_review(receipt,meta['W1_snapshot_sha256'])!=admission['receipt_sha256']:raise ValueError('Current independent W1 PASS required')
    if sha_file(folder/'W1-response.json')!=admission['raw_response_sha256']:raise ValueError('Original W1 reply changed')
    return meta


def publish(folder,markdown,w=None):
    folder=Path(folder);require_W1(folder,w)
    text=Path(markdown).read_text(encoding='utf-8');target=folder/'单题论文-中文审阅稿.md'
    if target.exists():raise ValueError('Preserve delivered manuscript; use a new revision')
    # Validate before publishing without creating a delivered failed draft.
    temp=folder/'author-draft.md'
    if Path(markdown).resolve()!=temp.resolve():
        with temp.open('x',encoding='utf-8') as f:f.write(text)
    report=validate_draft(temp,folder/'figure-catalog.json');new(folder/'paper-check.json',report)
    if report['status']!='passed':raise ValueError('Draft mechanical checks failed: '+str(report['findings']))
    with target.open('x',encoding='utf-8') as f:f.write(text)
    reviews=review_status(target,folder/'figure-catalog.json',None,read(folder/'figure-selection-review.json'))
    new(folder/'publication.json',{'markdown_sha256':sha(target),'catalog_sha256':sha(folder/'figure-catalog.json'),'W1_admission_sha256':sha(folder/'W1-admission.json'),'state':reviews,'paper_exported':False})
    new(folder/'reviews.json',{'review_version':'2.0.0','manuscript_review':None,'figure_selection_review':read(folder/'figure-selection-review.json')})
    current=read(folder/'state.json');current.update({'phase':'WAITING_MANUSCRIPT_APPROVAL','manuscript_review':'pending','figure_selection':reviews['figure_selection'],'can_export':False})
    state_write(folder,current);return status(folder,w)


def record_manuscript_decision(folder,*,decision,actor,statement,reason,w=None):
    folder=Path(folder);require_W1(folder,w)
    if actor!='user':raise ValueError('Only an explicit user decision can approve the manuscript')
    status(folder,w)  # Reject changed delivered bytes before accepting a user decision.
    target=folder/'单题论文-中文审阅稿.md'
    record=manuscript_record(target,folder/'figure-catalog.json',decision=decision,actor=actor,statement=statement,reason=reason)
    write_record_new(folder/'manuscript-review.json',record)
    review_bundle={'review_version':'2.0.0','manuscript_review':record,'figure_selection_review':read(folder/'figure-selection-review.json')}
    temp=folder/('reviews-'+uuid.uuid4().hex+'.tmp');new(temp,review_bundle);os.replace(temp,folder/'reviews.json')
    reviews=review_status(target,folder/'figure-catalog.json',record,read(folder/'figure-selection-review.json'))
    state_write(folder,{**read(folder/'state.json'),'phase':'READY_FOR_E_EXPORT' if reviews['can_export'] else 'MANUSCRIPT_REWORK_REQUIRED','manuscript_review':reviews['manuscript'],'can_export':reviews['can_export']})
    return reviews


def status(folder,w=None):
    folder=Path(folder);meta,_=guard(folder,w);state=read(folder/'state.json')
    if (folder/'W1-admission.json').exists():
        if read(folder/'W1-admission.json')['status']=='PASS':require_W1(folder,w)
    target=folder/'单题论文-中文审阅稿.md'
    if target.exists():
        pub=read(folder/'publication.json')
        if sha(target)!=pub['markdown_sha256'] or sha(folder/'figure-catalog.json')!=pub['catalog_sha256']:raise ValueError('Delivered writing bytes changed; new review revision required')
        mr=read(folder/'manuscript-review.json') if (folder/'manuscript-review.json').exists() else None
        state['reviews']=review_status(target,folder/'figure-catalog.json',mr,read(folder/'figure-selection-review.json'))
    return {'binding':meta['binding'],'run_dir':rel(folder),'state':state,'W1_snapshot_sha256':meta['W1_snapshot_sha256']}

def revise_publication(folder,destination,*,reason,w=None):
    """New editorial draft under the SAME admitted outline; preserve all prior bytes.

    Model, result, claims or outline changes require a new W1 plan instead.
    """
    import shutil
    folder=Path(folder).resolve();destination=Path(destination).resolve()
    if not destination.is_relative_to(ROOT.resolve()) or destination.exists():raise ValueError('Use a new workspace revision directory')
    if not reason.strip():raise ValueError('Revision reason required')
    require_W1(folder,w);status(folder,w)
    if not (folder/'publication.json').exists():raise ValueError('No prior delivered draft')
    ignored={'author-draft.md','单题论文-中文审阅稿.md','publication.json','paper-check.json','reviews.json','manuscript-review.json','authoring.json','state.json','revision.json'}
    shutil.copytree(folder,destination,ignore=lambda path,names:ignored.intersection(names) if Path(path).resolve()==folder else set())
    meta=read(destination/'run.json')
    meta['inputs'] += frozen_manifest([folder/'publication.json',folder/'单题论文-中文审阅稿.md'])
    # run.json is orchestration metadata; snapshots and prior publication remain immutable.
    temporary=destination/('run-'+uuid.uuid4().hex+'.tmp');new(temporary,meta);os.replace(temporary,destination/'run.json')
    new(destination/'revision.json',{'previous_run':rel(folder),'reason':reason,'scope':'editorial revision under unchanged W1 outline and claims','previous_manuscript_sha256':sha_file(folder/'单题论文-中文审阅稿.md'),'W1_snapshot_sha256':meta['W1_snapshot_sha256'],'manuscript_approval_carried':False})
    state_write(destination,{'phase':'READY_TO_DRAFT','W1':'PASS','W1_receipt_sha256':read(destination/'W1-admission.json')['receipt_sha256'],'manuscript_review':'pending','figure_selection':'approved_from_D4','can_export':False,'paper_exported':False})
    return status(destination,w)
