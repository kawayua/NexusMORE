"""Native assembly review routing/capture in a disposable synthetic database."""
import uuid,json,copy
from pathlib import Path
import pytest
from psycopg.types.json import Jsonb
from test_business_mcp import url,adapter,task
from test_dsh_decisions import service,host,chat_source
from modelcrew.workflow import Workflow
from modelcrew import assembly_builds as ab
from modelcrew import assembly_compose as ac
from modelcrew.contracts import digest
from modelcrew.dsh_chat import prepare_review,confirm_review
from modelcrew.business_contract import BusinessContractError
from test_assembly_builds import source


@pytest.mark.parametrize('mode',['approve','changed_source','partial_failure','unrelated'])
def test_task_chat_routes_to_assembly_and_confirms_both_or_neither(adapter,service,url,tmp_path,monkeypatch,mode):
    p,t,*_=task(adapter,url,tmp_path);rid=str(uuid.uuid4());bid=str(uuid.uuid4());root=ab.folder(bid)/'source'
    source('q1',root,0)
    sealed={ab.rel(f):ab.sha_file(f) for f in root.rglob('*') if f.is_file()}
    payload={'source_ready':True,'sealed':sealed,'context_identity':'a'*64,'decisions':{}}
    def guard(w,project,row):
        for path,sha in row['payload']['sealed'].items():
            if ab.sha_file(ab.workspace_path(ab.ROOT,path))!=sha:raise ValueError('TEST_ONLY source changed')
    monkeypatch.setattr(ab,'guard',guard)
    with Workflow(url) as w:
        w.action(t,version=1,actor='TEST_SIMULATED_USER',request_id='approve-model-fixture',kind='model',decision='approve',defer_execution=True)
        w.db.execute('INSERT INTO mc_assembly_runs(id,project_id,request_id,request_sha256,payload) VALUES(%s,%s,%s,%s,%s)',(rid,p,'TEST_ASSEMBLY_INPUT','a'*64,Jsonb({'chapters':[{'question_id':'q1','task_id':('UNRELATED_TASK' if mode=='unrelated' else t),'run_id':'TEST_WRITER'}]})))
        w.db.execute('INSERT INTO mc_assembly_builds(id,assembly_run_id,project_id,request_id,request_sha256,phase,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)',(bid,rid,p,'TEST_ASSEMBLY_BUILD','b'*64,'WAITING_ASSEMBLY_REVIEW',Jsonb(payload)))
    scope={'project_id':p,'task_id':t};h={**host(),'session_id':'TEST_ASSEMBLY_'+uuid.uuid4().hex}
    assert service.pending(scope)==[]
    preview=prepare_review(scope,h,chat_source('展示','before'),service)
    if mode=='unrelated':
        assert preview['status']=='no_pending'
        with Workflow(url) as w:assert not w.db.execute("SELECT 1 FROM mc_trusted_user_events WHERE request->'arguments'->>'build_id'=%s",(bid,)).fetchone()
        return
    assert preview['status']=='waiting_for_user' and preview['binding']['build_id']==bid
    assert preview['confirmation_scope']=='manuscript_and_figures' and preview['markdown'].count('### 候选图 ')==9
    if mode=='changed_source':
        md=root/ac.MD_NAME;md.write_bytes(md.read_bytes()+b' CHANGED')
        with pytest.raises((BusinessContractError,ValueError)):confirm_review(scope,h,preview['preview_id'],chat_source('确认','after'),service)
    else:
        if mode=='partial_failure':
            from modelcrew import writing_reviews
            def fail(*a,**kw):raise ValueError('TEST_ONLY second record failed')
            monkeypatch.setattr(writing_reviews,'selection_record',fail)
        response=confirm_review(scope,h,preview['preview_id'],chat_source('确认','after'),service)
        if mode=='approve':
            assert response['receipt']['state']=='succeeded',response
            assert response['data']['user_decision']['confirmation_scope']=='manuscript_and_figures'
            assert confirm_review(scope,h,preview['preview_id'],chat_source('确认','after'),service)['status']=='already_received'
        else:assert response['status']=='outcome_unknown'
    with Workflow(url) as w:
        row=ab.load(w,p,bid);assert bool(row['payload'].get('manuscript_review'))==bool(row['payload'].get('figure_review'))==(mode=='approve')
        if mode=='approve':
            assert row['phase']=='READY_TO_EXPORT' and ab.reviews(row)['can_export']
            event=w.db.execute("SELECT request FROM mc_trusted_user_events WHERE request->'arguments'->>'build_id'=%s",(bid,)).fetchone()['request']
            assert row['payload']['decisions'][event['request_id']]['request_sha256']==digest(event['arguments']['body'])
            assert event['operation']=='assembly_decide'
        n=w.db.execute("SELECT count(*) AS n FROM mc_trusted_user_event_claims c JOIN mc_trusted_user_events e USING(event_id) WHERE e.request->'arguments'->>'build_id'=%s",(bid,)).fetchone()['n']
        assert n==(1 if mode!='changed_source' else 0)
