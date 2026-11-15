import json
from copy import deepcopy
from pathlib import Path
import uuid
import pytest
from modelcrew.historical_assembly import verify_frozen_build
from modelcrew.contracts import digest
from modelcrew.collaboration import sha_file, historical_review_context
from modelcrew.writing_reviews import manuscript_record, selection_record
from modelcrew.assembly_compose import MD_NAME


@pytest.fixture
def frozen(tmp_path):
    source=tmp_path/'build/source'; source.mkdir(parents=True)
    inputs=tmp_path/'inputs'; inputs.mkdir()
    manuscript=source/MD_NAME; manuscript.write_text('合成历史正文，仅验证身份。',encoding='utf-8')
    image=source/'figure.png'; image.write_bytes(b'synthetic image bytes')
    catalog=source/'figure-catalog.json'
    catalog.write_text(json.dumps({'question_ids':['q1'],'figures':[{'id':'f1','category':'result',
      'question_ids':['q1'],'title':'合成图','purpose':'检查字节','formal':True,
      'files':{'png':{'path':'figure.png','sha256':sha_file(image)}}}]}),encoding='utf-8')
    policy=inputs/'frozen-policy.json';policy.write_bytes(b'{}\r\n')
    context={'documents':[{'path':'resources/paper/chinese-modeling-policy.json','sha256':sha_file(policy),'text':'{}\n'}]}
    for path in [source/'writer-context.json',inputs/'writer-context.json']:
        path.write_text(json.dumps(context),encoding='utf-8')
    aid=str(uuid.uuid4());bid=str(uuid.uuid4())
    payload={'files':[{'source':'resources/paper/chinese-modeling-policy.json','snapshot':'inputs/frozen-policy.json','sha256':sha_file(policy)}],
      'chapters':[{'question_id':'q1'}],'run_id':aid,'project_id':'synthetic',
      'context_sha256':sha_file(inputs/'writer-context.json')}
    manifest=inputs/'input-manifest.json';manifest.write_text(json.dumps(payload),encoding='utf-8')
    payload['manifest_sha256']=sha_file(manifest)
    with historical_review_context('a'*64,sha_file(policy)):
        text=manuscript_record(manuscript,catalog,decision='approve',actor='TEST_ONLY',statement='合成确认',reason='合成测试')
        figures=selection_record(catalog,['f1'],decision='approve',actor='TEST_ONLY',statement='合成确认',reason='合成测试')
    build={'id':bid,'assembly_run_id':aid,'project_id':'synthetic','payload':{
      'sealed':{p.relative_to(tmp_path).as_posix():sha_file(p) for p in source.iterdir()},
      'context_identity':digest(context),'manuscript_review':text,'figure_review':figures}}
    assembly={'id':aid,'project_id':'synthetic','payload':payload}
    return tmp_path,build,assembly,source,inputs


def test_frozen_review_survives_current_context_without_granting_permission(frozen):
    result=verify_frozen_build(*frozen)
    assert result['historical_integrity_valid']
    assert result['historical_manuscript_review']=='approved'
    assert result['historical_figure_review']=='approved'
    assert result['can_export_current'] is False
    assert result['new_approval_created'] is False


@pytest.mark.parametrize('target',['source','input','manifest'])
def test_tampered_historical_files_rejected(frozen,target):
    root,build,assembly,source,inputs=frozen
    path={'source':source/MD_NAME,'input':inputs/'frozen-policy.json','manifest':inputs/'input-manifest.json'}[target]
    path.write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='[Cc]hanged'):
        verify_frozen_build(*frozen)


def test_wrong_build_binding_and_unsealed_context_rejected(frozen):
    root,build,assembly,source,inputs=frozen
    broken=deepcopy(build);broken['assembly_run_id']=str(uuid.uuid4())
    with pytest.raises(ValueError,match='identity mismatch'):
        verify_frozen_build(root,broken,assembly,source,inputs)
    broken=deepcopy(build);broken['payload']['sealed'].pop('build/source/writer-context.json')
    with pytest.raises(ValueError,match='not sealed'):
        verify_frozen_build(root,broken,assembly,source,inputs)
