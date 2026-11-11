"""One explicit E-stage operation; no implicit approvals or repeated exports."""
import argparse
import json
from modelcrew.workflow import Workflow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['start','status','compose','build-status','decision','export','recover','render'])
    parser.add_argument('project')
    parser.add_argument('--run-id')
    parser.add_argument('--build-id')
    parser.add_argument('--request')
    args = parser.parse_args()
    if args.operation in ['start','compose','decision','export','render'] and not args.request:
        parser.error(args.operation+' requires --request')
    if args.operation in ['status','compose'] and not args.run_id:
        parser.error(args.operation+' requires --run-id')
    if args.operation in ['build-status','decision','export','recover','render'] and not args.build_id:
        parser.error(args.operation+' requires --build-id')
    request={}
    if args.request:
        with open(args.request,encoding='utf-8-sig') as f:request=json.load(f)
    with Workflow() as workflow:
        if args.operation=='start':answer=workflow.start_assembly(args.project,**request)
        elif args.operation=='status':answer=workflow.assembly_status(args.project,args.run_id)
        elif args.operation=='compose':answer=workflow.compose_assembly(args.project,args.run_id,**request)
        elif args.operation=='build-status':answer=workflow.assembly_build_status(args.project,args.build_id)
        elif args.operation=='decision':answer=workflow.assembly_build_decision(args.project,args.build_id,**request)
        elif args.operation=='recover':answer=workflow.recover_assembly(args.project,args.build_id)
        elif args.operation=='render':answer=workflow.render_assembly(args.project,args.build_id,**request)
        else:answer=workflow.export_assembly(args.project,args.build_id,**request)
    print(json.dumps(answer,ensure_ascii=False))


if __name__=='__main__':main()
