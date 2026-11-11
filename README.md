# 枢模 · NexusMORE

**仓库快照**：当前提交包含项目源码与阶段文档。外部参考原文及本地验证产物另行保留，使用前请看[快照范围](docs/source-snapshot.md)。

**最终交付目标与后续阶段（2026-11-10）**：可开源分发、可由外部 harness 引入的数学建模 Agent。E 后按 F（统一安装/配置/许可与可移植运行）→G（完整工作流 MCP 与首个真实宿主接入）→H（端到端评测、文档与首发准备）推进。现有检索/执行 MCP 不等于完整 Agent 已对外接入；上述为待实施计划，见[开源与 harness 路线](docs/open-source-harness-roadmap.md)。

**E阶段最新交付登记（2026-11-10）**：E0–E5 研究稿工程验收完成，已跑通真实 Q1 解释版本更新、Q2 引用影响检查及局部重建。既有 Word/PDF 已获用户验收，同源 LaTeX 已编译并通过独立局部 W2。见[E 阶段收口报告](stage-e/implementation/20261110-upstream-continuation-v1/E阶段联合验收收口报告.md)。以下较早记录保留为历史。


**阶段E接入更新（2026-11-10）**：通用汇编、正文/选图审阅、版本绑定、导出/渲染及独立多模态 W2 派发已接通。原正式 PDF/Word 已获用户验收；本次新通用导出实际渲染通过，供应商 W2 与唯一复核均因证据回执无效而阻断，未登记通过。真实局部更新闭环及 E 整体验收仍待完成。见[E阶段当前入口](stage-e/README.md)。

**阶段 E 启动（2026-11-10）**：D 已获用户验收；复用最新 Q1/Q2 合编与独立 W2。通用 E1 已接通输入冻结、恢复核验和依赖影响报告，通用汇编/导出/W2 全流程仍在建设，见 [E 阶段入口](stage-e/README.md)。

**阶段 D 最新状态（2026-11-08）**：D1 基础接口与 D2 建模手/M1 已实现；真实参考辅助建模及独立质检已跑通，演示任务仍等待用户方案确认，没有新求解。失败、误报及只读复核均保留。见[D2 工程报告](stage-d/d2/acceptance-report.md)和[接口说明](docs/d2-modeling-hand.md)。代码手与论文手在 D3—D5 接入；以下 A/B/C 及论文记录保留为历史。

枢模 · NexusMORE 是数学建模任务的辅助与流程研究工具，用于研究大语言模型在开放性建模任务中的协作、验证和可追溯机制，不用于实际竞赛作品提交。公开资料使用时保留来源说明和使用条件。

**当前状态（2026-11-07）：A+/B+/C+ 原任务完成；在 ABC+ 内继续完善中文论文与配图流程，现有单题正文已获用户通过，15 张候选图的最终选择待讨论。** 论文以 math-modeling 的中文数学建模结构为准，math-reasoning 只用于公式推导与证明，先输出 Markdown 供用户审阅和选图。见[新论文规范与使用入口](docs/chinese-modeling-paper.md)。历史 C+ PDF 保留为工程探针，阶段 D 通用角色写作尚未实现。

阶段 C 当前进度（2026-11-06）：阶段C已由用户明确验收通过，见[验收确认](stage-c/user-acceptance-20261106.json)。C1至C6工程检查和15项证据/状态核查均通过。C6故障恢复与清理演练24项检查通过，完整回归151项通过；修复监控退出后的超时接管和待发布回执绑定检查。本轮仅用合成任务，未调用LLM、求解正式赛题或取得真实用户批准，正式任务未改动，测试容器已清理。见[阶段C验收材料](stage-c/stage-c-acceptance-report-20261106.md)、[C6摘要](stage-c/c6-failure-verification-summary.json)及[恢复说明](docs/failure-recovery.md)。两个MCP、联网引用和任务/版本讨论快照已接入工作流。图片OCR按用户要求暂缓，多模态识图未接入；真实modeler协作与论文引用位置属于D。已按用户最新决定取消新任务和空白建模上下文的强制门槛，[阶段C验收](stage-c/stage-c-acceptance-report-20261106.md)已确认通过，阶段D尚未启动。

A+完成方法选择、数学推导与LaTeX源基线，49项直接检查、30项专项测试、全量181项回归通过；用户验收尚未记录。见[A+验收报告](stage-a-plus/acceptance-report.md)和[复核入口](stage-a-plus/README.md)。

B+已完成数学包Schema、版本/确认绑定、同源提案与数学变更失效机制；新增46项专项测试、全量227项回归及22项流程演示通过。见[B+验收报告](stage-b-plus/acceptance-report.md)及[操作入口](stage-b-plus/README.md)。正式v2/revision2未改，A+/B+用户验收尚未记录。

**协作架构（2026-11-08）：三手协作＋独立质检。** 建模手整合拆题/检索/建模，代码手负责受控求解与候选图，论文手负责中文建模稿与汇编；Validator/Reviewer 作为临时只读独立质检。已更新[阶段任务](modelcrew-agent-plan.md)和[三手实施约定](docs/three-hand-collaboration.md)，当前为计划/上下文配置，运行节点待 D 实施。

## 结果与设计入口

