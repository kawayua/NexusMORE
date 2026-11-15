"""Condition and provenance boundaries; synthetic vectors do not evaluate semantics."""
from modelcrew.project_assets import asset_path,local_history
import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient
from modelcrew.config import ROOT
from modelcrew.retrieval_paths import algorithm_catalog_path
from modelcrew.algorithm_retrieval import AlgorithmRequest,LegacyAlgorithmRetriever,assess,verify_sources,build_index
from modelcrew.retrieval import RetrievalUnavailable
from scripts.build_cplus_export import safe_math,tex_source
from modelcrew.mathematics import validate_package


@pytest.fixture
def catalog():
    # Isolated current-index test fixture exercises legacy vector guards. The historical catalog stays byte-identical.
    from modelcrew.contracts import digest
    from modelcrew.collaboration import sha_file
    value=json.loads(algorithm_catalog_path(ROOT).read_text(encoding='utf-8'))
    value['index']['sha256']=sha_file(asset_path(ROOT,'resources/algorithms/index.md'))
    value['scope']='TEST_ONLY legacy card/vector behavior with current-index fixture; not historical admission'
    value['catalog_sha256']=digest({k:v for k,v in value.items() if k!='catalog_sha256'})
    return value


class Vectors:
    signature='TEST_SYNTHETIC';dimension=2
    def encode(self,texts,**kwargs):return [[1.,0.] for _ in texts]


@pytest.mark.parametrize('arguments',[{'query':'x','facts':{'linear':1}},{'query':'x','variable_count':True},{'query':'x','layer':'arbitrary'},{'query':'x','limit':11}])
def test_request_strictness(arguments):
    with pytest.raises(ValidationError):AlgorithmRequest.model_validate(arguments)


def test_condition_failure_and_unknown_are_distinct(catalog):
    card=next(c for c in catalog['cards'] if c['id']=='bracketed-root')
    unknown=assess(card,AlgorithmRequest(query='root'))
    assert unknown['status']=='needs_review' and 'continuous_on_bracket' in unknown['unknown_facts']
    rejected=assess(card,AlgorithmRequest(query='root',facts={'continuous_on_bracket':False}))
    assert rejected['status']=='excluded' and rejected['reasons']==['premise_failed:continuous_on_bracket']


def test_integer_scale_dependency_filters(catalog):
    lp=next(c for c in catalog['cards'] if c['id']=='continuous-lp')
    assert assess(lp,AlgorithmRequest(query='LP',facts={'continuous_variables':False}))['status']=='excluded'
    assert 'scale_exceeds_reviewed_budget' in assess(lp,AlgorithmRequest(query='LP',variable_count=10001))['reasons']
    assert 'dependency_missing:scipy' in assess(lp,AlgorithmRequest(query='LP',available_dependencies=[]))['reasons']


def test_catalog_tamper_rejected_before_embedding(catalog):
    verify_sources(catalog)
    bad=copy.deepcopy(catalog);bad['sources'][0]['text']='changed'
    with pytest.raises(RetrievalUnavailable):verify_sources(bad)
    bad=copy.deepcopy(catalog);bad['cards'][0]['model']='changed'
    with pytest.raises(RetrievalUnavailable,match='hash mismatch'):verify_sources(bad)


def test_index_returns_full_section_and_excludes_failed_premises(catalog):
    client=QdrantClient(':memory:');model=Vectors();name=build_index(catalog,model,client)
    assert build_index(catalog,model,client)==name
    service=LegacyAlgorithmRetriever.__new__(LegacyAlgorithmRetriever);service.client=client;service.catalog=catalog;service.embedder=model
    service.config={'collection':name}
    result=service.search(AlgorithmRequest(query='root',category='geometry',layer='numerical_algorithm',facts={'scalar_equation':True,'continuous_on_bracket':True,'opposite_endpoint_signs':True}))
    hit=result['hits'][0]
    assert hit['doc_id']=='bracketed-root' and hit['applicability']['status']=='premises_satisfied'
    assert hit['source_sections'][0]['text'] in hit['text'] and '不保证唯一' in hit['text']
    denied=service.search(AlgorithmRequest(query='root',category='geometry',layer='numerical_algorithm',facts={'opposite_endpoint_signs':False}))
    assert denied['hits']==[] and denied['excluded'][0]['id']=='bracketed-root'
    client.close()


@pytest.mark.parametrize('latex',[r'\input{secret}',r'\write18{cmd}',r'\end{document}',r'\usepackage{shellesc}'])
def test_export_rejects_executable_tex(latex):
    with pytest.raises(ValueError):safe_math(latex)


def test_tex_retains_all_equations_symbols_and_ids():
    package=json.loads((asset_path(ROOT,'stage-b-plus/examples/valid-bench-dragon.json')).read_text(encoding='utf-8'))
    contract=json.loads((asset_path(ROOT,'stage-b-plus/examples/contract-v2-snapshot.json')).read_text(encoding='utf-8'))
    validate_package(package,contract)
    source=tex_source(package,'bench-dragon',figure=True)
    assert all(e['latex'] in source and source.count('\\label{'+e['id']+'}')==1 for e in package['dossier']['equations'])
    assert all(s['latex'] in source for s in package['dossier']['symbols'])
    assert r'\includegraphics[width=170mm]{kinematic-diagnostics.pdf}' in source
