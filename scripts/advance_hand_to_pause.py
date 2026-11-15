"""Bounded driver for the existing generic Workflow hand entry; no author content."""
import argparse,json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.workflow import Workflow

def main():
    parser=argparse.ArgumentParser();parser.add_argument('task');parser.add_argument('--run-id',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    folder=(ROOT/args.output).resolve();folder.relative_to(ROOT.resolve());folder.mkdir(parents=True,exist_ok=True)
    terminal={'WAITING_MANUSCRIPT_AND_FIGURES','READY_FOR_E_EXPORT','NEEDS_HUMAN','NEEDS_MODEL_REVISION','NEEDS_CODE_REVISION','NEEDS_RESULT_INTERPRETATION','NEEDS_WRITING_REVISION','PROVIDER_UNKNOWN','ATTACHED'}
    with Workflow() as workflow:
        state=workflow.hand_status(args.task,args.run_id)
        error=None
        for _ in range(16):
            with (folder/'state-events.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(state,ensure_ascii=False)+'\n')
            if state['phase'] in terminal:break
            try:state=workflow.advance_hand(args.task,args.run_id)
            except Exception as exc:
                error=type(exc).__name__;state=workflow.hand_status(args.task,args.run_id);break
        result={'task_id':args.task,'run_id':args.run_id,'state':state,'error_type':error,'driver':'Generic Workflow start/advance/status; no case-specific author draft or verdict','user_approval_created':False}
        (folder/'latest-state.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'run_id':args.run_id,'phase':state['phase'],'error_type':error}))
        if error:raise SystemExit(2)
if __name__=='__main__':main()