- [已通过的中文单题正文](output/md/modeling-q1-candidates-v3/单题论文-中文审阅稿.md) · [15 张候选配图讨论清单](output/md/modeling-q1-candidates-v3/配图讨论清单.md) · [流程维护与 ABC+ 分工](docs/paper-workflow-maintenance.md)（新增选图待确认）

- [项目内置算法索引](resources/algorithms/index.md)（七类完整参考资料与项目补充已内置；结构化检索和自动路由待接入）
- [参考 nature-figure 的科研绘图规范](docs/scientific-figure-contract.md)（规范，自动审图接入待实现）

- [A—F 统一主线：因题选法、数学论证与 LaTeX](docs/algorithm-math-latex-mainline.md)（A+ 基线与B+交接已实现；C+尚未实施）

- [参考算法资料、数学推理与角色分工优化后的 D—F 阶段设计](docs/stage-d-e-refined-roadmap.md)（规划，尚未实现）

- [阶段A验收小结与全部失败分类](stage-a/2024-A-problem-1/stage-a-summary.md)
- [阶段B交接设计与首轮任务](docs/stage-b-handoff.md)
- [成功模型代码的Excel结果](stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z/output/result1.xlsx)
- [容器使用说明与数值误差](stage-a/2024-A-problem-1/docker-execution-result.md)
- [人工参考结果](stage-a/2024-A-problem-1/reference-result.md)及[外部论文对照](stage-a/2024-A-problem-1/external-reference-check.md)
- [MiMo独立失败记录](stage-a/2024-A-problem-1/mimo-baseline-result.md)及[百炼生成过程](stage-a/2024-A-problem-1/model-retry-status.md)
- [范围](stage-a/2024-A-problem-1/scope.md)、[输入清单](stage-a/2024-A-problem-1/input-manifest.json)、[参数](stage-a/2024-A-problem-1/parameters.json)和[运行前验收清单](stage-a/2024-A-problem-1/acceptance-checklist.md)

## 本地复核

人工参考入口：`python scripts/reference_2024_a_q1.py`，每次创建独立run_id。默认输入路径在原始题目目录，见输入清单；依赖见scripts/requirements-reference.txt。参考计算不计入LLM生成代码成功率。

模型入口：`python scripts/generate_2024_a_q1.py`，从本机.env读取配置，可能产生API费用；仅生成方案与代码，不自动执行。API Key不提交、不写入日志。当前调用还需httpx、pypdf和openpyxl等依赖，完整干净环境安装流程尚待整理。生成后需人工数学与安全审阅，记录与代码原始字节匹配的哈希。

镜像构建只用execution目录作上下文，避免把密钥和项目数据送入构建：

```powershell
docker build --pull=false -f execution/Dockerfile.py311 -t modelcrew-reference:py311 execution
python scripts/execute_reviewed_2024_a_q1.py stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z --image modelcrew-reference:py311 --keep-container
python scripts/compare_2024_a_q1.py stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z
```

上面的执行目录已运行并有output，不能直接原样再次执行：执行脚本会拒绝覆盖已有output。正式重跑需新建工件目录并重新核对绑定、快照和审阅，不删旧证据。Docker Desktop手动启动保留容器会覆盖同一output，不产生新run_id，且不附带执行脚本的超时监控。

原始题面和论文图像未提交；runs目录被Git忽略，以上本地产物链接不会随仓库自动分发。当前证据在本机可复核，尚不宣称干净环境一键复现。阶段B契约、PostgreSQL迁移、LangGraph双确认流程与CLI已写入，真实数据库恢复测试待验证，MCP与检索后置。

## 阶段 B 开发入口

[契约字段与合法/非法样例](contracts/README.md) · [CLI、数据库及恢复设计](stage-b/README.md) · [实现与验证状态](stage-b/progress.json)。目前7项契约和11项数据库集成测试通过，两次真实数据库重启恢复通过；实际任务dragon-q1的v1方案及结果revision 1均已由用户明确确认，状态COMPLETED。请审阅[契约摘要](stage-b/contract-review.md)。

阶段B验证证据见[集成验证记录](stage-b/integration-verification.md)。当前执行节点仅使用A历史固定工件联调，不代表真实求解已迁入状态图。

[实际用户双确认联调记录](stage-b/user-confirmed-demo.md)：已完成v1；真实用户指导创建v2的演示尚未进行。

2026-11-04：用户指导已使模型生成并保存dragon-q1契约v2，新版本待确认，v1历史完整保留。详见[v2审阅](stage-b/v2-review.md)。

当前入口：[v2真实求解报告及Excel](stage-b/v2-solver-result.md)，26项测试及v2数值检查通过，结果revision 2已由用户确认。

[v2实际结果确认记录](stage-b/v2-confirmation.md)：任务已完成；阶段B整体验收仍需按原定条件核对。

**阶段B整体验收（2026-11-04）：暂未完整收尾。** 26项回归通过，但输入数据结构契约、可替换执行接口、解释修改后的重新审核尚需补齐。详见[验收报告](stage-b/acceptance-audit.md)。


阶段E证据协议更新：W2登记引用协议2.2已通过真实54页资格验证，模型FAIL原样保留，未创建正式W2回执或重置复核次数。见[协议修复记录](stage-e/implementation/20261110-w2-protocol-v2/证据协议修复记录.md)。
