"""Inventory release inputs without importing dependencies or granting redistribution permission."""
import argparse
from collections import Counter
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(site_packages):
    resource_root = ROOT / 'src/modelcrew/resources'
    manifest = json.loads((resource_root / 'resource-manifest.json').read_text(encoding='utf-8'))
    upstream = json.loads((resource_root / 'document-tools/manifest.json').read_text(encoding='utf-8'))
    official = {'document-tools/upstream/' + row['path']: row for row in upstream['files']}
    original = json.loads((ROOT / 'docs/release/resource-disposition-20261111.json').read_text(encoding='utf-8'))
    original_hashes = {}
    for row in original['files']:
        original_hashes.setdefault(row['source_sha256'], []).append(row['id'])
    resources = []
    for row in manifest['files']:
        path = resource_root / row['path']
        actual = sha(path)
        if actual != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('Resource mismatch: ' + row['path'])
        source = official.get(row['path'])
        if source and (source['sha256'] != actual or source['bytes'] != path.stat().st_size):
            raise ValueError('Official resource identity mismatch: ' + row['path'])
        resources.append({'path': row['path'], 'sha256': actual, 'bytes': path.stat().st_size,
            'category': 'official_document_tool' if source else 'local_runtime_resource',
            'license': source['license'] if source else 'project_license_declared_origin_review_still_required',
            'source_url': source.get('url') if source else None,
            'original_intake_exact_hash_matches': original_hashes.get(actual, []),
            'redistribution_cleared_by_this_audit': False})
    installed = []
    for dist in distributions(path=[str(site_packages.resolve())]):
        metadata = dist.metadata
        if metadata['Name'].lower() == 'nexusmore':
            continue
        texts = []
        for member in dist.files or []:
            name = str(member).replace('\\', '/')
            if '..' in Path(name).parts:
                continue
            if (any(token in Path(name).name.lower() for token in ['license', 'licence', 'notice', 'copying'])
                    or any(part.lower() in {'licenses','licences','build_licenses'} for part in Path(name).parts)):
                file = dist.locate_file(member)
                if file.is_file():
                    texts.append({'path': name, 'sha256': sha(file), 'bytes': file.stat().st_size})
        classifiers = [c for c in metadata.get_all('Classifier', []) if c.startswith('License ::')]
        expr = metadata.get('License-Expression')
        declared = metadata.get('License', '').strip()
        # Long License fields may contain bundled-library exceptions; do not
        # classify the main project from an incidental GPL/AGPL mention.
        labels = ' '.join([expr or '', declared.splitlines()[0] if declared else '', *classifiers]).lower()
        attention = []
        if 'agpl' in labels or 'affero' in labels:
            attention.append('AGPL_or_commercial_route_decision_required')
        elif 'lgpl' in labels or 'lesser' in labels:
            attention.append('LGPL_obligations_and_binary_components_review')
        elif 'gpl' in labels or 'general public license' in labels:
            attention.append('copyleft_scope_review')
        if len(declared.splitlines()) > 10:
            attention.append('bundled_license_text_requires_component_review')
        if not (expr or declared or classifiers):
            attention.append('license_metadata_missing')
        if not texts:
            attention.append('no_license_text_found_in_installed_file_inventory')
        installed.append({'name': metadata['Name'], 'version': dist.version,
            'license_expression': expr, 'license_field_excerpt': declared[:600],
            'license_classifiers': classifiers, 'license_files': texts,
            'project_urls': metadata.get_all('Project-URL', []), 'home_page': metadata.get('Home-page'),
            'attention': attention, 'scope': 'installed_runtime_metadata_not_independent_upstream_legal_clearance'})
    installed.sort(key=lambda row: row['name'].lower())
    project = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    return {'schema_version': '1.0.0', 'status': 'inventory_complete_not_release_clearance',
        'project_license_file_present': (ROOT/'LICENSE').is_file(),
        'project_license_metadata': project.get('license'),
        'source_runtime_site_packages': str(site_packages.resolve()),
        'resources': resources, 'resource_counts': dict(Counter(row['category'] for row in resources)),
        'dependencies': installed, 'dependency_count': len(installed),
        'direct_dependency_groups': {'core': project['dependencies'], **project['optional-dependencies']},
        'limits': ['Exact hash matching only detects byte-identical old intake; no derivative-work clearance inferred.',
            'Metadata and license file presence do not prove complete license compliance.',
            'Downloaded native tools, container contents, model weights, fonts and user materials need separate review.',
            'No dependency code imported; no network or publication performed.'],
        'public_release_cleared': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-packages', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.site_packages.is_dir():
        parser.error('site-packages directory missing')
    result = audit(args.site_packages)
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print(json.dumps({'status': result['status'], 'resources': len(result['resources']),
        'dependencies': result['dependency_count'], 'attention': [row['name'] for row in result['dependencies'] if row['attention']]}, ensure_ascii=False))

if __name__ == '__main__':
    main()
