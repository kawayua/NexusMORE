"""Condition-aware algorithm cards; source sections are never split from premises."""
import json
import os
import uuid
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from qdrant_client import QdrantClient,models
from .config import ROOT
from .contracts import digest
from .corpus import sha_file
from .retrieval import LocalBge,RetrievalUnavailable,META_ID

DEFAULT_CONFIG=ROOT/'stage-c-plus/runs/algorithm-index.json'


class AlgorithmRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,str_strip_whitespace=True)
    query:str=Field(min_length=1,max_length=400)
    limit:int=Field(default=3,ge=1,le=10)
    category:Literal['optimization','simulation','geometry']|None=None
    layer:Literal['model','numerical_algorithm','api']|None=None
    verification:Literal['reviewed_excerpt_not_executed','reviewed_numeric_baseline']|None=None
    facts:dict[str,bool]=Field(default_factory=dict)
    variable_count:int|None=Field(default=None,ge=1,le=10000000)
    available_dependencies:list[str]|None=Field(default=None,max_length=30)


def verify_sources(catalog):
    for source in catalog['sources']:
        path=(ROOT/source['path']).resolve()
        if not path.is_relative_to(ROOT/'resources/algorithms') or sha_file(path)!=source['sha256']:
            raise RetrievalUnavailable('Algorithm source file missing or changed')
        excerpt='\n'.join(path.read_text(encoding='utf-8-sig').splitlines()[source['line_start']-1:source['line_end']])+'\n'
        if excerpt!=source['text'] or digest(excerpt)!=source['section_sha256']:
            raise RetrievalUnavailable('Algorithm source section changed')
    index=ROOT/'resources/algorithms/index.md'
    if sha_file(index)!=catalog['index']['sha256']:raise RetrievalUnavailable('Algorithm index changed; rebuild catalog')
    if digest({k:v for k,v in catalog.items() if k!='catalog_sha256'})!=catalog['catalog_sha256']:
        raise RetrievalUnavailable('Algorithm catalog hash mismatch')


def assess(card,request):
    reasons=[];unknown=[]
    for name,expected in card['required_facts'].items():
        if name not in request.facts:unknown.append(name)
        elif request.facts[name]!=expected:reasons.append('premise_failed:'+name)
    if request.variable_count is not None and card['max_variables'] is not None and request.variable_count>card['max_variables']:
        reasons.append('scale_exceeds_reviewed_budget')
    if request.available_dependencies is not None:
        reasons.extend('dependency_missing:'+name for name in card['dependencies'] if name not in request.available_dependencies)
    return {'status':'excluded' if reasons else ('needs_review' if unknown else 'premises_satisfied'),
            'reasons':reasons,'unknown_facts':unknown,
            'scale_status':'not_declared' if request.variable_count is None else ('unbounded_not_certified' if card['max_variables'] is None else 'within_declared_review_budget'),
            'dependency_status':'not_declared' if request.available_dependencies is None else 'checked'}


def build_index(catalog,embedder,client):
    verify_sources(catalog)
    identity={'catalog_sha256':catalog['catalog_sha256'],'embedding_signature':embedder.signature,'dimension':embedder.dimension,'count':len(catalog['cards'])}
    collection='mc_cplus_'+digest(identity)[:24]
    if client.collection_exists(collection):
        marker=client.retrieve(collection,[META_ID])
        if marker and marker[0].payload==identity and client.count(collection,exact=True).count==len(catalog['cards'])+1:return collection
        raise RetrievalUnavailable('Existing algorithm index incomplete or mismatched')
    client.create_collection(collection,vectors_config=models.VectorParams(size=embedder.dimension,distance=models.Distance.COSINE))
    vectors=embedder.encode([c['retrieval_text'] for c in catalog['cards']])
    client.upsert(collection,[models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,c['id'])),vector=v,payload=c) for c,v in zip(catalog['cards'],vectors,strict=True)],wait=True)
    client.upsert(collection,[models.PointStruct(id=META_ID,vector=[0.]*embedder.dimension,payload=identity)],wait=True)
    return collection


