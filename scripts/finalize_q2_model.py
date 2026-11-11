"""Publish the independently reviewed Q2 proposal, leaving user approval pending."""
from pathlib import Path
import json,os,shutil
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.writing_hand import read,new,rel,frozen_manifest
from modelcrew.collaboration import sha_file
from modelcrew.modeling_hand import assert_m1
from modelcrew.mathematics import snapshot as math_snapshot
from scripts.run_d4_full import workflow

base=ROOT/'stage-d/q2-modeling';folder=ROOT/'stage-d/runs/modeling/q2-collision-20261109-v2'
meta=read(folder/'run.json');admission=read(folder/'M1-admission.json')
with workflow() as w:
    t=w.task(meta['task_id']);assert t['current_version']==2 and not t['model_approved'] and not t['result_approved'] and t['execution_id'] is None
    gate=assert_m1(w,t);math=math_snapshot(w,t['id'],2)
    assert gate['receipt_sha256']==admission['receipt_sha256']
    assert w.db.execute('SELECT count(*) AS n FROM mc_executions WHERE task_id=%s',(t['id'],)).fetchone()['n']==0
    assert w.db.execute('SELECT count(*) AS n FROM mc_backend_attempts WHERE task_id=%s',(t['id'],)).fetchone()['n']==0
    runs=w.db.execute('SELECT base_version,version,status FROM mc_modeling_runs WHERE task_id=%s ORDER BY sequence',(t['id'],)).fetchall()
    assert [r['status'] for r in runs]==['needs_human','ready']
    # Correct legacy creation metadata with an additive audit event; original events stay immutable.
    if not w.db.execute("SELECT 1 FROM mc_events WHERE task_id=%s AND kind='Q2_pending_code_audit'",(t['id'],)).fetchone():
        w._event(t['id'],'Q2_pending_code_audit','system',{'backend':'pending-code','executions':0,'backend_attempts':0,'legacy_initial_created_mode_label':'fixture','explanation':'Initial generic created-event mode label preceded pending-code classification fix; no fixture was dispatched or imported. Backend was pending-code from creation.'})
    current={'task_id':t['id'],'contract_version':2,'contract_sha256':meta['contract_sha256'],'math_semantic_sha256':math['semantic_sha256'],'phase':t['phase'],'model_approved':False,'result_approved':False,'execution':None,'independent_M1':'PASS_after_model_rework','M1_receipt_sha256':admission['receipt_sha256'],'M1_snapshot_sha256':admission['snapshot_sha256'],'run_dir':rel(folder),'proposal':rel(folder/'attempt-0/方案审阅.md'),'new_Q2_solver_runs':0,'new_supplier_model_API_calls':0,'continuous_collision_algorithm':'designed_not_implemented','model_scope':'conservative_nonadjacent_filled_rectangle_first_contact_with_full_adjacent_pair_exemption','new_assumptions_require_user_confirmation':True,'tests':{'targeted_passed':91,'full_regression_passed':477,'counts_overlap':True},'report':'stage-d/q2-modeling/acceptance-report.md'}
    new(base/'current-model.json',current)
