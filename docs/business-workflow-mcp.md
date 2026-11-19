# 完整工作流 MCP

2026-11-15，G2 提供标准 stdio MCP 入口，复用 G1 业务契约 1.0.0 和既有 Workflow、PostgreSQL、F6 内部路由。当前发现并适配 40 个模型通道工具，覆盖项目/任务、建模、代码手/论文手推进、状态/待办、版本修订/恢复、引用、汇编导出/渲染/W2 和产物读取。其余 10 项明确不向模型开放。本轮工程验证不代表真实 DeepSeek Harness 联调、真实新业务三手质量验收或用户批准；G3—G5/H 继续分别实施。

## 启动与安装边界

安装项目已声明的 workflow 依赖组后，使用同一个用户工作区和数据库配置：

```powershell
python -m modelcrew.workflow_mcp describe
python -m modelcrew.workflow_mcp migrate
python -m modelcrew.workflow_mcp
```

`describe` 无需打开数据库，返回实际能力和不可用项；启动 MCP 不隐式迁移数据库。`migrate` 经现有 `Workflow.setup()` 追加 013 迁移，不重建旧表或修改 001—012。安装包包含 SQL，资源通过包定位读取；PostgreSQL 继续是事实来源，没有新增 SQLite、宿主本地 JSON 工作流库或另一套三手编排。

宿主 stdio 配置的启动命令为实际 Python 解释器，args 为 `['-m','modelcrew.workflow_mcp']`；`MODELCREW_WORKSPACE` 与现有数据库/模型配置由可信宿主环境设置，工具参数不能指定命令、镜像、执行根、数据库连接或替代模型。不要把密钥写进聊天或模型参数。具体 DSH 注册界面、交互设计和真实宿主配置在 G4 完成，本文件不冒充其验收记录。

本批支持基线为项目固定的 `mcp==1.30.0`、stdio、协议 `2025-11-25`。真实标准 Python MCP 客户端执行 initialize/tools/list/tools/call，工具返回 `structuredContent`、兼容文本 content 和匹配的 isError；未知名称不回显调用数据。SDK 按其支持集协商协议，不推断所有未来协议或宿主兼容。协议依据为已安装 SDK 实现及官方工具/stdio 规范：`https://modelcontextprotocol.io/specification/2025-11-25/server/tools`、`https://modelcontextprotocol.io/specification/2025-11-25/basic/transports`。

stdio stdout 只给协议写入器。入口先独立复制真正 stdout 句柄，再把 Python print 和 fd 1 原生输出重定向 stderr，日志也写 stderr；错误只输出稳定代码和脱敏说明，内部异常仅记录类型，不发送连接串或原始异常详情。进程关闭或客户端取消不触发自动重发。

## G1 与实际运行能力

[G1 冻结文件](business-tool-contract.md)及其回执保持原字节。冻结清单中的 adapter_status 是 G1 时点记录，不改写为“已接通”；实际可用性由 `capabilities_read` 和 tools/list 给出。20 个读操作和20 个修改操作都采用原包络，不另造 actor 身份或默认 request_id。

| 范围 | 本批处理 |
|---|---|
| 已有核心映射 | 以显式白名单调用已有 Workflow 方法，工具本身不重写三手或审批逻辑 |
| pending_list | 投影当前模型、结果、单题正文/选图、汇编正文/选图；各项独立绑定版本/哈希 |
| operation_status | 查询原归属、操作和请求键；带原请求回执及当前核心状态；查询成功不代表原操作成功 |
| artifacts_list / assembly_artifacts_list | 从执行/档案、建模冻结 Snapshot、三手 sealed 及汇编 sealed 登记建立归属索引 |
| artifact_read | 精确 owner + artifact_id + SHA-256 的有界 base64 字节读取 |
| 可信通道 | task_decide、hand_decide、assembly_decide、final_decide、question_import、hand_repair、assembly_bind_reviews、assembly_retry_w2_delivery、manuscript_register_revision 均不注册为模型工具 |
| figures_select | 通用任意选图修订服务尚未实现，稳定拒绝；现有 formal 图目录及可信本地审阅流程继续保留 |

仅工具函数声明或导入成功不代表业务请求成功。响应还需通过 G1 Schema、当前数据库绑定、原有输入/数学/独立审查和用户关卡；缺失依赖、当前版本过期或证据变化必须停止。生产 task_create 只接受 pending-code 与空 executor_config；历史夹具后端通过 MCP 只读，不提供换后端途径。模型/结果批准继续使用现有可信本地入口；方案批准明确延后执行，再启动代码手。G2 没有替用户点击批准，也没有实现 G3 的真实宿主用户事件转交。

