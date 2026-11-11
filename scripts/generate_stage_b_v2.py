"""Generate a feedback-informed v2 contract patch; never auto-approve it."""
from pathlib import Path
import sys,json,time,hashlib,copy
from datetime import datetime,timezone
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from modelcrew.workflow import Workflow
from modelcrew.contracts import validate,bench_review,digest
from generate_2024_a_q1 import config
ROOT=Path(__file__).resolve().parents[1]
FEEDBACK='''用户要求：对照百炼原方案和实际代码与人工参考实现的差异，把分析作为修改意见生成契约v2。
核心数学模型不变，所有物理参数、单位、输入哈希、原有约束、原有输出和容差不得修改或删除。
事实：原方案写RK4，但实际百炼代码已使用弧长方程+Brent求根，因此不能声称当前代码存在RK4累计误差。v2应统一叙述为弧长求根；ODE仅作需验证收敛的可选等价方法。
修改要求：
G1 使用delta角差的稳定弦长平方表达式(b*delta)^2+4*r*(r+b*delta)*sin(delta/2)^2-L^2；在0<delta<pi证明单调并检查括区异号。无括区或收敛不满足时明确报错，不静默跳圈。
G2 明确速度来自距离约束求导，不将所有把手速率设为1。对速度递推分母接近0设置检测阈值、记录节点和时间并终止或待人工判断；不能仅用公式算出的速率自证。
G3 保存theta_rad形状(301,224)为诊断数组；检查同刻theta沿链严格增加、同节点随时间递减；最初点与顺时针方向正确。
G4 以独立数值积分核验龙头弧长；用时间差分核验速度，h=1e-2,1e-3,1e-4秒，在内部时刻取中心差分、端点用二阶单侧；报告误差随h变化，不强制浮点误差严格单调下降。以h=1e-3秒的向量误差<=1e-5 m/s为准。
G5 加严求根容差抽样复算；回读Excel核对标签、维度、时间列、数值及六位显示；容差和单位必须明确。
G6 确保每个新增检查有稳定ID、证据要求及初态unknown；未执行不得填passed。明确新版本尚未重写或执行求解代码；当前B节点仍是历史工件联调，不把旧结果称作已满足v2新增检查。
这些修改受参考实现启发，是反馈修订，不是独立生成；没有提供获奖论文或数值答案。'''
def apply_patch(original,ops):
    c=copy.deepcopy(original)
    allowed={'/method/steps','/method/root_selection','/method/allowed_equivalent_changes','/method/requires_new_confirmation'}
    for op in ops:
        if set(op)!={'op','path','value'}:raise ValueError('Unexpected patch fields')
        path=op['path']
        if path in allowed and op['op']=='replace':c['method'][path.rsplit('/',1)[1]]=op['value']
        elif path in ['/checks/-','/outputs/0/fields/-','/risks/-','/alternatives/-'] and op['op']=='add':
            if path=='/outputs/0/fields/-':c['outputs'][0]['fields'].append(op['value'])
            else:c[path.split('/')[1]].append(op['value'])
        else:raise ValueError('Patch outside allowed method/check/output additions')
    return c

