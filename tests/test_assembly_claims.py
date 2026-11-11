"""Exact frozen claim paths are checked separately from lifecycle mocks."""
import json
import uuid
import pytest
from modelcrew import assembly_builds as ab
from modelcrew import assembly_runtime as ar
from modelcrew.collaboration import sha_file
from modelcrew.contracts import digest
from modelcrew.workflow import WorkflowError


@pytest.fixture
def evidence(tmp_path,monkeypatch):
    monkeypatch.setattr(ab,'ROOT',tmp_path)
    frozen=tmp_path/'freeze'/'snapshot';source=frozen/'original';source.mkdir(parents=True)
    monkeypatch.setattr(ar,'folder',lambda key:tmp_path/'freeze')
    result={'rows':[{'a/b':2}]}
    claim={'id':'C1','statement':'合成结果仅用于测试','evidence':[{'artifact_id':'result','selector':'/rows/0/a~1b'}]}
    for name,data in [('result',result),('outline',{'claims':[claim]})]:
        (source/(name+'.json')).write_text(json.dumps(data),encoding='utf-8')
    artifacts=[{'artifact_id':name,'path':'original/'+name+'.json','sha256':sha_file(source/(name+'.json'))} for name in ['result','outline']]
    snapshot={'artifacts':artifacts};key=digest(snapshot)
    snap=source/'records/Snapshot'/(key+'.json');snap.parent.mkdir(parents=True);snap.write_text(json.dumps(snapshot),encoding='utf-8')
    row={'id':str(uuid.uuid4()),'payload':{'chapters':[{'question_id':'q','manuscript':'original/paper.md','binding':{'task_id':'TEST_ONLY'},'W1':{'snapshot_sha256':key}}]}}
    return row,source


def test_precise_claim_selector_is_preserved(evidence):
    row,source=evidence
    report=ab.claim_evidence(row)
    assert report['claims'][0]['global_claim_id']=='q-C1'
    assert report['claims'][0]['evidence'][0]['selector']=='/rows/0/a~1b'


def test_changed_claim_artifact_rejected(evidence):
    row,source=evidence;(source/'result.json').write_text('{}',encoding='utf-8')
    with pytest.raises(WorkflowError,match='claim artifact changed'):ab.claim_evidence(row)


def test_missing_json_pointer_rejected(evidence):
    row,source=evidence
    # Rebuild this synthetic snapshot legitimately; the pointer itself is invalid.
    outline={'claims':[{'id':'C1','statement':'TEST_ONLY','evidence':[{'artifact_id':'result','selector':'/absent'}]}]}
    (source/'outline.json').write_text(json.dumps(outline),encoding='utf-8')
    artifacts=[{'artifact_id':n,'path':'original/'+n+'.json','sha256':sha_file(source/(n+'.json'))} for n in ['result','outline']]
    snapshot={'artifacts':artifacts};key=digest(snapshot)
    (source/'records/Snapshot'/(key+'.json')).write_text(json.dumps(snapshot),encoding='utf-8')
    row['payload']['chapters'][0]['W1']['snapshot_sha256']=key
    with pytest.raises(WorkflowError):ab.claim_evidence(row)
