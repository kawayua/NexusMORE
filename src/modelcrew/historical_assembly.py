"""Verify sealed historical assembly bytes; never authorize current execution."""
import json
from pathlib import Path

from .contracts import digest
from .collaboration import sha_file
from .repository_migration import resolve_repository_path as workspace_path
from .writing_reviews import review_status
from .assembly_compose import MD_NAME


def verify_frozen_build(root, build, assembly, source, input_folder):
    root = Path(root).resolve()
    source, input_folder = Path(source), Path(input_folder)
    if str(build['assembly_run_id']) != str(assembly['id']) or build['project_id'] != assembly['project_id']:
        raise ValueError('Historical build/assembly identity mismatch')
    payload = build['payload']; frozen = assembly['payload']
    sealed = payload.get('sealed', {})
    required = [source/MD_NAME, source/'figure-catalog.json', source/'writer-context.json']
    for path in required:
        if not any(workspace_path(root,name)==path.resolve() for name in sealed):
            raise ValueError('Historical source file is not sealed')
    verified = 0
    for name, expected in sealed.items():
        if sha_file(workspace_path(root, name)) != expected:
            raise ValueError('Changed historical build file: '+name)
        verified += 1
    for filename, key in [('input-manifest.json','manifest_sha256'), ('writer-context.json','context_sha256')]:
        if sha_file(input_folder/filename) != frozen[key]:
            raise ValueError('Historical input manifest or context changed')
    manifest = json.loads((input_folder/'input-manifest.json').read_text(encoding='utf-8'))
    if (manifest['files'] != frozen['files'] or manifest['chapters'] != frozen['chapters'] or
            str(manifest['run_id']) != str(assembly['id']) or manifest['project_id'] != assembly['project_id']):
        raise ValueError('Historical input manifest binding mismatch')
    for item in frozen['files']:
        if sha_file(workspace_path(root, item['snapshot'])) != item['sha256']:
            raise ValueError('Changed historical input snapshot: '+item['snapshot'])
        verified += 1
    context = json.loads((source/'writer-context.json').read_text(encoding='utf-8'))
    if digest(context) != payload['context_identity']:
        raise ValueError('Historical source context identity mismatch')
    policy = next(d for d in context['documents'] if d['path']=='resources/paper/chinese-modeling-policy.json')
    # Stored text uses universal newlines; bind raw hashes to an original sealed
    # snapshot, then compare decoded text. Never normalize or rewrite its hash.
    policy_files = [item for item in frozen['files']
                    if item.get('source') == policy['path'] and item['sha256'] == policy['sha256']]
    if not any(workspace_path(root,item['snapshot']).read_text(encoding='utf-8') == policy['text']
               for item in policy_files):
        raise ValueError('Historical policy snapshot binding mismatch')
    reviews = review_status(source/MD_NAME, source/'figure-catalog.json', payload.get('manuscript_review'),
                            payload.get('figure_review'), historical_policy_sha256=policy['sha256'])
    # Do not return review_status.can_export: historical checks cannot grant current permission.
    return {'build_id':str(build['id']), 'assembly_run_id':str(assembly['id']),
            'historical_integrity_valid':True, 'verified_files':verified,
            'historical_manuscript_review':reviews['manuscript'],
            'historical_figure_review':reviews['figure_selection'],
            'can_export_current':False, 'new_approval_created':False,
            'scope':'sealed historical files and existing scoped decisions; no current-policy admission'}
