"""Publish a stage-D acceptance finding; this cannot grant user approval."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'stage-d/acceptance/20261109-v1'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
audit=read(BASE/'evidence-audit.json');assert audit['checks_status']=='passed'
assert all(sha(ROOT/f['path'])==f['sha256'] for f in audit['evidence_files'])
suites=list(ET.parse(BASE/'full-regression.xml').getroot().iter('testsuite'))
counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
assert counts=={'tests':491,'failures':0,'errors':0,'skipped':0}
q2=ROOT/'stage-d/runs/full/q2full-eead56d48f5b4d07'
additional=[]
for name in ['review-recheck/independent-math-adjudication.md','review-final/independent-precision-recheck.md','review-final/independent-citation-audit.json','precision-supplement.json']:
    p=q2/name;p.read_bytes();additional.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)})
# Bind actual failure-and-remediation evidence, without replacing original reviews.
assert '速度' in (q2/'review-final/independent-precision-recheck.md').read_text(encoding='utf-8') or 'speed' in (q2/'review-final/independent-precision-recheck.md').read_text(encoding='utf-8').lower()
save(BASE/'supplementary-evidence.json',{'scope':'Read existing P2 mathematical/precision/citation adjudication records; no new independent review','files':additional})
report='''# D阶段验收核查报告

本次核查已完成；工程结论为 **整体验收暂不通过（NOT_READY）**，不是模型或结果被否定。Q1、Q2在明确的题目专用实现范围内均已形成业务闭环，既有用户批准继续有效；通用代码手、论文手及其自动定向返工的统一编排仍有缺口。用户尚未作出阶段D验收决定，本报告不代用户批准，也不通过缩小范围消除未完成项。

## 验收依据与范围

依据 `modelcrew-agent-plan.md` 阶段D、`docs/three-hand-collaboration.md` 和实际D1—D6交付。D6优先采用用户更新记录 `stage-d/d6/requirements-update.json` 与 `docs/d6-approved-question-references.md`：前题各类产物在自身确认后，后题即可读取并参考；引用不能继承后题审批，来源版本和哈希必须绑定。不把旧版D6全部多题调度要求重新加回本次D6门槛，也不将D6范围更新扩张为其他阶段功能豁免。

本次属于工程验收核查：重新运行现有测试与准入演示，读取现有独立质检、用户确认、数据库状态和文件证据。没有新派发供应商请求或业务数值求解任务，没有把本次作者侧核查冒称一次新的独立M1/P1/P2/W1/W2。

## D1—D6逐项结果

| 项目 | 结论 | 实际完成与剩余边界 |
|---|---|---|
| D1 三手交接和独立质检基础 | 已实现范围通过 | 三手职责、版本/内容寻址交接、独立身份及回执准入、拒收自审/过期/缺项均有实现和测试；新目录15项演示通过。合成演示仅证明接口规则。 |
| D2 建模手与M1 | 已实现范围通过 | Q1配置供应商建模/M1已有真实调用；Q2模型由Codex建模上下文完成，M1真实FAIL→新版本返工→PASS，模型获用户确认。支持既有数学基线的建模流程，未宣称任意题型从零自主建模。 |
| D3 最小代码与P1 | 部分完成 | 两题真实受控Docker最小运行及独立P1均通过，失败历史保留；生成/修订/注册/恢复仍通过题目脚本衔接，通用代码手编排尚未实现。 |
| D4 全量计算与P2 | 两题案例通过 | Q1为301时刻×224把手，Q2为连续首事件搜索及224把手终态；实际复跑、全量证据、P2和结果确认有效。Q2速度包围证据缺口已补跑并独立复验关闭；通用运行编排继承D3缺口。 |
| D5 论文手与W1及双审阅 | 部分完成 | 两题W1、中文稿、正文和选图分别确认已完成，失败/返工/复验有证据；Q2确有配置供应商Writer调用，之后由Codex整合。通用Writer仍由调用方提供大纲/Markdown，未接成自主生成与统一业务流程。 |
| D6 已确认前题产物供后题参考 | 更新范围通过 | 数据库不可变引用、按产物分别检查确认、来源/目标版本绑定、失效拒读及恢复验证已实现。当前新读取的Q1→Q2上下文与保存快照相等；Q2独立完成自己的模型/结果确认。 |

“已实现范围通过”不表示任意题型、任意供应商或全部自动化均已覆盖。“案例通过”不能替代相应可复用运行节点的交付。

## 本次实际核验

- 完整真实数据库集成回归：**491 passed，0 failed，0 errors，0 skipped**，耗时169.52秒。命令：`python -m pytest tests --integration -q --basetemp=tmp/d-acceptance-20261109-v1 -p no:cacheprovider --junitxml=stage-d/acceptance/20261109-v1/full-regression.xml`。
- D1重新执行15项准入演示：`python -m scripts.verify_d1_collaboration --output stage-d/acceptance/20261109-v1/d1-verification`。它与491项回归有覆盖重叠，不相加宣称506项独立测试。
- 证据核查：**16项检查通过，661个来源文件哈希固定且核查前后未变**。重新执行既有回执准入与快照检查，覆盖两题P1/P2/W1、Q2 M1，以及M1/W1原FAIL回执的保留和有效性；原独立审查未被作者改写。
- 从当前数据库实际读取两题均为模型已批准、结果已批准、result revision 1；写作上游及W1门禁重验通过，正文/选图均已确认。D6引用上下文中的 `model_approved=false/result_approved=false` 表示“引用不赋予后题审批”，不能误读为Q2当前业务未批准；Q2业务批准已单独从数据库核对。
- Q1冻结全量结果包、Q2冻结全量结果包、两题当前写作输入与入文图的字节检查通过。新增4份P2裁定/精度证据绑定保存在补充清单中，不重复计入661文件主清单。

原始记录：`full-regression.xml`、`d1-verification/verification.json`、`evidence-audit.json`、`supplementary-evidence.json`。所有命令均作用于新的验收目录；没有覆盖已有阶段报告、批准、模型、正文或配图。

## 失败、返工与独立性证据

M1：Q2 `q2-collision-20261109-v1/M1-admission.json` 为FAIL，v2为PASS，随后用户确认新模型。W1：Q1写作v2为FAIL，论文手在新目录修正证据范围/映射后，v3独立复验PASS，v4正文获用户确认。P1/P2：Q1代码错误、执行失败和无效引用拒收原样保留；无效引用不冒充数值语义返工。Q2 P2争议经独立数学裁定，另发现速度认证缺口后实际补跑并独立复验关闭；原供应商回复、严格等值引用映射和独立引用审计均保留。实际案例中的这些返工证明已发生有效检查与修正，尚不能证明通用业务节点会自动完成同一路由。

原有独立身份及回执快照由准入程序重新校验；本次核查没有新派一个自审者替代既有独立质检。相同模型的独立上下文也不等于数学正确性的形式证明。

## 供应商API与执行责任

Q1建模与部分代码生成、独立质检有配置供应商真实调用。Q2建模和最小代码主要由Codex完成，全量供应商Coder仅贡献部分函数；配置供应商真实P2调用与Writer正文调用已留存。Q2最终W1为独立只读上下文通过，原供应商W1 FAIL保留，不能称其最终API通过。所有业务数值计算由受控Docker运行，LLM API不充当数值执行器。

核查依据包括 `modelcrew/executors.py` 的pending-code边界、`scripts/run_d3_minimal.py` 的case-specific声明、`modelcrew/writing_hand.py` 的caller-supplied内容边界、`modelcrew/api.py` 当前入口，以及两题真实调用与作者记录。因此不能据已有若干供应商成功调用，宣称三手已全部走项目配置的供应商API自主求解。

## 阻止D阶段整体验收的缺口

| 编号 | 待完成任务 | 关闭标准 |
|---|---|---|
| D-G1 | 将代码手专用脚本接成可复用的业务运行节点 | 已批准模型经统一入口进入代码生成、静态检查、注册、P1/P2、有限重试；按任务/版本保存状态，未知执行仅查status，恢复不重复派发。实际调用、受控执行及失败记录可追溯，不依赖临时人工调用串联。 |
| D-G2 | 接通通用论文手生成与现有W1/审批生命周期 | 从当前已批准结果和writing_context出发，通过统一入口调用项目配置供应商生成大纲/正文，接独立W1和定向修订，保存版本；正文与选图分别确认，过期输入阻断。题目专用Writer调用不能单独关闭此项。 |
| D-G3 | 将现有返工约定接入上述业务节点 | 至少以真实案例或明确标注的受控缺陷证明模型、实现、解释和基础设施问题进入正确责任节点；遵守既定重试预算，耗尽转人工，拒收旧回执。已有案例返工及单元测试保留为证据，不能代替通用运行链的实际接入。 |

D-G3是D3/D5集成收尾，不是把已由用户替换的旧版D6全部调度要求重新列为D6缺陷。下一项工程任务应优先关闭D-G1，再关闭D-G2并联调D-G3；之后按改动范围复验，重新提交D整体验收。

## E阶段补充证据与当前入口

Q1+Q2合编产物与独立W2已完成：PDF28页、Word27页，16图、9表、19个编号公式。三文件最终哈希与W2绑定一致，见 `stage-e/runs/q1-q2-20261109-v1/completion.json`。这是E阶段的实际汇编案例证据，不改变D阶段上述工程缺口，也不自动宣称通用E框架完成。

阶段级旧报告及局部current文件记载的是当时交付范围；本次以实时数据库核验、当前全量/写作指针和合编completion为综合依据，不回写旧报告中“待确认/尚未求解”的历史状态。`stage-d/README.md` 与 `stage-d/current-acceptance.json` 提供最新综合入口。

**最终状态：验收核查完成；两题案例闭环成立；阶段D完整工程验收暂不具备通过条件；用户阶段验收待定。**
'''
with (BASE/'acceptance-report.md').open('x',encoding='utf-8') as f:f.write(report)
status={'stage':'D','audit_status':'completed','engineering_verdict':'NOT_READY_FOR_FULL_STAGE_D_ACCEPTANCE','two_question_case':'PASSED_WITH_DOCUMENTED_IMPLEMENTATION_BOUNDARIES','user_stage_acceptance':'pending','D6_scope':'confirmed_previous_question_artifact_access','full_regression':counts,'evidence_checks_passed':16,'pinned_source_files':661,'open_gaps':['D-G1 generic coding runtime','D-G2 generic Writer integration','D-G3 integrated directional rework'],'business_approvals_preserved':True,'new_semantic_independent_review':False,'report':'stage-d/acceptance/20261109-v1/acceptance-report.md','created_at':datetime.now(timezone.utc).isoformat()}
save(BASE/'status.json',status)
files=['acceptance-report.md','status.json','evidence-audit.json','supplementary-evidence.json','full-regression.xml','d1-verification/verification.json']
save(BASE/'manifest.json',{'files':[{'path':(BASE/n).relative_to(ROOT).as_posix(),'sha256':sha(BASE/n)} for n in files],'audit_script_sha256':sha(ROOT/'scripts/audit_stage_d_acceptance.py'),'publisher_script_sha256':sha(Path(__file__)),'user_approval_created':False})
pointer=ROOT/'stage-d/current-acceptance.json'
assert not pointer.exists()
save(pointer,{**status,'manifest_sha256':sha(BASE/'manifest.json')})
print(json.dumps({'audit':'completed','regression':counts,'engineering_verdict':status['engineering_verdict'],'user_stage_acceptance':'pending'}))
