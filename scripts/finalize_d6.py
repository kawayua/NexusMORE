"""Document D6 approved-reference delivery; do not approve or solve Q2."""
import json,os,shutil
from pathlib import Path
from datetime import datetime,timezone
from modelcrew.config import ROOT
from modelcrew.writing_hand import read,new,rel,frozen_manifest
from modelcrew.collaboration import sha_file
from scripts.run_d4_full import workflow
from modelcrew.contracts import digest

base=ROOT/'stage-d/d6';folder=ROOT/'stage-d/runs/references/d6-q1-to-q2-20261109-v2'
request=read(folder/'resume-request.json')
with workflow() as w:
    context=w.question_context(**request)
    assert context==read(folder/'question-context.json') and not context['model_approved'] and not context['result_approved']
    live=w.task('d2-bench-q1-20261108');assert live['current_version']==1 and live['result_revision']==1 and live['result_approved']
    assert w.db.execute('SELECT count(*) AS n FROM mc_question_references WHERE target_id=%s',(request['target_id'],)).fetchone()['n']==2
    assert not w.db.execute('SELECT 1 FROM mc_tasks WHERE id=%s',(request['target_id'],)).fetchone()
    entry=w.record_entry(live['id'],version=1,kind='next_step',actor='codex-d6-orchestration',request_id='D6-Q1-to-Q2-reference-'+digest(request)[:24],text='按用户更新的D6约定，已确认的第一题产物供第二题只读参考；引用已绑定版本、确认记录与哈希，新进程恢复一致。第二题仅完成输入准备，未建模批准、未求解。',artifacts=[{'path':rel(folder/'question-context.json'),'sha256':sha_file(folder/'question-context.json'),'role':'Q2_confirmed_previous_question_references'},{'path':rel(base/'requirements-update.json'),'sha256':sha_file(base/'requirements-update.json'),'role':'user_D6_scope_update'}],metadata={'target_id':request['target_id'],'target_revision':1,'reference_ids':request['reference_ids'],'model_approved':False,'result_approved':False,'new_solver_runs':0})
    new(base/'registration.json',{'database_entry':entry,'target_id':request['target_id'],'reference_ids':request['reference_ids'],'reopened_context_identical':True,'previous_question_confirmations_preserved':True,'Q2_is_intake_not_approved_model_task':True})
