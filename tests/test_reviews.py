from modelcrew.project_assets import asset_path,local_history
import copy,json,uuid
from pathlib import Path
import numpy as np
import pytest
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.inputs import file_hash
from modelcrew.reviews import review_interpretation,render_claims,validate_claims

@pytest.fixture
def evidence():
    folder=asset_path(ROOT,'stage-b/runs')/('review-test-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    path=folder/'values.npz';np.savez(path,speed=np.array([[1.,2.],[3.,4.]]),baseline=np.ones((2,2)))
    content={'outputs':[{'id':'arrays','path':'values.npz','format':'npz','fields':[{'name':f,'shape':[2,2],'unit':'m/s'} for f in ['speed','baseline']]}]}
    artifact={'path':str(path),'sha256':file_hash(path),'role':'TEST_ONLY'}
    contract={'content':content,'sha256':digest(content)}
    execution={'id':uuid.uuid4(),'contract_sha256':contract['sha256'],'mode':'fixture','artifacts':[artifact]}
    source={'artifact_sha256':artifact['sha256'],'output_id':'arrays','field':'speed','selector':{'index':[0,0]}}
    claims={'schema_version':'1.0.0','claims':[{'id':'head_speed','source':source,'operator':'eq','expected':1.,'unit':'m/s','abs_tolerance':1e-9}]}
    return contract,execution,claims,path

def test_structured_claims_pass_and_free_narrative_remains_unknown(evidence):
    c,e,claims,_=evidence
    r=review_interpretation(c,e,'guidance',claims,True)
    assert r['status']=='passed' and r['interpretation']==render_claims(claims) and not r['numeric_rerun']
    r=review_interpretation(c,e,'This unverified prose adds a physical claim.',claims)
    assert r['claims_status']=='passed' and r['semantic_status']=='unknown' and r['status']=='unknown'

@pytest.mark.parametrize('field,value',[('expected',9.),('unit','km/h')])
def test_false_numeric_or_unit_claim_fails(evidence,field,value):
    c,e,claims,_=evidence;claims['claims'][0][field]=value
    r=review_interpretation(c,e,'guidance',claims,True)
    assert r['status']=='failed' and r['claim_checks'][0]['status']=='failed'

def test_comparisons_and_reductions(evidence):
    c,e,claims,_=evidence;item=claims['claims'][0];item.pop('expected');item['compare_to']=copy.deepcopy(item['source']);item['compare_to']['field']='baseline'
    item['source']['selector']={'reduce':'max'};item['compare_to']['selector']={'reduce':'max'};item['operator']='ge'
    r=review_interpretation(c,e,'guidance',claims,True);assert r['status']=='passed'
    item['operator']='le';assert review_interpretation(c,e,'guidance',claims,True)['status']=='failed'

@pytest.mark.parametrize('mutation',['sha','field','index','shape','binding'])
def test_wrong_evidence_or_contract_binding_fails(evidence,mutation):
    c,e,claims,_=evidence
    if mutation=='sha':claims['claims'][0]['source']['artifact_sha256']='0'*64
    elif mutation=='field':claims['claims'][0]['source']['field']='missing'
    elif mutation=='index':claims['claims'][0]['source']['selector']['index']=[99,0]
    elif mutation=='shape':c['content']['outputs'][0]['fields'][0]['shape']=[999]
    else:e['contract_sha256']='0'*64
    assert review_interpretation(c,e,'guidance',claims,True)['status']=='failed'

def test_mutated_or_nonfinite_evidence_fails(evidence):
    c,e,claims,p=evidence;np.savez(p,speed=np.full((2,2),np.nan),baseline=np.ones((2,2)))
    assert review_interpretation(c,e,'guidance',claims,True)['status']=='failed'
    e['artifacts'][0]['sha256']=file_hash(p);claims['claims'][0]['source']['artifact_sha256']=file_hash(p)
    assert review_interpretation(c,e,'guidance',claims,True)['status']=='failed'

def test_schema_rejects_duplicate_nonfinite_and_ambiguous_predicates(evidence):
    _,_,claims,_=evidence
    for mutation in ['duplicate','nan','two_rhs','negative_index']:
        value=copy.deepcopy(claims)
        if mutation=='duplicate':value['claims']*=2
        elif mutation=='nan':value['claims'][0]['expected']=float('nan')
        elif mutation=='two_rhs':value['claims'][0]['compare_to']=copy.deepcopy(value['claims'][0]['source'])
        else:value['claims'][0]['source']['selector']['index']=[-1,0]
        with pytest.raises(ValueError):validate_claims(value)

def test_json_output_and_unsupported_format(evidence):
    c,e,claims,p=evidence;new=p.with_suffix('.json');new.write_text('{"speed":[[1,2],[3,4]]}',encoding='utf-8')
    c['content']['outputs'][0].update(path='values.json',format='json');c['sha256']=digest(c['content']);e['contract_sha256']=c['sha256'];e['artifacts'][0].update(path=str(new),sha256=file_hash(new));claims['claims'][0]['source']['artifact_sha256']=file_hash(new)
    assert review_interpretation(c,e,'guidance',claims,True)['status']=='passed'
    c['content']['outputs'][0]['format']='unsupported';c['sha256']=digest(c['content']);e['contract_sha256']=c['sha256']
    assert review_interpretation(c,e,'guidance',claims,True)['status']=='unknown'
