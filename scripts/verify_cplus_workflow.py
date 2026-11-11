"""Real algorithm MCP -> version-bound proposed adoption, with no approval/run."""
import argparse,json,uuid
from pathlib import Path
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.workflow import Workflow
from modelcrew.contracts import digest


def verify(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    load=lambda path:json.loads((ROOT/path).read_text(encoding='utf-8'))
    task='cplus-resource-'+uuid.uuid4().hex[:10]
    with Workflow() as w:
        before=w.task('dragon-q1')
        w.create(task,load('stage-b-plus/examples/resource-contract.json'),project='cplus-verification',math_package=load('stage-b-plus/examples/valid-resource.json'))
        args=dict(version=1,tool='algorithm_search',arguments={'query':'连续资源分配的线性规划适用条件与求解接口','category':'optimization','facts':{'linear_objective_constraints':True,'continuous_variables':True,'integer_variables':False},'variable_count':2,'available_dependencies':['scipy']},actor='CPLUS_ENGINEERING_PROBE',request_id='algorithm-query')
        result=w.retrieve_references(task,**args)
        assert result['envelope']['status']=='ok'
        hits=result['envelope']['data']['hits'];selected=next(h for h in hits if h['doc_id']=='continuous-lp')
        assert selected['applicability']['status']=='premises_satisfied'
        assert w.retrieve_references(task,**args)==result
        discussion=w.discuss_references(task,version=1,kind='proposal',text='Engineering-authored proposal only: consider continuous LP because this synthetic B+ package has divisible continuous variables, fixed linear objective and linear capacity constraints. Integer LP is unnecessary. This external excerpt supports method selection; it is not modeler-original work, an autonomous modeler discussion, or user approval.',references=[{'reference_id':h['citation']['reference_id'],'decision':'adopted' if h is selected else 'rejected'} for h in hits],actor='CPLUS_ENGINEERING_PROBE',request_id='method-reason')
        evidence=w.tool_evidence(task,1);current=w.task(task);after=w.task('dragon-q1')
        checks={'citation_version_binding':all(r['version']==1 and r['task_id']==task for r in evidence['references']),
                'complete_external_source':all(h['source_sections'] and h['citation']['modeler_generated'] is False for h in hits),
                'adoption_reason_recorded':bool(discussion['entry_id']) and len(evidence['reference_discussions'])==1,
                'idempotent_one_mcp_call':len(evidence['mcp_traces'])==2,
                'unapproved_no_execution':not current['model_approved'] and current['phase']=='WAITING_MODEL_APPROVAL',
                'formal_task_unchanged':before==after}
        report={'timestamp':datetime.now(timezone.utc).isoformat(),'status':'passed' if all(checks.values()) else 'failed','checks':checks,'task_id':task,'state':current,'query':result,'discussion':discussion,'evidence':evidence,'formal_task_before':before,'formal_task_after':after,'new_llm_calls':0,'new_contest_solver_runs':0,'new_real_user_approvals':0,'scope':'Engineering-authored synthetic proposal, not autonomous modeler collaboration or user adoption.'}
        (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps({'status':report['status'],'checks':checks,'task_id':task}))
        if report['status']!='passed':raise RuntimeError('Workflow check failed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);verify(p.parse_args().output)
