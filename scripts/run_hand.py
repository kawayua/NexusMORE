"""One durable hand transition at a time; no implicit approvals or unbounded loops."""
import argparse,json
from modelcrew.workflow import Workflow

def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['start','advance','status','decision','recheck','repair']);p.add_argument('task');p.add_argument('--hand',choices=['coding','writing']);p.add_argument('--run-id');p.add_argument('--request',help='UTF-8 JSON request file')
    a=p.parse_args()
    with Workflow() as w:
        if a.operation=='start':value=w.start_hand(a.task,a.hand,**json.load(open(a.request,encoding='utf-8-sig')))
        elif a.operation=='decision':value=w.hand_decision(a.task,a.run_id,**json.load(open(a.request,encoding='utf-8-sig')))
        elif a.operation=='recheck':value=w.recheck_hand(a.task,a.run_id,**json.load(open(a.request,encoding='utf-8-sig')))
        elif a.operation=='repair':value=w.repair_hand(a.task,a.run_id,**json.load(open(a.request,encoding='utf-8-sig')))
        elif a.operation=='advance':value=w.advance_hand(a.task,a.run_id)
        else:value=w.hand_status(a.task,a.run_id)
    print(json.dumps(value,ensure_ascii=False,default=str))
if __name__=='__main__':main()