def main():
    cfg=config();key=cfg['MODELCREW_LLM_API_KEY']
    folder=ROOT/'stage-b/runs'/datetime.now(timezone.utc).strftime('contract-v2-%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True)
    with Workflow() as w:
        state=w.inspect('dragon-q1')
        if state['task']['current_version']!=1 or state['task']['phase']!='COMPLETED':raise ValueError('Expected completed v1 before feedback revision')
        original=state['contract']['content'];original_hash=state['contract']['sha256']
    (folder/'guidance.txt').write_text(FEEDBACK,encoding='utf-8')
    (folder/'v1-contract.json').write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf-8')
    prompt={'model':cfg['MODELCREW_LLM_MODEL'],'max_tokens':24000,'messages':[{'role':'system','content':'你是ModelCrew建模契约修订者。按用户反馈修改，不能伪造运行或用户确认。只返回严格JSON对象，不要markdown。必须保留既有事实与检查。'}, {'role':'user','content':'当前v1契约：\n'+json.dumps(original,ensure_ascii=False)+'\n反馈：\n'+FEEDBACK+'\n请输出{"summary":"简短中文修改说明","patch":[...]}，patch采用JSON Patch条目，每项恰含op/path/value。允许replace的路径仅/method/steps、/method/root_selection、/method/allowed_equivalent_changes、/method/requires_new_confirmation；允许add路径仅/checks/-、/outputs/0/fields/-、/risks/-、/alternatives/-。现有检查不删改，通过新增检查落实反馈。新增check条目字段必须完全为id,description,method,tolerance,unit,evidence_required,initial_status(恒unknown)。新增输出字段完全为name,shape,unit。id只能英文字母开头、其余字母数字下划线点横线。method.steps等为非空字符串数组，root_selection为字符串。tolerance为数值或null。不要输出代码或数值结果。'}]}
    (folder/'request.json').write_text(json.dumps(prompt,ensure_ascii=False,indent=2),encoding='utf-8')
    meta={'mode':'feedback_informed_contract_revision','status':'started','model':cfg['MODELCREW_LLM_MODEL'],'provider':cfg.get('MODELCREW_LLM_PROVIDER'),'parent_contract_sha256':original_hash,'reference_method_feedback_sent':True,'reference_numeric_answers_sent':False,'award_paper_sent':False,'user_guidance_origin':'User requested method comparison and instructed revision to v2. Assistant operationalized numerical checks.','approval':'not_granted'}
    start=time.perf_counter()
    try:
        r=httpx.post(cfg['MODELCREW_LLM_BASE_URL'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=prompt,timeout=httpx.Timeout(600,connect=30))
        meta.update(http_status=r.status_code,elapsed_seconds=time.perf_counter()-start)
        if r.status_code>=400:
            (folder/'error.txt').write_text(r.text.replace(key,'[REDACTED]'),encoding='utf-8');raise RuntimeError(f'API {r.status_code}')
        data=r.json();(folder/'response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');meta['usage']=data.get('usage')
        choice=data['choices'][0];meta['finish_reason']=choice.get('finish_reason')
        if choice.get('finish_reason')=='length':raise ValueError('Output truncated')
        text=choice['message'].get('content') or '';(folder/'response.txt').write_text(text,encoding='utf-8')
        patch=json.loads(text)
        if set(patch)!={'summary','patch'} or not isinstance(patch['patch'],list):raise ValueError('Invalid response shape')
        revised=apply_patch(original,patch['patch']);validate(revised)
        if bench_review(revised)['status']=='failed':raise ValueError('Mathematical relation failed')
        # Hard invariants: model numerical inputs and old constraints/checks unchanged.
        for field in ['problem','inputs','conventions','parameters','variables','assumptions','constraints','sources']:
            assert revised[field]==original[field],field
        assert revised['checks'][:len(original['checks'])]==original['checks']
        assert any(f['name']=='theta_rad' and f['shape']==[301,224] for f in revised['outputs'][0]['fields'])
        assert len(revised['checks'])>len(original['checks'])
        (folder/'patch.json').write_text(json.dumps(patch,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'proposed-v2.json').write_text(json.dumps(revised,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        meta.update(status='generated_validated_pending_manual_review',proposed_sha256=digest(revised))
        print('V2_PROPOSAL',folder,flush=True)
        print(json.dumps({'summary':patch['summary'],'new_check_ids':[x['id'] for x in revised['checks'][len(original['checks']):]],'usage':meta['usage']},ensure_ascii=False,indent=2),flush=True)
    except Exception as e:
        meta['status']='failed';meta['error']=str(e).replace(key,'[REDACTED]');raise
    finally:(folder/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
