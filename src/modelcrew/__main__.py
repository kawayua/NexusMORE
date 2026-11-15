"""Trusted local CLI; actors are audit labels, not authentication."""
import argparse,json,sys
from pathlib import Path

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str,allow_nan=False)

def main():
    from . import __version__
    p=argparse.ArgumentParser(prog='modelcrew')
    p.add_argument('--version',action='version',version='nexusmore '+__version__)
    p.add_argument('--workspace',type=Path,help='Dedicated user workspace; set before the command')
    p.add_argument('--config',type=Path,help='Explicit settings JSON; no fallback if missing')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('resources-check',help='Verify declared bundled resources; no services required')
    c=sub.add_parser('license-info',help='Read license, no-warranty notice and source access information offline')
    c.add_argument('--text',choices=['agpl','apache'])
    sub.add_parser('init',help='Create user settings and directories without starting services')
    sub.add_parser('config-show',help='Show redacted configuration presence and paths')
    c=sub.add_parser('doctor');c.add_argument('--profile',choices=['core','workflow','full'],default='core');c.add_argument('--services',action='store_true')
    c=sub.add_parser('environment',help='Prepare and operate workspace-owned services and native tools')
    c.add_argument('action',choices=['prepare','up','status','migrate','restart','stop','executor','tools','smoke','recover','documents','setup','embedding','retrieval'])
    c.add_argument('--offline',action='store_true');c.add_argument('--archives',type=Path);c.add_argument('--output',type=Path);c.add_argument('--report',type=Path);c.add_argument('--model',type=Path)
    c=sub.add_parser('route',help='Shared program-owned reference/document routing; no approvals or arbitrary code')
    c.add_argument('--request',type=Path,required=True);c.add_argument('--input-root',type=Path,required=True)
    c.add_argument('--output',type=Path,required=True);c.add_argument('--plan-only',action='store_true')
    sub.add_parser('init-db')
    c=sub.add_parser('validate');c.add_argument('contract',type=Path)
    c=sub.add_parser('inspect-input');c.add_argument('path',type=Path);c.add_argument('--role',default='dataset');c.add_argument('--kind');c.add_argument('--output',type=Path)
    c=sub.add_parser('draft-inputs');c.add_argument('contract',type=Path);c.add_argument('--output',type=Path,required=True)
    c=sub.add_parser('resolve-input');c.add_argument('contract',type=Path);c.add_argument('--input-id',required=True);c.add_argument('--question-id',required=True);c.add_argument('--resolution',required=True);c.add_argument('--output',type=Path,required=True)
    c=sub.add_parser('generate-draft');c.add_argument('--statement',type=Path,required=True);c.add_argument('--attachment',action='append',nargs=2,metavar=('ROLE','PATH'),default=[]);c.add_argument('--scope',required=True);c.add_argument('--output',type=Path,required=True)
    c=sub.add_parser('math-show');c.add_argument('task');c.add_argument('--version',type=int);c.add_argument('--output',type=Path)
    c=sub.add_parser('math-publish');c.add_argument('task');c.add_argument('--version',type=int,required=True);c.add_argument('--package',type=Path,required=True);c.add_argument('--actor',required=True);c.add_argument('--request-id',required=True);c.add_argument('--reason',required=True)
    c=sub.add_parser('create');c.add_argument('task');c.add_argument('contract',type=Path);c.add_argument('--draft-dir',type=Path);c.add_argument('--math-package',type=Path);c.add_argument('--executor',default='historical-fixture',choices=['historical-fixture','manifest-fixture','reviewed-run','mcp-code-executor','pending-code']);c.add_argument('--executor-config',type=Path)
    for cmd in ['show','resume','versions']:
        c=sub.add_parser(cmd);c.add_argument('task')
    c=sub.add_parser('dossier');c.add_argument('task');c.add_argument('--version',type=int);c.add_argument('--output',type=Path)
    c=sub.add_parser('record');c.add_argument('task');c.add_argument('--version',type=int,required=True);c.add_argument('--kind',choices=['proposal','feedback','next_step','change_note','code','experiment'],required=True);c.add_argument('--text-file',type=Path,required=True);c.add_argument('--actor',required=True);c.add_argument('--request-id',required=True);c.add_argument('--artifacts',type=Path);c.add_argument('--metadata',type=Path)
    c=sub.add_parser('retrieve');c.add_argument('task');c.add_argument('--version',type=int,required=True);c.add_argument('--tool',choices=['paper_search','web_search','web_read','reference_get','algorithm_search'],required=True);c.add_argument('--arguments',type=Path,required=True);c.add_argument('--actor',required=True);c.add_argument('--request-id',required=True)
    c=sub.add_parser('discuss-references');c.add_argument('task');c.add_argument('--version',type=int,required=True);c.add_argument('--kind',choices=['proposal','feedback'],required=True);c.add_argument('--text-file',type=Path,required=True);c.add_argument('--references',type=Path,required=True);c.add_argument('--actor',required=True);c.add_argument('--request-id',required=True)
    c=sub.add_parser('tool-evidence');c.add_argument('task');c.add_argument('--version',type=int)
    c=sub.add_parser('attach-solver');c.add_argument('task');c.add_argument('--version',type=int,required=True);c.add_argument('--run-dir',type=Path,required=True)
    c=sub.add_parser('modeling-run');c.add_argument('task');c.add_argument('--version',type=int,required=True);c.add_argument('--guidance-file',type=Path,required=True);c.add_argument('--actor',required=True);c.add_argument('--request-id',required=True);c.add_argument('--no-auto-correct',action='store_true')
    c=sub.add_parser('modeling-status');c.add_argument('task')
    c=sub.add_parser('modeling-recheck');c.add_argument('task');c.add_argument('--version',type=int,required=True);c.add_argument('--run-id',required=True);c.add_argument('--rationale-file',type=Path,required=True);c.add_argument('--actor',required=True);c.add_argument('--request-id',required=True)
    c=sub.add_parser('act');c.add_argument('task');c.add_argument('--kind',choices=['model','result','revise_model','revise_mathematics','revise_interpretation','restore_version'],required=True);c.add_argument('--version',required=True,type=int);c.add_argument('--source-version',type=int);c.add_argument('--actor',required=True);c.add_argument('--request-id',required=True);c.add_argument('--decision',choices=['approve','reject']);c.add_argument('--result-revision',type=int);c.add_argument('--reason',default='');c.add_argument('--contract',type=Path);c.add_argument('--claims',type=Path);c.add_argument('--math-package',type=Path);c.add_argument('--math-semantic-sha256');c.add_argument('--structured-only',action='store_true');c.add_argument('--defer-execution',action='store_true');c.add_argument('--executor',choices=['historical-fixture','manifest-fixture','reviewed-run','mcp-code-executor','pending-code']);c.add_argument('--executor-config',type=Path)
    a=p.parse_args()
    if a.cmd=='license-info':
        from .licensing import information,license_text
        print(license_text(a.text) if a.text else json.dumps(information(),ensure_ascii=False,indent=2))
        return
    try:
        import os
        if a.workspace is not None: os.environ['MODELCREW_WORKSPACE']=str(a.workspace.absolute())
        if a.config is not None: os.environ['MODELCREW_CONFIG']=str(a.config.absolute())
        if a.cmd=='environment':
            from . import service_environment as services
            if a.action=='prepare':answer=services.prepare()
            elif a.action=='status':answer=services.status()
            elif a.action in {'up','migrate','restart','stop'}:answer=services.operate(a.action,offline=a.offline)
            elif a.action=='executor':answer=services.executor(offline=a.offline)
            elif a.action=='tools':
                from .environment_tools import prepare
                answer=prepare(offline=a.offline,archives=a.archives)
            elif a.action in {'embedding','retrieval'}:
                from . import environment_retrieval
                if a.action=='embedding':answer=environment_retrieval.embedding(source=a.model,offline=a.offline)
                else:
                    if a.output is None:raise ValueError('Retrieval initialization requires a new --output')
                    answer=environment_retrieval.initialize(a.output)
            elif a.action=='setup':
                from .environment_tools import prepare
                answer={'services':services.prepare()}
                answer['health']=services.operate('up',offline=a.offline);answer['migrations']=services.operate('migrate')
                answer['executor']=services.executor(offline=a.offline);answer['tools']=prepare(offline=a.offline,archives=a.archives)
                answer['status']='prepared'
            else:
                from . import environment_probe
                if a.action=='recover':
                    if a.report is None:raise ValueError('Recovery requires --report')
                    answer=environment_probe.recover(a.report)
                else:
                    if a.output is None:raise ValueError('Probe requires a new --output directory')
                    answer=environment_probe.smoke(a.output) if a.action=='smoke' else environment_probe.documents(a.output,offline=a.offline)
            print(json.dumps(answer,ensure_ascii=False,indent=2,default=str,allow_nan=False))
            if answer.get('status') in {'incomplete','blocked','failed'}:raise SystemExit(1)
            return
        if a.cmd=='route':
            from .resource_routing import route
            answer=route(a.output,read(a.request),a.input_root,execute=not a.plan_only)
            print(json.dumps(answer,ensure_ascii=False,indent=2,allow_nan=False))
            if answer['status'] not in {'planned','completed'}:raise SystemExit(1)
            return
        if a.cmd in {'init','config-show','doctor'}:
            from .user_workspace import initialize,configuration_summary,doctor
            answer=initialize() if a.cmd=='init' else configuration_summary() if a.cmd=='config-show' else doctor(profile=a.profile,services=a.services)
            print(json.dumps(answer,ensure_ascii=False,indent=2,allow_nan=False))
            if a.cmd=='doctor' and answer['status']!='passed':raise SystemExit(1)
            return
        from .contracts import validate,bench_review
        if a.cmd=='resources-check':
            from .package_resources import verify_resources
            answer=verify_resources()
        elif a.cmd=='validate':
            from .inputs import pending_questions
            value=read(a.contract);validate(value);answer={'structure':'passed','mathematical_review':bench_review(value),'pending_questions':pending_questions(value)}
        elif a.cmd=='inspect-input':
            from .inputs import inspect_file
            answer=inspect_file(a.path,a.role,a.kind)
            if a.output:write_new(a.output,answer)
        elif a.cmd=='draft-inputs':
            from .inputs import draft_inputs,pending_questions
            contract=draft_inputs(read(a.contract));write_new(a.output,contract);answer={'output':str(a.output.resolve()),'approval':'not_granted','pending_questions':pending_questions(contract)}
        elif a.cmd=='resolve-input':
            from .inputs import resolve_question
            contract=resolve_question(read(a.contract),a.input_id,a.question_id,a.resolution);write_new(a.output,contract);answer={'output':str(a.output.resolve()),'approval':'not_granted'}
        elif a.cmd=='generate-draft':
            from .drafts import generate_draft
            answer=generate_draft(a.statement,a.attachment,a.output,a.scope)
        else:
            from .workflow import Workflow
            with Workflow() as w:
                if a.cmd=='init-db':w.setup();answer={'database':'initialized'}
                elif a.cmd=='create':
                    contract=read(a.contract)
                    # Validate the whole bundle before creating business records.
                    if a.draft_dir:
                        from .contracts import digest
                        meta=read(a.draft_dir/'metadata.json')
                        if meta.get('status')!='draft_awaiting_review' or meta.get('contract_sha256')!=digest(contract):raise ValueError('Draft bundle does not match contract')
                        proposal=(a.draft_dir/'proposal.md').read_text(encoding='utf-8');next_steps=read(a.draft_dir/'next-steps.json')
                    entries=[{'kind':kind,'text':text,'actor':'configured-model','request_id':'draft-import-'+kind,'metadata':{k:meta.get(k) for k in ['model','provider','usage']}} for kind,text in [('proposal',proposal),('next_step','\n'.join(next_steps))]] if a.draft_dir else []
                    answer=w.create(a.task,contract,entries=entries,executor_key=a.executor,executor_config=read(a.executor_config) if a.executor_config else None,math_package=read(a.math_package) if a.math_package else None)
                elif a.cmd=='math-show':
                    answer=w.mathematical_proposal(a.task,a.version)
                    if a.output:write_new(a.output,answer)
                elif a.cmd=='math-publish':answer=w.publish_mathematics(a.task,version=a.version,package=read(a.package),actor=a.actor,request_id=a.request_id,reason=a.reason)
                elif a.cmd=='modeling-run':answer=w.run_modeling(a.task,version=a.version,guidance=a.guidance_file.read_text(encoding='utf-8-sig'),actor=a.actor,request_id=a.request_id,auto_correct=not a.no_auto_correct)
                elif a.cmd=='modeling-status':answer=w.modeling_status(a.task)
                elif a.cmd=='modeling-recheck':answer=w.recheck_modeling(a.task,version=a.version,run_id=a.run_id,rationale=a.rationale_file.read_text(encoding='utf-8-sig'),actor=a.actor,request_id=a.request_id)
                elif a.cmd=='show':answer=w.inspect(a.task)
                elif a.cmd=='resume':answer=w.resume(a.task)
                elif a.cmd=='versions':answer=w.versions(a.task)
                elif a.cmd=='dossier':
                    answer=w.version_dossier(a.task,a.version)
                    if a.output:write_new(a.output,answer)
                elif a.cmd=='record':answer=w.record_entry(a.task,version=a.version,kind=a.kind,text=a.text_file.read_text(encoding='utf-8-sig'),actor=a.actor,request_id=a.request_id,artifacts=read(a.artifacts) if a.artifacts else None,metadata=read(a.metadata) if a.metadata else None)
                elif a.cmd=='retrieve':answer=w.retrieve_references(a.task,version=a.version,tool=a.tool,arguments=read(a.arguments),actor=a.actor,request_id=a.request_id)
                elif a.cmd=='discuss-references':answer=w.discuss_references(a.task,version=a.version,kind=a.kind,text=a.text_file.read_text(encoding='utf-8-sig'),references=read(a.references),actor=a.actor,request_id=a.request_id)
                elif a.cmd=='tool-evidence':answer=w.tool_evidence(a.task,a.version)
                elif a.cmd=='attach-solver':answer=w.attach_solver_result(a.task,version=a.version,run_dir=a.run_dir)
                else:answer=w.action(a.task,actor=a.actor,request_id=a.request_id,version=a.version,kind=a.kind,decision=a.decision,result_revision=a.result_revision,reason=a.reason,contract=read(a.contract) if a.contract else None,source_version=a.source_version,math_package=read(a.math_package) if a.math_package else None,math_semantic_sha256=a.math_semantic_sha256,claims=read(a.claims) if a.claims else None,structured_only=a.structured_only,defer_execution=a.defer_execution,executor_key=a.executor,executor_config=read(a.executor_config) if a.executor_config else None)
        print(json.dumps(answer,ensure_ascii=False,indent=2,default=str,allow_nan=False))
    except (ValueError,RuntimeError,OSError,ImportError) as e:
        message=('Missing optional Python dependency; install the required nexusmore[workflow,retrieval,paper] groups: '+str(e)) if isinstance(e,ImportError) else str(e)
        print(json.dumps({'error':message},ensure_ascii=False),file=sys.stderr);raise SystemExit(2)
if __name__=='__main__':main()
