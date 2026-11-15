"""End-to-end MCP client -> separate server -> local BGE -> real Qdrant."""
from modelcrew.project_assets import asset_path
import argparse
import json
import os
import sys
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client

from modelcrew.config import ROOT
from modelcrew.paper_search_mcp import Envelope


async def main(folder):
    folder=folder.resolve()
    folder.mkdir(exist_ok=False)
    log=folder/'calls.jsonl'
    server_args=['-m','modelcrew.paper_search_mcp','--log',str(log)]
    params=StdioServerParameters(command=sys.executable,args=server_args,
        cwd=str(ROOT),env={**{key:os.environ[key] for key in ['HF_HOME','LANG','LC_ALL'] if key in os.environ},'PYTHONIOENCODING':'utf-8','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'})
    checks=[];responses=[]
    with (folder/'server-stderr.log').open('w',encoding='utf-8') as stderr:
        async with stdio_client(params,errlog=stderr) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=180)) as session:
                init=await session.initialize()
                checks.append({'id':'initialize','passed':init.serverInfo.name=='modelcrew-paper-search','protocol_version':init.protocolVersion})
                tools=await session.list_tools()
                checks.append({'id':'discover_tool_and_schema','passed':{t.name for t in tools.tools}=={'paper_search','web_search','web_read','reference_get','algorithm_search'} and bool(tools.tools[0].outputSchema)})
                queries=json.loads((asset_path(ROOT,'stage-c/corpus/queries.json')).read_text(encoding='utf-8-sig'))
                for q in queries:
                    response=await session.call_tool('paper_search',{'query':q['query'],'limit':3,'filters':q['filters']})
                    envelope=Envelope.model_validate(response.structuredContent)
                    hits=envelope.data.hits if envelope.data else []
                    rank=next((i for i,h in enumerate(hits,1) if h.doc_id==q['expected_doc_id'] and
                        ('expected_page' not in q or h.locator.get('page')==q['expected_page']) and
                        any(t.lower() in h.text.lower() for t in q['expected_text_any'])),None)
                    checks.append({'id':q['id'],'passed':not response.isError and rank is not None,'rank':rank})
                    responses.append(response.model_dump(mode='json'))
                empty=await session.call_tool('paper_search',{'query':'generic algorithm','filters':{'year':1999}})
                checks.append({'id':'empty_is_success','passed':not empty.isError and empty.structuredContent['data']['hits']==[]})
                responses.append(empty.model_dump(mode='json'))
                for name,args,code in [
                    ('paper_search',{'query':'x','include_same_problem':'yes'},'invalid_request'),
                    ('paper_search',{'query':'x','limit':21},'invalid_request'),
                    ('unknown_tool',{'query':'x'},'unknown_tool')]:
                    response=await session.call_tool(name,args)
                    checks.append({'id':code+'_'+name,'passed':response.isError and response.structuredContent['error']['code']==code and response.structuredContent['data'] is None})
                    responses.append(response.model_dump(mode='json'))
    audit=[json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    checks.append({'id':'all_calls_audited','passed':len(audit)==len(responses) and {v['call_id'] for v in audit}=={r['structuredContent']['call_id'] for r in responses}})
    report={'date':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'status':'passed' if all(c['passed'] for c in checks) else 'failed',
            'transport':'stdio','separate_server_process':True,'sdk':'mcp==1.30.0','checks':checks,'responses':responses,
            'audit_log':str(log.relative_to(ROOT)),'new_llm_api_calls':0,'new_solve_executions':0,
            'independent_modeling_trial':False,'next_stage_gate':'stage-c/next-stage-entry-requirements.json'}
    (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':checks,'tool_calls':len(responses)}))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    anyio.run(main,args.output)
