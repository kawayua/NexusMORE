"""Verify relocated bytes and exact historical path resolution; no database writes."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path,PurePosixPath
from modelcrew.repository_migration import relative_path, resolve_historical, sha256


def check(root):
    root=Path(root).resolve(strict=True)
    policy=json.loads((root/'configs/repository-layout.json').read_text(encoding='utf-8'))
    records=[json.loads(relative_path(root,name).read_text(encoding='utf-8'))
             for name in policy['relocation_records']]
    index={}
    for record in records:
        for item in record['files']:index.setdefault(item['old_path'],[]).append(item)
    checked_parents=set()
    def audit_path(name):
        # This read-only batch checks shared parents once, then rechecks them at
        # completion. Runtime resolution keeps the per-call strict path checker.
        parts=PurePosixPath(name)
        if not name or parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe registered audit path')
        candidate=root.joinpath(*parts.parts)
        if candidate==root:raise ValueError('Repository root is not a file')
        for parent in candidate.parents:
            if parent==root:break
            if parent not in checked_parents:
                if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Audit path crosses link')
                checked_parents.add(parent)
        if candidate.is_symlink() or (hasattr(candidate,'is_junction') and candidate.is_junction()):raise ValueError('Audit file is a link')
        return candidate
    def verify_item(item):
        target=resolve_historical(root,item['old_path'],records,file_index=index,path_resolver=audit_path)
        if sha256(target) != item['sha256'] or target.stat().st_size != item['bytes']:
            raise ValueError('Changed relocated file identity')
        return 1
    count=0; links=0
    with ThreadPoolExecutor(max_workers=8) as workers:
        for record in records:
            count+=sum(workers.map(verify_item,record['files']))
            for link in record.get('links',[]):
                target=root/link['new_path']
                if not (target.is_symlink() or (hasattr(target,'is_junction') and target.is_junction())) or os.readlink(target)!=link['target']:
                    raise ValueError('Historical link metadata changed')
                links+=1
    for parent in checked_parents:
        if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise ValueError('Audit parent changed to link')
    return {'status':'passed','records':len(records),'verified_files':count,
            'links_verified_without_traversal':links, 'scope':'registered_file_bytes_and_exact_resolver_only',
            'database_recovery_verified':False}


if __name__ == '__main__':
    print(json.dumps(check(Path(__file__).resolve().parents[1]),ensure_ascii=False))
