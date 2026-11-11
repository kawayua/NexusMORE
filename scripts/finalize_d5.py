"""Register a pending D5 manuscript without granting user consent or exporting."""
from pathlib import Path
import json,hashlib,shutil
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from scripts.run_d4_full import workflow

folder=ROOT/'stage-d/runs/writing/d5-q1-20261108-v4';base=ROOT/'stage-d/d5'
with workflow() as w:
    state=wh.status(folder,w);meta=wh.read(folder/'run.json');admission=wh.read(folder/'W1-admission.json')
    assert state['state']['phase']=='WAITING_MANUSCRIPT_APPROVAL' and not state['state']['reviews']['can_export']
    artifacts=[{'path':wh.rel(folder/name),'sha256':wh.sha(folder/name),'role':role} for name,role in [('单题论文-中文审阅稿.md','pending_D5_manuscript'),('publication.json','D5_publication'),('W1-admission.json','independent_W1_admission'),('figure-catalog.json','approved_nine_figures'),('figure-selection-review.json','carried_forward_D4_figure_consent')]]
    entry=w.record_entry(meta['binding']['task_id'],version=meta['binding']['contract_version'],kind='experiment',actor='codex-writing-hand',request_id='D5-W1-pending-manuscript-'+wh.sha(folder/'publication.json')[:24],text='D5：独立W1首次FAIL后定向返工，复验四项PASS；已生成问题一中文建模Markdown，九图继承D4确认，新正文等待用户审阅，未正式导出。',artifacts=artifacts,metadata={'binding':meta['binding'],'W1_receipt_sha256':admission['receipt_sha256'],'manuscript_approved':False,'figure_selection':'approved_from_explicit_D4_user_consent','new_model_API_calls':0,'new_solver_runs':0})
    wh.new(base/'registration.json',{'entry':entry,'binding':meta['binding'],'writing_run':wh.rel(folder),'manuscript_approved':False,'figure_selection':'approved','solver_task_phase':w.task(meta['binding']['task_id'])['phase'],'solver_phase_does_not_mean_D5_complete':True})