## 持久化、并发与恢复

013 迁移新增 `mc_business_operations`、不可变 `mc_business_operation_events` 和不可变 `mc_business_artifacts`。请求账本使用“归属范围 + operation + request_id”，保存 G1 规范化完整请求哈希、原请求、核心资源键和结构化响应。兼容核心更宽的历史请求域：方案 action、引用检索/讨论及数学发布共享 task 级 mc_requests 键；建模、三手、汇编有各自冲突检查。跨操作同键不得误命中旧回执。

每次修改取得业务资源锁和原有核心锁，按既有汇编项目→有序任务的顺序进入核心。先提交 claimed，再提交 dispatched，最后调用核心；成功响应和不可变事件持久化后才发送。相同请求在进程重启或并发连接下读取已存响应，replayed=true，不重新调用核心。相同键改变参数、版本或事件引用会返回 idempotency_conflict。

回执 succeeded 表示适配调用已有可核验结果，不表示求解、独立质检、正式成品或用户确认通过；原生 FAIL/BLOCKED、空检索和检索失败仍分别保留。result_sha256 对 receipt 置 null 后的完整响应做 G1 canonical JSON SHA-256，避免哈希自引用。

修改丢失响应时保留 claimed/dispatched/outcome_unknown，不清空派发标记。相同资源的其他新请求键也被阻断，不能换键绕过。operation_status 只做对账与只读状态查询：

- 已有项目自然键、初始任务契约/后端、mc_requests、已建立三手运行等能明确关联原请求时，可从核心事实补齐账本回执，不重发命令。
- 手阶段在 claim 后出现不可变核心事件，且当前阶段/尝试与该事件一致时，可确认原有单步已经推进。阶段名、checkpoint 或磁盘上多了文件本身均不足以成立；PROVIDER_UNKNOWN 不据此放行。
- 已派发执行的当前阶段只能请求 code_execution_status；不会请求 code_execute、推进另一手阶段或重新求解。已知后端状态允许记录可核验当前响应，下一次显式 advance 仍由核心使用同一任务包的 status-only 分支恢复。
- 无法证明完成的复合操作继续保持未决，不伪造成功；原生可信本地恢复与后续对账仍可能必要。G5 继续扩展具体断点的恢复证据，本批不承诺所有进程杀点都能无人干预继续。

`operation_status.status=ok` 只表示账本查询成功，必须继续读取 receipt.state、data.original_status 和 data.current。当前产物损坏或旧 run 已过期时，仍尽量返回原账本及“当前状态不可用”，不会因读取失败把原修改当成未执行。

## 输入和产物

模型不能借冻结的原生 body 字段读取任意本机文件。可信本地操作者先为明确 project/task/version 登记输入，命令不作为 MCP 工具开放：

```powershell
python -m modelcrew.workflow_mcp register-input --project demo --task q1 --version 1 --file 'D:\inputs\statement.json' --role input
```

登记复用既有内容寻址快照；返回 artifact_id、归属和哈希，不返回源文件绝对路径。题目文本/扫描件的理解与题目导入不是该工程命令自动完成的功能。题目导入仍经已有可信本地 question_intake，宿主的通用上传/事件转交另行接入。

候选建模契约 `inputs[].path` 可写 `artifact:<artifact_id>`；适配器在创建未确认契约之前解析到同任务/版本的已登记快照，并核对提交哈希。批准绑定的始终是核心保存的完整契约哈希。sources/result_evidence/figure_catalog 同样必须可解析为已有、同归属输入；未登记路径、跨项目/任务/版本输入拒绝。恢复旧版复用已登记历史输入，创建新待确认版本，逐项保留历史批准。正文/入文图修改仍遵守原有影响范围审阅，本批没有提供任意正文导入或替用户选图。

产物来自数据库已登记的执行、档案、冻结 Snapshot 和 sealed 身份，不扫描任意目录当作产物。artifact_id 对 owner、登记路径及 SHA-256 绑定；相同字节在不同归属下不自动授权。owner 精确包含 project/task/version 与可选 run，或 project/build。

读取前拒绝越出工作区的路径、symlink/junction；打开后再次校验实际文件句柄最终路径。Windows 使用 GetFinalPathNameByHandleW，Linux 使用 /proc/self/fd，无法验证的其他平台拒绝。对同一打开句柄流式计算完整 SHA-256、核对前后 stat 和登记大小，再返回请求范围；不先验哈希再另开可变路径。单块最多262144字节，offset 和 EOF 按字节定义，UTF-8、PDF、图片和 Word 都以 base64 返回，不冒充解析或视觉审查通过。

