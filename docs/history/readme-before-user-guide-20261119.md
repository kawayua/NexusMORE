# 枢模 · NexusMORE

**原生对话审阅更新（2026-11-16）**：待审文件直接附在 DSH 原生回复中，用原生文件侧栏查看；用户在同一输入框回复“通过”或提出修改意见。默认流程不再弹出完整 JSON，确认仍绑定真实用户消息与当前版本，详见[原生对话审阅](docs/dsh-chat-review.md)。真实 G5 模型已由用户先前批准并进入代码阶段，此次交互改动不推进业务或代用户确认结果。

**G5 小题修复进度（2026-11-16）**：四处接入缺口已补齐，真实 DSH 文本小题已自动导入并通过独立 M1，达到原生方案审阅就绪，重启后可恢复；未代用户批准或求解，完整 G5 继续验证。见[修复与复测记录](docs/dsh-small-question-repair.md)。

**G4.2 当前进度（2026-11-16）**：原生会话绑定、自动审阅、模型批准后的受控继续、右侧独立下一题及重开原会话恢复已通过本机工程验收，详见[连续会话与验收边界](docs/dsh-conversation-workspace.md)。真实供应商模型自然语言端到端及业务质量仍由 G5/H 验证；以下带日期段落保留历史时点。

**G3 原生桥接进度（2026-11-15）**：DSH 原生人类命令已通过私有管道接入 G3，支持完整审阅、分别决定及原回执对账；模型 MCP 仍为 40 项，新增不可变宿主捕获证据和迁移 015。真实 DSH 隔离工程流程验证退回提交、取消、M1 阻断及重启后不重发恢复；未代签真实用户业务验收。日常用 `/nexusmore-review` 和 `/nexusmore-review-status`，详见[使用与边界](docs/dsh-local-connection.md)。以下 G4.1/G1—G4 段落保留历史时点含义。

