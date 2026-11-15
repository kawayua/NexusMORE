"""Real public network -> separate stdio MCP -> immutable reference archive."""
from modelcrew.project_assets import asset_path
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from modelcrew.config import ROOT

CATALOG='https://dxs.moe.gov.cn/zx/hd/sxjm/sxjmlw/2024qgdxssxjmjslwzs/'


async def verify(folder):
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=False)
    checks=[];responses=[];log=folder/'calls.jsonl';refs=folder/'references'
    params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.paper_search_mcp',
        '--config',str(folder/'no-local-index.json'),'--references',str(refs),'--log',str(log)],
        cwd=str(ROOT),env={'PYTHONIOENCODING':'utf-8'})
    async def call(session,name,args):
        result=await session.call_tool(name,args)
        payload=result.structuredContent;responses.append(result.model_dump(mode='json'))
        if result.isError:raise RuntimeError(name+': '+json.dumps(payload['error']))
        return payload
    try:
        with (folder/'stderr.log').open('w',encoding='utf-8') as stderr:
            async with stdio_client(params,errlog=stderr) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=120)) as session:
                    await session.initialize();tools=await session.list_tools()
                    checks.append({'id':'four_tools_discovered','passed':{t.name for t in tools.tools}=={'paper_search','web_search','web_read','reference_get','algorithm_search'}})
                    broad=await call(session,'web_search',{'query':'2024A题论文','limit':10})
                    checks.append({'id':'public_search_returns_cited_candidate','passed':any('dxs.moe.gov.cn' in h['source_url'] and h['citation']['modeler_generated'] is False for h in broad['data']['hits'])})
                    search=await call(session,'web_search',{'query':'A163','scope_url':CATALOG,'limit':3})
                    hits=search['data']['hits']
                    checks.append({'id':'official_catalog_locates_same_problem_paper','passed':bool(hits) and 'A163' in hits[0]['title']})
                    paper=await call(session,'web_read',{'url':hits[0]['source_url']})
                    checks.append({'id':'paper_page_read_images_not_misrepresented_as_fulltext','passed':len(paper['data']['images'])>=40 and bool(paper['data']['content_warning'])})
                    algorithm=await call(session,'web_read',{'url':'https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.brentq.html'})
                    hit=algorithm['data']['hits'][0];citation=hit['citation'];ref_id=citation['reference_id']
                    checks.append({'id':'readable_original_text_citation_bound_to_call','passed':'brentq' in hit['text'] and citation['bound_call_id']==algorithm['call_id'] and citation['source_sha256']==hit['source_sha256']})
                    refused=await session.call_tool('web_read',{'url':'http://127.0.0.1:56333/'})
                    responses.append(refused.model_dump(mode='json'))
                    checks.append({'id':'private_network_rejected','passed':refused.isError and refused.structuredContent['error']['code']=='invalid_request'})
            async with stdio_client(params,errlog=stderr) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=120)) as session:
                    await session.initialize()
                    restored=await call(session,'reference_get',{'reference_id':ref_id})
                    checks.append({'id':'new_server_restores_same_reference_and_excerpt','passed':restored['data']['hits'][0]['citation']==citation and restored['data']['hits'][0]['text']==hit['text']})
    except Exception as exc:
        checks.append({'id':'execution_exception','passed':False,'error':str(exc)})
    audit=[json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
    checks.append({'id':'every_call_has_audit_and_reference_binding','passed':len(audit)==len(responses) and {a['call_id'] for a in audit}=={r['structuredContent']['call_id'] for r in responses} and all(a['reference_ids'] for a in audit if a['status']=='ok')})
    report={'timestamp':datetime.now(timezone.utc).isoformat(),'status':'passed' if all(c['passed'] for c in checks) else 'failed',
            'checks':checks,'responses':responses,'mcp_calls':len(responses),'new_llm_calls':0,
            'formal_solves':0,'workflow_task_version_binding':False,'ocr_performed':False}
    (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='responses'},ensure_ascii=True))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    anyio.run(verify,parser.parse_args().output)
