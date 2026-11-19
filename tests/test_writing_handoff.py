"""Approved-result writer handoff, with explicitly synthetic model/executor fixtures."""
import copy,json
from pathlib import Path
import pytest
from modelcrew import hand_runtime as hr
from modelcrew.workflow import Workflow,WorkflowError
from modelcrew.business_adapter import BusinessAdapter
from modelcrew.business_projection import binding
from test_hand_runtime import task,execution,Provider,start,until,isolated_host_repair_permission


def test_completed_result_can_start_writer_without_recreating_task_or_catalog(task,execution):
    with Workflow() as w:
        coding=start(w,task)['run_id'];until(w,task,coding,Provider(),'ATTACHED')
        w.action(task,actor='TEST_SIMULATED_USER',request_id='confirm-result-for-paper',version=1,kind='result',decision='approve',result_revision=1)
        baseline=copy.deepcopy(w.task(task));assert baseline['phase']=='COMPLETED'
        writer=w.start_hand(task,'writing',version=1,actor='TEST_OPERATOR',request_id='auto-writer',guidance='SYNTHETIC read-only handoff')
        assert writer['phase']=='PLAN' and writer['binding']['execution_id']==str(baseline['execution_id'])
        after=w.task(task);assert (after['current_version'],after['result_revision'],after['result_approved'],str(after['execution_id']))==(1,1,True,str(baseline['execution_id']))
        row=hr.load(w,task,writer['run_id']);folder=hr.run_folder(row);result=hr.read(folder/'result.json');assert result['values'] and result['acceptance_context']['read_only_approved_result']
        assert all(':' not in Path(a['path']).name for f in hr.read(folder/'figure-catalog.json')['figures'] for a in f['files'].values())
        assert len(execution[1])==3  # original synthetic minimal/full/replica only
        assert w.start_hand(task,'writing',version=1,actor='TEST_OPERATOR',request_id='auto-writer',guidance='SYNTHETIC read-only handoff')['run_id']==writer['run_id']


def test_unconfirmed_result_is_rejected_before_business_claim(task,execution):
    with Workflow() as w:
        coding=start(w,task)['run_id'];until(w,task,coding,Provider(),'ATTACHED');bound=binding(w,{'task_id':task})
    req={'contract_version':'1.0.0','operation':'hand_start','request_id':'writer-before-result-approval','expected_binding':bound,'arguments':{'task_id':task,'hand':'writing','body':{'version':1,'actor':'TEST_ONLY','request_id':'writer-before-result-approval','guidance':'SYNTHETIC request must be rejected'}}}
    response=BusinessAdapter().invoke('hand_start',req)
    assert response['status']=='error' and response['error']['code']=='workflow_conflict'
    with Workflow() as w:
        assert not w.db.execute('SELECT 1 FROM mc_business_operations WHERE resource_key=%s AND request_id=%s',('task:'+task,'writer-before-result-approval')).fetchone()
        assert not w.db.execute("SELECT 1 FROM mc_hand_runs WHERE task_id=%s AND hand='writing'",(task,)).fetchone()