## 工程验证与后续

可复现检查入口：

```powershell
python -m scripts.verify_business_mcp --output tmp/business-mcp-validation-new
```

该工程脚本新建独立合成 PostgreSQL 数据库，运行契约/协议/包资源/路由等相关测试，保存 JUnit、日志和账本聚合证据；默认仅清理自己创建的测试库，可显式 --keep-database 保留。测试不运行付费模型、不创建用户批准或真正独立业务审查结论。真实子进程提交后退出、客户端重连和 stdout 隔离通过标准 MCP 客户端验证；单题/汇编待办及部分故障点使用明确合成状态，只证明投影和适配机制。

本批实际测试、构建、源码外安装和冻结文件身份见 [G2 工程回执](release/business-workflow-mcp-20261115.json)。真实 DSH 入口、可信宿主用户事件、安全交互与宿主端到端分别在 G3/G4/G5/H 继续验收。F5 暂缓、全新 Windows 例外、公开发布门禁及历史批准不因本批实现而改变。

本轮最终回归为 **130 passed、1 skipped**，其中 G2 专项25项全部通过；跳过项仍是既有官方 Word 评论 XML 校验缺少 documents 依赖，未改成通过。旧 JS 桥5项通过。原 wheel、sdist 与 sdist 重建 wheel 均审计通过，两个 wheel 在源码目录之外分别安装；标准 MCP 客户端共完成10次真实调用，验证40项发现、项目创建重放、重启对账和登记产物读取，232项资源逐项核验。安装探针显式复用已准备基础依赖和 pywin32 路径/bootstrap，没有安装新外部技能，不等于全新 Windows 或 DSH 实测。初次隔离探针的依赖搜索路径、嵌套启动脚本引号与 argv 问题分别留有失败日志，修正仅限工程探针；产品代码没有静默回退。127份原有证据和 G1 冻结材料、G1 文档/校验器/测试均核验未变。

## 模型修订缺少数学包的本地恢复（2026-11-16）

已有数学基线的 `task_revise` 必须同时提交 `math_package`，契约和数学包一起写入新版本。适配器现在在创建派发记录之前检查缺包和数学包结构错误，返回 `invalid_request`；这种已知输入错误不再留下 `outcome_unknown` 围栏。尚无数学基线的旧工程任务仍可按原契约修订；解释修订不强制新数学包。冻结的 1.0.0 线协议、旧请求字节和批准记录不改写。

对于旧适配器已经留下的“缺少数学包”记录，可信本机操作者可使用受限恢复入口（不向模型开放为 MCP 工具）：

```powershell
python -m modelcrew.business_recovery --task TASK_ID --request-id ORIGINAL_REQUEST_ID
python -m modelcrew.business_recovery --task TASK_ID --request-id ORIGINAL_REQUEST_ID --apply
```

默认只读检查。恢复同时持有业务锁和原生任务锁，在同一数据库事务内核对原请求哈希、任务归属、版本和待审状态，要求原数学包早于派发记录、原请求确实缺少数学包，且不存在核心回执或任何后续版本契约/数学包。只有这些证据齐备，才保存原请求的 `failed / invalid_request` 回执并追加不可变事件。重复恢复复用该回执；原键仍只能回放失败，不能改参数重用。修正后的请求使用新键提交完整契约与数学包，仍需新版独立 M1 和用户确认。

没有回执本身不是失败证明；提供过数学包、源数学包晚于派发、已有核心回执、后续版本或任务已推进时均拒绝本入口，不据此放开其他未知操作。未使用 DSH 会话生成的直接 SQL 修复脚本。源码更新须由新的 MCP 后端进程加载；已运行进程需重新连接或完整重启 DSH。


## 大对象修订的文件传输扩展（2026-11-17）

`task_revise`可在`arguments.revision_files`提供`contract_path`、`contract_sha256`、`math_package_path`、`math_package_sha256`，四项必须齐全；`body`仍含actor、request_id、version、kind=revise_model、reason，但不能再混入contract或math_package内联对象。旧内联请求和冻结Action/G1资源字节不变。新增schema由运行时兼容扩展并通过MCP发现，不是新审批工具。

