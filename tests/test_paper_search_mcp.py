"""MCP adapter contract checks; semantic retrieval is verified separately."""
import json
from datetime import timedelta
import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from modelcrew.config import ROOT
from modelcrew.paper_search_mcp import Envelope, SearchTool, tool_definition
from modelcrew.retrieval import RetrievalUnavailable


class FixedService:
    def search(self, query, **kwargs):
        assert type(kwargs['include_same_problem']) is bool
        return {'status':'ok','query':query,'collection':'TEST','corpus_sha256':'corpus',
                'embedding_signature':'model','include_same_problem':kwargs['include_same_problem'],'hits':[]}


def test_tool_schema_allows_reference_assisted_mode():
    schema = tool_definition().inputSchema
    assert schema['additionalProperties'] is False
    assert schema['properties']['include_same_problem']['default'] is True
    assert schema['properties']['limit']['maximum'] == 20


def test_empty_is_success_with_saved_audit(tmp_path):
    log = tmp_path/'audit.jsonl'
    result = SearchTool(FixedService, log_path=log).invoke('paper_search', {'query':'generic algorithm'})
    envelope = Envelope.model_validate(result.structuredContent)
    assert not result.isError and envelope.data.hits == []
    assert json.loads(result.content[0].text) == result.structuredContent
    audit = json.loads(log.read_text(encoding='utf-8'))
    assert audit['call_id'] == envelope.call_id and audit['status'] == 'ok'
    assert 'generic algorithm' not in log.read_text(encoding='utf-8')


def test_invalid_request_never_loads_model(tmp_path):
    def forbidden(): raise AssertionError('Invalid request loaded model')
    tool = SearchTool(forbidden, log_path=tmp_path/'audit.jsonl')
    for args in [{'query':'x','include_same_problem':'yes'}, {'query':'x','limit':True},
                 {'query':'  '}, {'query':'x','filters':{'arbitrary':'x'}}]:
        result = tool.invoke('paper_search',args)
        assert result.isError and result.structuredContent['error']['code'] == 'invalid_request'
    assert tool.invoke('unknown',{}).structuredContent['error']['code'] == 'unknown_tool'


def test_backend_fault_is_error_and_hides_details(tmp_path):
    def unavailable(): raise RetrievalUnavailable('secret connection URL')
    result = SearchTool(unavailable,log_path=tmp_path/'audit.jsonl').invoke('paper_search',{'query':'x'})
    assert result.isError and result.structuredContent['data'] is None
    assert result.structuredContent['error']['code'] == 'retrieval_unavailable'
    assert 'secret' not in result.model_dump_json()


def test_unexpected_fault_is_sanitized(tmp_path):
    def broken(): raise RuntimeError('secret path')
    result = SearchTool(broken,log_path=tmp_path/'audit.jsonl').invoke('paper_search',{'query':'x'})
    assert result.isError and result.structuredContent['error']['code'] == 'internal_error'
    assert 'secret' not in result.model_dump_json()


def test_audit_failure_does_not_return_unlogged_evidence(tmp_path):
    result = SearchTool(FixedService,log_path=tmp_path).invoke('paper_search',{'query':'x'})
    assert result.isError and result.structuredContent['data'] is None
    assert result.structuredContent['error']['code'] == 'audit_unavailable'


def test_backend_cannot_return_prohibited_evidence(tmp_path):
    class Bad(FixedService):
        def search(self,query,**kwargs):
            value=super().search(query,**kwargs);value['include_same_problem']=True;return value
    result=SearchTool(Bad,log_path=tmp_path/'audit.jsonl').invoke('paper_search',{'query':'x','include_same_problem':False})
    assert result.isError and result.structuredContent['error']['code']=='retrieval_unavailable'


def test_stdio_protocol_initialization_discovery_and_errors(tmp_path):
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.paper_search_mcp',
            '--web-only','--config',str(tmp_path/'missing.json'),'--log',str(tmp_path/'stdio.jsonl')],
            cwd=str(ROOT),env={'PYTHONIOENCODING':'utf-8','HF_HUB_OFFLINE':'1'})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=20)) as session:
                initialized=await session.initialize()
                assert initialized.serverInfo.name=='modelcrew-paper-search'
                tools=await session.list_tools()
                assert {t.name for t in tools.tools}=={'paper_search','web_search','web_read','reference_get','algorithm_search'}
                result=await session.call_tool('paper_search',{'query':'x','include_same_problem':'yes'})
                assert result.isError and result.structuredContent['error']['code']=='invalid_request'
                result=await session.call_tool('paper_search',{'query':'x'})
                assert result.isError and result.structuredContent['error']['code']=='retrieval_unavailable'
    anyio.run(exercise)
