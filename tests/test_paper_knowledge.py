"""Current authored paper inputs must resolve without changing historical inputs."""
from copy import deepcopy
import hashlib
from pathlib import Path
import pytest
from modelcrew.config import ROOT
from modelcrew.modeling_paper import writing_context
from modelcrew.package_resources import resource
from modelcrew.paper_layout import REQUIRED,LEGACY_REQUIRED,contract
from modelcrew.project_assets import asset_path
from modelcrew.repository_migration import resolve_repository_location


def test_current_context_reads_five_authored_files_and_hashes():
    context=writing_context();documents={d['path']:d for d in context['documents']}
    assert context['workflow']['paper_reference_version']=='1.0.0'
    for name in REQUIRED:
        raw=resource(name.removeprefix('resources/')).read_bytes()
        assert documents[name]['text']==raw.decode('utf-8').replace('\r\n','\n')
        assert documents[name]['sha256']==hashlib.sha256(raw).hexdigest()
    assert contract(context)['template']==REQUIRED[-1]


def test_current_template_does_not_replace_legacy_main_or_chinese_sources():
    for name in LEGACY_REQUIRED:
        assert asset_path(ROOT,name)==resolve_repository_location(ROOT,name)
        assert asset_path(ROOT,name)!=Path(resource(REQUIRED[-1].removeprefix('resources/')))


def test_missing_current_reference_never_falls_back_to_history(monkeypatch):
    import modelcrew.project_assets as assets
    def unavailable(name):raise FileNotFoundError(name)
    monkeypatch.setattr(assets,'resource',unavailable)
    with pytest.raises(FileNotFoundError):assets.asset_path(ROOT,REQUIRED[0])


def test_current_contract_cannot_downgrade_to_complete_legacy_set():
    context=writing_context();legacy=deepcopy(context)
    for current,old in zip(REQUIRED,LEGACY_REQUIRED):
        doc=next(d for d in legacy['documents'] if d['path']==current);doc['path']=old
    with pytest.raises(ValueError,match='five'):contract(legacy)
    legacy['workflow'].pop('paper_reference_version')
    result=contract(legacy)
    assert result['template']==LEGACY_REQUIRED[-1] and result['version']=='1.0.0'


@pytest.mark.parametrize('changed',[r'12pt',r'left=2.5cm'])
def test_unsupported_baseline_needs_explicit_mapping(changed):
    context=deepcopy(writing_context())
    doc=next(d for d in context['documents'] if d['path']==REQUIRED[-1])
    doc['text']=doc['text'].replace(changed,'11pt' if changed=='12pt' else 'left=1cm')
    with pytest.raises(ValueError):contract(context)
