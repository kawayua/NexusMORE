"""Synthetic presentation fixtures; no user approval or scientific validation."""
import copy,hashlib,json
from pathlib import Path
import pytest
from modelcrew.result_review_documents import render_result,result_sources,RESULT_RENDERER_VERSION
from modelcrew.dsh_chat import save_review_document,_verify_document
from modelcrew.business_contract import BusinessContractError
from modelcrew.contracts import digest


def fixture(root):
    binding={'task_id':'synthetic-task','contract_version':6,'contract_sha256':'a'*64,'execution_id':'synthetic-execution','result_revision':1}
    result={'binding':binding,'config':{'duration_s':1800,'dt_s':1,'Nr_nodes':121,'Nz_nodes':82},'histories':{'z_m':0,'nsteps':1800,'columns':21},'checks':[],
        'tables':{'table1_temperature':{'times_s':[100,1800],'radii_cm':[0,2],'values':[[28,29],[33.5765,36.7863]]},'table2_moisture':{'times_s':[100,1800],'radii_cm':[0,2],'values':[[2.55,2.4],[2.55,1.5104]]}}}
    acceptance={'accepted_checks':{'chk_dt':{'tolerance':.002,'value':{'dt21':{'C':{'maximum_all_times':.00840012658875,'maximum_common_even_times':.0024762217669}}}},'chk_analytic2d':{'tolerance':.001,'value':{'maximum':.00105970786259}}}}
    p2={'checks':[{'check_id':k,'status':'PASS'} for k in ['execution','contract_implementation','error','reproduction','figure_meaning']]}
    sources=[]
    def add(name,value):
        target=root/'objects'/name;target.parent.mkdir(parents=True,exist_ok=True);data=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,dict) else value;target.write_bytes(data)
        ref={'name':name,'path':target.relative_to(root).as_posix(),'sha256':hashlib.sha256(data).hexdigest(),'role':'output'};sources.append(ref);return ref
    png=add('fig-temp.png',b'SYNTHETIC_IMAGE_BYTES');add('fig-temp.pdf',b'SYNTHETIC_PDF');add('fig-temp.svg',b'SYNTHETIC_SVG')
    catalog={'figures':[{'id':'fig:res-temp-field','title':'温度变化图','category':'result','files':{fmt:{'path':'fig-temp.'+fmt} for fmt in ['png','pdf','svg']}}]}
    add('result.json',result);add('figure-catalog.json',catalog);add('user-accepted-deviations.json',acceptance);add('independent-p2.json',p2);add('independent-visual.json',{'status':'PASS','page_count':13});add('outputs/result1.xlsx',b'SYNTHETIC_WORKBOOK')
    review={'pending':{'kind':'result','binding':{'project_id':'p','task_id':'synthetic-task','version':6,'contract_sha256':'a'*64,'execution_id':'synthetic-execution','result_revision':1}},
       'dossier':{'contract':{'content':{'problem':{'scope':'药材预热阶段计算'},'risks':['没有内部实测数据，不能宣称实验验证。']}},'result':{'revision':1,'interpretation':'Technical placeholder'},'execution':{'artifacts':[]},'result_review_evidence':{'sources':sources}},'review_files':[],'review_texts':[]}
    return review


def test_result_view_shows_numbers_tables_errors_and_confirmation_scope(tmp_path):
    r=fixture(tmp_path);p=save_review_document(r,{'project_id':'p','task_id':'synthetic-task'},'session-result',None,tmp_path)
    text=p['markdown']
    for value in ['33.5765','36.7863','2.5500','1.5104','0.00840013','0.10597%','未达到原要求','你已接受','论文正文','最终选图','![温度变化图]','完整 Excel']:
        assert value in text
    assert text.index('先看主要结果')<text.index('误差与检查')
    assert 'task_id' not in text and 'created_at' not in text and 'execution_id' not in text
    assert p['renderer_version']==RESULT_RENDERER_VERSION and Path(p['local_path']).parent.name=='readable-result-v1'
    record=json.loads(Path(p['local_path']).with_suffix('.json').read_text(encoding='utf-8'))
    assert record['review']==r and len(list((Path(p['local_path']).parent/'assets').rglob('fig-temp.png')))==1
    assert save_review_document(r,{'project_id':'p','task_id':'synthetic-task'},'session-result',None,tmp_path)==p


@pytest.mark.parametrize('target',['original','displayed_asset','evidence'])
def test_changed_result_bytes_or_displayed_files_cannot_be_confirmed(tmp_path,target):
    r=fixture(tmp_path);p=save_review_document(r,{},'session-result',None,tmp_path);path=Path(p['local_path']);record=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    changed=tmp_path/r['dossier']['result_review_evidence']['sources'][0]['path'] if target=='original' else next((path.parent/'assets').rglob('fig-temp.png')) if target=='displayed_asset' else path.parent/record['evidence_file']
    changed.write_bytes(b'changed')
    with pytest.raises(BusinessContractError):_verify_document(record,path.parent,p['preview_id'],tmp_path)


def test_old_machine_dump_is_preserved_and_new_readable_view_has_new_identity(tmp_path):
    r=fixture(tmp_path);base=tmp_path/'runs/reviews/dsh'/digest('session-result');base.mkdir(parents=True);old=base/'old-review.md';old.write_bytes(b'old immutable machine fields')
    p=save_review_document(r,{},'session-result',None,tmp_path)
    assert old.read_bytes()==b'old immutable machine fields' and Path(p['local_path']).parent!=base


def test_no_data_does_not_invent_scientific_results(tmp_path):
    review={'pending':{'kind':'result','binding':{'version':1}},'dossier':{'result':{'interpretation':'只有登记记录。'},'execution':{}},'review_files':[]}
    _,text,sources=render_result(review,tmp_path)
    assert not sources and '没有可读取的结构化结果表' in text
    assert '33.5765' not in text and '独立视觉审查实际接收' not in text


def test_wrong_execution_or_result_source_outside_workspace_is_rejected(tmp_path):
    r=fixture(tmp_path);r['pending']['binding']['execution_id']='different'
    with pytest.raises(BusinessContractError):render_result(r,tmp_path)
    r=fixture(tmp_path);r['dossier']['result_review_evidence']['sources'][0]['path']='../outside'
    with pytest.raises(BusinessContractError):result_sources(r,tmp_path)
