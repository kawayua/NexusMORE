from modelcrew.project_assets import asset_path
import json
from pathlib import Path
from modelcrew.config import ROOT
stage=asset_path(ROOT,'stage-b');data=json.loads((stage/'stage-b-acceptance-20261106.json').read_text(encoding='utf-8'))
recovered=data['evidence_recovery'][0];xml='runs/stage-b-final-acceptance-20261106.xml'
text=f'''# 阶段 B 复审与验收报告

验收日期：2026-11-06（北京时间）。验收对象：ModelCrew“契约与人工关卡”，本地工作区及专用PostgreSQL。依据为[原计划](../modelcrew-agent-plan.md)阶段B六项任务，以及用户确认的输入结构、版本档案和回退补充要求。

## 验收结论

**阶段 B 功能验收通过，整体验收有条件通过；暂不标记为无保留收尾。** 此前输入结构契约、可替换执行接口和解释修改后审核三项功能缺口已补齐。本次76项测试全部通过，两个真实重启演练合计5次数据库重启通过；未新增真实模型调用、数值求解或用户确认。

唯一阻止无保留收尾的事项是H1：历史固定样例Excel的原字节证据仍有缺失。它不否定已验证的新工作流功能，但不能把当前数值一致包装成旧文件完全未变。v2真实求解的原确认Excel已找到同哈希副本并独立归档，详见下文。历史版本资料补录、真实模型草稿质量及干净环境部署另列为范围限制或后续项，不混作已完成事项。

机器可读结论与证据哈希见[验收JSON](stage-b-acceptance-20261106.json)；此前审查记录保留于[历史验收记录](acceptance-audit.md)。本报告替代其早期“功能缺口未补齐”的当前状态，不改写那些历史事实。

## 原计划逐项验收

| 项目 | 本次结论 | 审查依据与实际边界 |
|---|---|---|
| B1 契约、字段说明、输入输出结构、合法与非法样例 | 功能通过 | JSON Schema 1.0.0/1.1.0兼容；按类型描述结构、来源、单位与待确认项。结构校验与数学检查分开；不能从JSON合法推导模型正确。正式v1/v2仍保留原1.0.0格式，没有静默升级。 |
| B2 业务记录、指导、版本、确认、执行与产物关系 | 功能通过，附H1历史例外 | PostgreSQL不可变契约/执行/结果/事件/档案/回执记录，事务、外键和内容哈希验证通过；旧固定样例字节缺失仍留痕。 |
| B3 单题状态图、双人工关卡、可替换执行接口 | 通过 | 支持historical-fixture、manifest-fixture、reviewed-run；CLI选择、按新业务版本保存配置、统一回执及安全恢复。真实受控运行可登记，未实现自动运行新生成代码，也不属于本阶段强制项。 |
| B4 查看、确认、指导修改、拒绝、幂等与过期请求 | 通过 | 真实数据库测试覆盖重复/并发请求、过期版本/结果、拒绝保持等待、非法原始graph resume不能授权。actor为本地审计标签，未宣称身份认证完成。 |
| B5 修改影响、复用计算重审、检查点恢复 | 通过 | 模型/输入/执行设置变化创建新待确认版本，清空当前下游引用；解释变更复用execution_id并新建结果revision。审核失败阻止确认，unknown需明确人工意见；回执先持久化，可恢复发布。 |
| B6 完整人工干预演练 | 通过，区分证据来源 | 实际dragon-q1保留v1→反馈→v2→方案确认→已有真实受控求解→结果确认历史。本次新增演练全部使用模拟用户与固定证据，没有伪造真实确认或新求解。 |

输入结构与版本操作见[操作说明](../docs/input-contract-and-version-cli.md)，执行与解释审核见[专项说明](../docs/execution-and-interpretation-review.md)。旧版本未保存执行配置时，恢复必须显式选择后端；系统不会推测旧设置。

## 本次直接验证证据

**完整回归：76 passed，0 failed，0 errors，0 skipped，用时{data['pytest_duration_seconds']:.2f}秒。** 命令为`python -m pytest tests --integration -q --junitxml=stage-b/runs/stage-b-final-acceptance-20261106.xml`，原始结果见[JUnit XML]({xml})。使用真实PostgreSQL与checkpointer；草稿API测试和部分求解登记事务测试采用模拟模型/数值验证器，不能把76项都表述成真实模型或真实求解测试。

| 重启演练 | 本次实测结果 | 证据 |
|---|---|---|
| 版本与等待点恢复 | 3次数据库重启；方案等待、结果等待、恢复旧方案业务提交后/检查点推进前均恢复。旧方案生成新待确认版本；重复请求不重复建版本、执行或档案。 | [版本恢复记录](version-recovery-verification.json) |
| 执行回执与解释审核 | 2次数据库重启；回执已保存/执行未登记时中断后复用回执，未再派发。passed/failed/unknown全部演练；错误断言无法确认，unknown需明确人工审阅。4个结果revision共用1条执行、1份回执。 | [执行与审核记录](executor-review-verification.json) |

测试还覆盖执行配置与版本绑定、错误回执拒绝、失败尝试留痕、未知外部结果先recover、数值/单位/字段/形状/索引/证据错误、规范化解释、自定义后端缺失不回退、原产物覆盖后的独立副本读取、任务与初始档案原子入库，以及不可变记录保护。

本次数值审核支持NPZ与JSON中的明确断言。结构化解释通过只表示给定单位、选择器与声明容差下断言符合证据；不替代原契约验收容差，不证明任意自然语言、物理假设或泛化能力。自由文字仍保留unknown与人工审阅关卡。

## 正式任务现场审查

只读核对`dragon-q1`：当前业务版本 **v2**、结果 **revision 2**、状态 **COMPLETED**，方案与结果确认标志均为true，checkpoint无待执行节点；共2份契约、3条执行、3个结果、2份确认摘要和4条原用户确认。契约内容哈希、输入文件哈希及执行—契约关联通过核对，数据库历史未被重写。详细数据见[正式任务现场审查](stage-b-production-audit-20261106.json)。

3条执行分别包含历史fixture与已有真实solver，不能视为三次新求解。当前两份输出Excel重新回读后，六位小数显示、与各自未舍入数组的回读误差及与独立参考结果的误差均通过：舍入阈值5.00001e-7，独立参考对照阈值1e-6。数值通过与字节哈希一致是两项不同检查。

正式任务在新版`mc_version_entries`中尚无补录条目。原契约method、原代码/方案文件、执行产物与指导/确认事件仍可追溯，但不能宣称每版的原始Agent说明、实验叙述和下一步都已统一整理。功能测试任务已验证这些条目的记录、幂等、原子提交与查询能力；历史缺项见H2。

## 历史证据异常与本次找回

现场检查发现2个原路径上的Excel字节哈希变化，涉及3条历史执行引用。时间上与此前手动重启一次性求解容器后重新写出文件一致；本报告不根据时间相关性单独证明唯一原因。

本次只读搜索了项目内101个Excel/内容副本候选，找到8份与v2真实solver原登记哈希完全一致的Excel。已将其中一份保存为独立内容副本：

- 原登记哈希：`{recovered['archive_sha256']}`。
- 原始匹配副本：[来源文件](../{Path(recovered['path']).as_posix()})。
- 独立归档：[原确认字节副本](../{Path(recovered['archive_path']).as_posix()})。
- [找回映射记录](historical-evidence-recovery-20261106.json)与[搜索记录](historical-artifact-copy-search-20261106.json)。

复制过程按原哈希复核，没有覆盖当前运行目录、改写数据库原登记路径或沿用旧确认去批准新文件。因此v2原确认文件的字节证据已能通过归档映射取得；原路径的changed状态仍如实保留。阶段A历史固定样例的原登记Excel哈希在本次范围内仍无匹配副本，影响v1/v2两条fixture引用；未搜索整个磁盘或外部备份，不能据此断言永不可恢复。

## 遗留项与收尾条件

| 编号 | 状态与影响 | 后续处理 |
|---|---|---|
| H1 历史固定样例原字节缺失 | 开放；阻止“全部历史证据无异常”的无保留收尾 | 优先从备份找回原哈希文件；若确实无法找回，保留旧登记和异常，明确归档例外，或以新版本、新产物和独立用户确认建立替代证据。不能替换旧哈希、覆盖旧确认来伪装修复。 |
| H1R v2真实结果原Excel | 原字节已找到并独立归档 | 保存本报告的映射与归档副本；原路径不静默改写。 |
| H2 历史版本档案补录 | 待补录；不否定档案功能测试 | 从确有原文的方案、代码、实验和用户事件追加带来源条目；不存在的原始说明标缺失，不事后伪造。 |
| N1 完整草稿真实模型验证 | 尚未实测；属于新增扩展验证 | 当前模拟接口测试通过；后续另做真实调用质量验证，不将其追溯新增为原计划B的强制验收门槛。 |
| N2 自由文字/通用数学审核 | 明确范围边界 | 继续保留人工关卡；本阶段没有宣称通用语义自动证明。 |
| N3 部署及后续阶段能力 | 未在本次验收范围内 | 未测试Gitee干净检出部署、Web/API、MCP、角色并行或真实论文生成。运行缓存仍为本地资料，不能据此声称可分发部署完成。 |

本次结论是**有条件通过**。关闭H1或明确处置并记录历史例外后，再评定是否可改为无保留收尾；本报告不自动启动阶段C，不改变既有方案/结果确认。历史功能缺口已补齐，剩余问题应围绕证据保全和归档处理，不重复扩张到后续阶段范围。
'''
path=stage/'stage-b-acceptance-report-20261106.md';path.write_text(text,encoding='utf-8')
p=stage/'progress.json';progress=json.loads(p.read_text(encoding='utf-8'))
progress.update(date='2026-11-06',status='stage_b_conditional_acceptance',acceptance_date='2026-11-06',acceptance_report='stage-b/stage-b-acceptance-report-20261106.md',acceptance_json='stage-b/stage-b-acceptance-20261106.json',functional_acceptance='passed_with_documented_scope',unconditional_closeout=False)
progress['verification']['acceptance_retest']={'passed':76,'failed':0,'errors':0,'skipped':0,'integration':True,'date':'2026-11-06','xml':'stage-b/runs/stage-b-final-acceptance-20261106.xml','production_audit':'stage-b/stage-b-production-audit-20261106.json','historical_integrity':'v2 original recovered; legacy fixture original still not found'}
progress['verification']['database_restart']={'passed':True,'restarts_this_acceptance':5,'evidence':['stage-b/version-recovery-verification.json','stage-b/executor-review-verification.json']}
progress['acceptance_gaps']=['H1: Original byte copy of historical fixture workbook not found within audited local candidates; two legacy fixture references affected']
progress['nonblocking_followups']=['H2: Backfill existing v1/v2 materials into version dossiers with source attribution','N1: Real configured-model full draft quality validation','N3: Clean deployment/repository evidence packaging in later scope']
progress['next_required']=['Resolve H1 by recovering the original fixture bytes or explicitly documenting a historical exception/replacement evidence with separate user confirmation','Review unconditional closeout after the evidence disposition; retain all original hashes and confirmations']
progress['blockers']=['H1 blocks unconditional evidence closeout; stage B functional acceptance passed']
p.write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ['README.md','acceptance-audit.md']:
    p=stage/name;old=p.read_text(encoding='utf-8-sig');banner='> 2026-11-06最新复审结论：阶段B功能通过、整体验收有条件通过。完整结论以[本次验收报告](stage-b-acceptance-report-20261106.md)为准；v2原确认Excel已找到并归档，旧固定样例原字节与历史档案补录仍有遗留。下文保留各次历史记录。\n\n'
    if banner not in old:p.write_text(banner+old,encoding='utf-8')
print(path)
