"""Writer transport protocol preserves literal math; reviewers remain strict JSON."""
import json
import httpx
import pytest
from modelcrew.model_client import JsonModel,ModelCallError,decode_content

CONFIG={'MODELCREW_LLM_API_KEY':'TEST-SECRET','MODELCREW_LLM_MODEL':'fixture','MODELCREW_LLM_BASE_URL':'https://fixture.invalid/v1'}
TEXT='# 中文正文\n\n'+r'$$S(\theta)=\int_0^\theta b\sqrt{1+u^2}\,\mathrm du$$'+'\n\n'+r'$\theta$ 与 $\frac{1}{2}$'+'\n'

def test_raw_writer_transport_preserves_exact_content_and_receipt(tmp_path):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':TEXT}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        answer,meta=JsonModel(client=client,config=CONFIG).call(tmp_path,'Writer','raw text',{'output_protocol':'raw_markdown_v1'})
    assert answer=={'markdown':TEXT} and len(calls)==1
    raw=json.loads(next(tmp_path.glob('*response.json')).read_text(encoding='utf-8'))
    assert raw['choices'][0]['message']['content']==TEXT
    assert meta['status']=='completed' and meta['output_protocol']=='raw_markdown_v1'

@pytest.mark.parametrize('stage,data',[('W1',{'output_protocol':'raw_markdown_v1'}),('P1',{}),('Writer',{})])
def test_raw_protocol_cannot_relax_review_or_legacy_json(stage,data):
    with pytest.raises(json.JSONDecodeError):decode_content(TEXT,stage,data)
    assert decode_content('{"status":"FAIL"}',stage,data)=={'status':'FAIL'}

@pytest.mark.parametrize('reason,text',[('length',TEXT),('stop','  ')])
def test_raw_writer_rejects_truncation_or_blank_without_retry(tmp_path,reason,text):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(200,json={'choices':[{'finish_reason':reason,'message':{'content':text}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelCallError):JsonModel(client=client,config=CONFIG).call(tmp_path,'Writer','raw',{'output_protocol':'raw_markdown_v1'})
    assert len(calls)==1 and list(tmp_path.glob('*response.json'))

def test_multimodal_review_sends_verified_native_images_and_raw_response_hash(tmp_path):
    import hashlib,base64
    from PIL import Image
    image=tmp_path/'page.png';Image.new('RGB',(10,10),'white').save(image)
    expected=hashlib.sha256(image.read_bytes()).hexdigest();requests=[]
    def handler(request):
        data=json.loads(request.content);requests.append(data)
        parts=data['messages'][1]['content']
        assert parts[0]['type']=='text' and parts[1]['text']=='latex physical page 1'
        assert base64.b64decode(parts[2]['image_url']['url'].split(',',1)[1])==image.read_bytes()
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"status":"BLOCKED"}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model=JsonModel(client=client,config=CONFIG)
        answer,meta=model.call(tmp_path,'W2','independent',{},image_inputs=[{'path':image,'sha256':expected,'label':'latex physical page 1'}])
        with pytest.raises(ModelCallError,match='changed'):
            model.call(tmp_path,'W2','independent',{},image_inputs=[{'path':image,'sha256':'0'*64,'label':'changed'}])
    assert len(requests)==1 and answer['status']=='BLOCKED' and meta['image_count']==1
    raw=next(tmp_path.glob('*response.json'))
    assert meta['response_sha256']==hashlib.sha256(raw.read_bytes()).hexdigest()

@pytest.mark.parametrize('exception,domain,status',[(httpx.ConnectError,'not_sent','not_sent'),(httpx.ReadTimeout,'infrastructure','unknown')])
def test_transport_distinguishes_no_connection_from_ambiguous_delivery(tmp_path,exception,domain,status):
    def handler(request):raise exception('SYNTHETIC transport failure')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelCallError) as error:JsonModel(client=client,config=CONFIG).call(tmp_path,'W2','review',{})
    assert error.value.domain==domain
    meta=json.loads(next(tmp_path.glob('*metadata.json')).read_text(encoding='utf-8'))
    assert meta['status']==status and meta['error_type']==exception.__name__


def test_w2_v2_structured_transport_uses_real_response_format_not_prompt_only(tmp_path):
    from modelcrew.w2_protocol import Answer
    schema=Answer.model_json_schema();seen=[]
    def handler(request):
        raw=json.loads(request.content);seen.append(raw)
        assert raw['response_format']=={'type':'json_schema','json_schema':{'name':'w2_evidence_refs_v2','strict':True,'schema':schema}}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"status":"BLOCKED"}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _,meta=JsonModel(client=client,config={**CONFIG,'MODELCREW_W2_RESPONSE_FORMAT':'json_schema'}).call(tmp_path,'W2','independent',{'output_protocol':'w2_evidence_refs_v2','schema':schema})
    assert len(seen)==1 and meta['output_protocol']=='w2_evidence_refs_v2' and meta['response_format_type']=='json_schema'
    assert meta['server_schema_requested'] and meta['server_schema_enforced'] is None


