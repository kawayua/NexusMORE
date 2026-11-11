"""D6 database/reference invariants. Every approval here is synthetic test data."""
import copy,json,uuid
from pathlib import Path
import pytest
from modelcrew.workflow import Workflow
from modelcrew.config import ROOT
from modelcrew import question_references as qr
from modelcrew.collaboration import sha_file
from modelcrew.contracts import digest

@pytest.fixture
def data(tmp_path):
    contract=json.loads((ROOT/'contracts/examples/valid-2024-a-q1.json').read_text(encoding='utf-8'))
    statement=tmp_path/'source.txt';statement.write_text('TEST_ONLY SYNTHETIC STATEMENT',encoding='utf-8')
    contract['inputs']=[{'id':'test-input','source_id':'statement','path':str(statement),'sha256':sha_file(statement),'role':'problem_statement'}]
    excerpt=tmp_path/'q2.txt';excerpt.write_text('TEST_ONLY SECOND QUESTION',encoding='utf-8')
    source='test-d6-source-'+uuid.uuid4().hex;dest='test-d6-target-'+uuid.uuid4().hex
    with Workflow() as w:
        w.create(source,contract,project='automated-tests')
        args=dict(target_id=dest,revision=1,case_id=contract['problem']['case_id'],question_id='Q2',statement_path=str(statement),statement_sha256=sha_file(statement),pages=[1],excerpt_path=excerpt)
        w.question_intake(**args)
    return source,dest,args,contract

def approve(w,source):
    w.action(source,actor='TEST_SIMULATED_USER',request_id='model-only',version=1,kind='model',decision='approve',defer_execution=True)

def attach(w,source,dest,scopes=['model']):
    return w.attach_question_reference(target_id=dest,target_revision=1,source_task=source,scopes=scopes,purpose='TEST_ONLY reference use')

def test_unconfirmed_model_cannot_be_read(data):
    s,d,_,_=data
    with Workflow() as w:
        with pytest.raises(ValueError,match='unconfirmed'):attach(w,s,d)

def test_model_confirmation_opens_reference_before_results_paper_and_export(data):
    s,d,_,_=data
    with Workflow() as w:
        approve(w,s);ref=attach(w,s,d)
        assert not w.task(s)['result_approved'] and w.inspect(s)['execution'] is None
        context=w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']])
        assert 'model' in context['references'][0]['source']['values']
        assert not context['model_approved'] and not context['result_approved']
        assert not w.db.execute('SELECT 1 FROM mc_tasks WHERE id=%s',(d,)).fetchone()

def test_result_requires_its_own_confirmation(data):
    s,d,_,_=data
    with Workflow() as w:
        approve(w,s)
        with pytest.raises(ValueError,match='result is unconfirmed'):attach(w,s,d,['result'])

def test_resume_reads_identical_reference_and_attach_is_idempotent(data):
    s,d,_,_=data
    with Workflow() as w:approve(w,s);first=attach(w,s,d)
    with Workflow() as w:
        assert attach(w,s,d)==first
        assert w.question_context(target_id=d,target_revision=1,reference_ids=[first['reference_id']])['references'][0]['reference_id']==first['reference_id']
        assert w.db.execute('SELECT count(*) AS n FROM mc_question_references WHERE target_id=%s',(d,)).fetchone()['n']==1

def test_source_version_change_blocks_current_read_and_keeps_history(data):
    s,d,_,c=data
    with Workflow() as w:
        approve(w,s);ref=attach(w,s,d);changed=copy.deepcopy(c);changed['risks'].append('TEST_ONLY model changed')
        w.action(s,actor='TEST_SIMULATED_USER',request_id='change',version=1,kind='revise_model',contract=changed,reason='TEST_ONLY')
        with pytest.raises(ValueError,match='unconfirmed'):w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']])
        approve2=w.action(s,actor='TEST_SIMULATED_USER',request_id='approve2',version=2,kind='model',decision='approve',defer_execution=True)
        with pytest.raises(ValueError,match='version changed'):w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']])
        assert w.db.execute('SELECT 1 FROM mc_question_references WHERE id=%s',(ref['reference_id'],)).fetchone()
        newer=attach(w,s,d);assert newer['reference_id']!=ref['reference_id']