class AlgorithmRetriever:
    def __init__(self,config=None):
        path=Path(config or os.environ.get('MODELCREW_ALGORITHM_CONFIG',DEFAULT_CONFIG))
        try:
            self.config=json.loads(path.read_text(encoding='utf-8-sig'))
            catalog_path=(ROOT/self.config['catalog_path']).resolve()
            if not catalog_path.is_relative_to(ROOT):raise RetrievalUnavailable('Algorithm catalog must be within workspace')
            self.catalog=json.loads(catalog_path.read_text(encoding='utf-8-sig'));verify_sources(self.catalog)
            if self.config['catalog_sha256']!=self.catalog['catalog_sha256']:raise RetrievalUnavailable('Configured algorithm catalog changed')
            self.embedder=LocalBge(self.config['model_path'])
            if self.embedder.signature!=self.config['embedding_signature']:raise RetrievalUnavailable('Algorithm embedding model changed')
            self.client=QdrantClient(url=self.config['qdrant_url'],timeout=15)
        except RetrievalUnavailable:raise
        except Exception as exc:raise RetrievalUnavailable('Algorithm retrieval configuration unavailable') from exc

    def search(self,request):
        verify_sources(self.catalog)
        try:
            marker=self.client.retrieve(self.config['collection'],[META_ID])
            expected={'catalog_sha256':self.catalog['catalog_sha256'],'embedding_signature':self.embedder.signature,'dimension':self.embedder.dimension,'count':len(self.catalog['cards'])}
            if not marker or marker[0].payload!=expected:raise RetrievalUnavailable('Algorithm index identity mismatch')
            candidates=[c for c in self.catalog['cards'] if all(getattr(request,key) is None or c[key]==getattr(request,key) for key in ('category','layer','verification'))]
            assessments={c['id']:assess(c,request) for c in candidates}
            eligible=[c['id'] for c in candidates if assessments[c['id']]['status']!='excluded']
            hits=[]
            if eligible:
                vector=self.embedder.encode([request.query],query=True)[0]
                points=self.client.query_points(self.config['collection'],query=vector,limit=request.limit,
                    query_filter=models.Filter(must=[models.FieldCondition(key='id',match=models.MatchAny(any=eligible))]),with_payload=True).points
                source_map={s['id']:s for s in self.catalog['sources']}
                for point in points:
                    card=point.payload
                    # Catalog is the source of truth; reject changed Qdrant payloads.
                    expected_card=next(c for c in candidates if c['id']==card['id'])
                    if card!=expected_card:raise RetrievalUnavailable('Algorithm index payload changed')
                    sections=[source_map[s] for s in card['source_ids']]
                    text='\n\n'.join(s['text'] for s in sections)
                    hits.append({'doc_id':card['id'],'chunk_id':digest(card),'text':text,'title':card['title'],
                        'source_url':card.get('source_url'),'source_sha256':digest([s['sha256'] for s in sections]),
                        'parser':'cplus-whole-sections-1','locator':{'sections':[{k:s[k] for k in ('path','line_start','line_end','section_sha256')} for s in sections]},
                        'same_problem_reference':False,'score':point.score,'card':card,'applicability':assessments[card['id']],
                        'source_sections':sections,'origin':'external_reference','modeler_generated':False})
            return {'status':'ok','query':request.query,'collection':self.config['collection'],'corpus_sha256':self.catalog['catalog_sha256'],
                'embedding_signature':self.embedder.signature,'include_same_problem':True,'provider':'condition_aware_algorithm_cards',
                'index_read':self.catalog['index'],'excluded':[{'id':key,**v} for key,v in assessments.items() if v['status']=='excluded'],
                'hits':hits,'interpretation':'Similarity ranks references, not mathematical truth. Premises are caller declarations; unknowns require review.'}
        except RetrievalUnavailable:raise
        except Exception as exc:raise RetrievalUnavailable('Algorithm vector retrieval unavailable') from exc
