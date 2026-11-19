"""Synthetic image/PDF transport fixtures, not real scientific review approvals."""
import copy,json,hashlib,base64
from types import SimpleNamespace
import httpx,pytest
from PIL import Image
from modelcrew import p2_vision as pv,hand_runtime as hr
from modelcrew.model_client import JsonModel
from modelcrew.workflow import WorkflowError

CONFIG={'MODELCREW_LLM_API_KEY':'TEST_ONLY','MODELCREW_LLM_MODEL':'text-fixture','MODELCREW_LLM_BASE_URL':'https://fixture.invalid/v1','MODELCREW_VISION_MODEL':'vision-fixture'}


def test_p2_actual_image_bytes_metadata_and_stage_only_model_selection(tmp_path):
    image=tmp_path/'page.png';Image.new('RGB',(60,40),'red').save(image);sha=hashlib.sha256(image.read_bytes()).hexdigest();seen=[]
    def handler(req):
        body=json.loads(req.content);seen.append(body)
        if len(seen)==1:
            assert body['model']=='vision-fixture';parts=body['messages'][1]['content'];assert base64.b64decode(parts[-1]['image_url']['url'].split(',',1)[1])==image.read_bytes()
        else:assert body['model']=='text-fixture' and isinstance(body['messages'][1]['content'],str)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model=JsonModel(client=client,config=CONFIG)
        _,meta=model.call(tmp_path,'P2','independent',{},image_inputs=[{'image_id':'visual-page-0001','path':image,'sha256':sha,'label':'page 1'}])
        model.call(tmp_path,'P1','independent',{})
    assert meta['image_count']==1 and meta['image_bytes_total']==image.stat().st_size
    assert meta['image_manifest'][0]['sha256']==sha and meta['image_manifest'][0]['image_id']=='visual-page-0001'
    assert len(meta['request_record_sha256'])==64


def answer(status='PASS',pages=None):
    return SimpleNamespace(visual_pages=pages or [SimpleNamespace(image_id='visual-page-0001',image_sha256='a'*64,status='PASS')],checks=[SimpleNamespace(check_id='figure_meaning',status=status)])


def test_visual_coverage_requires_exact_images_and_actual_dispatch():
    images=[{'image_id':'visual-page-0001','sha256':'a'*64}];meta={'image_count':1,'image_manifest':images}
    assert pv.validate_answer(answer(),images,meta)=='PASS'
    with pytest.raises(WorkflowError,match='dispatch'):pv.validate_answer(answer(),images,{'image_count':0})
    bad=answer(pages=[SimpleNamespace(image_id='other',image_sha256='a'*64,status='PASS')])
    with pytest.raises(WorkflowError,match='coverage'):pv.validate_answer(bad,images,meta)
    bad=answer(pages=[SimpleNamespace(image_id='visual-page-0001',image_sha256='a'*64,status='FAIL')])
    with pytest.raises(WorkflowError,match='Failed visual'):pv.validate_answer(bad,images,meta)