current={'stage':'D6','effective_scope':'前题产物确认后，后题即可读取并参考使用','status':'confirmed_reference_access_verified','task_scope':'current_Q1_to_Q2_case_and_reusable_database_reference_interfaces','target_id':request['target_id'],'target_revision':1,'run_dir':rel(folder),'reference_ids':request['reference_ids'],'source_task_id':'d2-bench-q1-20261108','source_contract_version':1,'source_result_revision':1,'source_execution_id':str(live['execution_id']),'new_solver_runs':0,'new_model_API_calls':0,'Q2_model_approved':False,'Q2_result_approved':False,'Q2_stage':'INTAKE_AND_REFERENCE_READY','complete_paper_or_formal_export_required':False,'tests':{'targeted_database_passed':13,'full_database_regression_passed':474,'counts_overlap':True},'next':'Second-question collision-model design, independent M1 and explicit user model approval before solving','legacy_full_D6_or_all_three_generic_agents_claimed':False,'report':'stage-d/d6/acceptance-report.md'}
new(base/'current-references.json',current)
report='''# D6 已确认前题产物向后题开放读取

用户更新的D6范围为“前题产物确认后，后题即可读取并参考使用”。本次已实现数据库引用接口，并用问题一→问题二完成实际读取与重启恢复验证；不再将前题论文完成、正式导出或W2作为已确认模型/结果的读取前提。

[第二题输入交接](question2-handoff.md) · [当前引用状态](current-references.json) · [实际上下文](../runs/references/d6-q1-to-q2-20261109-v2/question-context.json)

## 实际路径

第一题任务d2-bench-q1-20261108的契约版本1、结果修订1，以及已确认D5正文和九图保持原状。第二题使用独立输入工作区d6-bench-q2-20261109、修订1，原题第3页问题2和result2.xlsx模板已登记来源与哈希。没有把第一题契约复制成假第二题已批准模型，也没有给第二题创建可误调历史fixture的业务求解任务。

模型引用和结果/正文/图引用分别建立，共两条数据库不可变记录。实际读入第一题已确认的模型和数学说明、301时刻×224把手的全量数组、正文及9图。数组、论文及图文件真实打开并核对哈希；独立新进程连接数据库后恢复的上下文逐字一致。

引用不仅是文件路径：记录来源任务、契约版本及哈希、结果执行ID与修订、模型/结果确认事件、正文/选图确认数据库条目、所用文件内容哈希和使用目的。数值从已登记执行的内容寻址快照读取，不接受调用方随意指定未确认文件。正文与图的批准从数据库用户反馈工件取得，不信任可变current指针。图、正文自身确认单独校验；只读取模型时不查询结果或论文确认。

## 实现及安全边界

迁移009增加mc_question_intakes与mc_question_references及数据库禁止修改/删除触发器。modelcrew.question_references提供独立产物范围的确认验证、幂等引用登记、目标绑定、历史留存和当前读取校验；Workflow新增question_intake、attach_question_reference、question_context入口。源题必须早于目标题，目前题序显式采用Qn；不支持的自定义序号必须先扩展规则，不能默认猜测。跨题案例不匹配、相同题、自引用、反向引用、重复ID与路径越界均拒绝。

现有建模入口新增可选question_reference参数：显式绑定对应后题与契约范围后，将已确认前题上下文送入原始输入证据与规划调用；M1接纳路径在后题批准/执行之前重新校验已经绑定的前题引用。历史未启用跨题引用的任务保持原行为。本次没有为第二题生成建模方案或发起M1，因此不将接口接入冒充第二题建模闭环已经运行。

前题版本、确认、正文或图字节变更会阻断旧引用的新读取，旧记录保留；重新使用必须明确登记新引用。后题输入修订变化同样阻断旧目标绑定。前题的确认不会生成后题模型、结果或正文批准。结果、正文、图范围的当前实现使用现有D4/D5工件结构，未宣称任意题型或任意供应商产物适配已经完成。

## 核验与限制

数据库专项13项全部通过，见[专项JUnit](../d6-targeted-db.xml)；之后增加引用上下文篡改、反向题序、建模入口目标错配及题面摘录篡改检查，完整数据库回归474项全部通过，0失败、0跳过，耗时88.63秒，见[全量JUnit](../d6-regression.xml)。专项与全量存在重叠，不相加。实际Q2工作区有2条引用，新进程恢复一致，来源任务原有批准保留，Q2模型与结果批准均为false。

首次沙箱内数据库连接超时，未完成业务登记；原失败运行目录v1及失败测试XML保留，获准访问现有本地数据库后在新目录v2完成真实验证。基础设施连接失败没有当作数学或求解失败；未删除历史产物。程序不重跑求解器，不使用供应商模型API，不生成正式论文，不派发非必要质检Agent。

本次按用户更新完成的是“确认后的前题产物向后题开放读取参考”，不将历史D6所列所有多题调度/恢复演示、通用自主Coder/Writer/API或整个D阶段一并宣称完成。独立M1/P1/P2/W1仍沿各题自身流程运行，正式导出和W2归E。既有D4/D5用户确认、正文、图文件和其原配置哈希未修改。

## 第二题下一步

第二题要求确定不发生碰撞的盘入终止时刻。第一题中心点运动学和0—300秒状态不能提供无碰撞结论，也不能给出300秒之后的状态。下一步需要建立实体几何与碰撞判据，区分相邻铰接允许接触和构件碰撞，提出终止时刻定位与复核计划，经独立M1审查后交用户确认，再执行求解。本次不报告未经求解的终止时刻。
'''
(base/'acceptance-report.md').write_text(report,encoding='utf-8')
doc=ROOT/'docs/d6-approved-question-references.md'
doc.write_text('''# D6 更新：已确认前题产物供后题读取参考

用户于2026-11-09明确更新：前题产物确认后，后题即可读取并参考使用。本文件记录这一更新，优先于three-hand-collaboration.md中早期“D6：多小题与恢复”的验收范围；原文件作为既有已确认写作上下文的哈希来源保留，不原地改写。

模型确认后即可读取模型；结果、正文、图片分别在自身确认后开放，不以整篇论文、正式导出或W2作为前题模型/结果可读的前提。跨题使用固定来源版本和哈希，保留实际引用记录；来源新版本不能静默覆盖旧引用。引用仅是参考，不继承前题审批，不自动批准后题。

当前已实现可复用数据库引用与建模输入接口，实际问题一→问题二读取及恢复验证见[验收报告](../stage-d/d6/acceptance-report.md)。第二题只完成输入与引用准备，尚需自身建模、独立M1、用户确认与后续求解审查。历史D6其余能力和通用Agent/API完成情况不由本次范围更新自动视为通过。
''',encoding='utf-8')
p=read(ROOT/'stage-d/progress.json');p['current_milestone']='D6_confirmed_Q1_references_available_to_Q2'
p['milestones']['D6']={'status':'updated_scope_implemented_and_verified','user_acceptance':'not_recorded','scope':'前题产物确认后，后题即可读取并参考使用','report':'stage-d/d6/acceptance-report.md','target_id':request['target_id'],'target_revision':1,'reference_count':2,'Q2_stage':'INTAKE_AND_REFERENCE_READY','Q2_model_approved':False,'Q2_result_approved':False,'legacy_full_D6_capabilities_claimed':False}
p['next']='Q2 collision-model proposal and independent M1, then user confirms Q2 model before solving; E/W2 remain separate'
p['approved_question_reference_access_implemented']=True
path=ROOT/'stage-d/progress.next.json';new(path,p);os.replace(path,ROOT/'stage-d/progress.json')
r=ROOT/'stage-d/README.md';s=r.read_text(encoding='utf-8');s=s.replace('| D6 多小题、定向返工与恢复 | 待实施 |','| D6 已确认前题产物供后题读取参考（用户更新） | 已实现并用Q1→Q2验证；第二题输入就绪，尚未确认或求解，见 [D6报告](d6/acceptance-report.md) |')
s+='\nD6最新范围见[更新说明](../docs/d6-approved-question-references.md)。第一题结果、正文与九图的既有确认不变，第二题的模型与结果仍需单独确认。\n';r.write_text(s,encoding='utf-8')
(base/'README.md').write_text('# D6 已确认前题产物复用\n\n第一题已确认产物已向第二题开放参考；实际读取与恢复验证完成，第二题未批准、未求解。\n\n[第二题输入交接](question2-handoff.md) · [执行报告](acceptance-report.md) · [当前状态](current-references.json)\n',encoding='utf-8')
source_dir=base/'sources';source_dir.mkdir(exist_ok=True)
code=['migrations/009_question_references.sql','modelcrew/question_references.py','modelcrew/workflow.py','modelcrew/modeling_hand.py','scripts/run_d6_references.py','scripts/finalize_d6.py','tests/test_question_references.py','tests/conftest.py']
for name in code:shutil.copyfile(ROOT/name,source_dir/Path(name).name)
paths=[*base.glob('*.json'),*base.glob('*.md'),*source_dir.glob('*'),*folder.glob('*'),ROOT/'stage-d/progress.json',r,doc,ROOT/'stage-d/d6-targeted-db.xml',ROOT/'stage-d/d6-regression.xml']
new(base/'evidence.json',{'created_at':datetime.now(timezone.utc).isoformat(),'scope':'D6 updated requirement and actual Q1-to-Q2 reference verification','files':frozen_manifest([p for p in paths if p.is_file()])})
print(json.dumps({'D6':'updated_scope_verified','Q2':'INTAKE_AND_REFERENCE_READY','references':2,'full_regression_passed':474,'new_solver_runs':0,'Q2_model_approved':False,'Q2_result_approved':False}))
