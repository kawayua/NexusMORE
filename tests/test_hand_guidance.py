"""Shared policy admission and frozen-call recovery; no real model or database."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from modelcrew.hand_guidance import (SNAPSHOT_NAME, load_bundle, guidance_context,
                                    freeze_guidance, frozen_bundle, frozen_context)
from modelcrew.collaboration import REQUIRED_CHECKS, RESPONSIBILITIES


def test_local_contracts_and_independent_gate_contexts():
    bundle = load_bundle()
    assert bundle['manifest']['responsibilities'] == RESPONSIBILITIES
    for gate, checks in REQUIRED_CHECKS.items():
        context = guidance_context(bundle, gate)
        assert context['read_only'] and context['independent_context_required']
        assert context['required_checks'] == checks
        assert not context['review_grants_user_approval']
        assert not any(x['path'].endswith('-hand.md') for x in context['documents'])
        assert 'messages' not in context and 'evidence' not in context
    assert not guidance_context(bundle, 'coding')['read_only']
    with pytest.raises(ValueError, match='selector'):
        guidance_context(bundle, 'Reviewer')


def test_english_is_explicit_optional_writing_context():
    bundle = load_bundle()
    ordinary = guidance_context(bundle, 'writing')
    english = guidance_context(bundle, 'writing', english=True)
    assert not any(x['path'] == 'english-adaptation.md' for x in ordinary['documents'])
    assert any(x['path'] == 'english-adaptation.md' for x in english['documents'])
    with pytest.raises(ValueError, match='explicit writing'):
        guidance_context(bundle, 'W2', english=True)


def test_frozen_bytes_preserved_across_installed_policy_updates(tmp_path, monkeypatch):
    expected = freeze_guidance(tmp_path)
    frozen = frozen_bundle(tmp_path, expected)
    import modelcrew.hand_guidance as module
    monkeypatch.setattr(module, 'load_bundle', lambda: (_ for _ in ()).throw(AssertionError('must use frozen version')))
    assert frozen_context(tmp_path, expected, 'M1') == guidance_context(frozen, 'M1')
    with pytest.raises(FileExistsError):
        # Restore only loading so this checks the write-once output boundary.
        monkeypatch.undo()
        freeze_guidance(tmp_path)
    with (tmp_path / SNAPSHOT_NAME).open('ab') as stream:
        stream.write(b' ')
    with pytest.raises(ValueError, match='Frozen'):
        frozen_context(tmp_path, expected, 'M1')


def test_document_bytes_cannot_be_changed_with_unchanged_manifest():
    from modelcrew.hand_guidance import validate_bundle
    bundle = load_bundle()
    assert any('\r\n' in value for value in bundle['documents'].values()) or all('\n' in value for value in bundle['documents'].values())
    bundle['documents']['quality-gates.md'] += 'bypass'
    with pytest.raises(ValueError, match='document changed'):
        validate_bundle(bundle)


def test_runtime_call_uses_frozen_gate_scope_and_cached_response(tmp_path, monkeypatch):
    from modelcrew import hand_runtime as runtime
    expected = freeze_guidance(tmp_path)
    monkeypatch.setattr(runtime, 'run_folder', lambda row: tmp_path)
    monkeypatch.setattr(runtime, 'save', lambda *args, **kwargs: None)
    row = {'hand': 'coding', 'phase': 'REVIEW_P1',
           'payload': {'ops': {}, 'collaboration_guidance_sha256': expected}}
    class Model:
        def __init__(self): self.calls = []
        def call(self, folder, stage, system, data, **kwargs):
            self.calls.append(copy.deepcopy(data))
            assert data['nexusmore_guidance']['selector'] == 'P1'
            assert 'nexusmore_guidance' in system
            return {'fixture': True}, {'status': 'completed'}
    model = Model()
    data = {'gate': 'P1', 'evidence': {'contract': {'fixture': True}}}
    assert runtime.provider(None, row, 'P1-0', 'P1', data, model=model)[0] == {'fixture': True}
    assert 'nexusmore_guidance' not in data
    runtime.provider(None, row, 'P1-0', 'P1', data, model=model)
    assert len(model.calls) == 1
    (tmp_path / SNAPSHOT_NAME).write_bytes(b'changed')
    with pytest.raises(ValueError, match='Frozen'):
        runtime.provider(None, row, 'P1-0', 'P1', data, model=model)
    assert len(model.calls) == 1


def test_historical_operation_does_not_gain_new_inputs(tmp_path, monkeypatch):
    from modelcrew import hand_runtime as runtime
    monkeypatch.setattr(runtime, 'run_folder', lambda row: tmp_path)
    monkeypatch.setattr(runtime, 'save', lambda *args, **kwargs: None)
    row = {'hand': 'writing', 'phase': 'PLAN', 'payload': {'ops': {}}}
    class Model:
        def call(self, folder, stage, system, data, **kwargs):
            assert data == {'legacy': True}
            assert 'nexusmore_guidance' not in system
            return {'legacy': True}, {'status': 'completed'}
    runtime.provider(None, row, 'legacy', 'Writer-plan', {'legacy': True}, model=Model())
    assert not (tmp_path / SNAPSHOT_NAME).exists()

def test_python_pdf_policy_is_shared_and_old_context_shape_is_preserved():
    from modelcrew.hand_guidance import validate_bundle
    bundle=load_bundle()
    for selector in [*RESPONSIBILITIES,*REQUIRED_CHECKS]:
        context=guidance_context(bundle,selector)
        assert context['figure_tools_policy']=={
            'protocol':'1.0.0','backend':'python','all_pdf_pages_required':True,
            'html_panel':False,'machine_checks_are_visual_approval':False}
    old=copy.deepcopy(bundle)
    old['manifest']['guidance_version']='1.0.0'
    for key in ['backend','figure_tools_protocol','html_panel_included','all_pdf_pages_required']:
        old['manifest']['boundaries'].pop(key,None)
    old['manifest_sha256']=hashlib.sha256(json.dumps(old['manifest'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    validate_bundle(old)
    assert 'figure_tools_policy' not in guidance_context(old,'coding')
