# 中文数学建模论文：Markdown 首稿与用户选图

**协作组织更新（2026-11-08）**：使用[三手协作＋独立质检](three-hand-collaboration.md)。建模手包含 Planner/Researcher/Modeler，代码手承担 Coder，论文手承担 Writer；Validator/Reviewer 按节点临时独立审查。下文英文名称为职责标签，不再要求七个独立业务 Agent。既有结果、正文/选图确认和正式导出保留，D5/E 接入通用三手工作流。

更新：2026-11-07。用户确认 A+/B+/C+ 当前任务已完成，同时指出 C+ 单题输出偏向公式证明文章。本次补充独立的论文体裁与审阅流程；不覆盖历史数学包、确认快照、已编译 PDF 或原验收记录。

## 最新状态与维护入口

用户已选择全部15张图，并明确“补图后的新版正文也通过”。最新中文稿、图件及独立确认记录已在C+重执行目录复核，正文与全部选图均通过；未重画已选图或执行正式论文排版。原先9图/15候选的历史首稿说明保留，当前状态以[最新双确认记录](../output/md/modeling-q1-cplus-recheck-20261107/review-status-confirmed.json)为准。最新清单和如何长期修改见[流程维护指南](paper-workflow-maintenance.md)。下文9张图的首稿记录保留为初版说明。

## 两类产物的边界

`modelcrew.mathematics.render` 与 `scripts.build_cplus_export` 仍负责数学交接和工程编译探针，不作为论文生成器。其历史英文输出不是论文风格模板。新的论文内容由 math-modeling 论文手与中文数学建模模板约束，math-reasoning 仅参与公式推导、必要证明及公式核对，不能主导论文大纲、语言或排版。

正式规范位于 [writer-instructions.md](../resources/paper/writer-instructions.md)，机器规则位于 [chinese-modeling-policy.json](../resources/paper/chinese-modeling-policy.json)，原文/模板快照与来源记录位于 resources/paper/reference 和 [provenance.json](../resources/paper/provenance.json)。复制的 SKILL.md 是评估参考，不是项目运行时执行指令。用户要求的“中文、先 MD 审阅”优先于外部技能默认 Word 交付方式；本次没有核验某届官方提交格式。

正文组织为标题、摘要、关键词、问题重述、问题分析、模型假设、符号说明、模型建立、模型求解、结果分析、误差分析与模型检验、模型评价与推广、结论和参考文献。正文重心是如何回答题目、如何求解、得到什么结果、如何验证。较长证明放附录；内部 JSON 快照、检查点、编译日志和哈希不进入论文。

## 首稿与配图讨论

先产出中文 Markdown 供用户审阅，附候选图说明；本轮单题样稿使用已有用户确认的板凳龙结果，不运行新求解、不新增模型调用。当前模板为针对该题人工组织、可复现填入真实数值的研究首稿，不宣称已实现任意题的自主 Writer。

参考论文手的图数目标，本项目当前论文政策为 raw/process/result 三类候选各至少 3 张、总计至少 9 张；正式入文至少 8 幅。图数按逻辑图计，不按 PNG/PDF/SVG、同图面板或灰度版本重复计数。每个问题覆盖三类候选且有正式图，所有图有题注与正文引用。这替代旧计划中“无固定图数”的默认规则；如果用户讨论后要求减图，需明确记录新的政策版本和理由。

“原始”类允许题目输入与几何/尺寸示意，必须明确其性质；过程类使用真实数值诊断而非编造迭代轨迹。正式图也必须有独立证据用途。用重复视图凑数不符合科学审阅要求，机械计数不替代人对证据价值的判断。

候选清单展示每张图的类别、用途、建议和预览；首稿采用暂选图，用户可保留、替换、合并或要求补图。稿件审阅与图片选择各自需明确同意；确认绑定 Markdown、图目录和政策 SHA-256，变更图片文件或清单后原确认失效。这些确认只用于写作导出，不替代方案/结果双确认。

## 入口与验证

本轮审阅稿：[中文单题论文](../output/md/modeling-q1-review-v2/单题论文-中文审阅稿.md)；[配图讨论清单](../output/md/modeling-q1-review-v2/配图讨论清单.md)。9 张候选图均保留 PNG/PDF/SVG，正文暂选 8 张；第 9 张尺寸对照图与尺寸示意有重叠，暂列备用，不将两张都塞入正文。

```powershell
python -m scripts.build_modeling_review --output output/md/new-chinese-review --qa-tools <nature-figure脚本目录>
python -m scripts.check_modeling_paper output/md/new-chinese-review/单题论文-中文审阅稿.md --catalog output/md/new-chinese-review/figure-catalog.json
```

构建拒绝覆盖已存在目录。图的数据来自既有未舍入轨迹及题目参数；新增的约束曲线是公式诊断，不是新增赛题求解。绘图仍遵循 nature-figure 的 Python 规范，实际执行源预检、每图 PDF 字号/碰撞检查，对齐检查对单面板记录不适用；最终逐图视觉检查另存记录。源预检中的 170 mm 宽度和不输出 TIFF 警告已明确记录研究稿理由。

`modelcrew.modeling_paper.validate_draft` 校验中文体裁、必须章节、内部材料泄漏、图数/分题覆盖、连续编号、实际图文件与哈希、PNG DPI、题注及正文引用，成功仅表示机械检查通过，始终返回 user_review=pending。不能以其证明数学或视觉正确。`require_review_for_export` 为未来正式导出入口提供审阅检查：必须同时明确同意正文与选图，且三份哈希未变；本轮未创建批准记录或导出论文 PDF/Word。当前没有新增通用论文导出 API，也不把该函数说成已接到尚未实现的 D/E 导出节点。

## 阶段归属

本次按用户授权作为 A+/B+/C+ 内的“中文论文体裁与审阅”完善，不重开或覆盖原工程验收。当前完成规范、机器检查、中文单题示例和15图新版正文；用户已通过新版正文与全部选图。D5 的 Writer 应加载新规范，将任意小题结果组织成中文建模 Markdown，W1 检查证据；E 只在用户确认正文和选图后套中文模板排版、编译与 W2 视觉审查。模板快照提供中文 ctexart 基线，不能把其占位内容直接交付或冒称当届官方模板。
