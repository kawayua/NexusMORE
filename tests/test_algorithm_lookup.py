"""New algorithm entrypoints share installed references; history never silently rebases."""
import json
import os
import sys
from pathlib import Path
import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client
from modelcrew.algorithm_knowledge import load_catalog
from modelcrew.algorithm_retrieval import AlgorithmRequest,AlgorithmRetriever
from modelcrew.algorithm_lookup import BuiltinAlgorithmSearch,builtin_context
from modelcrew.collaboration_retrieval import algorithm_context
from modelcrew.paper_search_mcp import SearchTool
from modelcrew.retrieval import RetrievalUnavailable


@pytest.fixture(autouse=True)
def builtin_default(monkeypatch):
    monkeypatch.delenv('MODELCREW_ALGORITHM_CONFIG',raising=False)


@pytest.mark.parametrize('category',['optimization','prediction','evaluation','graph','statistics','simulation','machine-learning'])
def test_every_installed_category_has_exact_id_lookup(category):
    catalog=load_catalog();cat=next(c for c in catalog['categories'] if c['id']==category)
    key=cat['algorithm_ids'][0]
    result=AlgorithmRetriever().search(AlgorithmRequest(query=key,category=category))
    assert result['provider']=='builtin_algorithm_literal_lookup' and result.get('embedding_signature') is None
    hit=result['hits'][0];assert hit['doc_id']==key and hit['score_kind']=='literal_match_weight_not_semantic_probability'
    assert hit['source_sections'][0]['text']==hit['text']
    assert hit['applicability']['status']=='needs_review' and hit['formal_approval'] is False


def test_defaults_never_load_legacy_or_embeddings(monkeypatch,tmp_path):
    import modelcrew.algorithm_retrieval as module
    def forbidden(*a,**k):pytest.fail('Default installed lookup accessed legacy vectors')
    monkeypatch.setattr(module,'LegacyAlgorithmRetriever',forbidden)
    monkeypatch.setattr(module,'LocalBge',forbidden)
    monkeypatch.setattr(module,'QdrantClient',forbidden)
    result=AlgorithmRetriever().search(AlgorithmRequest(query='线性规划'))
    assert result['hits'][0]['doc_id']=='lp'
    assert algorithm_context('prediction')['legacy_runtime_catalog_used'] is False


@pytest.mark.parametrize('configured', [False,True])
def test_explicit_missing_legacy_config_fails_without_builtin_fallback(monkeypatch,tmp_path,configured):
    import modelcrew.algorithm_lookup as module
    def forbidden(*a,**k):pytest.fail('Explicit broken legacy config silently fell back')
    monkeypatch.setattr(module,'BuiltinAlgorithmSearch',forbidden)
    missing=tmp_path/'missing.json'
    if configured:
        monkeypatch.setenv('MODELCREW_ALGORITHM_CONFIG',str(missing))
        action=lambda:AlgorithmRetriever()
    else:action=lambda:AlgorithmRetriever(missing)
    with pytest.raises(RetrievalUnavailable):action()


@pytest.mark.parametrize('ids',[[],['lp','lp'],['unknown-id']])
def test_context_rejects_invalid_or_ambiguous_selections(ids):
    with pytest.raises(ValueError):algorithm_context('optimization',card_ids=ids)


def test_false_or_unknown_premises_are_not_approved():
    assert not AlgorithmRetriever().search(AlgorithmRequest(query='lp',facts={'lp_premises_verified':False}))['hits']
    for facts in ({'continuous_variables':False},{'linear_objective_constraints':False},{'integer_variables':True}):
        rejected=AlgorithmRetriever().search(AlgorithmRequest(query='lp',facts=facts))
        assert not rejected['hits'] and rejected['excluded']
    result=AlgorithmRetriever().search(AlgorithmRequest(query='lp',facts={'lp_premises_verified':True},available_dependencies=[],variable_count=100000))
    hit=result['hits'][0]
    assert hit['applicability']['status']=='needs_review'
    assert hit['applicability']['scale_status']=='unbounded_not_certified'
    assert hit['general_business_solver_registered'] is False
    assert algorithm_context('geometry',card_ids=['bracketed-root'],facts={'continuous_on_bracket':False})['status']=='no_applicable_cards'


def test_unmatched_is_empty_and_legacy_verification_not_invented():
    backend=BuiltinAlgorithmSearch()
    assert backend.search(AlgorithmRequest(query='zzzz_nonexistent_algorithm_7349'))['hits']==[]
    rejected=backend.search(AlgorithmRequest(query='lp',verification='reviewed_numeric_baseline'))
    assert rejected['hits']==[] and 'not_certified' in rejected['excluded'][0]['reasons'][0]
    assert not backend.search(AlgorithmRequest(query='arima',category='optimization'))['hits']


