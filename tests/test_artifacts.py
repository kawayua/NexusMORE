from modelcrew.project_assets import asset_path,local_history
import uuid
import pytest
from modelcrew.config import ROOT
from modelcrew.inputs import file_hash
from modelcrew.artifacts import snapshot_artifacts,same_artifacts
from modelcrew.reviews import artifact_status

def test_snapshots_survive_original_overwrite_and_reuse_identical_bytes():
    folder=asset_path(ROOT,'stage-b/runs')/('snapshot-test-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    p=folder/'source.txt';p.write_text('TEST_ONLY '+uuid.uuid4().hex,encoding='utf-8')
    source={'path':str(p.relative_to(ROOT)),'sha256':file_hash(p),'role':'test_artifact'}
    first=snapshot_artifacts([source]);assert first==snapshot_artifacts([source])
    assert same_artifacts(first,[source])
    p.write_text('TEST_ONLY overwritten',encoding='utf-8')
    assert artifact_status(first[0])=='verified' and artifact_status(source)=='changed'
    with pytest.raises(ValueError,match='changed before'):snapshot_artifacts([source])

def test_snapshot_rejects_existing_corruption():
    folder=asset_path(ROOT,'stage-b/runs')/('snapshot-corrupt-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    p=folder/'x';p.write_text('TEST_ONLY '+uuid.uuid4().hex,encoding='utf-8')
    source={'path':str(p),'sha256':file_hash(p),'role':'test_artifact'};saved=snapshot_artifacts([source])[0]
    (asset_path(ROOT,saved['path'])).write_text('TEST_ONLY corrupted snapshot',encoding='utf-8')
    with pytest.raises(ValueError,match='corrupted'):snapshot_artifacts([source])
