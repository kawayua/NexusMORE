"""Stage D evidence audit; never dispatches a provider call or numerical job."""
from modelcrew.project_assets import asset_path
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from psycopg.conninfo import make_conninfo
from modelcrew.config import ROOT,database_url
from modelcrew.repository_migration import resolve_repository_path
from modelcrew.workflow import Workflow
from modelcrew import writing_hand as wh
from modelcrew.collaboration import CollaborationStore,Receipt,Snapshot,Ticket
from modelcrew.modeling_hand import assert_m1
from modelcrew.mathematics import assert_gate_binding
from modelcrew.full_result import verify_frozen_files
from modelcrew.q2_full_result import verify_q2_frozen_files

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def audit(out):
    out=Path(out).resolve();out.mkdir(exist_ok=True,parents=True)
    assert out.is_relative_to(asset_path(ROOT,'stage-d/acceptance'))
    checks=[];evidence={}
    def pin(path):
        p=Path(path);p=p if p.is_absolute() else ROOT/p
        key=p.relative_to(ROOT).as_posix();p=resolve_repository_path(ROOT,key);evidence[key]=sha(p);return p
    def check(name,fn):
        value=fn();assert value is not False,name
        checks.append({'id':name,'status':'passed','details':value})
        return value
    for rel in ['AGENTS.md','modelcrew-agent-plan.md','docs/three-hand-collaboration.md','docs/d6-approved-question-references.md','stage-d/d6/requirements-update.json','resources/paper/workflow.json','resources/paper/writer-instructions.md','resources/paper/chinese-modeling-policy.json','docs/scientific-figure-contract.md','modelcrew/api.py','modelcrew/executors.py','modelcrew/writing_hand.py','modelcrew/modeling_hand.py','modelcrew/question_references.py','scripts/run_d3_minimal.py','scripts/run_d4_full.py','scripts/write_q2_paper.py']:
        pin(rel)
    for rel in ['d1','d2','d3','d4','d5','d6','q2-modeling','q2-coding','q2-full']:
        pin('stage-d/'+rel+'/acceptance-report.md')
    pointers={n:read(pin(p)) for n,p in {'q1_solve':'stage-d/d4/current-solve.json','q1_write':'stage-d/d5/current-writing.json','q2_solve':'stage-d/q2-full/current-run.json','q2_write':'stage-d/q2-full/current-writing.json','d6':'stage-d/d6/current-references.json'}.items()}
    for k in ['q1_write','q2_write']:
        folder=ROOT/pointers[k]['run_dir']
        for n in ['run.json','manuscript-review.json','figure-selection-review.json','publication.json','figure-catalog.json','单题论文-中文审阅稿.md','W1-admission.json']:pin(folder/n)
        for f in read(folder/'figure-catalog.json')['figures']:
            if f['formal']:
                for asset in f['files'].values():assert sha(pin(folder/asset['path']))==asset['sha256']
    q1=ROOT/pointers['q1_solve']['run_dir'];q2=ROOT/pointers['q2_solve']['folder']
    for label,folder,verify in [('q1',q1,verify_frozen_files),('q2',q2,verify_q2_frozen_files)]:
        result=verify(folder);manifest,files=result
        for p in files:pin(p)
        pin(folder/'frozen-artifacts.json')
        check(label+'_frozen_result_bytes',lambda files=files:{'verified_files':len(files)})
    def gate(folder,name,expected='PASS'):
        p=pin(folder/(name+'-admission.json'));a=read(p);store=CollaborationStore(folder/'records')
        r=store.load(Receipt,a['receipt_sha256']);snap=store.load(Snapshot,a['snapshot_sha256']);ticket=store.load(Ticket,r.ticket_sha256)
        assert ticket.gate==name and r.status==expected
        assert store.accept_review(r,a['snapshot_sha256'])==a['receipt_sha256']
        for kind,key in [('Receipt',a['receipt_sha256']),('Snapshot',a['snapshot_sha256']),('Ticket',r.ticket_sha256)]:pin(folder/'records'/kind/(key+'.json'))
        return {'status':expected,'receipt_sha256':a['receipt_sha256'],'snapshot_sha256':a['snapshot_sha256'],'check_count':len(r.checks),'binding':snap.binding.model_dump(mode='json')}
    for name,folder,gn in [('q1_P1',asset_path(ROOT,'stage-d/runs/coding/minimal-f3630a0b71e246b686a0017e5cd3a69b'),'P1'),('q2_P1',asset_path(ROOT,'stage-d/runs/coding/q2-minimal-027eb6ae1c3642a185725e844f745fcf'),'P1'),('q1_P2',q1,'P2'),('q2_P2',q2,'P2'),('q2_M1',asset_path(ROOT,'stage-d/runs/modeling/q2-collision-20261109-v2'),'M1'),('q1_W1',ROOT/pointers['q1_write']['run_dir'],'W1'),('q2_W1',ROOT/pointers['q2_write']['run_dir'],'W1')]:
        check(name,lambda folder=folder,gn=gn:gate(folder,gn))
    for name,folder,gn in [('M1_failure_retained',asset_path(ROOT,'stage-d/runs/modeling/q2-collision-20261109-v1'),'M1'),('W1_failure_retained',asset_path(ROOT,'stage-d/runs/writing/d5-q1-20261108-v2'),'W1')]:
        check(name,lambda folder=folder,gn=gn:gate(folder,gn,'FAIL'))
    tasks={}
    with Workflow(url=make_conninfo(database_url(),connect_timeout=5)) as w:
        for label,task in [('q1','d2-bench-q1-20261108'),('q2','d6-bench-q2-20261109')]:
            t=w.task(task)
            assert t['model_approved'] and t['result_approved'] and t['result_revision']==1
            assert_m1(w,t);assert_gate_binding(w,t,'model');assert_gate_binding(w,t,'result')
            state=wh.status(ROOT/pointers[label+'_write']['run_dir'],w=w)
            assert state['state']['reviews']['can_export']
            tasks[label]={k:str(t[k]) if k=='execution_id' else t[k] for k in ['id','current_version','model_approved','result_approved','result_revision','phase','execution_id']}
            check(label+'_durable_approvals_and_current_writing_guards',lambda state=state:state)
        d6=pointers['d6'];old_context=read(pin(ROOT/d6['run_dir']/'question-context.json'))
        fresh=w.question_context(target_id=d6['target_id'],target_revision=d6['target_revision'],reference_ids=d6['reference_ids'])
        assert fresh==old_context
        for ref in fresh['references']:
            for item in ref['source']['files']:assert sha(pin(item['path']))==item['sha256']
        check('D6_current_confirmed_source_read_and_recovery_snapshot',lambda:{'reference_ids':d6['reference_ids'],'current_context_matches_saved':True,'reference_does_not_inherit_target_approval':fresh['model_approved'] is False and fresh['result_approved'] is False,'actual_Q2_approvals_checked_separately':True})
    assembly=read(pin('stage-e/runs/q1-q2-20261109-v1/completion.json'));w2=read(pin('stage-e/runs/q1-q2-20261109-v1/W2-response.json'))
    pin('stage-e/runs/q1-q2-20261109-v1/W2-independent-review.md')
    output=ROOT/'output/paper/q1-q2-20261109-v1'
    assert w2['status']=='PASS'
    for n,h in assembly['artifacts'].items():assert sha(pin(output/n))==h and h in json.dumps(w2)
    check('E_case_W2_bound_artifacts_supplementary_not_generic_E_acceptance',lambda:{'pages':assembly['page_counts'],'figures':16,'W2':'PASS'})
    d1=read(pin(out/'d1-verification/verification.json'));assert d1['status']=='passed'
    check('D1_fresh_synthetic_admission_demo',lambda:{'checks':len(d1['checks']),'not_new_semantic_review':True})
    unchanged=all(sha(ROOT/p)==h for p,h in evidence.items());assert unchanged
    payload={'audit_version':'2.0-case-audit','created_at':datetime.now(timezone.utc).isoformat(),'checks_status':'passed','scope':'Fresh read-only existing Q1/Q2 business evidence audit; runtime closure evaluated separately','checks':checks,'live_tasks':tasks,'source_evidence_unchanged':unchanged,'evidence_files':[{'path':p,'sha256':h} for p,h in sorted(evidence.items())],'user_stage_acceptance':'pending','D6_effective_scope':'confirmed_previous_question_artifact_access'}
    (out/'case-evidence-audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':len(checks),'pinned_files':len(evidence),'source_unchanged':unchanged,'scope':'case evidence only'}))

