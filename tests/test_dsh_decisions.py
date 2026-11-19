"""Explicitly synthetic native-host capture tests in a disposable database."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from psycopg.types.json import Jsonb
import pytest

from modelcrew.business_adapter import BusinessAdapter
from modelcrew.business_contract import BusinessContractError, request_digest
from modelcrew.contracts import digest
from modelcrew.dsh_decisions import (NativeDecisionSession, adapter_sha256, capture_status,
                                    validate_scope, validate_host, PROTOCOL)
from modelcrew.trusted_decisions import TrustedDecisions
from modelcrew.workflow import Workflow
from test_business_mcp import task, request
from test_trusted_decisions import counts, revise


@pytest.fixture(scope='module')
def url():
    value=os.environ.get('MODELCREW_DSH_DECISIONS_TEST_URL')
    if not value:pytest.skip('Run scripts/verify_dsh_decisions.py for explicit isolated probes')
    with Workflow(value) as w:w.setup()
    return value


@pytest.fixture
def adapter(url):return BusinessAdapter(lambda:Workflow(url))


@pytest.fixture
def service(url,monkeypatch):
    monkeypatch.setattr('modelcrew.trusted_decisions.local_principal',lambda:{'kind':'test_simulated_dsh','subject_sha256':'c'*64})
    return TrustedDecisions(lambda:Workflow(url))


def host():return {'instance_id':'TEST_ENGINEERING_INSTANCE','session_id':'TEST_ENGINEERING_SESSION',
                  'pid':os.getppid(),'adapter_sha256':adapter_sha256(),'engineering_only':True}


def answer(frame,values):
    result={'answers':[{'id':q['id'],'selected':[v]} if q.get('options') else {'id':q['id'],'selected':[],'custom':v}
                       for q,v in zip(frame['questions'],values)]}
    return {'type':'answer','frame_id':frame['frame_id'],'result':result}


def capture(service,scope,*,decision='reject',kind='model',during=None):
    session=NativeDecisionSession(scope,host(),service);frame=session.begin()
    item=next(p for p in session.items if p['kind']==kind)
    frame=session.answer(answer(frame,[item['pending_id']]))
    assert '完整' in frame['questions'][0]['header'];assert digest(session.review) in frame['questions'][0]['detail']
    frame=session.answer(answer(frame,[decision]))
    frame=session.answer(answer(frame,['TEST_SIMULATED_USER: native reason','TEST_SIMULATED_USER: native decision, not real approval']))
    assert session.request['user_event']['channel']=='trusted_host_ui'
    if during:during()
    receipt=session.answer(answer(frame,['确认本次决定']))
    assert receipt['type']=='captured'
    return session,receipt


def submit(session):return session.submit({'type':'submit','request_sha256':request_digest(session.request)})['result']


def test_private_worker_rejects_ordinary_shell_pipe_before_database():
    p=subprocess.run([sys.executable,'-m','modelcrew.dsh_decisions','--private-stdio'],input='{}\n',capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert p.returncode==1;assert json.loads(p.stdout)['code']=='untrusted_user_event'
    assert 'Traceback' not in p.stderr


@pytest.mark.parametrize('scope',[{}, {'project_id':'p'}, {'project_id':'p','task_id':'t','build_id':'b'},
    {'project_id':'p','task_id':'t','actor':'user'},{'project_id':'p','build_id':'b','run_id':'r'},
    {'project_id':'../p','task_id':'t'}])
def test_scope_never_accepts_decision_or_identity(scope):
    with pytest.raises(BusinessContractError):validate_scope(scope)


def test_exact_host_parent_and_installed_adapter_are_required():
    assert validate_host(host())==host()
    for field,value in [('pid',0),('adapter_sha256','a'*64),('session_id',''),('engineering_only','yes')]:
        forged=host();forged[field]=value
        with pytest.raises(BusinessContractError):validate_host(forged)


def test_capture_is_independent_then_reuses_g3_submission(service,adapter,url,tmp_path):
    p,t,*_=task(adapter,url,tmp_path);session,_=capture(service,{'project_id':p,'task_id':t})
    assert counts(url,t)=={'core':0,'claims':0}
    with Workflow(url) as w:
        event=w.db.execute('SELECT * FROM mc_trusted_user_events WHERE event_id=%s',(session.request['user_event']['event_id'],)).fetchone()
        cap=w.db.execute('SELECT * FROM mc_trusted_host_captures WHERE event_id=%s',(event['event_id'],)).fetchone()
        assert event['principal']['kind']=='test_simulated_dsh';assert cap['capture_sha256']==digest(cap['capture'])
        assert cap['capture']['host']['engineering_only'] is True
    result=submit(session);assert result['receipt']['state']=='succeeded',result
    assert service.submit(session.request)['replayed'] is True
    assert counts(url,t)=={'core':1,'claims':1}
    with pytest.raises(BusinessContractError):submit(session)


@pytest.mark.parametrize('step',['select','decision','statement','confirm'])
def test_skip_cancel_and_wrong_reply_close_conversation(service,adapter,url,tmp_path,step):
    p,t,*_=task(adapter,url,tmp_path);s=NativeDecisionSession({'project_id':p,'task_id':t},host(),service);f=s.begin()
    if step!='select':f=s.answer(answer(f,[s.items[0]['pending_id']]))
    if step in ('statement','confirm'):f=s.answer(answer(f,['reject']))
    if step=='confirm':f=s.answer(answer(f,['TEST_SIMULATED_USER: reason','TEST_SIMULATED_USER: statement']))
    bad=answer(f,['取消'] if step=='confirm' else [])
    with pytest.raises(BusinessContractError):s.answer(bad)
    with pytest.raises(BusinessContractError):s.answer(answer(f,['确认本次决定']))
    assert counts(url,t)=={'core':0,'claims':0}
    with Workflow(url) as w:assert not w.db.execute("SELECT 1 FROM mc_trusted_user_events WHERE request->'arguments'->>'task_id'=%s",(t,)).fetchone()


@pytest.mark.parametrize('change',['frame','id','decision','custom','duplicate','oversized','foreign'])
def test_native_response_tampering_never_captures(service,adapter,url,tmp_path,change):
    p,t,*_=task(adapter,url,tmp_path);s=NativeDecisionSession({'project_id':p,'task_id':t},host(),service);f=s.begin();a=answer(f,[s.items[0]['pending_id']])
    if change=='frame':a['frame_id']='a'*64
    elif change=='id':a['result']['answers'][0]['id']='other-session-question'
    elif change=='decision':a['result']['answers'][0]['selected']=['approve']
    elif change=='custom':a['result']['answers'][0]['custom']='approve'
    elif change=='duplicate':a['result']['answers']*=2
    elif change=='oversized':a['result']['answers'][0]['selected']=['a'*2100]
    else:a['actor']='user'
    with pytest.raises(BusinessContractError):s.answer(a)
    assert counts(url,t)=={'core':0,'claims':0}


def test_expiry_before_capture_has_no_event(service,adapter,url,tmp_path):
    p,t,*_=task(adapter,url,tmp_path);s=NativeDecisionSession({'project_id':p,'task_id':t},host(),service);f=s.begin();s.deadline=0
    with pytest.raises(BusinessContractError):s.answer(answer(f,[s.items[0]['pending_id']]))
    assert counts(url,t)=={'core':0,'claims':0}


def test_change_during_review_cannot_capture(service,adapter,url,tmp_path):
    p,t,_,created,state=task(adapter,url,tmp_path)
    with pytest.raises(BusinessContractError) as exc:
        capture(service,{'project_id':p,'task_id':t},during=lambda:revise(adapter,t,created,state))
    assert exc.value.code=='stale_binding';assert counts(url,t)=={'core':0,'claims':0}


def test_change_after_capture_cannot_spend_event(service,adapter,url,tmp_path):
    p,t,_,created,state=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t})
    revise(adapter,t,created,state);assert submit(s)['error']['code']=='stale_binding';assert counts(url,t)=={'core':0,'claims':0}


def test_host_event_without_separate_capture_record_is_rejected(service,adapter,url,tmp_path):
    p,t,*_=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t})
    with Workflow(url) as w:
        w.db.execute('ALTER TABLE mc_trusted_host_captures DISABLE TRIGGER mc_trusted_host_captures_immutable')
        try:w.db.execute('DELETE FROM mc_trusted_host_captures WHERE event_id=%s',(s.request['user_event']['event_id'],))
        finally:w.db.execute('ALTER TABLE mc_trusted_host_captures ENABLE TRIGGER mc_trusted_host_captures_immutable')
    assert submit(s)['error']['code']=='untrusted_user_event';assert counts(url,t)=={'core':0,'claims':0}


def test_host_approval_retains_m1_gate_and_defers_execution(service,adapter,url,tmp_path,monkeypatch):
    p,t,*_=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t},decision='approve')
    assert s.request['arguments']['body']['defer_execution'] is True
    assert submit(s)['error']['code']=='workflow_conflict'
    assert counts(url,t)=={'core':0,'claims':0}
    monkeypatch.setattr('modelcrew.modeling_hand.assert_m1',lambda *a,**k:{'TEST_SIMULATED_M1':True})
    # No new capture or real M1: this exercises shared core behavior only.
    result=service.submit(s.request);assert result['receipt']['state']=='succeeded',result
    with Workflow(url) as w:assert not w.task(t)['execution_id']


def test_status_never_submits_unspent_capture(service,adapter,url,tmp_path):
    p,t,*_=task(adapter,url,tmp_path);scope={'project_id':p,'task_id':t};s,_=capture(service,scope)
    result=capture_status(scope,service);assert result['dispatch_performed'] is False
    assert result['captures'][0]['event_id']==s.request['user_event']['event_id']
    assert counts(url,t)=={'core':0,'claims':0}
    submit(s);result=capture_status(scope,service);assert result['captures'][0]['operation_status']['receipt']['state']=='succeeded'


def test_concurrent_identical_submission_has_one_core_event(service,adapter,url,tmp_path):
    p,t,*_=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:service.submit(s.request),range(2)))
    assert all(r['receipt']['state']=='succeeded' for r in results);assert counts(url,t)=={'core':1,'claims':1}


def test_fabricated_host_reference_not_callable_through_model_adapter(service,adapter,url,tmp_path):
    p,t,*_=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t})
    assert adapter.invoke('task_decide',s.request)['error']['code']=='unsupported_operation';assert counts(url,t)=={'core':0,'claims':0}


@pytest.mark.parametrize('assembly',[False,True])
def test_native_manuscript_and_figures_remain_separate(service,adapter,url,tmp_path,monkeypatch,assembly):
    import test_trusted_decisions as original
    def native_capture(service,scope,monkeypatch,*,kind='model',decision='reject',**kwargs):
        session,_=capture(service,scope,kind=kind,decision=decision);return session.request
    monkeypatch.setattr(original,'capture',native_capture)
    original.test_manuscript_and_figures_need_separate_captured_events(service,adapter,url,tmp_path,monkeypatch,assembly)


@pytest.mark.parametrize('changed',[False,True])
def test_native_result_keeps_execution_and_revision_binding(service,adapter,url,tmp_path,monkeypatch,changed):
    import test_trusted_decisions as original
    def native_capture(service,scope,monkeypatch,*,kind='model',decision='reject',**kwargs):
        session,_=capture(service,scope,kind=kind,decision=decision);return session.request
    monkeypatch.setattr(original,'capture',native_capture)
    original.test_result_decision_binds_execution_and_revision(service,adapter,url,tmp_path,monkeypatch,changed)


def test_changed_os_principal_cannot_submit_capture(service,adapter,url,tmp_path,monkeypatch):
    p,t,*_=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t})
    monkeypatch.setattr('modelcrew.trusted_decisions.local_principal',lambda:{'kind':'test_simulated_dsh','subject_sha256':'d'*64})
    assert submit(s)['error']['code']=='untrusted_user_event';assert counts(url,t)=={'core':0,'claims':0}


@pytest.mark.parametrize('stage',['before_core','after_core','after_save'])
def test_native_crash_and_restart_keep_original_fence(service,adapter,url,tmp_path,stage):
    p,t,*_=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t})
    path=tmp_path/'TEST_SIMULATED_NATIVE_REQUEST.json';path.write_text(json.dumps(s.request),encoding='utf-8')
    child="""import json,os,sys
