"""Project-authored hand/gate guidance, frozen per new run and shared by hosts.

This supplies context, not review authority, user decisions or a tool executor.
Historical operations without a guidance binding keep their original protocol.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

from .package_resources import resource

SNAPSHOT_NAME = 'collaboration-guidance.json'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _name(value):
    if not isinstance(value, str) or not value or value != PurePosixPath(value).name or value in {'.', '..'} or ':' in value or '\\' in value:
        raise ValueError('Invalid collaboration guidance resource name')
    return value


def validate_bundle(bundle):
    manifest = bundle['manifest']
    if manifest['schema_version'] != '1.0.0':
        raise ValueError('Unsupported collaboration guidance schema')
    entries = manifest['files']
    names = [_name(item['path']) for item in entries]
    if len(names) != len(set(names)) or set(names) != set(bundle['documents']):
        raise ValueError('Collaboration guidance file set differs')
    if _sha(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')) != bundle['manifest_sha256']:
        raise ValueError('Collaboration guidance manifest changed')
    for item in entries:
        raw = bundle['documents'][item['path']].encode('utf-8')
        if _sha(raw) != item['sha256'] or len(raw) != item['bytes']:
            raise ValueError('Collaboration guidance document changed: ' + item['path'])
    for route in [*manifest['routes'].values(), *manifest.get('optional_routes', {}).values()]:
        if not route or len(route) != len(set(route)) or any(name not in names for name in route):
            raise ValueError('Invalid collaboration guidance route')
    return bundle


def load_bundle():
    """Read the installed resources; never fall back to an external skills folder."""
    manifest = json.loads(resource('collaboration/manifest.json').read_text(encoding='utf-8'))
    # Tie the new bundle to the runtime's existing hand and gate contracts.
    from .hand_contracts import RESPONSIBILITIES, REQUIRED_CHECKS
    if manifest['responsibilities'] != RESPONSIBILITIES or manifest['required_checks'] != REQUIRED_CHECKS:
        raise ValueError('Collaboration guidance differs from local hand/gate contracts')
    if set(manifest['routes']) != set(RESPONSIBILITIES) | set(REQUIRED_CHECKS):
        raise ValueError('Missing collaboration hand/gate guidance route')
    boundaries = manifest['boundaries']
    if boundaries['review_is_user_approval'] or not boundaries['quality_read_only'] or not boundaries['independent_context_required']:
        raise ValueError('Independent read-only guidance required')
    bundle = {'manifest': manifest,
              'manifest_sha256': _sha(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')),
              'documents': {item['path']: resource('collaboration/' + _name(item['path'])).read_bytes().decode('utf-8') for item in manifest['files']}}
    return validate_bundle(bundle)


def freeze_guidance(folder):
    """Write once. A run retains this version even if installed defaults change."""
    bundle = load_bundle()
    target = Path(folder) / SNAPSHOT_NAME
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(bundle, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return _sha(target.read_bytes())


def frozen_bundle(folder, expected_sha256):
    raw = (Path(folder) / SNAPSHOT_NAME).read_bytes()
    if _sha(raw) != expected_sha256:
        raise ValueError('Frozen collaboration guidance changed')
    return validate_bundle(json.loads(raw))


def guidance_context(bundle, selector, *, english=False):
    """Select only project policy. Author output/history never enters this packet."""
    validate_bundle(bundle)
    manifest = bundle['manifest']
    if selector not in manifest['routes']:
        raise ValueError('Unknown collaboration guidance selector')
    if english and selector != 'writing':
        raise ValueError('English adaptation belongs to an explicit writing request')
    names = list(manifest['routes'][selector])
    if english:
        names += manifest['optional_routes']['english']
    entries = {item['path']: item for item in manifest['files']}
    context = {'guidance_version': manifest['guidance_version'], 'manifest_sha256': bundle['manifest_sha256'],
            'selector': selector, 'read_only': selector in manifest['required_checks'],
            'independent_context_required': selector in manifest['required_checks'],
            'review_grants_user_approval': False,
            'required_checks': copy.deepcopy(manifest['required_checks'].get(selector, [])),
            'documents': [{**entries[name], 'text': bundle['documents'][name]} for name in names]}


    if 'figure_tools_protocol' in manifest['boundaries']:
        context['figure_tools_policy'] = {
            'protocol': manifest['boundaries']['figure_tools_protocol'],
            'backend': 'python', 'all_pdf_pages_required': True,
            'html_panel': False, 'machine_checks_are_visual_approval': False}
    return context


def frozen_context(folder, expected_sha256, selector):
    return guidance_context(frozen_bundle(folder, expected_sha256), selector)
