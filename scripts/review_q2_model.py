"""Codex-authored Q2 model + actual independent M1 admission; no solver dispatch."""
import argparse,json,uuid,shutil
from pathlib import Path
from psycopg.types.json import Jsonb
from modelcrew.config import ROOT
from modelcrew.contracts import digest,validate
from modelcrew.mathematics import validate_package
from modelcrew.writing_hand import read,new,rel
from modelcrew.collaboration import Call,Binding,Artifact,Snapshot,Receipt,CollaborationStore,sha_file,REQUIRED_CHECKS
from modelcrew.modeling_hand import M1Answer,pointer,update,assert_m1
from scripts.run_d4_full import workflow

TASK='d6-bench-q2-20261109'
SOURCE=ROOT/'stage-d/q2-modeling/proposal-v5'
REF=ROOT/'stage-d/runs/references/d6-q1-to-q2-20261109-v2'

def prepare(folder,revision_of=None):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    c=read(SOURCE/'contract.json');p=read(SOURCE/'mathematics.json');validate(c);validate_package(p,c)
    with workflow() as w:
        context=w.question_context(**read(REF/'resume-request.json'))
        prior=w.db.execute('SELECT * FROM mc_tasks WHERE id=%s',(TASK,)).fetchone()
        if prior:
            if revision_of is None or prior['model_approved']:raise ValueError('Explicit failed-run revision required')
            if read(Path(revision_of)/'M1-admission.json')['status']!='FAIL':raise ValueError('Revision requires admitted independent FAIL')
            w.action(TASK,actor='codex-modeling-hand',request_id='Q2-M1-rework-'+digest(c)[:24],version=prior['current_version'],kind='revise_model',contract=c,math_package=p,reason='独立M1定向返工：统一板孔距ell_k与后把手L_i索引，并校正新增假设来源。')
        else:w.create(TASK,c,project='stage-d6-second-question',executor_key='pending-code',math_package=p)
        t=w.task(TASK);version=t['current_version'];assert not t['model_approved'] and not t['result_approved'] and t['execution_id'] is None
        author=Call(call_id='codex-Q2-model-'+uuid.uuid4().hex,context_id='codex-Q2-modeling-'+uuid.uuid4().hex,role='modeling',binding=Binding(task_id=TASK,contract_version=version,contract_sha256=digest(c)))
        store=CollaborationStore(folder/'records');store.register_call(author)
        step=folder/'attempt-0';step.mkdir()
        for name in ['contract.json','mathematics.json','model-design.json','numerical-policy.json','方案审阅.md']:shutil.copyfile(SOURCE/name,step/name)
        proposal={'text':(step/'方案审阅.md').read_text(encoding='utf-8-sig'),'questions':[],'explicit_new_assumptions_pending_user_approval':['whole adjacent-pair exemption','filled-hole outer rectangles','first nonadjacent contact stops'],'not_user_approval':True}
        new(step/'proposal.json',proposal)
        graph=[{'id':'Q2','scope':c['problem']['scope'],'conclusion_type':'certified_first_contact_interval_and_terminal_state','depends_on':['Q1_confirmed_kinematics_only']}]
        new(step/'task_graph.json',graph)
        source_paths=['resources/algorithms/index.md','resources/algorithms/numerical-geometry.md','stage-d/runs/full/full-ed1a97c89d2c4aa3a4a2298a44a8ce77/geometry-provenance.json','stage-d/d6/question2-statement.json']
        sources={'selected_category':'geometry','selection_rationale':'矩形凸几何与连续事件，不能强行当全局优化；内置索引没有现成连续碰撞证明','read_sources':[{'path':s,'sha256':sha_file(ROOT/s),'read_scope':'full text'} for s in source_paths],'mathematical_support':'SAT由凸多边形分离轴原理与矩形投影公式直接推导；区间方案为条件性实现设计，不伪称已有数值证书','references_context':context,'revision_of':rel(revision_of) if revision_of else None,'new_solver_runs':0,'new_model_API_calls':0,'author_type':'Codex modeling hand, no supplier-generation claim'}
        new(step/'sources.json',sources)
        original={'problem':c['problem'],'input_hashes':c['inputs'],'confirmed_previous_question_references':context,'scope':'actual source-read evidence, Q2 no inherited approvals'}
        new(folder/'original-evidence.json',original);new(step/'original.json',original)
        artifacts=[]
        for name,kind,path in [('contract','contract','contract.json'),('mathematics','mathematics','mathematics.json'),('proposal','method_selection','proposal.json'),('design','method_selection','model-design.json'),('sources','source','sources.json'),('original','source','original.json'),('task_graph','task_graph','task_graph.json'),('policy','source','numerical-policy.json')]:
            target=step/path;artifacts.append(Artifact(artifact_id=name,kind=kind,path=rel(target),sha256=sha_file(target),author_call_ids=[author.call_id]))
        key=store.freeze(Snapshot(binding=author.binding,hand='modeling',artifacts=artifacts,lineage_call_ids=[author.call_id]))
        run_id=str(uuid.uuid4());payload={'folder':rel(folder),'attempts':[],'calls':[author.model_dump(mode='json')],'snapshot_sha256':key,'math_package_sha256':digest(p),'authoring':'Codex-authored Q2 proposal; no new model API call','source_reference_ids':read(REF/'resume-request.json')['reference_ids']}
        with w.db.transaction():
            w.db.execute('INSERT INTO mc_modeling_runs(id,task_id,base_version,version,request_id,request_sha256,actor,guidance,status,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(run_id,TASK,version,version,'user-Q2-model-design-M1-v'+str(version),digest({'request':'进入碰撞模型设计与独立M1审查','contract':digest(c)}),'user-authorized-codex-modeling','进入碰撞模型设计与独立M1审查','reviewing',Jsonb(payload)))
            w.db.execute('INSERT INTO mc_modeling_events(run_id,status,payload) VALUES(%s,%s,%s)',(run_id,'reviewing',Jsonb(payload)))
        new(folder/'run.json',{'run_id':run_id,'task_id':TASK,'contract_version':version,'contract_sha256':digest(c),'author':author.model_dump(mode='json'),'snapshot_sha256':key,'payload':payload})
        new(folder/'M1-context.json',{'snapshot_sha256':key,'required_checks':REQUIRED_CHECKS['M1'],'evidence':{a.artifact_id:a.path for a in artifacts},'response_schema':M1Answer.model_json_schema(),'read_only':True,'scope':'Q2 pre-solve model design; independent M1 not execution verification or user model approval','proposal_markdown':rel(step/'方案审阅.md')})
    print(json.dumps({'task':TASK,'snapshot_sha256':key,'model_approved':False,'solver_runs':0}))

def dispatch(folder,reviewer):
    meta=read(folder/'run.json');store=CollaborationStore(folder/'records')
    call=Call(call_id='M1-agent-'+reviewer,context_id='independent-agent-'+reviewer,role='quality',binding=Call.model_validate(meta['author']).binding)
    store.register_call(call);ticket=store.dispatch_review(meta['snapshot_sha256'],'M1',call.call_id)
    new(folder/'M1-dispatch.json',{'reviewer_agent_id':reviewer,'reviewer_call_id':call.call_id,'ticket_sha256':ticket,'snapshot_sha256':meta['snapshot_sha256'],'fork_turns':'none','read_only':True})
    print(json.dumps({'ticket_sha256':ticket}))

def admit(folder):
    meta=read(folder/'run.json');version=meta['contract_version'];context=read(folder/'M1-context.json');packet=read(folder/'M1-dispatch.json');answer=M1Answer.model_validate(read(folder/'M1-response.json'))
    for c in answer.checks:
        for proof in c.evidence:
            if proof.artifact_id not in context['evidence']:raise ValueError('Unknown M1 evidence')
            pointer(read(ROOT/context['evidence'][proof.artifact_id]),proof.selector)
    status='FAIL' if any(c.status=='FAIL' for c in answer.checks) else ('BLOCKED' if any(c.status=='BLOCKED' for c in answer.checks) else 'PASS')
    if answer.status!=status:raise ValueError('M1 aggregate mismatch')
    receipt=Receipt(ticket_sha256=packet['ticket_sha256'],reviewer_call_id=packet['reviewer_call_id'],status=status,checks=answer.checks,issues=answer.issues)
    store=CollaborationStore(folder/'records');key=store.accept_review(receipt,meta['snapshot_sha256'])
    admission={'status':status,'receipt_sha256':key,'snapshot_sha256':meta['snapshot_sha256'],'raw_response_sha256':sha_file(folder/'M1-response.json'),'reviewer_agent_id':packet['reviewer_agent_id'],'independent_context':True,'semantic_findings_modified':False,'user_approval':False}
    new(folder/'M1-admission.json',admission)
    payload=meta['payload'];payload.update(receipt_sha256=key)
    payload['attempts'].append({'status':status,'version':version,'snapshot_sha256':meta['snapshot_sha256'],'receipt_sha256':key,'proposal_path':rel(folder/'attempt-0/方案审阅.md'),'author_call_id':meta['author']['call_id'],'review_call_id':packet['reviewer_call_id']})
    with workflow() as w:
        update(w,meta['run_id'],'ready' if status=='PASS' else 'needs_human',payload,version)
        entry=w.record_entry(TASK,version=version,kind='proposal',actor='codex-modeling-hand',request_id='Q2-model-'+key[:20],text='第二题碰撞模型方案；独立M1='+status+'；相邻豁免、填孔外包络、首接触即停为新增假设，尚待用户确认。',artifacts=[{'path':rel(folder/'M1-admission.json'),'sha256':sha_file(folder/'M1-admission.json'),'role':'Q2_independent_M1'},{'path':rel(folder/'attempt-0/方案审阅.md'),'sha256':sha_file(folder/'attempt-0/方案审阅.md'),'role':'Q2_pending_model_proposal'}],metadata={'modeling_run_id':meta['run_id'],'M1_status':status,'user_approval':False})
        t=w.task(TASK);assert not t['model_approved'] and not t['result_approved'] and t['execution_id'] is None
        if status=='PASS':assert_m1(w,t)
        new(folder/'registration.json',{'entry':entry,'task_id':TASK,'version':version,'phase':t['phase'],'independent_M1':status,'model_approved':False,'result_approved':False,'execution':None})
    print(json.dumps({'M1':status,'receipt_sha256':key,'model_approved':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('step',choices=['prepare','dispatch','admit']);p.add_argument('--run',type=Path,required=True);p.add_argument('--reviewer-id');p.add_argument('--proposal',type=Path);p.add_argument('--revision-of',type=Path);a=p.parse_args()
    if a.proposal:SOURCE=a.proposal.resolve()
    if a.step=='prepare':prepare(a.run,a.revision_of)
    elif a.step=='dispatch':dispatch(a.run,a.reviewer_id)
    else:admit(a.run)
