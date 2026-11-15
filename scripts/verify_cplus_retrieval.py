"""Explicit legacy six-card BGE/Qdrant probe; never the default installed lookup."""
import argparse,json,os,sys,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
from modelcrew.config import ROOT
from modelcrew.retrieval_paths import algorithm_config_path
from modelcrew.runtime_paths import data_root
from modelcrew.workflow import Workflow
from scripts.c5_fixture import contract_for


async def verify(folder, config):
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=False);checks=[];responses=[]
    config=algorithm_config_path(ROOT,config)
    params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.paper_search_mcp','--log',str(folder/'calls.jsonl'),'--references',str(folder/'references')],
        cwd=str(ROOT),env={**{k:os.environ[k] for k in ('HF_HOME',) if k in os.environ},'MODELCREW_ALGORITHM_CONFIG':str(config),'PYTHONIOENCODING':'utf-8','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'})
    async def call(session,args):
        result=await session.call_tool('algorithm_search',args);responses.append(result.model_dump(mode='json'))
        if result.isError:raise RuntimeError(str(result.structuredContent['error']))
        return result.structuredContent['data']
    with (folder/'server-stderr.log').open('w',encoding='utf-8') as stderr:
        async with stdio_client(params,errlog=stderr) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as session:
                await session.initialize();tools=await session.list_tools();checks.append({'id':'algorithm_tool_discovered','passed':'algorithm_search' in {t.name for t in tools.tools}})
                for query,expected,extras in [
                    ('标量连续函数异号区间用Brent求根','bracketed-root',{'layer':'numerical_algorithm','category':'geometry'}),
                    ('连续资源分配线性规划目标和约束','continuous-lp',{'category':'optimization','facts':{'continuous_variables':True,'integer_variables':False}}),
                    ('常微分方程初值积分的误差控制与事件','ivp-integrator',{'category':'simulation'}),
                    ('scipy brentq 接口的xtol和rtol','brentq-api',{'layer':'api'})]:
                    value=await call(session,{'query':query,'limit':3,**extras});rank=next((i for i,h in enumerate(value['hits'],1) if h['doc_id']==expected),None)
                    checks.append({'id':'semantic_'+expected,'passed':rank is not None,'rank':rank})
                    checks.append({'id':'source_and_citation_'+expected,'passed':all(h['source_sections'] and all(s['text'] in h['text'] for s in h['source_sections']) and h['citation']['modeler_generated'] is False for h in value['hits'])})
                value=await call(session,{'query':'Brent求根','category':'geometry','layer':'numerical_algorithm','facts':{'continuous_on_bracket':False}})
                checks.append({'id':'discontinuous_bracket_excluded','passed':value['hits']==[] and any('premise_failed:continuous_on_bracket' in c['reasons'] for c in value['excluded'])})
                value=await call(session,{'query':'连续LP','category':'optimization','facts':{'continuous_variables':False,'integer_variables':True}})
                checks.append({'id':'integer_case_does_not_use_continuous_relaxation','passed':all(h['doc_id']!='continuous-lp' for h in value['hits']) and any(c['id']=='continuous-lp' for c in value['excluded'])})
                value=await call(session,{'query':'算法','available_dependencies':[],'variable_count':100000})
                checks.append({'id':'dependency_and_scale_filters','passed':all(h['doc_id']=='geometry-model' for h in value['hits']) and len(value['excluded'])==5})
                value=await call(session,{'query':'Brent','category':'geometry','layer':'numerical_algorithm'})
                checks.append({'id':'unknown_premises_not_claimed_verified','passed':value['hits'][0]['applicability']['status']=='needs_review'})
    audit=[json.loads(line) for line in (folder/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
    checks.append({'id':'all_calls_and_reference_ids_audited','passed':len(audit)==len(responses) and all(a['reference_ids'] or r['structuredContent']['data']['hits']==[] for a,r in zip(audit,responses,strict=True))})
    report={'timestamp':datetime.now(timezone.utc).isoformat(),'status':'passed' if all(c['passed'] for c in checks) else 'failed','checks':checks,'responses':responses,'calls':len(responses),'new_llm_calls':0}
    (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='responses'},ensure_ascii=True))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--config',type=Path,required=True);args=parser.parse_args();anyio.run(verify,args.output,args.config)