def test_index_is_read_before_catalog(monkeypatch):
    import modelcrew.algorithm_lookup as module
    events=[];original_resource=module.resource;original_load=module.load_catalog
    def read(name):events.append(('resource',name));return original_resource(name)
    def load():events.append(('catalog','load'));return original_load()
    monkeypatch.setattr(module,'resource',read);monkeypatch.setattr(module,'load_catalog',load)
    module.BuiltinAlgorithmSearch().search(AlgorithmRequest(query='no-match'))
    assert events[0]==('resource','algorithms/index.md')


def test_resource_failure_is_unavailable_not_empty_or_legacy(monkeypatch,tmp_path):
    import modelcrew.algorithm_lookup as module
    def bad():raise ValueError('TEST corrupted installed manifest')
    monkeypatch.setattr(module,'load_catalog',bad)
    response=SearchTool(log_path=tmp_path/'calls.jsonl').invoke('algorithm_search',{'query':'lp'})
    assert response.isError and response.structuredContent['error']['code']=='retrieval_unavailable'
    assert response.structuredContent['data'] is None


def test_builtin_citation_archive_keeps_authorship_and_exact_content(tmp_path):
    tool=SearchTool(log_path=tmp_path/'calls.jsonl')
    first=tool.invoke('algorithm_search',{'query':'lp'}).structuredContent
    assert first['status']=='ok'
    hit=first['data']['hits'][0];citation=hit['citation']
    assert citation['origin']=='builtin_project_reference' and '枢模内置' in citation['label']
    again=tool.invoke('reference_get',{'reference_id':citation['reference_id']}).structuredContent
    archived=again['data']['hits'][0]
    assert archived['text']==hit['text'] and archived['citation']==citation
    tool.close()  # The installed backend has no Qdrant client to close.


def test_clean_workspace_stdio_lookup_needs_no_index_or_embedding(tmp_path):
    async def exercise():
        env={'MODELCREW_WORKSPACE':str(tmp_path),'PYTHONIOENCODING':'utf-8'}
        params=StdioServerParameters(command=sys.executable,args=['-m','modelcrew.paper_search_mcp','--web-only','--log',str(tmp_path/'calls.jsonl')],env=env)
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                definitions=(await session.list_tools()).tools
                definition=next(t for t in definitions if t.name=='algorithm_search')
                assert 'prediction' in definition.inputSchema['properties']['category']['anyOf'][0]['enum']
                assert definition.annotations.openWorldHint is False
                response=await session.call_tool('algorithm_search',{'query':'arima','category':'prediction'})
                assert not response.isError,response.structuredContent
                result=response.structuredContent['data']
                assert result['hits'][0]['doc_id']=='arima' and result['embedding_signature'] is None
    anyio.run(exercise)
    assert not (tmp_path/'runs/algorithm-retrieval').exists()


def test_full_doctor_uses_installed_algorithm_resources_without_stale_default(tmp_path):
    from modelcrew.user_workspace import initialize,doctor,configuration_summary
    initialize(tmp_path)
    stale=tmp_path/'runs/algorithm-retrieval/index.json';stale.parent.mkdir(parents=True);stale.write_text('NOT VALID OLD JSON')
    summary=configuration_summary(tmp_path)
    assert summary['algorithm_retrieval_mode']=='installed_literal_lookup'
    result=doctor(tmp_path,profile='full')
    algorithm=next(c for c in result['checks'] if c['name']=='algorithm_index')
    assert algorithm['status']=='passed' and algorithm['embedding_required'] is False
    assert stale.read_text()=='NOT VALID OLD JSON'


def test_explicit_historical_catalog_never_rebases_to_installed_index():
    from modelcrew.retrieval_paths import algorithm_catalog_path
    from modelcrew.config import ROOT
    from modelcrew.project_assets import asset_path
    from modelcrew.collaboration import sha_file
    path=algorithm_catalog_path(ROOT)
    original=path.read_bytes();catalog=json.loads(original)
    if catalog['index']['sha256']!=sha_file(asset_path(ROOT,'resources/algorithms/index.md')):
        with pytest.raises(RetrievalUnavailable,match='rebuild catalog'):
            algorithm_context('geometry',card_ids=['bracketed-root'],catalog_path=path.relative_to(ROOT).as_posix())
        assert path.read_bytes()==original


@pytest.mark.parametrize('module',['scripts.index_algorithms','scripts.prepare_algorithm_catalog','scripts.verify_cplus_retrieval'])
def test_legacy_maintenance_requires_explicit_inputs(module):
    import subprocess
    result=subprocess.run([sys.executable,'-m',module],capture_output=True,text=True)
    assert result.returncode==2 and 'required' in result.stderr


def test_all_113_canonical_ids_resolve_to_their_own_complete_section():
    backend=BuiltinAlgorithmSearch();catalog=load_catalog()
    assert len(catalog['algorithms'])==113
    for card in catalog['algorithms']:
        value=backend.search(AlgorithmRequest(query=card['id'],category=card['categories'][0],limit=1))
        assert value['hits'] and value['hits'][0]['doc_id']==card['id'],card['id']
        hit=value['hits'][0]
        assert hit['source_sections'][0]['text']==hit['text']
        assert hit['source_sections'][0]['line_end']>=hit['source_sections'][0]['line_start']