def test_w2_v2_default_json_mode_is_explicit_and_does_not_claim_server_schema(tmp_path):
    from modelcrew.w2_protocol import Answer
    calls=[]
    def handler(request):
        data=json.loads(request.content);calls.append(data)
        assert data['response_format']=={'type':'json_object'}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"status":"FAIL"}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _,meta=JsonModel(client=client,config=CONFIG).call(tmp_path,'W2','independent',{'output_protocol':'w2_evidence_refs_v2','schema':Answer.model_json_schema()})
    assert len(calls)==1 and not meta['server_schema_enforced']


def test_schema_rejection_does_not_silently_retry_as_json_mode(tmp_path):
    from modelcrew.w2_protocol import Answer
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(400,json={'error':{'message':'This response_format type is unavailable now'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelCallError):
            JsonModel(client=client,config={**CONFIG,'MODELCREW_W2_RESPONSE_FORMAT':'json_schema'}).call(tmp_path,'W2','independent',{'output_protocol':'w2_evidence_refs_v2','schema':Answer.model_json_schema()})
    assert len(calls)==1 and calls[0]['response_format']['type']=='json_schema'


@pytest.mark.parametrize("stage", ["planning", "modeling", "M1", "Coder", "P1", "P2", "Writer-plan", "W1"])
def test_structured_stages_request_json_and_preserve_fenced_failure(tmp_path, stage):
    content='```json\n{"status":"PASS"}\n```'
    calls=[]
    def handler(request):
        body=json.loads(request.content);calls.append(body)
        assert body["response_format"] == {"type":"json_object"}
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":content}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(json.JSONDecodeError):
            JsonModel(client=client,config=CONFIG).call(tmp_path,stage,"Only JSON",{})
    assert len(calls)==1
    raw=json.loads(next(tmp_path.glob("*response.json")).read_text(encoding="utf-8"))
    assert raw["choices"][0]["message"]["content"]==content
    meta=json.loads(next(tmp_path.glob("*metadata.json")).read_text(encoding="utf-8"))
    assert meta["response_format_type"]=="json_object" and not meta["server_schema_enforced"]
    assert meta["status"]=="invalid_response"


def test_native_json_request_keeps_raw_writer_protocol(tmp_path):
    def handler(request):
        assert "response_format" not in json.loads(request.content)
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":TEXT}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        answer,meta=JsonModel(client=client,config=CONFIG).call(tmp_path,"Writer","raw Markdown",{"output_protocol":"raw_markdown_v1"})
    assert answer=={"markdown":TEXT} and meta["response_format_type"]=="none"


def test_writer_navigation_preserves_all_result_locations_and_exact_sources():
    from modelcrew.hand_runtime import writer_evidence_navigation
    from modelcrew.modeling_hand import pointer
    evidence={'result':{'values':[{'value':{'figures':[{'deep':list(range(100))}]*9}},
                                {'value':{'base':{'profit':2200},'scenarios':[], 'a/b~c':1}}]},
              'sources':{'sources':[{'path':'case/statement.md','text':'SYNTHETIC'}]}}
    navigation, locations, sources=writer_evidence_navigation(evidence)
    assert locations[1]['selector']=='/values/1/value'
    assert '/values/1/value/base' in navigation['result']
    assert '/values/1/value/a~1b~0c' in navigation['result']
    assert sources==['case/statement.md']
    assert not any('limits' in p for p in navigation['result'])
    for name,paths in navigation.items():
        for path in paths:pointer(evidence[name],path)


def test_writer_navigation_never_invents_numerics_or_references():
    from modelcrew.hand_runtime import writer_evidence_navigation
    nav,locations,sources=writer_evidence_navigation({'result':{'values':[]},'sources':{'sources':[]}})
    assert locations==[] and sources==[] and nav['result']==['/values']