report=f'''# 第二题碰撞模型与独立M1

第二题碰撞模型已形成，独立M1在首次FAIL后经建模返工，复验六项全部PASS。当前任务`{t['id']}`的契约版本为2，状态WAITING_MODEL_APPROVAL，模型批准与结果批准均为false；第二题没有任何执行或后端尝试。当前只完成求解前方案设计与审查，不报告终止时刻或碰撞对。

[打开方案审阅稿](../runs/modeling/q2-collision-20261109-v2/attempt-0/方案审阅.md) · [当前模型绑定](current-model.json) · [M1原回复](../runs/modeling/q2-collision-20261109-v2/M1-response.json)

## 模型及明确的新假设

继承第一题已确认的螺线、弧长反解、孔中心距、外侧最近根及速度递推。通过D6重新读取当前确认引用，来源版本与哈希保持绑定；不以第一题0—300秒数据或范围证明替代第二题更晚时刻的状态计算与分支检查。

对223节板凳按题面全长与0.30m板宽建立完整矩形，孔外两端各保留0.275m；共有224个把手，首板孔距2.86m，其余1.65m。完整矩形使用四轴SAT检查，覆盖24531对非相邻板凳，不仅检查龙头，也不只检测角点入内。坐标及间隙单位m，角速度1/s，速度m/s，事件时间s。

新增并需用户确认的三项约定为：相邻板凳整对排除，视为理想分层铰接；孔洞按完整实心外包矩形处理；非相邻外矩形第一次边界接触即停止，孤立相切也停止。这些不是题面已经证实的三维物理事实，结论仅限此二维外包络模型。若需相邻真实干涉或精确孔洞/厚度碰撞，须改变模型及补充输入，不能静默替换。

## 首次事件设计与未实现边界

首接触定义为所有非相邻对分离裕量首次非正。固定步长只能调度候选，不能充当连续首碰证明；不假设全局间隙单调。计划对整个时间区间做外向舍入运动状态包围，证明分支存在唯一、分母不含零，并为全部板对提供严格分离证书后才排除该区间。最早未决区间不得跳过，切触不能强求端点变号；需要接触特征的验证式根包围或相应连续性和见证。

时间包围目标1e-6s、几何核验目标1e-8m是提案验收目标，不是题面参数；最终六位显示还需速度界、求根误差与舍入格证据。终态速度为接触前左极限，不模拟撞击之后运动。任何分支失效、最早未决无法消除、切触无法认证或预算耗尽均UNKNOWN/BLOCKED，不能输出更晚碰撞冒充首碰，也不能把运动学有效域终点当碰撞。

连续区间算法及其数值证书当前**尚未实现或运行**。M1只认可条件性设计和验证计划，不证明后续代码已经能产生证书。方案获用户批准后，仍需代码实现、受控最小运行和独立P1；不满足证书要求时不得把采样结果包装成连续首碰结论。

## 独立M1的真实失败与返工

作者为Codex建模手，供应商模型生成API调用0；独立审查使用未参与产物编写的`/root/q2_independent_m1`上下文，实际查看冻结证据。首次发现契约按板索引写L0，而数学包按后把手索引写L1，属于会影响代码的硬约束冲突；还发现设计文件将新增假设来源误标题面。

原始回复的警告路由explanation→modeling不符合既有D1接纳规则，作者未代改；审查者自行返回同一FAIL、正确model→modeling路由的完整回复，两个原始版本分别保留。合法FAIL接纳回执为`be17a3fe680968d2941b4981a708245917d5051dfcb3401ebe39c120d3abffe6`，版本1进入needs_human。

经Workflow.revise_model创建新业务版本2，统一板孔距ell_k=L_(k+1)，并明确首板ell0=L1=2.86m、第二板ell1=L2=1.65m、末板ell222=L223=1.65m；新增假设来源改为proposal-policy，契约、数学包、设计、审阅稿同步。旧契约和失败证据不覆盖。

同一审查者未参与修改，复验model、assumptions、units、constraints、algorithm_premises、validation_plan六项全部PASS，无待修问题。新冻结快照为`{admission['snapshot_sha256']}`，PASS接纳回执为`{admission['receipt_sha256']}`。程序重新检查完整项、证据JSON指针、作者/审查身份、快照字节、当前数学包与前题引用，assert_m1在真实数据库中通过；没有发出用户方案批准。

## 工程核验

新增pending-code后端在未登记代码前拒绝执行，禁止落回历史fixture。原始创建事件沿用旧通用fixture标签，但实际后端从创建起即为pending-code，第二题执行与后端尝试均为0；补充审计事件说明，保留原事件不改写。之后已修正新建事件分类为pending，并增加相关测试。

专项91项通过；完整真实数据库回归477项通过、0失败、0跳过，耗时144.38秒，见[全量JUnit](regression.xml)。两组有重叠不相加。方案编写的若干早期结构检查失败仅是本地schema/记号修正，未运行求解器；草稿目录保留，不冒称独立M1返工。

当前可审核正文、接纳回执和版本绑定均已保存。下一步是用户明确确认版本2方案及三项新增约定，然后代码手实现碰撞模型并开展P1；本轮不生成第二题论文、候选图或正式导出，不启动P2/W1/W2。
'''
(base/'acceptance-report.md').write_text(report,encoding='utf-8')
(base/'README.md').write_text('# 第二题方案审阅\n\n独立M1返工复验六项PASS，当前版本2等待用户确认，尚未求解。\n\n[方案审阅稿](../runs/modeling/q2-collision-20261109-v2/attempt-0/方案审阅.md) · [当前绑定](current-model.json) · [审查报告](acceptance-report.md)\n',encoding='utf-8')
progress=read(ROOT/'stage-d/progress.json');progress['current_milestone']='Q2_collision_model_M1_passed_waiting_user_approval'
progress.setdefault('questions',{})['Q2']={'task_id':t['id'],'contract_version':2,'phase':'WAITING_MODEL_APPROVAL','independent_M1':'PASS_after_model_rework','model_approved':False,'result_approved':False,'new_solver_runs':0,'proposal':current['proposal'],'report':current['report'],'continuous_collision_algorithm':'designed_not_implemented'}
progress['next']='User confirms Q2 contract v2 and its adjacent-exemption/filled-envelope/contact-stop assumptions; then Coder implementation and independent P1 before full solving'
nextpath=ROOT/'stage-d/progress.next.json';new(nextpath,progress);os.replace(nextpath,ROOT/'stage-d/progress.json')
r=ROOT/'stage-d/README.md';s=r.read_text(encoding='utf-8');s+='\n第二题进展：碰撞模型版本2已通过独立M1返工复验，等待用户确认方案，尚未求解。见[方案审阅与报告](q2-modeling/README.md)。\n';r.write_text(s,encoding='utf-8')
log=base/'sources';log.mkdir(exist_ok=True)
for name in ['modelcrew/executors.py','modelcrew/workflow.py','scripts/prepare_q2_model.py','scripts/review_q2_model.py','scripts/finalize_q2_model.py','tests/test_pending_code.py','tests/test_workflow.py']:shutil.copyfile(ROOT/name,log/Path(name).name)
paths=[*base.glob('*.json'),*base.glob('*.md'),*log.glob('*'),base/'regression.xml',base/'targeted-v2.xml',ROOT/'stage-d/progress.json',r,folder/'run.json',folder/'M1-response.json',folder/'M1-admission.json',folder/'registration.json',*list((folder/'attempt-0').glob('*'))]
new(base/'evidence.json',{'created_at':datetime.now(timezone.utc).isoformat(),'scope':'Q2 model v2 independent M1 PASS; no user approval or numerical solve','files':frozen_manifest([p for p in paths if p.is_file()])})
print(json.dumps({'Q2_version':2,'M1':'PASS','phase':'WAITING_MODEL_APPROVAL','model_approved':False,'solver_runs':0,'regression_passed':477}))
