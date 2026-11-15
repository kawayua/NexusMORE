"""Validate installed algorithm entrypoints through actual stdio and PostgreSQL; no model/solver/approval."""
import argparse
import json
import sys
import uuid
from pathlib import Path
from datetime import timedelta
import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
from modelcrew.config import ROOT
from modelcrew.algorithm_knowledge import load_catalog
from modelcrew.workflow import Workflow
from modelcrew.contracts import digest
from scripts.c5_fixture import contract_for


def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str)


async def stdio_checks(folder):
    workspace=folder/'clean-workspace';workspace.mkdir()
    params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.paper_search_mcp','--web-only','--log',str(folder/'stdio-audit.jsonl'),'--references',str(folder/'references')],
        cwd=str(ROOT),env={'MODELCREW_WORKSPACE':str(workspace),'PYTHONIOENCODING':'utf-8'})
    responses=[];checks=[]
    async with stdio_client(params) as (read,send):
        async with ClientSession(read,send,read_timeout_seconds=timedelta(seconds=120)) as session:
            await session.initialize()
            tools=(await session.list_tools()).tools
            write(folder/'tool-discovery.json',[t.model_dump(mode='json') for t in tools])
            async def call(name,args):
                result=await session.call_tool(name,args);responses.append(result.model_dump(mode='json'))
                if result.isError:raise RuntimeError(str(result.structuredContent['error']))
                return result.structuredContent['data']
            first=None
            for category in load_catalog()['categories']:
                key=category['algorithm_ids'][0]
                result=await call('algorithm_search',{'query':key,'category':category['id']})
                hit=result['hits'][0]
                assert hit['doc_id']==key and result['provider']=='builtin_algorithm_literal_lookup'
                assert hit['citation']['origin']=='builtin_project_reference' and result['embedding_signature'] is None
                checks.append({'id':'installed_'+category['id'],'passed':True,'algorithm':key})
                if first is None:first=hit
            denied=await call('algorithm_search',{'query':'bracketed-root','category':'geometry','facts':{'continuous_on_bracket':False}})
            assert not denied['hits'] and denied['excluded']
            lp_denied=await call('algorithm_search',{'query':'lp','category':'optimization','facts':{'continuous_variables':False}})
            assert not lp_denied['hits'] and lp_denied['excluded']
            checks.append({'id':'explicit_noncontinuous_lp_excluded','passed':True})
            empty=await call('algorithm_search',{'query':'zzzz_nonexistent_7349'})
            assert empty['hits']==[]
            recovered=await call('reference_get',{'reference_id':first['citation']['reference_id']})
            assert recovered['hits'][0]['citation']==first['citation'] and recovered['hits'][0]['text']==first['text']
            checks.extend([{'id':'false_geometry_premise_excluded','passed':True},{'id':'unknown_query_empty','passed':True},{'id':'archive_recovery_same_binding','passed':True}])
    assert not (workspace/'runs/algorithm-retrieval').exists()
    write(folder/'stdio-responses.json',responses)
    return checks,len(responses)


def validate(output):
    output=output.resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Output must be within workspace')
    output.mkdir(parents=True,exist_ok=False)
    from modelcrew.collaboration import sha_file
    sources=['src/modelcrew/algorithm_lookup.py','src/modelcrew/algorithm_retrieval.py','src/modelcrew/collaboration_retrieval.py','src/modelcrew/paper_search_mcp.py','src/modelcrew/mcp_client.py','src/modelcrew/web_references.py','src/modelcrew/mcp_workflow.py']
    identity={name:sha_file(ROOT/name) for name in sources}
    write(output/'implementation-before.json',identity)
    checks,calls=anyio.run(stdio_checks,output)
    data=output/'engineering-input.json';data.write_text('[1,2,3]',encoding='utf-8')
    task='algorithm-lookup-validation-'+uuid.uuid4().hex[:12]
    with Workflow() as w:
        production='production-allocation-live-20261114'
        prior=w.task(production)
        run=w.hand_status(production,'4b5d1f79-d7ef-4bb1-ba59-1706b4fbaa93')
        w.create(task,contract_for(data),project='automated-tests')
        kwargs={'version':1,'tool':'algorithm_search','arguments':{'query':'lp','category':'optimization'},'actor':'ENGINEERING_PROBE','request_id':'installed-lp-v1'}
        response=w.retrieve_references(task,**kwargs)
        assert response['envelope']['status']=='ok'
        hit=response['envelope']['data']['hits'][0]
        assert hit['doc_id']=='lp' and hit['citation']['origin']=='builtin_project_reference'
        assert w.retrieve_references(task,**kwargs)==response
        evidence=w.tool_evidence(task)
        assert len(evidence['references'])==1 and len(evidence['mcp_traces'])==2
        assert not w.task(task)['model_approved'] and not w.task(task)['result_revision']
        assert w.task(production)==prior and w.hand_status(production,run['run_id'])==run
        checks.extend([{'id':'real_workflow_mcp_and_reference_binding','passed':True},{'id':'idempotent_no_extra_mcp','passed':True},
            {'id':'engineering_no_approval_or_solver','passed':True},{'id':'production_task_unchanged','passed':True}])
        write(output/'workflow-evidence.json',{'task_id':task,'response':response,'evidence':evidence,'business_state':w.task(task),
            'production_state':run,'production_task_sha256':digest(json.loads(json.dumps(prior,default=str)))})
    assert all(sha_file(ROOT/name)==value for name,value in identity.items())
    report={'implementation_sha256':identity,'status':'passed','checks':checks,'actual_stdio_calls':calls,'actual_workflow_mcp_calls':1,
        'categories':7,'new_model_calls':0,'new_solver_runs':0,'user_approvals_created':0,
        'embedding_or_vector_index_used':False,'production_phase':run['phase'],
        'scope':'Installed literal references, actual stdio/archive/real PostgreSQL idempotency; not semantic ranking, modeling review or full solving'}
    write(output/'verification.json',report)
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);validate(p.parse_args().output)
