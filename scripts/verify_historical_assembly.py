"""Read-only historical assembly verification, independent of current workflow admission."""
import argparse
import json
from pathlib import Path
import uuid
import psycopg
from psycopg.rows import dict_row
from modelcrew.config import ROOT, database_url
from modelcrew import assembly_builds, assembly_runtime
from modelcrew.historical_assembly import verify_frozen_build
from modelcrew.contracts import digest
from modelcrew.modeling_paper import writing_context
from modelcrew.repository_migration import resolve_repository_location


def verify(project, build_id):
    key=str(uuid.UUID(build_id))
    with psycopg.connect(database_url(),row_factory=dict_row,connect_timeout=5,
                         options='-c default_transaction_read_only=on -c statement_timeout=30000') as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        build=db.execute('SELECT * FROM mc_assembly_builds WHERE id=%s AND project_id=%s',(key,project)).fetchone()
        if build is None:
            raise ValueError('Unknown historical build')
        assembly=db.execute('SELECT * FROM mc_assembly_runs WHERE id=%s AND project_id=%s',
                            (build['assembly_run_id'],project)).fetchone()
        if assembly is None:
            raise ValueError('Unknown historical assembly')
        source=resolve_repository_location(ROOT,'stage-e/builds/'+str(build['id'])+'/source')
        frozen_input=resolve_repository_location(ROOT,'stage-e/runs/runtime/'+str(assembly['id']))
        # New-layout builds have no stage alias: keep the public folder locators for those.
        if not source.exists():source=assembly_builds.source_folder(build)
        if not frozen_input.exists():frozen_input=assembly_runtime.folder(assembly['id'])
        result=verify_frozen_build(ROOT,build,assembly,source,frozen_input)
        result['current_context_matches_frozen'] = digest(writing_context()) == build['payload']['context_identity']
        result['database_read_only'] = db.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--build',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'tmp'):
        parser.error('Verification evidence must stay under workspace tmp/')
    if output.exists():
        raise FileExistsError(output)
    try:
        result=verify(args.project,args.build)
    except (ValueError,OSError,KeyError,StopIteration,psycopg.Error) as exc:
        result={'historical_integrity_valid':False,'error_type':type(exc).__name__,
                'can_export_current':False,'new_approval_created':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['historical_integrity_valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