current={**state,'manuscript_path':wh.rel(folder/'单题论文-中文审阅稿.md'),'manuscript_sha256':wh.sha(folder/'单题论文-中文审阅稿.md'),'W1_receipt_sha256':admission['receipt_sha256'],'initial_W1_failed_run':'stage-d/runs/writing/d5-q1-20261108-v2','W1_passed_plan_run':'stage-d/runs/writing/d5-q1-20261108-v3','selected_figures':9,'formal_exports':0,'new_solver_runs':0,'new_model_API_calls':0,'generic_autonomous_Writer_API':'not_implemented','tests':{'full_regression_passed':456,'final_lifecycle_passed':20,'counts_overlap':True},'report':'stage-d/d5/acceptance-report.md'}
wh.new(base/'current-writing.json',current)
readme='''# D5 中文论文审阅

当前开发题的论文手写作路径与独立W1已完成，现等待用户审阅**新论文正文**。D4批准的是全量结果审阅页；新稿包含完整建模叙述、公式和题注，须单独确认。九幅图沿用已明确通过的文件，选图确认继续有效。

[打开中文论文审阅稿](../../stage-d/runs/writing/d5-q1-20261108-v4/单题论文-中文审阅稿.md) · [执行与审查报告](acceptance-report.md) · [当前状态](current-writing.json) · [九图内容清单](../../stage-d/runs/writing/d5-q1-20261108-v4/figure-catalog.json)

论文仅回答问题一，含9幅图、9个编号公式、5张表。题目指定六时刻、七把手的126个位置与速率显示值已与原始未舍入数组核对。现阶段交付Markdown，无正式论文PDF/Word/LaTeX，无W2排版验收。

W1在长篇正文之前进行：首次FAIL的差分抽样范围和求解参数映射问题，均已定向退论文手并在新大纲中修复；复验四项PASS。正文公式排版修正另存v4，保留v3原稿，不改变已通过的论断与证据。W1不等于本稿用户批准，也不等于W2。
'''
(base/'README.md').write_text(readme,encoding='utf-8')
report=f'''# D5 当前开发题论文手与独立W1

当前开发题已完成“已批准模型与全量结果→代码手向论文手交接→实际读取writing_context→论断证据大纲→独立W1失败及定向返工→W1复验通过→中文建模Markdown→正文与选图分开等待/恢复”的真实路径。新正文待用户审阅，全部9幅图沿用D4明确批准的字节；这不是整个阶段D或通用自主Writer的验收。

[中文论文审阅稿](../runs/writing/d5-q1-20261108-v4/单题论文-中文审阅稿.md) · [机器状态](current-writing.json) · [交付检查](delivery-check.json)

## 实际输入与写作

任务`{meta['binding']['task_id']}`，契约版本1、结果修订1，执行ID`{meta['binding']['execution_id']}`。准备阶段重新验证用户模型/结果双确认、D4全量包及P2，核对九图确认回执及全部文件哈希。D1内容寻址库保存真实代码手→论文手Handoff、调用身份、上下文和快照；论文手不获得改模型或运行代码的工具能力。该能力声明是编排约束，不夸称操作系统强隔离。

`modelcrew.writing_hand`提供prepare/dispatch/admit/publish/status、独立正文决策及新目录修订入口；`scripts.run_d5_writing`提供CLI，当前正文由Codex论文手撰写，`scripts.build_d5_draft`在展开正文前强制验证当前W1。每次运行重新读取writing_context和当前批准绑定，不靠聊天历史推断。配置原文保存在writer-context.json，来源及哈希列入输入冻结；每次状态恢复校验源包、题面附件、政策、候选图和W1票据。

当前稿只采用本次确认结果，未重跑求解器，未调用新的供应商模型API。论文按中文数学建模体裁组织，而不是数学证明文章；math-reasoning仅用于公式、单位和记号核对。文章含约5272个汉字、9个编号公式、5张表及9幅图；篇幅不是官方最低要求。引文仅为实际读取的原题与SciPy 1.15.3版本化官方API文档，未把其转引专著列作已读文献。原题下载URL和竞赛投稿规则未在线核验，当前为研究审阅稿，不宣称符合当届正式提交规范。

## 独立W1、失败与复验

长篇正文展开前，`/root/d5_independent_w1`在独立、只读、未参与作者修改的上下文审查claims/evidence/citations/outline四项。首次审查真实FAIL，指出C7未将差分误差限定为8个抽样时刻，C4没有把主求解容差和最大迭代数映射到精确源码证据。程序接纳FAIL，进入W1_REWORK_REQUIRED，未生成长篇正文；两项均定向退论文手。

原FAIL见[v2原回复](../runs/writing/d5-q1-20261108-v2/W1-response.json)，接纳回执`f6dfff3440e74ba8473b2f9b264c8ebf4d1c2536459187791464a7a454afecee`。作者在新v3大纲明确内部1/60/120/180/240/299秒、端点0/300秒、各224把手以及中心/二阶单侧公式，补充冻结源码摘录、行号与SHA。两份support_files本身也进入输入冻结，不只信任作者填写的参数。

同一独立审查者未参与修正，复验四项全部PASS，无待修问题。PASS快照`810f5f59c56abed9af475333dac4e62b72c29b512ee54e9b19142a305035beb9`；接纳回执`{admission['receipt_sha256']}`。原始JSON与接纳记录分别保存，程序验证JSON指针、身份、作者沿革、完整检查项和逐项状态，不修改审查者语义判断。见[v3复验原回复](../runs/writing/d5-q1-20261108-v3/W1-response.json)。

W1通过后才生成v3全文。作者检查发现式(1)矩阵换行转义问题，另建v4修订为等价行向量转置，保留v3原字节；论断、模型、结果、引用、图意和W1大纲未变，沿用同一已接纳W1证据大纲。修订过程会清除正文批准，仅继承字节未变的图集确认。

## 本稿检查与审批边界

机械检查通过：中文结构、正文中文比例、9图三类各3幅、图号连续、题注及正文引用、PNG约300dpi与PDF/SVG字节、无占位符或内部流程材料。可信检查器将表2与表3全部126个数值直接与未舍入NPZ比较，位置最大显示差4.772688e-7 m、速率最大显示差4.901479e-7 m/s。公式编号1—9及基础LaTeX定界检查通过。上述是作者侧检查，不冒充独立W2或最终排版审查。

完整数据库回归456项通过、0失败、0跳过，见[全量JUnit](../d5-regression-tests.xml)。此后新增正文修订函数的最终生命周期专项20项通过，见[专项JUnit](../d5-lifecycle-final.xml)；有重叠，不相加宣称单轮数量。最初从仓库根递归收集测试误扫到历史受限临时目录，27项收集错误原样保留于d5-regression.xml；改用真实tests目录后完成上述456项。未为读取无关历史临时目录放宽权限。

状态经新进程与真实数据库恢复验证为WAITING_MANUSCRIPT_APPROVAL，正文pending、选图approved、can_export=false。D4结果批准与原图确认不撤销，不代用户批准当前Markdown或新增题注。业务任务COMPLETED仅指建模求解双确认，不表示论文或整个阶段D完成。登记见[registration.json](registration.json)。

通用供应商Writer生成API、HTTP写作接口、多题汇编、跨题D6及正式导出E/W2尚未实现或未验收；当前仅声明本开发题真实路径及可复用的本地生命周期入口。不生成正式PDF、Word或LaTeX，不启动W2，不改历史正式论文。
'''
(base/'acceptance-report.md').write_text(report,encoding='utf-8')
p=wh.read(ROOT/'stage-d/progress.json');p['current_milestone']='D5_case_W1_passed_waiting_manuscript_review'
p['milestones']['D5']={'status':'single_case_writing_review_ready','user_acceptance':'not_recorded','report':'stage-d/d5/acceptance-report.md','task_id':meta['binding']['task_id'],'run_dir':wh.rel(folder),'independent_W1':'PASS_after_writing_rework','W1_receipt_sha256':admission['receipt_sha256'],'manuscript_review':'pending_user','figure_selection':'approved_all_nine_from_D4','generic_autonomous_Writer_API':'not_implemented','formal_export':'not_started','W2':'not_started'}
p['case_specific_writing_runner_implemented']=True;p['next']='User reviews current D5 Chinese manuscript; existing nine-figure consent remains valid; D6/E/W2 require subsequent work'
# Preserve historical evidence records; this mutable pointer describes only the latest state.
temp=ROOT/'stage-d/progress.next.json';wh.new(temp,p);import os;os.replace(temp,ROOT/'stage-d/progress.json')
r=ROOT/'stage-d/README.md';s=r.read_text(encoding='utf-8');s=s.replace('通用代码手及论文手仍待后续集成','当前开发题论文手与独立W1也已完成并等待新正文审阅；通用代码手及自主Writer/API仍待后续集成')
s=s.replace('| D5 论文手、W1 与写作审批状态图 | 待实施 |','| D5 论文手、W1 与写作审批状态图 | 当前开发题W1真实FAIL→论文手返工→PASS；中文稿待用户审阅，九图确认保留，见 [D5报告](d5/acceptance-report.md) |');r.write_text(s,encoding='utf-8')
for name in ['modelcrew/writing_hand.py','scripts/run_d5_writing.py','scripts/build_d5_draft.py','scripts/check_d5_delivery.py','tests/test_writing_hand.py']:
 target=base/'sources'/Path(name).name
 if not target.exists():shutil.copyfile(ROOT/name,target)
paths=[base/'README.md',base/'acceptance-report.md',base/'current-writing.json',base/'registration.json',base/'delivery-check.json',base/'source-read-log.json',ROOT/'stage-d/progress.json',r,ROOT/'stage-d/d5-regression-tests.xml',ROOT/'stage-d/d5-lifecycle-final.xml']
paths += list((base/'sources').glob('*'))+[folder/'单题论文-中文审阅稿.md',folder/'run.json',folder/'publication.json',folder/'W1-admission.json',folder/'W1-response.json',folder/'revision.json',folder/'figure-selection-review.json']
wh.new(base/'evidence.json',{'created_at':datetime.now(timezone.utc).isoformat(),'binding':meta['binding'],'scope':'D5 engineering/delivery; authoritative W1 evidence lives in content-addressed snapshots','files':wh.frozen_manifest(paths)})
print(json.dumps({'manuscript':current['manuscript_path'],'W1':'PASS_after_rework','user_review':'pending','figures':'nine_approved','formal_exports':0,'entry_id':entry['entry_id']},ensure_ascii=False))