来源限当前工作区内常规文件，沿用打开句柄后的路径、SHA256与读取稳定性校验，每份最多2MiB。UTF-8 JSON必须为对象，重复键、非有限常量、非法编码和越界路径拒绝；所有文件、输入登记、契约及数学包检查发生在持久派发之前。大对象解析结果只在宿主内传给原Workflow.action，不要求模型输出整份JSON，也不执行请求文件中的脚本。外部项目工作文件可由可信宿主按字节复制到工作区，但不能靠路径参数扩大读取范围。

请求摘要绑定来源路径和哈希。相同键/内容重放原回执，不重新读取已变更工作文件；完成核心写入后若响应丢失，operation_status从原mc_requests回执对账，不重新提交。文件式提交不批准新模型，不复用旧版M1；新版本仍需相应审查和用户确认。新增参数需重连MCP后发现。


## 建模规划结构失败与围栏对账（2026-11-17）

规划输出的 `facts` 仅接受 JSON 布尔值；未知事实省略对应键，不能填 `unknown` 字符串或把未知转成 `false`。`auto_correct=true` 时，规划结构校验失败最多纠正一次，完整保留各次原始调用、局部校验错误与修正反馈；关闭时不纠正。此纠正仅发生在已完整返回的规划输出上，不用于重发传输状态未知的调用，也不放宽模型、契约或独立 M1 门禁。

若核心已持久记录明确的规划校验失败，适配器在派发异常时可直接生成 `failed / workflow_conflict` 回执；旧 `outcome_unknown` 记录可由已有 `operation_status` 只读核心事实进行对账，无需新增人工授权工具。证明必须同时匹配业务请求摘要、任务、原请求键、版本、作者、指导内容和核心请求摘要；核心状态须为 `failed`，最新不可变核心事件与投影负载一致，已有调用及落盘调用记录均限成功返回的 planning，且不存在方案尝试、模型快照或 M1 回执。证据不足、调用状态未知或已进入方案编写时继续保留围栏，不套用本恢复。

恢复追加原业务操作的失败事件并保存可重放回执，不删除历史、不重写模型运行、不重置次数、不代用户批准。原请求键以后只回放失败；修正后使用新请求键继续。新源码须由新进程加载；当前已运行的 DSH MCP 后端需要重新连接后才能使用规划纠正逻辑。真实恢复证据和离线/隔离数据库测试记录位于 `runs/maintenance/m1-planning-recovery-20261117/`。


### W2 已完成无效回答的对账（2026-11-19）

`operation_status(assembly_review_w2)` 现可依据相同请求的不可变 `W2_INVALID_RESPONSE` 事件结清业务账本。必须核对归一化请求、请求/范围摘要、终态事件、原回答/原始供应商响应/元数据/证据包的封存哈希，且确认供应商完整返回、原回答一致。仅结清为明确失败，保留原审查状态与校验错误，不重发、不改写原回答、不占复核额度；证据缺失、不符或真正未知时继续围栏。业务派发异常分支也使用同一核验逻辑，不能把所有异常统称为未知。

符号说明表的范围标签与章节标题分别呈现：`问题 1：长题名` 在范围单元格显示为 `问题 1`，原章节标题和完整题名保留。修补会改变组稿实现身份，后续修订使用新 build 并重新取得受影响正文确认；不修改旧 build 的文件、哈希或批准。


### W2 v3 输出与外部复跑证据（2026-11-19）

新冻结 W2 使用 `w2_evidence_refs_v3`：审查者只填写五项检查、逐页判定和问题，不再重复填写总状态。核心按原有 FAIL > BLOCKED > PASS 规则聚合；失败页与 layout、问题与分项的一致性仍严格校验，不隐藏任何真实缺陷。

审查者的全部文字原样保存于 `answer.json` 与封存的 `review-details.json`。超过原生300字符回执字段的文字不裁剪，回执保存短的详情位置与规范JSON摘要，详细论据仍可完整追溯。该编码只适用于新 v3 回答；v2 的矛盾/超长旧回答仍为 INVALID_RESPONSE，不重新解释，也不重置任何复核额度。

新 W2 证据包按每个章节的 task/version/contract/execution/result revision 精确定位已附着代码运行，校验封存的两次执行包、代码/输入/授权、全部实际产物哈希及已接受独立 P2 的票据和快照。外部逐字节复跑事实与生成器当时的 `PENDING_RUNTIME` 自报字段分开提供；缺失时明确 NOT_AVAILABLE，不伪造 PASS，不重算数值。哈希一致不自动证明实验有效性，用户接受偏差也不把原阈值 FAIL 改成 PASS。

更换 W2 协议不恢复旧复核额度。真正修改正文时创建新 build 并按影响重新确认；只做协议工程探针不得声称正式 W2 已通过。