def test_prepare_covers_every_physical_page_and_refuses_changed_preview(tmp_path,monkeypatch):
    import fitz
    from modelcrew.figure_tools import audit_catalog
    monkeypatch.setattr(hr,'ROOT',tmp_path)
    image=tmp_path/'plot.png';Image.new('RGB',(600,400),'white').save(image,dpi=(300,300))
    svg=tmp_path/'plot.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"></svg>',encoding='utf-8')
    pdf=tmp_path/'plot.pdf'
    with fitz.open() as d:
        for i in range(2):page=d.new_page(width=300,height=200);page.insert_text((30,70),'Synthetic physical page '+str(i+1),fontsize=12)
        d.save(pdf)
    catalog={'evidence':{'task_id':'fixture'},'figures':[{'id':'synthetic-figure','files':{fmt:{'path':path.name,'sha256':hr.sha_file(path)} for fmt,path in [('png',image),('pdf',pdf),('svg',svg)]}}]}
    cat=tmp_path/'figure-catalog.json';cat.write_text(json.dumps(catalog),encoding='utf-8');qa=tmp_path/'qa';audit_catalog(cat,qa)
    path,manifest,inputs=pv.prepare(cat,qa,catalog['evidence'],tmp_path)
    assert manifest['image_count']==2 and [i['page'] for i in manifest['images']]==[1,2]
    assert len(inputs)==2 and hr.sha_file(inputs[1]['path'])==inputs[1]['sha256']
    original=cat.read_bytes();assert path.exists()
    (qa/'figure-0001/page-0002.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='preview changed'):pv.prepare(cat,qa,catalog['evidence'],tmp_path)
    assert cat.read_bytes()==original


def test_visual_only_recovery_refuses_new_source_or_wrong_phase(monkeypatch):
    row={'id':'synthetic','phase':'EXECUTE_FULL','payload':{'binding':{},'attempt':8,'last_review':{'gate':'P2','attempt':7,'stage_key':'P2-7-recheck'},'reviews':{'P2-7-recheck':{'status':'FAIL'}}}}
    from contextlib import nullcontext
    w=SimpleNamespace(db=object(),lock=lambda *a:nullcontext(),task=lambda t:{'result_revision':0})
    monkeypatch.setattr(hr,'load',lambda *a:row);monkeypatch.setattr(hr,'guard',lambda *a:None)
    import modelcrew.business_store as bs
    monkeypatch.setattr(bs,'BusinessStore',lambda db:SimpleNamespace(unresolved=lambda *a:None))
    with pytest.raises(WorkflowError,match='untouched'):pv.resume_existing_visual_failure(w,'task','synthetic',request_id='fixture',reason='No extra author execution')

def test_model_only_references_id_and_program_binds_immutable_hash():
    page=pv.PageAssessment(image_id='visual-page-0001',status='PASS',observations='Actual visible axes and units readable.')
    result=SimpleNamespace(visual_pages=[page]);images=[{'image_id':'visual-page-0001','sha256':'c'*64}]
    assert pv.bind_page_hashes(result,images)==[{'image_id':'visual-page-0001','status':'PASS','observations':'Actual visible axes and units readable.','image_sha256':'c'*64}]
    assert 'image_sha256' not in pv.PageAssessment.model_fields

def test_visual_feature_recovery_reuses_sealed_previous_attempt_without_recompute(tmp_path,monkeypatch):
    from contextlib import nullcontext
    source=tmp_path/'source.py';source.write_text('pass\n',encoding='utf-8');sha=hr.sha_file(source)
    packet={'receipt':{'status':'succeeded'},'job':{'code_sha256':sha},'artifacts':[{'path':'runs/old-full/artifacts/result.json','sha256':'a'*64}]}
    for name in ['primary.json','replica.json']:(tmp_path/name).write_text(json.dumps(packet),encoding='utf-8')
    row={'id':'fixture','task_id':'task','phase':'GENERATE_FULL','payload':{'binding':{'task_id':'task'},'attempt':8,'retries':3,'last_review':{'gate':'P2','attempt':7,'stage_key':'P2-7-recheck'},'reviews':{'P2-7-recheck':{'status':'FAIL','receipt_sha256':'p2','snapshot_sha256':'s2'},'P1-0':{'status':'PASS','receipt_sha256':'p1','snapshot_sha256':'s1'}},'accepted_reviews':{'P1':'P1-0'},'full_packet':None,'replica_packet':None,'full-7':'primary.json','full-7-replica':'replica.json','full_code_path':'source.py','ops':{},'jobs':{},'sealed':{}}}
    w=SimpleNamespace(db=object(),lock=lambda *a:nullcontext(),task=lambda *a:{'result_revision':0})
    monkeypatch.setattr(hr,'ROOT',tmp_path);monkeypatch.setattr(hr,'load',lambda *a:row);monkeypatch.setattr(hr,'guard',lambda *a:None);monkeypatch.setattr(hr,'run_folder',lambda r:tmp_path);monkeypatch.setattr(hr,'status',lambda *a:{'phase':row['phase']});monkeypatch.setattr(hr,'save',lambda w,r,phase=None:r.update(phase=phase or r['phase']))
    import modelcrew.business_store as bs,modelcrew.collaboration as c
    monkeypatch.setattr(bs,'BusinessStore',lambda db:SimpleNamespace(unresolved=lambda *a:None))
    class Store:
        def __init__(self,*a):pass
        def load(self,cls,key):return SimpleNamespace(key=key,status='PASS' if key=='p1' else 'FAIL',checks=[SimpleNamespace(check_id=k,status='FAIL' if k=='figure_meaning' else 'PASS') for k in ['execution','contract_implementation','error','reproduction','figure_meaning']])
        def accept_review(self,r,s):return r.key
    monkeypatch.setattr(c,'CollaborationStore',Store)
    original=(tmp_path/'primary.json').read_bytes()
    assert pv.resume_existing_visual_failure(w,'task','fixture',request_id='feature',reason='Actual images now implemented')['phase']=='REVIEW_P2'
    p=row['payload'];assert p['full_packet']=='primary.json' and p['replica_packet']=='replica.json'
    assert p['attempt']==8 and p['retries']==3 and p['ops']=={} and p['jobs']=={}
    assert (tmp_path/'primary.json').read_bytes()==original and p['reviews']['P2-7-recheck']['status']=='FAIL'
    assert pv.resume_existing_visual_failure(w,'task','fixture',request_id='feature',reason='Actual images now implemented')['phase']=='REVIEW_P2'
    with pytest.raises(WorkflowError,match='idempotency'):pv.resume_existing_visual_failure(w,'task','fixture',request_id='feature',reason='Different intent')
