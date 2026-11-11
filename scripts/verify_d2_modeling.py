"""Real configured modeling hand + independent M1; no approvals or solving.

Existing baseline is intentionally supplied. Development guidance is constructed
by the verification operator, not attributed to an actual user discussion.
"""
import argparse
import json
from pathlib import Path

from modelcrew.config import ROOT
from modelcrew.workflow import Workflow
from modelcrew.contracts import digest

GUIDANCE = ('工程验证指导（助手构造，不是用户对具体模型的确认）：复用已有板凳龙问题1数学基线，'
            '核对与原题的对应、弧长反解、首根分支和速度约束，说明外部方法的适配及局限。'
            '必要时用最小JSON修改补齐方法或验证说明，已有给定参数/输入/检查不得改变。'
            '不执行求解、不提供新数值，不生成论文，不确认方案。')


def verify(task, request_id, recheck_run=None, rationale_file=None):
    with Workflow() as w:
        w.setup()
        existing=w.db.execute('SELECT * FROM mc_tasks WHERE id=%s',(task,)).fetchone()
        if existing is None:
            contract=json.loads((ROOT/'stage-b-plus/examples/contract-v2-snapshot.json').read_text(encoding='utf-8'))
            package=json.loads((ROOT/'stage-b-plus/examples/valid-bench-dragon.json').read_text(encoding='utf-8'))
            w.create(task,contract,project='stage-d2-development',math_package=package)
        elif existing['project_id']!='stage-d2-development':
            raise ValueError('Refusing to use a task outside the D2 development project')
        old=w.db.execute('SELECT base_version FROM mc_modeling_runs WHERE task_id=%s AND request_id=%s',(task,request_id)).fetchone()
        version=old['base_version'] if old else w.task(task)['current_version']
        if recheck_run:
            if rationale_file is None: raise ValueError('Explicit rationale file required')
            answer=w.recheck_modeling(task,version=version,run_id=recheck_run,actor='DEVELOPMENT_OPERATOR_DEMO',request_id=request_id,rationale=rationale_file.read_text(encoding='utf-8-sig'))
        else:
            answer=w.run_modeling(task,version=version,actor='DEVELOPMENT_OPERATOR_DEMO',request_id=request_id,guidance=GUIDANCE)
        state=w.inspect(task)
        assert not state['task']['model_approved'] and state['execution'] is None
        folder=ROOT/answer['folder']
        summary={'task_id':task,'run_id':answer['run_id'],'status':answer['status'],'version':answer['version'],
                 'calls':answer['calls'],'attempts':answer['attempts'],'model_approved':False,'execution':None,
                 'checkpoint_next':state['checkpoint_next'],'user_approvals_created':0,'new_solver_runs':0,
                 'reference_assisted':True,'guidance_origin':'verification operator, not actual user modeling feedback',
                 'real_model_api_calls':len(list(folder.rglob('*-metadata.json'))),'all_three_primary_hands_implemented':False,
                 'result_quality_not_proven_by_M1':True}
        (folder/('verification-summary-'+digest(request_id)[:12]+'.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps({'task':task,'status':answer['status'],'version':answer['version'],
                          'calls':len(answer['calls']),'folder':str(folder)},ensure_ascii=False))
        if answer['status']!='ready':
            raise SystemExit(2)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--task',required=True)
    parser.add_argument('--request-id',required=True)
    parser.add_argument('--recheck-run')
    parser.add_argument('--rationale-file',type=Path)
    args=parser.parse_args(); verify(args.task,args.request_id,args.recheck_run,args.rationale_file)