def test_changed_original_statement_blocks_read(data):
    s,d,args,_=data
    with Workflow() as w:
        approve(w,s);ref=attach(w,s,d);Path(args['statement_path']).write_text('CHANGED',encoding='utf-8')
        with pytest.raises(ValueError,match='statement changed'):w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']])

def test_new_target_revision_blocks_old_context_and_wrong_target(data):
    s,d,args,_=data
    with Workflow() as w:
        approve(w,s);ref=attach(w,s,d)
        w.question_intake(**{**args,'revision':2})
        with pytest.raises(ValueError,match='stale'):w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']])
        with pytest.raises(ValueError,match='another question'):w.question_context(target_id=d,target_revision=2,reference_ids=[ref['reference_id']])
        other=d+'-other';w.question_intake(**{**args,'target_id':other})
        with pytest.raises(ValueError,match='another question'):w.question_context(target_id=other,target_revision=1,reference_ids=[ref['reference_id']])

def test_cross_case_and_self_references_are_rejected(data):
    s,d,args,_=data
    with Workflow() as w:
        approve(w,s);other=d+'-wrong';w.question_intake(**{**args,'target_id':other,'case_id':'OTHER_CASE'})
        with pytest.raises(ValueError,match='mismatch'):attach(w,s,other)
        with pytest.raises(ValueError,match='Self reference'):attach(w,s,s)

@pytest.mark.parametrize('scopes',[[],['code'],['model','model']])
def test_invalid_scope_cannot_read_unapproved_artifacts(data,scopes):
    s,d,_,_=data
    with Workflow() as w:
        approve(w,s)
        with pytest.raises(ValueError,match='scopes'):attach(w,s,d,scopes)

def test_target_intake_conflict_and_reference_rows_are_immutable(data):
    s,d,args,_=data
    with Workflow() as w:
        approve(w,s);ref=attach(w,s,d)
        with pytest.raises(ValueError,match='already bound'):w.question_intake(**{**args,'question_id':'Q3'})
        with pytest.raises(Exception):
            with w.db.transaction():w.db.execute('UPDATE mc_question_references SET payload=%s WHERE id=%s',(json.dumps({}),ref['reference_id']))
        with pytest.raises(ValueError,match='Duplicate'):w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']]*2)

def test_broken_reference_file_and_record_hash_rejected(tmp_path):
    p=tmp_path/'file';p.write_text('TEST_ONLY',encoding='utf-8')
    with pytest.raises(ValueError,match='changed'):qr.artifact(p,'0'*64)
    with pytest.raises(ValueError,match='outside'):qr.artifact(ROOT.parent/'outside.json')
    with pytest.raises(ValueError,match='record'):qr.verify_record({'payload':{},'sha256':'0'*64})

def test_revalidation_blocks_modified_context_without_changing_source(data):
    s,d,_,_=data
    with Workflow() as w:
        approve(w,s);ref=attach(w,s,d)
        context=w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']])
        assert qr.revalidate_context(w,context,expected_target=d)==context
        altered=copy.deepcopy(context);altered['model_approved']=True
        with pytest.raises(ValueError,match='context changed'):qr.revalidate_context(w,altered,expected_target=d)
        with pytest.raises(ValueError,match='target mismatch'):qr.revalidate_context(w,context,expected_target='another')

def test_later_question_cannot_supply_an_earlier_question(data):
    s,d,args,c=data
    other_source=s+'-q3';c=copy.deepcopy(c);c['problem']['subproblem_id']='Q3'
    with Workflow() as w:
        w.create(other_source,c,project='automated-tests');approve(w,other_source)
        with pytest.raises(ValueError,match='earlier questions'):attach(w,other_source,d)

def test_modeling_input_rejects_reference_for_another_task_before_provider(data):
    s,d,_,_=data
    with Workflow() as w:
        with pytest.raises(ValueError,match='target must match'):w.run_modeling(s,version=1,actor='TEST_ONLY',request_id='bad-target',guidance='TEST_ONLY',question_reference={'target_id':d,'target_revision':1,'reference_ids':[]})

def test_original_excerpt_tampering_is_rejected(data):
    s,d,args,_=data
    with Workflow() as w:
        approve(w,s);ref=attach(w,s,d);Path(args['excerpt_path']).write_text('TAMPERED',encoding='utf-8')
        with pytest.raises(ValueError,match='changed'):w.question_context(target_id=d,target_revision=1,reference_ids=[ref['reference_id']])
