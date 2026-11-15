"""Security boundaries of interpretation-only numerical P2 inheritance."""
import copy
import pytest
from modelcrew.result_lineage import same_execution,verify_proof
from modelcrew.workflow import WorkflowError

def pair():
    return ({'execution_id':'a','revision':1,'review':{'kind':'d4_P2_review','status':'passed'}}, {'execution_id':'a','revision':2,'review':{'kind':'interpretation_review','status':'passed','narrative_status':'structured_only'}})

def test_same_execution_can_preserve_original_numerical_review():
    a,b=pair();same_execution(a,b)

@pytest.mark.parametrize('mutation', ['execution','baseline_failed','baseline_not_p2','failed_claims','free_narrative','not_new_revision'])
def test_interpretation_cannot_promote_incompatible_or_unreviewed_result(mutation):
    a,b=pair()
    if mutation=='execution':b['execution_id']='other'
    elif mutation=='baseline_failed':a['review']['status']='failed'
    elif mutation=='baseline_not_p2':a['review']['kind']='execution_success_only'
    elif mutation=='failed_claims':b['review']['status']='failed'
    elif mutation=='free_narrative':b['review']['narrative_status']='unknown'
    else:b['revision']=1
    with pytest.raises(WorkflowError):same_execution(a,b)

@pytest.mark.parametrize('change', ['unconfirmed','wrong_task','old_revision','old_contract'])
def test_lineage_rechecks_live_confirmation_before_reading_any_old_review(change):
    t={'id':'q','current_version':1,'result_revision':2,'result_approved':True}
    proof={'task_id':'q','version':1,'revision':2}
    if change=='unconfirmed':t['result_approved']=False
    elif change=='wrong_task':proof['task_id']='other'
    elif change=='old_revision':proof['revision']=1
    else:proof['version']=2
    class W:
        def task(self,_):return t
    with pytest.raises(WorkflowError,match='Confirmed current interpretation'):verify_proof(W(),'q',proof)

@pytest.mark.parametrize('tamper', ['claims','snapshot_binding','frozen_package','none'])
def test_full_lineage_rejects_unreviewed_claims_or_different_p2_package(tmp_path,monkeypatch,tamper):
    import json
    from types import SimpleNamespace as NS
    from modelcrew import result_lineage as rl, mathematics,reviews,full_result
    from modelcrew.contracts import digest
    from modelcrew.collaboration import sha_file,Receipt,Ticket,Snapshot
    monkeypatch.setattr(rl,'ROOT',tmp_path)
    monkeypatch.setattr(mathematics,'assert_gate_binding',lambda *a:None)
    base,current=pair()
    current.update(task_id='q',version=1,interpretation='approved structured result')
    current['review']['claims']=[{'id':'C8','value':0.9964}]
    t={'id':'q','current_version':1,'result_revision':2,'result_approved':True,'execution_id':'a'}
    reviewed=copy.deepcopy(current)
    if tamper=='claims':reviewed['review']['claims'].append({'id':'UNREVIEWED','value':999})
    state=tmp_path/'state.json';state.write_text(json.dumps({'result':reviewed}),encoding='utf-8')
    report=tmp_path/'P2.json';report.write_text(json.dumps({'status':'PASS','gate':'P2','read_only':True,'independent_context':True,'reviewer':'independent-test-reviewer','task_id':'q','contract_version':1,'result_revision':2,'execution_id':'a','contract_sha256':'contract','input_hashes':{'state.json':sha_file(state)}}),encoding='utf-8')
    proof={'task_id':'q','version':1,'revision':2,'base_revision':1,'execution_id':'a','review_sha256':digest(current['review']),'base_review_sha256':digest(base['review']),'independent_review_path':'P2.json','independent_review_sha256':sha_file(report)}
    folder=tmp_path/'full';folder.mkdir();base['review']['source_run']='full'
    # The proof must include the real baseline review identity, including source_run.
    proof['base_review_sha256']=digest(base['review'])
    (folder/'run.json').write_text(json.dumps({'task_id':'q','contract_version':1,'execution_id':'a','result_revision':1,'contract_sha256':'contract'}),encoding='utf-8')
    (folder/'P2-admission.json').write_text(json.dumps({'receipt_sha256':'receipt','snapshot_sha256':'snapshot'}),encoding='utf-8')
    (folder/'frozen-artifacts.json').write_text('{}',encoding='utf-8')
    binding=NS(task_id='q',contract_version=1,contract_sha256='contract',execution_id='a',result_revision=1)
    if tamper=='snapshot_binding':binding.result_revision=999
    frozen_hash=sha_file(folder/'frozen-artifacts.json') if tamper!='frozen_package' else 'different'
    snapshot=NS(binding=binding,artifacts=[NS(artifact_id='frozen_files',sha256=frozen_hash)])
    class Store:
        def __init__(self,*a):pass
        def load(self,cls,key):
            return NS(ticket_sha256='ticket',status='PASS') if cls is Receipt else NS(gate='P2',policy_sha256='historical') if cls is Ticket else snapshot
        def accept_review(self,*a,**kw):return 'receipt'
    monkeypatch.setattr(rl,'CollaborationStore',Store)
    monkeypatch.setattr(full_result,'verify_frozen_files',lambda f:({},None))
    monkeypatch.setattr(reviews,'review_interpretation',lambda *a:{'status':'passed'})
    class DB:
        def execute(self,sql,args):
            v=base if 'mc_results' in sql and args[-1]==1 else current if 'mc_results' in sql else {'artifacts':[]} if 'mc_executions' in sql else {'sha256':'contract'}
            return NS(fetchone=lambda:v)
    class W:
        db=DB()
        def task(self,_):return t
    if tamper=='none':assert verify_proof(W(),'q',proof)==proof
    else:
        error={'claims':'exact result and claim set','snapshot_binding':'snapshot binding mismatch','frozen_package':'this frozen package'}[tamper]
        with pytest.raises(WorkflowError,match=error):verify_proof(W(),'q',proof)
