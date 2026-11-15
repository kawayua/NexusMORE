"""D5 current-case CLI; supplied Codex-authored content, no autonomous API claim."""
import argparse,json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from scripts.run_d4_full import workflow

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('step',choices=['prepare','dispatch','admit','publish','status']);p.add_argument('--run',type=Path,required=True);p.add_argument('--source-run',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--citations',type=Path);p.add_argument('--reviewer-id');p.add_argument('--markdown',type=Path)
    a=p.parse_args()
    with workflow() as w:
        if a.step=='prepare':result=wh.prepare(w,a.run,a.source_run,wh.read(a.plan),wh.read(a.citations),context_id='codex-D5-writing-'+a.run.name)
        elif a.step=='dispatch':result={'ticket_sha256':wh.dispatch(a.run,a.reviewer_id,w)}
        elif a.step=='admit':result=wh.admit(a.run,w)
        elif a.step=='publish':result=wh.publish(a.run,a.markdown,w)
        else:result=wh.status(a.run,w)
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()
