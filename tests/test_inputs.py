import copy,json,uuid
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from modelcrew.contracts import ROOT,SCHEMAS,validate,ContractError
from modelcrew.inputs import inspect_file,draft_inputs,assert_ready,resolve_question,pending_questions,file_hash

@pytest.fixture
def scratch():
    path=ROOT/'stage-b/runs'/('input-tests-'+uuid.uuid4().hex);path.mkdir(parents=True);return path

@pytest.fixture
def base():return json.loads((ROOT/'contracts/examples/valid-2024-a-q1.json').read_text(encoding='utf-8'))

def local_contract(base,path):
    c=copy.deepcopy(base);c['inputs']=[{**c['inputs'][0],'path':str(path),'sha256':file_hash(path),'role':'dataset'}];return c

def resolved(c):
    for q in pending_questions(c):c=resolve_question(c,q['input_id'],q['id'],'TEST_SIMULATED_USER: reviewed semantics for this test')
    return c

def test_schemas_are_valid_and_old_format_unchanged(base):
    for schema in SCHEMAS.values():Draft202012Validator.check_schema(schema)
    validate(base);assert base['schema_version']=='1.0.0'

def test_csv_profile_and_blocking_questions(scratch,base):
    p=scratch/'values.csv';p.write_text('time,value\n0,10\n1,11\n',encoding='utf-8')
    original=local_contract(base,p);c=draft_inputs(original);validate(c)
    assert original['schema_version']=='1.0.0' and 'structure' not in original['inputs'][0]
    assert c['inputs'][0]['structure']['observed']['tables'][0]['rows']==3
    assert len(c['inputs'][0]['structure']['fields'])==3
    with pytest.raises(ContractError,match='Unresolved'):assert_ready(c)
    c=resolved(c);assert_ready(c)
    assert draft_inputs(c)==c
    p.write_text('changed',encoding='utf-8')
    with pytest.raises(ContractError,match='changed'):assert_ready(c)
    with pytest.raises(ContractError,match='snapshot changed'):draft_inputs(c)

def test_observed_shape_cannot_be_fabricated(scratch,base):
    p=scratch/'x.csv';p.write_text('a,b\n1,2',encoding='utf-8');c=resolved(draft_inputs(local_contract(base,p)))
    c['inputs'][0]['structure']['observed']['tables'][0]['rows']=999
    with pytest.raises(ContractError,match='does not match'):assert_ready(c)

def test_unknown_schema_and_duplicate_pending_rejected(scratch,base):
    bad=copy.deepcopy(base);bad['schema_version']='9.0'
    with pytest.raises(ContractError):validate(bad)
    p=scratch/'data.json';p.write_text('{"x":1}',encoding='utf-8');c=draft_inputs(local_contract(base,p))
    c['inputs'][0]['structure']['pending']*=2
    with pytest.raises(ContractError,match='Duplicate'):validate(c)

def test_nested_json_does_not_invent_required_keys(scratch):
    p=scratch/'x.json';p.write_text('{"a":[1,null],"b":true}',encoding='utf-8');v=inspect_file(p)['structure']
    assert v['template_id']=='nested'
    schema=v['observed']['data_schema'];assert 'required' not in schema
    assert schema['properties']['b']['type']=='boolean'
    assert inspect_file(p,kind='parameters')['structure']['template_id']=='parameters'

@pytest.mark.parametrize('suffix',['npy','npz'])
def test_array_shape_and_no_pickle(scratch,suffix):
    import numpy as np
    p=scratch/('a.'+suffix)
    if suffix=='npy':np.save(p,np.ones((2,3)))
    else:np.savez(p,data=np.ones((2,3)))
    a=inspect_file(p)['structure']['observed']['arrays'][0];assert a['shape']==[2,3]
    evil=scratch/'object.npy';np.save(evil,np.array([{'x':1}],dtype=object))
    with pytest.raises(ValueError):inspect_file(evil)

def test_image_and_geo_profiles(scratch):
    from PIL import Image
    p=scratch/'x.png';Image.new('RGB',(12,7)).save(p)
    assert inspect_file(p)['structure']['observed']['height']==7
    p=scratch/'x.geojson';p.write_text('{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[1,2]}}]}',encoding='utf-8')
    v=inspect_file(p)['structure'];assert v['observed']['crs'] is None and v['pending'][0]['blocking']

def test_output_template_not_dataset_and_time_series(scratch):
    from openpyxl import Workbook
    p=scratch/'template.xlsx';wb=Workbook();wb.active.title='位置';wb.active.append(['node','0 s']);wb.active.append(['head',None]);wb.save(p);wb.close()
    v=inspect_file(p,'required_output_template')['structure'];assert v['template_id']=='output_template'
    assert '空单元格不是缺失观测值' in v['pending'][0]['question']
    p=scratch/'series.csv';p.write_text('time,x\n0,1',encoding='utf-8')
    assert len(inspect_file(p,kind='time_series')['structure']['pending'])==2

def test_unsupported_cannot_be_approved(scratch,base):
    p=scratch/'mystery.bin';p.write_bytes(b'abc');c=draft_inputs(local_contract(base,p))
    assert c['inputs'][0]['structure']['template_id']=='unsupported'
    with pytest.raises(ContractError):resolved(c)

def test_pdf_extraction_has_page_locators(scratch):
    from pypdf import PdfWriter
    p=scratch/'blank.pdf';w=PdfWriter();w.add_blank_page(width=100,height=100)
    with p.open('wb') as f:w.write(f)
    assert inspect_file(p,'problem_statement')['structure']['observed']['pages']==[{'page':1,'text':''}]

def test_question_requires_resolution(scratch,base):
    p=scratch/'x.csv';p.write_text('a\n1',encoding='utf-8');c=draft_inputs(local_contract(base,p))
    with pytest.raises(ContractError):resolve_question(c,'input0','layout',' ')
    c['inputs'][0]['structure']['pending'][0]['status']='resolved'
    with pytest.raises(ContractError):validate(c)
