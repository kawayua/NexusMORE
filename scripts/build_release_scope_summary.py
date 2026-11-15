"""Consolidate reviewed source decisions without rewriting frozen ledgers.

This is a scope review builder, not a license grant or release approval.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = 'docs/release/resource-disposition-20261111.json'
LEDGER_SHA = 'a13e9b8b35620d87c11f1b6979dfbf7c3f701590486042774c7a60414b3a7e1c'


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def identity(name):
    path = ROOT / name
    return {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


def build():
    if identity(LEDGER)['sha256'] != LEDGER_SHA:
        raise ValueError('Frozen source ledger changed')
    ledger = read(LEDGER)
    sources = {item['id']: item for item in ledger['files']}
    if len(sources) != 251 or len(ledger['files']) != 251:
        raise ValueError('Expected 251 distinct source identities')
    rows = {}
    reports = {LEDGER}

    def add(source_id, category, outcome, report, targets=(), source_hash=None,
            handoff=(), capability_status='reviewed_scope_only'):
        if source_id in rows:
            raise ValueError('Source mapped more than once: ' + source_id)
        original = sources[source_id]
        if source_hash is not None and source_hash != original['source_sha256']:
            raise ValueError('Source identity mismatch: ' + source_id)
        reports.add(report)
        current_targets = [identity(path) for path in sorted(set(targets))]
        rows[source_id] = {
            'resource_id': source_id, 'source': original['source'],
            'source_path': original['source_path'],
            'source_sha256': original['source_sha256'],
            'initial_disposition': original['disposition'],
            'category': category, 'current_disposition': outcome,
            'original_source_in_distribution': False,
            'original_source_redistribution_approved': False,
            'decision_report': report, 'current_project_targets': current_targets,
            'target_hash_basis': 'current files; historical report hashes remain unchanged',
            'capability_status': capability_status, 'handoff': list(handoff),
        }

    for source in ledger['files']:
        if source['disposition'] == 'authorized_replacement':
            replacement = source['replacement']
            target = identity(replacement['package_path'])
            if target['sha256'] != replacement['sha256']:
                raise ValueError('Authorized replacement changed: ' + source['id'])
            add(source['id'], 'official-document-replacement',
                'use_pinned_authorized_official_replacement', LEDGER,
                [replacement['package_path']], handoff=['F2', 'F5', 'F6'],
                capability_status='official files available; registered execution and routing have separate scope')
            rows[source['id']]['authorized_replacement'] = replacement

    simple = [
        ('host-plugin-redesign-20261111', 'host-business', 'independent_project_redesign',
         ['src/harness/nexusmore-workflow.js', 'src/harness/package.json'], ['F2', 'F6', 'G'],
         'business bridge foundation exists; transport, desktop registration and UI not complete'),
        ('project-test-adoption-20261111', 'project-tests', 'retain_goals_in_project_tests',
         [], ['F6', 'H2'], 'project tests retained; tests do not imply missing features are implemented'),
        ('excluded-upstream-assets-20261111', 'excluded-assets', 'explicitly_excluded_no_replacement',
         [], [], 'excluded by user'),
        ('maintenance-review-20261111', 'maintenance', 'use_project_maintenance_policy',
         ['.gitignore', 'docs/changelog.md', 'pyproject.toml'], ['F2', 'F5'],
         'project policies retained; upstream automation not copied or executed'),
        ('algorithm-reference-review-20261111', 'algorithm-knowledge', 'retain_goal_original_text_excluded_until_authorized_or_replaced',
         ['src/modelcrew/resources/algorithms/index.md', 'docs/release/algorithm-retention-decision-20261112.json'],
         ['F5', 'F2', 'F6'], 'seven categories retained; current index/cards are not complete reference texts'),
        ('figure-tools-adaptation-20261112', 'figure-tools', 'project_python_adaptation',
         [], ['F2', 'F5', 'F6'], 'project helpers and gate checks implemented; full reference knowledge and generic routing separate'),
    ]
    for basename, category, outcome, targets, handoff, status in simple:
        report = 'docs/release/' + basename + '.json'
        for item in read(report)['files']:
            local_targets = list(targets)
            for target in item.get('project_targets', []):
                local_targets.append(target if isinstance(target, str) else target['path'])
            for test in item.get('project_tests', []):
                local_targets.append(test['path'])
            if category == 'figure-tools' and item['resource_id'] == 'resource-191':
                add(item['resource_id'], 'excluded-html-panel', 'explicitly_excluded_no_replacement',
                    report, source_hash=item['source_sha256'], capability_status='excluded by user')
            else:
                add(item['resource_id'], category, outcome, report, local_targets,
                    item['source_sha256'], handoff, status)

    report = 'docs/release/roles-workflow-adaptation-20261112.json'
    for item in read(report)['mappings']:
        for source_id in item['source_ids']:
            add(source_id, 'roles-and-workflow', 'project_local_contract_adaptation', report,
                [target['path'] for target in item['local_resources']], item['source_sha256'],
                ['F2', 'F5', 'F6'], 'local triad and read-only gate guidance; auxiliary features separate')

    report = 'docs/release/latex-tools-adaptation-20261112.json'
    latex = read(report)
    for item in latex['sources']:
        add(item['resource_id'], 'latex-tools', 'project_supported_latex_adaptation', report,
            latex['implementation']['targets'], item['source_sha256'], ['F2', 'F5', 'F6'],
            'Tectonic 0.17.0/Pandoc 3.6.4; other engines/external bibliography/arbitrary conversion unsupported')

    report = 'docs/release/remaining-resource-adaptation-20261112.json'
    for item in read(report)['source_mappings']:
        targets = [target['path'] for target in item.get('project_targets', [])]
        if item.get('project_target'):
            targets.append(item['project_target'])
        add(item['resource_id'], item['category'], 'project_supported_capability_adaptation', report,
            targets, item['source_sha256'], ['F2', 'F5', 'F6'], item['current_outcome'])

    if set(rows) != set(sources):
        raise ValueError('Unmapped identities: ' + str(sorted(set(sources) - set(rows))))
    manifest = read('src/modelcrew/resources/resource-manifest.json')
    runtime = []
    for item in manifest['files']:
        current = identity('src/modelcrew/resources/' + item['path'])
        if current['sha256'] != item['sha256'] or current['bytes'] != item['bytes']:
            raise ValueError('Runtime resource identity changed: ' + item['path'])
        runtime.append({**current, 'manifest_disposition': item['disposition']})
    if len(runtime) != 193 or len({item['path'] for item in runtime}) != 193:
        raise ValueError('Expected 193 unique declared runtime resources')
    official = read('src/modelcrew/resources/document-tools/manifest.json')
    for item in official['files']:
        current = identity('src/modelcrew/resources/document-tools/upstream/' + item['path'])
        if current['sha256'] != item['sha256']:
            raise ValueError('Official bundle hash mismatch: ' + item['path'])
    if len(official['files']) != 126:
        raise ValueError('Expected complete 126-file official bundle')
    guidance = read('src/modelcrew/resources/collaboration/manifest.json')
    if len(guidance['files']) != 21 or guidance['guidance_version'] != '1.3.0':
        raise ValueError('Unexpected current guidance scope')
    runtime_paths = {item['path'] for item in runtime}
    if any('src/modelcrew/resources/document-tools/upstream/' + item['path'] not in runtime_paths
           for item in official['files']):
        raise ValueError('Official bundle missing from runtime allowlist')
    reports.update([
        'configs/runtime-environment.json', 'configs/model-interface-scope.json',
        'configs/release-scope.json', 'src/modelcrew/resources/resource-manifest.json',
        'src/modelcrew/resources/document-tools/manifest.json',
        'src/modelcrew/resources/collaboration/manifest.json',
        'src/modelcrew/resources/capabilities/registry.json',
        'docs/release/pending-resource-review-20261112-adapted.json',
        'docs/release/deepseek-harness-desktop-review-20261112.json',
        'docs/release/latex-support-decision-20261112.json',
    ])
    return {
        'schema_version': '1.0.0', 'date': '2026-11-12',
        'status': 'consolidated_scope_ready_for_user_review_not_release_approval',
        'source_ledger': identity(LEDGER),
        'coverage': {'source_files': 251, 'mapped_once': len(rows), 'unmapped': 0,
                     'duplicate_ids': 0, 'initial_non_runtime_reviewed': 38,
                     'initial_pending_reviewed': 139,
                     'category_counts': dict(sorted(Counter(x['category'] for x in rows.values()).items())),
                     'initial_authorized_replacement_mappings': 74,
                     'official_bundle_files': 126, 'declared_runtime_resources': 193,
                     'local_guides': 21, 'guidance_version': '1.3.0'},
        'release_boundary': {'mode': 'Private; no public release permission',
                             'original_intake_sources_included': 0,
                             'full_knowledge_builtin': False,
                             'all_source_permissions_resolved': False,
                             'historical_pending_139_ledger_rewritten': False,
                             'project_license_selected': False},
        'runtime_scope': read('configs/runtime-environment.json'),
        'model_and_first_harness_scope': read('configs/model-interface-scope.json'),
        'registered_capability_scope': read('src/modelcrew/resources/capabilities/registry.json'),
        'handoff': [
            {'milestone': 'F2', 'task': 'Freeze wheel/sdist, CLI, optional dependencies and complete installed resource layout; determine JS distribution', 'acceptance': 'outside-source installation and all promised resources resolve without external skills'},
            {'milestone': 'F3', 'task': 'User configuration, data directories, initialization, diagnostics and first-download/mirror prerequisites', 'acceptance': 'no mandatory developer-machine paths; missing services/tools/fonts clearly reported'},
            {'milestone': 'F4', 'task': 'Fresh Windows x64/Python 3.13/Docker Linux service deployment and restart validation', 'acceptance': 'clean installation, required service startup, confirmation pause and recovery evidence'},
            {'milestone': 'F5', 'task': 'Project license, third-party notices; obtain permission or independently author retained knowledge/templates', 'acceptance': 'seven algorithm categories and promised math/Chinese paper knowledge have distributable coverage; original unlicensed texts remain excluded'},
            {'milestone': 'F6', 'task': 'Complete automatic knowledge/tool routing and registered capability gaps; provider-specific request adaptation', 'acceptance': 'actual reads/calls with hashes and receipts; no silent fallback or skipped approval/review'},
            {'milestone': 'G', 'task': 'DeepSeek Harness Desktop 0.2.2-rc.1 live MCP/confirmation integration; choose exact model IDs and capability matrix before compatibility claims', 'acceptance': 'tool discovery, trustworthy user decisions, repeated calls, reconnect/recovery and artifact access verified'},
            {'milestone': 'H2', 'task': 'Clean-environment target-harness end-to-end acceptance', 'acceptance': 'confirmed plan/results, Chinese Markdown and figure approval, same-source formal export and complete PDF review'},
        ],
        'acceptance': {'scope_consolidation_checks': 'passed', 'user_approval': 'pending',
                       'F1_completion_recorded': False, 'public_release_approved': False,
                       'provider_compatibility_verified': False, 'harness_live_compatibility_verified': False},
        'sources': [rows[key] for key in sorted(rows)],
        'runtime_resources': runtime,
        'input_evidence': [identity(path) for path in sorted(reports)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New JSON file; existing review records are never overwritten')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT.resolve()):
        parser.error('Output must remain inside the workspace')
    value = build()
    with output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'passed', **value['coverage'],
                      'user_approval': 'pending'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