def audit_runtime(out):
    from modelcrew import hand_runtime as hr
    out=Path(out).resolve();audit(out)
    baseline=read(out/'case-evidence-audit.json');checks=[];evidence={x['path']:x['sha256'] for x in baseline['evidence_files']}
    def pin(path):
        path=Path(path);path=path if path.is_absolute() else ROOT/path
        key=path.relative_to(ROOT).as_posix();h=sha(path)
        if key in evidence:assert evidence[key]==h,key
        evidence[key]=h;return path
    def check(name,value):
        checks.append({'id':name,'status':'passed','details':value})
    def admission(folder,stage_key,item,expected_gate):
        store=CollaborationStore(folder/'records');r=store.load(Receipt,item['receipt_sha256']);snap=store.load(Snapshot,item['snapshot_sha256']);ticket=store.load(Ticket,r.ticket_sha256)
        assert r.status=='PASS' and ticket.gate==expected_gate
        assert store.accept_review(r,item['snapshot_sha256'])==item['receipt_sha256']
        for kind,key in [('Receipt',item['receipt_sha256']),('Snapshot',item['snapshot_sha256']),('Ticket',r.ticket_sha256)]:pin(folder/'records'/kind/(key+'.json'))
        for artifact in snap.artifacts:assert sha(pin(artifact.path))==artifact.sha256
        return {'stage':stage_key,'receipt_sha256':item['receipt_sha256'],'snapshot_sha256':item['snapshot_sha256'],'independent_checks':len(r.checks)}
    integration=read(pin('stage-d/runtime-integration/20261110-v1/P1-integration-review.json'))
    latest=read(pin('stage-d/runtime-integration/writer-fix-20261110-v1/P1-review.json'))
    assert integration['status']==latest['status']=='PASS'
    stable=['modelcrew/workflow.py','modelcrew/api.py','modelcrew/__main__.py','migrations/010_hand_runtime.sql','scripts/run_hand.py','modelcrew/collaboration.py','modelcrew/modeling_hand.py','modelcrew/writing_reviews.py']
    final=['modelcrew/hand_runtime.py','modelcrew/model_client.py','tests/test_writer_transport.py','tests/test_hand_runtime.py']
    current_review={x['path']:x['sha256'] for x in latest['file_hashes']}
    for name in stable:assert sha(pin(name))==integration['source_sha256'][name],name
    for name in final:assert sha(pin(name))==current_review[name],name
    check('independent_implementation_P1_matches_current_production_and_tests',{'stable_sources':len(stable),'final_sources':len(final),'independent_reports':['integration P1','Writer fix P1'],'not_new_semantic_review':True})
    for name in ['modelcrew/hand_runtime.py','modelcrew/model_client.py','scripts/verify_hand_runtime_live.py','docs/hand-runtime.md','scripts/audit_stage_d_reacceptance.py','tests/conftest.py']:pin(name)
    with Workflow(url=make_conninfo(database_url(),connect_timeout=5)) as w:
        task='runtime-live-linear-c5004405e38e4a65b6e40efa5a901d70';rid='9bad5e1e-d114-4f18-8417-7f9cd39582cf'
        state=hr.status(w,task,rid);row=hr.load(w,task,rid);p=row['payload'];folder=hr.run_folder(row)
        assert state['phase']=='GENERATE_FULL' and p['reviews']['P1-0']['status']=='PASS'
        for path,h in p['sealed'].items():assert sha(pin(path))==h
        check('generic_Coder_real_supplier_Docker_minimal_and_independent_P1',{'state':state,'gate':admission(folder,'P1-0',p['reviews']['P1-0'],'P1'),'synthetic_engineering_task':True,'no_real_supplier_full_P2_claim':True})
        task='d2-bench-q1-20261108';rid='0c0f465a-c34a-4094-9425-3dad03fd1405'
        state=hr.status(w,task,rid);row=hr.load(w,task,rid);p=row['payload'];folder=hr.run_folder(row)
        assert state['phase']=='READY_FOR_E_EXPORT' and state['reviews']['can_export']
        for path,h in p['sealed'].items():assert sha(pin(path))==h
        stage=p['accepted_reviews']['W1'];gate=admission(folder,stage,p['reviews'][stage],'W1')
        check('generic_Writer_real_supplier_W1_and_user_dual_approval_current',{'state':state,'gate':gate,'manuscript_review':read(pin(folder/'manuscript-review.json')),'figure_review':read(pin(folder/'figures-review.json'))})
        md=ROOT/p['manuscript'];operation=folder/'operations'/('draft-'+str(p['attempt']))
        answer=read(pin(operation/'answer.json'));raw=read(pin(next(operation.glob('*-response.json'))))
        assert raw['choices'][0]['message']['content']==answer['markdown']==md.read_text(encoding='utf-8')
        report=hr.validate_draft(md,folder/'figure-catalog.json');assert report['status']=='passed' and report['formal_figures']==9
        check('Writer_raw_Markdown_text_integrity_and_fresh_mechanical_checks',report)
        confirmation=read(pin('stage-d/runtime-integration/writer-fix-20261110-v1/user-approval-confirmation.json'))
        assert confirmation['manuscript_sha256']==sha(md) and confirmation['figure_catalog_sha256']==sha(folder/'figure-catalog.json') and not confirmation['user_stage_D_acceptance_inferred']
        check('explicit_new_manuscript_and_figures_approval_binding',{'run_id':rid,'user_statement':confirmation['user_statement'],'formal_figures':9,'stage_acceptance_inferred':False})
        rows=w.db.execute("SELECT id,hand,phase,payload FROM mc_hand_runs WHERE payload->'request'->>'actor'='ENGINEERING_PROBE' ORDER BY created_at").fetchall()
        runs=[];metadata=[]
        for run in rows:
            f=asset_path(ROOT,'stage-d/runs/runtime')/str(run['id']);body=run['payload']
            runs.append({'run_id':str(run['id']),'hand':run['hand'],'phase':run['phase'],'attempt':body['attempt'],'failure_domain':body.get('failure_domain'),'operator_stop':body.get('operator_stop')})
            for m in sorted((f/'operations').glob('*/*-metadata.json')):
                data=read(pin(m));metadata.append({'run_id':str(run['id']),'operation':m.parent.name,'path':m.relative_to(ROOT).as_posix(),**{k:data.get(k) for k in ['stage','status','configured_model','finish_reason','output_protocol']}})
            for m in (f/'operations').glob('*/*-response.json'):pin(m)
            for m in (f/'records/Receipt').glob('*.json'):pin(m)
        check('real_supplier_failure_and_rework_history_retained',{'runs':runs,'provider_metadata':metadata,'history_is_not_a_success_rate':True})
    for name in ['stage-d/runtime-integration/writer-fix-20261110-v1/root-cause.json','stage-d/runtime-integration/writer-fix-20261110-v1/live-success-evidence.json','stage-d/runtime-integration/writer-fix-20261110-v1/repair-report.md','stage-d/runtime-integration/20261110-v1/implementation-report.md']:pin(name)
    check('scope_D6_user_update_and_E_boundaries',{'D6':'confirmed_previous_question_artifact_access','no_generic_E_export_claim':True,'user_stage_acceptance':'pending'})
    assert all(sha(ROOT/path)==h for path,h in evidence.items())
    result={'created_at':datetime.now(timezone.utc).isoformat(),'checks_status':'passed','scope':'Fresh read-only D1-D6 engineering evidence reacceptance; existing independent reviews revalidated, not replaced','case_checks':baseline['checks'],'runtime_checks':checks,'evidence_files':[{'path':p,'sha256':h} for p,h in sorted(evidence.items())],'source_evidence_unchanged':True,'new_provider_calls':0,'new_business_solver_runs':0,'user_stage_acceptance':'pending','regression_must_be_checked_separately':True}
    with (out/'evidence-audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'case_checks':len(baseline['checks']),'runtime_checks':len(checks),'pinned_files':len(evidence),'source_evidence_unchanged':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);audit_runtime(p.parse_args().output)