**G4.1 当前进度（2026-11-15）**：已在本机 DSH Desktop 0.2.2-rc.1 真实原生问答卡验证显示、选择返回、取消、跳过、补充文字和关闭行为，新增 `/nexusmore-ui-check` 无审批工程检查命令。结论为原生交互机制可适配；正式 `trusted_host_ui` 桥接尚未实现，真实业务决定继续走 G3。范围和后续条件见[原生交互兼容性](docs/dsh-local-connection.md#g41dsh-原生交互兼容性2026-11-15)。以下 G1—G4 段落保留历史时点含义。

**G4 当前进度（2026-11-15）**：已连接本机 DeepSeek Harness Desktop 0.2.2-rc.1，经真实 DSH ToolRuntime 注册 40 项业务 MCP 工具并验证能力与数据库只读调用；新增保留原配置的注册/哈希回退入口及 `/nexusmore` 只读检查命令。用户决定继续走 G3 本地交互式入口，未启用宿主 UI 审批，也未宣称真实模型端到端已验收。配置、使用与边界见[本地 DSH 接入](docs/dsh-local-connection.md)；G5 故障与恢复矩阵继续实施。下方 G1—G3 段落保留历史时点含义。

**G3 当前进度（2026-11-15）**：已增加绑定本机进程身份、原始决定、当前待办与完整审阅快照的交互式本地用户决定入口，持久化单次事件占用及只读回放对账；旧 HTTP/act 文本参数批准入口关闭，模型 MCP 继续只开放 40 项模型工具。范围与复验见[可信用户决定说明](docs/trusted-user-decisions.md)。真实宿主 UI 捕获与 DSH 联调仍待 G4/G5；下方 G1/G2/F6 段落保留历史时点含义。

**G2 当前进度（2026-11-15）**：完整工作流 stdio MCP 已实现，按 G1 契约开放 40 个模型通道工具，新增 PostgreSQL 派发账本、待确认项与受控产物访问，保持真实用户决定在可信本地入口。实现与验证范围见[业务 MCP 说明](docs/business-workflow-mcp.md)；真实 DeepSeek Harness 联调和宿主用户事件转交仍待 G3—G5。以下 G1/F6 段落保留历史时点含义。

**G1 当前进度（2026-11-15）**：完整业务工具契约 1.0.0 已完成工程冻结，含 50 项操作、机器 Schema、核心映射、版本/幂等/错误与真实用户决定边界；39 项已有核心映射、5 项部分具备、6 项通用操作缺失。详见[冻结说明](docs/business-tool-contract.md)。本轮未实现完整工作流 MCP 或真实 DeepSeek Harness 联调，G2—G5 继续实施；未新增用户验收或公开发行授权。以下带日期段落保留历史状态。

**当前进度（2026-11-15）**：F6.1—F6.6 已按首发范围完成技术验收与收口。当前代码重新构建 wheel/sdist，源码目录外的安装、七类检索、三手路由及真实导出验证通过；既有 M1/P1/P2/W1/W2 和用户成品确认均已复核。当前以[收口报告](docs/internal-routing-closure.md)为准，下列带日期段落保留当时状态。G 的 DeepSeek Harness 接入尚未开始，F5 暂缓及全新 Windows 验证例外继续保留。


2026-11-14：用户决定暂缓 F5 剩余核对并进入 F6 自动资料与工具路由；暂缓项未登记通过，公开发行门禁保留，见[决定记录](docs/release/licensing-deferral-20261114.json)。

F6 内部路由入口已接入三手新运行，按任务实际读取包内资料，并调用受控 PDF/表格/Word 只读工具；范围和恢复规则见[自动资料与工具路由](docs/resource-routing.md)。完整业务与 Harness 验证仍单独验收。

当前组合发行（含 PyMuPDF）采用 **AGPLv3**，根 [LICENSE](LICENSE) 与[组合发行说明](docs/combined-distribution-license.md)载明适用范围。原创文件既有 Apache-2.0 授权与第三方许可保留；没有担保，详见 AGPL 第15/16条。`modelcrew license-info` 提供离线许可和源码材料指引。本项目的学术诚信定位不构成对开源软件权利的额外许可限制。当前仍为私有开发候选，完整公开发行审查未完成。

2026-11-14：本轮原生构建与源码许可材料核对已完成，PyMuPDF/MuPDF 本地功能重建及全页 PDF 检查通过；完整对应源码与公开发行仍有明确门禁，见[核对结果与剩余事项](docs/source-completeness.md)。

2026-11-14：F4 已提供 Windows 私有环境准备入口：通过独立可嵌入 Python 自动安装生产依赖，配置工作区独立 Docker 服务、迁移及固定版本文档工具；使用方法见 [服务与环境准备](docs/environment-preparation.md)。Docker Desktop/WSL2 和 Harness 仍由用户准备，Word 原生渲染另需本机已授权 Word；公开发行和宿主端到端继续分别验收。

2026-11-14：F2私有安装包已收口，F3已新增用户配置与初始化入口。安装后先运行 `modelcrew init`，再用 `modelcrew doctor` 检查基础环境；完整设置见 [用户配置文档](docs/user-configuration.md)。默认业务数据位于用户工作区，Docker服务管理、原生工具准备及宿主端到端仍由后续阶段验证。

首发环境已选定 Windows x86_64、CPython 3.13 和 Docker Linux amd64 执行器；新任务默认 Python 3.13 镜像，本机验证范围及后续安装要求见[运行环境](docs/runtime-environment.md)。

**当前实施（2026-11-11）**：F0 仓库迁移已收口，F1 发布范围与资源清单已启动；新任务按用途命名。详见[发布范围与待办](docs/release-scope.md)。完整知识内置与干净环境端到端尚待后续验收。

**LaTeX 工具（2026-11-12）**：项目自编初始化、环境诊断、资源绑定、真实编译及完整校验，当前支持 Tectonic 0.17.0 / Pandoc 3.6.4，其他编译引擎、外置 BibTeX/Biber、任意 LaTeX→Word 暂不支持；中文默认骨架与审批边界见[LaTeX 工具](docs/latex-tools.md)。

**共享能力与资料适配（2026-11-12）**：`python -m modelcrew.capabilities` 查看当前入口与支持范围；论文候选追踪、受控文档工作区及项目自编数学/统计/证明资料已按本地契约适配。当前193项资源、21份指南，使用与边界见[能力适配](docs/capability-adaptation.md)。

**Python 后端与配图（2026-11-12）**：数据、数值求解、绘图和导出统一 Python，不采用 HTML 选图面板。完整数据读取、三格式图导出、所有 PDF 全页预览/检查及新任务准入见[绘图工具](docs/figure-tools.md)；实际审图、独立质检与用户确认分别保留。

**F0 整理进度（2026-11-11）**：根级阶段材料已逐文件登记并迁入本地档案，必要Schema、数据库迁移、监督器与项目规则已进入包资源；新运行使用用途目录，旧UUID运行保留可恢复工作副本。最终目录检查通过，wheel/sdist隔离安装及历史核验范围见[迁移说明](docs/repository-migration.md)。这不代表完整知识库许可、干净环境工作流或F阶段已全部验收。

**内置文档工具**：已逐项核对84个来源文件，从官方 Apache-2.0 固定版本取得配套工具，接入 PDF 读取、Word 结构校验和表格预览，见[入口与实测](docs/document-tool-integration.md)。完整知识库内置和单包安装仍待完成。

**单 Agent 安装目标**：建模知识、数学论证与中文论文能力随项目内置，使用者无需另装技能包。完整内置尚待 F 阶段落实，具体内容及许可缺口见[内置能力要求](docs/builtin-capabilities.md)。

**仓库快照**：当前工作区按用途组织源码与资源；历史阶段材料保留为本地档案，导航见[历史归档](docs/history/research-archive.md)。外部参考原文及本地验证产物另行保留，使用前请看[快照范围](docs/source-snapshot.md)。

**最终交付目标与后续阶段（2026-11-10）**：可开源分发、可由外部 harness 引入的数学建模 Agent。E 后按 F（统一安装/配置/许可与可移植运行）→G（完整工作流 MCP 与首个真实宿主接入）→H（端到端评测、文档与首发准备）推进。现有检索/执行 MCP 不等于完整 Agent 已对外接入；上述为待实施计划，见[开源与 harness 路线](docs/open-source-harness-roadmap.md)。

**E阶段最新交付登记（2026-11-10）**：E0–E5 研究稿工程验收完成，已跑通真实 Q1 解释版本更新、Q2 引用影响检查及局部重建。既有 Word/PDF 已获用户验收，同源 LaTeX 已编译并通过独立局部 W2。见[E 阶段收口报告](archive/research/stages/stage-e/implementation/20261110-upstream-continuation-v1/E阶段联合验收收口报告.md)。以下较早记录保留为历史。


**阶段E接入更新（2026-11-10）**：通用汇编、正文/选图审阅、版本绑定、导出/渲染及独立多模态 W2 派发已接通。原正式 PDF/Word 已获用户验收；本次新通用导出实际渲染通过，供应商 W2 与唯一复核均因证据回执无效而阻断，未登记通过。真实局部更新闭环及 E 整体验收仍待完成。见[E阶段当前入口](archive/research/stages/stage-e/README.md)。

**阶段 E 启动（2026-11-10）**：D 已获用户验收；复用最新 Q1/Q2 合编与独立 W2。通用 E1 已接通输入冻结、恢复核验和依赖影响报告，通用汇编/导出/W2 全流程仍在建设，见 [E 阶段入口](archive/research/stages/stage-e/README.md)。

**阶段 D 最新状态（2026-11-08）**：D1 基础接口与 D2 建模手/M1 已实现；真实参考辅助建模及独立质检已跑通，演示任务仍等待用户方案确认，没有新求解。失败、误报及只读复核均保留。见[D2 工程报告](archive/research/stages/stage-d/d2/acceptance-report.md)和[接口说明](docs/d2-modeling-hand.md)。代码手与论文手在 D3—D5 接入；以下 A/B/C 及论文记录保留为历史。

枢模 · NexusMORE 是数学建模任务的辅助与流程研究工具，用于研究大语言模型在开放性建模任务中的协作、验证和可追溯机制，不用于实际竞赛作品提交。公开资料使用时保留来源说明和使用条件。

**当前状态（2026-11-07）：A+/B+/C+ 原任务完成；在 ABC+ 内继续完善中文论文与配图流程，现有单题正文已获用户通过，15 张候选图的最终选择待讨论。** 论文以项目中文论文库的中文数学建模结构为准，数学论证库只用于公式推导与证明，先输出 Markdown 供用户审阅和选图。见[新论文规范与使用入口](docs/chinese-modeling-paper.md)。历史 C+ PDF 保留为工程探针，阶段 D 通用角色写作尚未实现。

阶段 C 当前进度（2026-11-06）：阶段C已由用户明确验收通过，见[验收确认](archive/research/stages/stage-c/user-acceptance-20261106.json)。C1至C6工程检查和15项证据/状态核查均通过。C6故障恢复与清理演练24项检查通过，完整回归151项通过；修复监控退出后的超时接管和待发布回执绑定检查。本轮仅用合成任务，未调用LLM、求解正式赛题或取得真实用户批准，正式任务未改动，测试容器已清理。见[阶段C验收材料](archive/research/stages/stage-c/stage-c-acceptance-report-20261106.md)、[C6摘要](archive/research/stages/stage-c/c6-failure-verification-summary.json)及[恢复说明](docs/failure-recovery.md)。两个MCP、联网引用和任务/版本讨论快照已接入工作流。图片OCR按用户要求暂缓，多模态识图未接入；真实modeler协作与论文引用位置属于D。已按用户最新决定取消新任务和空白建模上下文的强制门槛，[阶段C验收](archive/research/stages/stage-c/stage-c-acceptance-report-20261106.md)已确认通过，阶段D尚未启动。

A+完成方法选择、数学推导与LaTeX源基线，49项直接检查、30项专项测试、全量181项回归通过；用户验收尚未记录。见[A+验收报告](archive/research/stages/stage-a-plus/acceptance-report.md)和[复核入口](archive/research/stages/stage-a-plus/README.md)。

B+已完成数学包Schema、版本/确认绑定、同源提案与数学变更失效机制；新增46项专项测试、全量227项回归及22项流程演示通过。见[B+验收报告](archive/research/stages/stage-b-plus/acceptance-report.md)及[操作入口](archive/research/stages/stage-b-plus/README.md)。正式v2/revision2未改，A+/B+用户验收尚未记录。

**协作架构（2026-11-08）：三手协作＋独立质检。** 建模手整合拆题/检索/建模，代码手负责受控求解与候选图，论文手负责中文建模稿与汇编；Validator/Reviewer 作为临时只读独立质检。已更新[阶段任务](docs/roadmap.md)和[三手实施约定](docs/three-hand-collaboration.md)，当前为计划/上下文配置，运行节点待 D 实施。

## 结果与设计入口

- [已通过的中文单题正文](output/md/modeling-q1-candidates-v3/单题论文-中文审阅稿.md) · [15 张候选配图讨论清单](output/md/modeling-q1-candidates-v3/配图讨论清单.md) · [流程维护与 ABC+ 分工](docs/paper-workflow-maintenance.md)（新增选图待确认）

- [项目内置算法索引](src/modelcrew/resources/algorithms/index.md)（算法索引与项目补充随包提供；完整参考原文目前在本机归档，授权、完整内置和自动路由待完成）
- [参考 nature-figure 的科研绘图规范](docs/scientific-figure-contract.md)（历史基础规范；当前 Python 与全页 PDF 实现见上方绘图工具，自动检查不替代实际审图）

- [A—F 统一主线：因题选法、数学论证与 LaTeX](docs/algorithm-math-latex-mainline.md)（A+ 基线与B+交接已实现；C+尚未实施）

- [参考算法资料、数学推理与角色分工优化后的 D—F 阶段设计](docs/stage-d-e-refined-roadmap.md)（规划，尚未实现）

- [阶段A验收小结与全部失败分类](archive/research/stages/stage-a/2024-A-problem-1/stage-a-summary.md)
- [阶段B交接设计与首轮任务](docs/stage-b-handoff.md)
- [成功模型代码的Excel结果](archive/research/stages/stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z/output/result1.xlsx)
- [容器使用说明与数值误差](archive/research/stages/stage-a/2024-A-problem-1/docker-execution-result.md)
- [人工参考结果](archive/research/stages/stage-a/2024-A-problem-1/reference-result.md)及[外部论文对照](archive/research/stages/stage-a/2024-A-problem-1/external-reference-check.md)
- [MiMo独立失败记录](archive/research/stages/stage-a/2024-A-problem-1/mimo-baseline-result.md)及[百炼生成过程](archive/research/stages/stage-a/2024-A-problem-1/model-retry-status.md)
- [范围](archive/research/stages/stage-a/2024-A-problem-1/scope.md)、[输入清单](archive/research/stages/stage-a/2024-A-problem-1/input-manifest.json)、[参数](archive/research/stages/stage-a/2024-A-problem-1/parameters.json)和[运行前验收清单](archive/research/stages/stage-a/2024-A-problem-1/acceptance-checklist.md)

## 本地复核

人工参考入口：`python scripts/reference_2024_a_q1.py`，每次创建独立run_id。默认输入路径在原始题目目录，见输入清单；依赖见scripts/requirements-reference.txt。参考计算不计入LLM生成代码成功率。

模型入口：`python scripts/generate_2024_a_q1.py`，从本机.env读取配置，可能产生API费用；仅生成方案与代码，不自动执行。API Key不提交、不写入日志。当前调用还需httpx、pypdf和openpyxl等依赖，完整干净环境安装流程尚待整理。生成后需人工数学与安全审阅，记录与代码原始字节匹配的哈希。

历史参考任务的执行示例（旧路径及 py311 仅用于追溯，不是首发安装命令）；当前新任务采用 Windows x86_64、CPython 3.13 与 Docker Linux py313，见[首发运行环境](docs/runtime-environment.md)。镜像构建只使用执行器配置目录作上下文，避免发送密钥和项目数据：

```powershell
docker build --pull=false -f execution/Dockerfile.py311 -t modelcrew-reference:py311 execution
python scripts/execute_reviewed_2024_a_q1.py stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z --image modelcrew-reference:py311 --keep-container
python scripts/compare_2024_a_q1.py stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z
```

上面的执行目录已运行并有output，不能直接原样再次执行：执行脚本会拒绝覆盖已有output。正式重跑需新建工件目录并重新核对绑定、快照和审阅，不删旧证据。Docker Desktop手动启动保留容器会覆盖同一output，不产生新run_id，且不附带执行脚本的超时监控。

原始题面和论文图像未提交；runs目录被Git忽略，以上本地产物链接不会随仓库自动分发。当前证据在本机可复核，尚不宣称干净环境一键复现。阶段B契约、PostgreSQL迁移、LangGraph双确认流程与CLI已写入，真实数据库恢复测试待验证，MCP与检索后置。

## 阶段 B 开发入口

[契约字段与合法/非法样例](src/modelcrew/resources/contracts/README.md) · [CLI、数据库及恢复设计](archive/research/stages/stage-b/README.md) · [实现与验证状态](archive/research/stages/stage-b/progress.json)。目前7项契约和11项数据库集成测试通过，两次真实数据库重启恢复通过；实际任务dragon-q1的v1方案及结果revision 1均已由用户明确确认，状态COMPLETED。请审阅[契约摘要](archive/research/stages/stage-b/contract-review.md)。

阶段B验证证据见[集成验证记录](archive/research/stages/stage-b/integration-verification.md)。当前执行节点仅使用A历史固定工件联调，不代表真实求解已迁入状态图。

[实际用户双确认联调记录](archive/research/stages/stage-b/user-confirmed-demo.md)：已完成v1；真实用户指导创建v2的演示尚未进行。

2026-11-04：用户指导已使模型生成并保存dragon-q1契约v2，新版本待确认，v1历史完整保留。详见[v2审阅](archive/research/stages/stage-b/v2-review.md)。

当前入口：[v2真实求解报告及Excel](archive/research/stages/stage-b/v2-solver-result.md)，26项测试及v2数值检查通过，结果revision 2已由用户确认。

[v2实际结果确认记录](archive/research/stages/stage-b/v2-confirmation.md)：任务已完成；阶段B整体验收仍需按原定条件核对。

**阶段B整体验收（2026-11-04）：暂未完整收尾。** 26项回归通过，但输入数据结构契约、可替换执行接口、解释修改后的重新审核尚需补齐。详见[验收报告](archive/research/stages/stage-b/acceptance-audit.md)。


阶段E证据协议更新：W2登记引用协议2.2已通过真实54页资格验证，模型FAIL原样保留，未创建正式W2回执或重置复核次数。见[协议修复记录](archive/research/stages/stage-e/implementation/20261110-w2-protocol-v2/证据协议修复记录.md)。

开发安装入口：`python -m pip install --no-build-isolation --no-deps -e .`（复用已具备的开发依赖），随后使用 `python -m modelcrew --help`。F2已启动Private安装包构建与独立安装验证，详见[安装包说明](docs/package-installation.md)；统一用户工作区、完整知识与端到端仍按F3/F5/F6/F4/H2继续完成，尚非完整新用户Quickstart。