import modelcrew.trusted_decisions as trusted
from modelcrew.workflow import Workflow
trusted.local_principal=lambda:{'kind':'test_simulated_dsh','subject_sha256':'c'*64}
def fault(stage,row):
    if stage==sys.argv[2]:os._exit(37)
service=trusted.TrustedDecisions(lambda:Workflow(os.environ['MODELCREW_DSH_DECISIONS_TEST_URL']),fault=fault)
service.submit(json.load(open(sys.argv[1],encoding='utf-8')))
"""
    child_result=subprocess.run([sys.executable,'-c',child,str(path),stage],capture_output=True,text=True,timeout=60)
    assert child_result.returncode==37,child_result.stderr
    state=capture_status({'project_id':p,'task_id':t},service)['captures'][0]['operation_status']
    replay=service.submit(s.request)
    if stage=='before_core':
        assert state['receipt']['state']=='dispatched';assert replay['status']=='outcome_unknown';assert counts(url,t)=={'core':0,'claims':1}
    else:
        assert state['receipt']['state']==replay['receipt']['state']=='succeeded';assert counts(url,t)=={'core':1,'claims':1}


@pytest.mark.parametrize('changed',['confirmation','statement','scope','host'])
def test_consistent_rehashed_but_invalid_capture_transcript_is_rejected(service,adapter,url,tmp_path,changed):
    p,t,*_=task(adapter,url,tmp_path);s,_=capture(service,{'project_id':p,'task_id':t});event=s.request['user_event']['event_id']
    with Workflow(url) as w:
        c=w.db.execute('SELECT capture FROM mc_trusted_host_captures WHERE event_id=%s',(event,)).fetchone()['capture']
        if changed=='confirmation':
            c['transcript'][3]['result']['answers'][0]['selected']=['取消']
            c['transcript'][3]['result_sha256']=digest(c['transcript'][3]['result'])
        elif changed=='statement':
            c['transcript'][2]['result']['answers'][1]['custom']='TEST_SIMULATED_USER: altered original statement'
            c['transcript'][2]['result_sha256']=digest(c['transcript'][2]['result'])
        elif changed=='scope':c['scope']['project_id']='different-project'
        else:c['host']['session_id']='invalid session with spaces'
        # Engineering corruption probe only, never an exposed application API.
        w.db.execute('ALTER TABLE mc_trusted_host_captures DISABLE TRIGGER mc_trusted_host_captures_immutable')
        try:w.db.execute('UPDATE mc_trusted_host_captures SET capture=%s,capture_sha256=%s WHERE event_id=%s',(Jsonb(c),digest(c),event))
        finally:w.db.execute('ALTER TABLE mc_trusted_host_captures ENABLE TRIGGER mc_trusted_host_captures_immutable')
    assert submit(s)['error']['code']=='untrusted_user_event';assert counts(url,t)=={'core':0,'claims':0}

# New persistent chat UX: synthetic DB/host only; never a real user's approval.
from modelcrew.dsh_chat import prepare_review, confirm_review, is_approval


def chat_source(text='原始合成题目',suffix='before'):
    return {'id':'TEST_MESSAGE_'+suffix,'rpc_id':'TEST_RPC_'+suffix,'text':text}


def ready_chat(service,adapter,url,tmp_path,monkeypatch):
    p,t,*_=task(adapter,url,tmp_path)
    monkeypatch.setattr('modelcrew.dsh_chat.host_review_readiness',lambda *a:{'model_ready':True})
    monkeypatch.setattr('modelcrew.modeling_hand.assert_m1',lambda *a,**k:{'TEST_SIMULATED_M1':True})
    scope={'project_id':p,'task_id':t}
    preview=prepare_review(scope,host(),chat_source(),service)
    assert preview['status']=='waiting_for_user'
    return t,scope,preview


def test_chat_document_is_persistent_readable_and_creates_no_capture(service,adapter,url,tmp_path,monkeypatch):
    t,scope,preview=ready_chat(service,adapter,url,tmp_path,monkeypatch)
    assert Path(preview['local_path']).read_text(encoding='utf-8')==preview['markdown']
    assert '# 建模方案待审稿' in preview['markdown']
    assert '### 模型假设' in preview['markdown'] and '### 检查计划' in preview['markdown']
    assert '"dossier":' not in preview['markdown']
    assert prepare_review(scope,host(),None,service)==preview
    assert counts(url,t)=={'core':0,'claims':0}
    with Workflow(url) as w:
        assert not w.db.execute("SELECT 1 FROM mc_trusted_user_events WHERE request->'arguments'->>'task_id'=%s",(t,)).fetchone()


def test_chat_preview_still_requires_input_math_and_independent_m1(service,adapter,url,tmp_path):
    p,t,*_=task(adapter,url,tmp_path)
    assert prepare_review({'project_id':p,'task_id':t},host(),chat_source(),service)['status']=='not_ready'
    assert counts(url,t)=={'core':0,'claims':0}


@pytest.mark.parametrize('text',['不通过','是否通过？','通过，但先修改假设','如果检查正确就通过','“通过”','他说通过','好的','继续','审核意见：通过','通过\n修改第二项'])
def test_chat_discussion_is_never_an_approval(text):
    assert not is_approval(text)


def test_chat_exact_source_message_approves_once_without_card_transcript(service,adapter,url,tmp_path,monkeypatch):
    t,scope,p=ready_chat(service,adapter,url,tmp_path,monkeypatch)
    msg=chat_source('通过','confirm')
    result=confirm_review(scope,host(),p['preview_id'],msg,service)
    assert result['receipt']['state']=='succeeded',result
    assert result['data']['user_decision']['confirmed_binding']==p['binding']
    assert counts(url,t)=={'core':1,'claims':1}
    repeated=confirm_review(scope,host(),p['preview_id'],msg,service)
    assert repeated['status']=='already_received' and repeated['dispatch_performed'] is False
    with Workflow(url) as w:
        assert w.task(t)['model_approved'] and not w.task(t)['execution_id']
        event=w.db.execute('SELECT * FROM mc_trusted_user_events WHERE event_id LIKE %s AND request->\'arguments\'->>\'task_id\'=%s',('chat-event-%',t)).fetchone()
        cap=w.db.execute('SELECT capture FROM mc_trusted_host_captures WHERE event_id=%s',(event['event_id'],)).fetchone()['capture']
        assert cap['source']=='dsh_native_chat' and cap['message']==msg
        assert 'transcript' not in cap and event['statement']=='通过'


def test_chat_cannot_reuse_message_that_preceded_the_document(service,adapter,url,tmp_path,monkeypatch):
    t,scope,p=ready_chat(service,adapter,url,tmp_path,monkeypatch)
    msg=chat_source('通过')
    with pytest.raises(BusinessContractError):confirm_review(scope,host(),p['preview_id'],msg,service)
    assert counts(url,t)=={'core':0,'claims':0}


def test_chat_changed_version_or_other_session_never_approves(service,adapter,url,tmp_path,monkeypatch):
    project,t,_,created,state=task(adapter,url,tmp_path)
    monkeypatch.setattr('modelcrew.dsh_chat.host_review_readiness',lambda *a:{'model_ready':True})
    scope={'project_id':project,'task_id':t};p=prepare_review(scope,host(),chat_source(),service)
    other={**host(),'session_id':'TEST_OTHER_SESSION'}
    with pytest.raises(BusinessContractError):confirm_review(scope,other,p['preview_id'],chat_source('通过','other'),service)
    revised=revise(adapter,t,created,state)
    assert revised['status']=='needs_user_input',revised
    with pytest.raises(BusinessContractError):confirm_review(scope,host(),p['preview_id'],chat_source('通过','stale'),service)
    assert counts(url,t)=={'core':0,'claims':0}


def test_chat_modified_displayed_markdown_cannot_capture(service,adapter,url,tmp_path,monkeypatch):
    t,scope,p=ready_chat(service,adapter,url,tmp_path,monkeypatch)
    path=Path(p['local_path']);old=path.read_bytes()
    try:
        path.write_text('changed displayed plan',encoding='utf-8')
        with pytest.raises(BusinessContractError):confirm_review(scope,host(),p['preview_id'],chat_source('通过','edited'),service)
    finally:path.write_bytes(old)
    assert counts(url,t)=={'core':0,'claims':0}


def test_chat_private_worker_rejects_shell_and_model_supplied_frames():
    p=subprocess.run([sys.executable,'-m','modelcrew.dsh_chat','--private-stdio'],input='{}\n',capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert p.returncode==1 and json.loads(p.stdout)['code']=='untrusted_user_event'
    assert 'Traceback' not in p.stderr

@pytest.mark.parametrize('text',[
    '确认你的三个口径 通过建模方案 进入代码手',
    '通过建模方案，进入代码手','同意建模方案',
    '我同意当前建模方案，请进入代码手阶段！','确认上述三项口径，通过模型方案。'])
def test_chat_explicit_model_sentences_are_scope_bound(text):
    assert is_approval(text,'model')
    for kind in ['result','manuscript','figures']:
        assert not is_approval(text,kind)


@pytest.mark.parametrize('text',[
    '不同意建模方案','是否通过建模方案','同意建模方案吗？',
    '通过建模方案，但先修改第二条','如果没有问题就通过建模方案',
    '他说“通过建模方案”','通过建模方案，同时通过正文',
    '确认三个口径\n通过建模方案','先不要通过建模方案','通过旧版建模方案'])
def test_chat_extended_sentences_never_admit_conditions_or_other_decisions(text):
    assert not is_approval(text,'model')


def test_chat_full_model_confirmation_commits_original_text_exactly_once(service,adapter,url,tmp_path,monkeypatch):
    t,scope,p=ready_chat(service,adapter,url,tmp_path,monkeypatch)
    text='确认你的三个口径 通过建模方案 进入代码手'
    message=chat_source(text,'full-sentence')
    result=confirm_review(scope,host(),p['preview_id'],message,service)
    assert result['receipt']['state']=='succeeded',result
    assert counts(url,t)=={'core':1,'claims':1}
    with Workflow(url) as w:
        event=w.db.execute('SELECT statement,request FROM mc_trusted_user_events WHERE request->\'arguments\'->>\'task_id\'=%s',(t,)).fetchone()
        assert event['statement']==text and event['request']['arguments']['body']['reason']==text
        assert w.task(t)['model_approved']
    repeat=confirm_review(scope,host(),p['preview_id'],message,service)
    assert repeat['status']=='already_received' and not repeat['dispatch_performed']
    assert counts(url,t)=={'core':1,'claims':1}

@pytest.mark.parametrize('target',['evidence'])
def test_chat_changed_readable_evidence_cannot_capture(service,adapter,url,tmp_path,monkeypatch,target):
    t,scope,p=ready_chat(service,adapter,url,tmp_path,monkeypatch)
    md=Path(p['local_path']);record=json.loads(md.with_suffix('.json').read_text(encoding='utf-8'))
    evidence=md.parent/record['evidence_file'];old=evidence.read_bytes()
    try:
        evidence.write_text('{}',encoding='utf-8')
        with pytest.raises(BusinessContractError):confirm_review(scope,host(),p['preview_id'],chat_source('通过','edited-evidence'),service)
    finally:evidence.write_bytes(old)
    assert counts(url,t)=={'core':0,'claims':0}


def test_legacy_chat_record_remains_verifiable_without_rewriting(service,adapter,url,tmp_path,monkeypatch):
    t,scope,p=ready_chat(service,adapter,url,tmp_path,monkeypatch)
    current=Path(p['local_path']);record=json.loads(current.with_suffix('.json').read_text(encoding='utf-8'))
    old=copy.deepcopy(record);old['schema']=1;old.pop('presentation');old.pop('evidence_file')
    key=digest({'session':host()['session_id'],'review':old['review_sha256']})
    folder=current.parent.parent
    path=folder/(key+'.json');path.write_text(json.dumps(old,ensure_ascii=False),encoding='utf-8')
    md=folder/(key+'.md');md.write_bytes(old['markdown'].encode('utf-8'))
    before=path.read_bytes(),md.read_bytes()
    result=confirm_review(scope,host(),key,chat_source('通过','legacy-record-confirm'),service)
    assert result['receipt']['state']=='succeeded',result
    assert (path.read_bytes(),md.read_bytes())==before
    assert counts(url,t)=={'core':1,'claims':1}
