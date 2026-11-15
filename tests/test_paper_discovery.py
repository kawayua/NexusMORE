"""Candidate grouping and actual existing MCP adapter error/evidence behavior."""
import json
from types import SimpleNamespace
import pytest
from modelcrew.paper_discovery import candidates,discover,normalized_doi


def record(source='local',doi=None,**kwargs):
    return {'source':source,'doi':doi,'title':'A study of a model','year':2023,'authors':['Author'],**kwargs}


def test_doi_groups_keep_conflicting_fields_and_original_records():
    a=record(doi='HTTPS://DOI.ORG/10.1234/ABC');b=record('web',doi='doi:10.1234/abc',year=2024)
    result=candidates([a,b]);group=result['candidates'][0]
    assert len(result['candidates'])==1 and len(group['records'])==2
    assert group['conflicts']['year']==[2023,2024]
    assert group['verification']=='UNVERIFIED_CANDIDATE' and not result['user_approval']
    assert normalized_doi('https://example.test/10.1234/abc') is None


def test_same_title_different_doi_and_versions_not_collapsed():
    result=candidates([record(doi='10.1234/one'),record('web',doi='10.1234/two')])
    assert len(result['candidates'])==2 and result['possible_matches']==[]


def test_title_suggestions_are_one_to_one_without_merging():
    result=candidates([record('a'),record('b'),record('c')])
    assert len(result['candidates'])==3 and len(result['possible_matches'])==1
    assert result['possible_matches'][0]['merge_performed'] is False


def test_year_filter_applies_to_all_sources_and_missing_year_is_excluded():
    result=candidates([record('a',year=2020),record('b',year=None),record('c',year=2024)],year_from=2023)
    assert len(result['candidates'])==1 and len(result['excluded'])==2
    with pytest.raises(ValueError):candidates([],year_from=2024,year_to=2020)


class Replies:
    def invoke(self,name,args):
        if name=='web_search':return SimpleNamespace(structuredContent={'status':'error','error':{'code':'web_unavailable'}})
        return SimpleNamespace(structuredContent={'status':'ok','call_id':'probe','data':{'hits':[]}})


def test_empty_and_partial_failure_are_distinct_and_evidence_is_durable(tmp_path):
    empty=discover('model',tmp_path/'empty',adapter=Replies())
    partial=discover('model',tmp_path/'partial',sources=['paper_search','web_search'],adapter=Replies())
    assert empty['status']=='empty' and partial['status']=='partial'
    assert (tmp_path/'partial/web_search.json').is_file()
    with pytest.raises(FileExistsError):discover('model',tmp_path/'partial',adapter=Replies())


def test_actual_mcp_adapter_failure_is_not_empty_success(tmp_path):
    from modelcrew.paper_search_mcp import SearchTool
    from modelcrew.retrieval import RetrievalUnavailable
    def unavailable():raise RetrievalUnavailable('private connection details')
    adapter=SearchTool(unavailable,log_path=tmp_path/'audit.jsonl')
    result=discover('model',tmp_path/'attempt',adapter=adapter)
    assert result['status']=='failed' and result['sources'][0]['code']=='retrieval_unavailable'
    assert 'private connection' not in json.dumps(result)
    assert (tmp_path/'attempt/paper_search.json').is_file()
    assert (tmp_path/'audit.jsonl').is_file()


def test_actual_mcp_success_archives_original_citation(tmp_path):
    from modelcrew.paper_search_mcp import SearchTool
    class Service:
        def search(self,query,**kwargs):
            return {'status':'ok','query':query,'include_same_problem':True,'hits':[
              {'doc_id':'doc','chunk_id':'chunk','text':'A synthetic method excerpt','source_url':'https://doi.org/10.1234/example',
               'source_sha256':'a'*64,'parser':'fixture','locator':{'page':1},'score':0.8,'same_problem_reference':False}]}
    adapter=SearchTool(Service,log_path=tmp_path/'audit.jsonl',references=tmp_path/'refs')
    result=discover('model',tmp_path/'attempt',adapter=adapter)
    assert result['status']=='ok',result
    candidate=result['candidates'][0];assert candidate['doi']=='10.1234/example'
    record=candidate['records'][0]['original'];reference=adapter.references.get(record['reference_id'])
    assert reference['citation']['reference_id']==record['reference_id']


@pytest.mark.parametrize('args',[{'sources':['openalex']},{'sources':[]},{'sources':['paper_search','paper_search']},{'limit':True},{'limit':11}])
def test_invalid_requests_do_not_create_attempt(tmp_path,args):
    with pytest.raises(ValueError):discover('model',tmp_path/'attempt',adapter=Replies(),**args)
    assert not (tmp_path/'attempt').exists()
