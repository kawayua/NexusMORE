# 通用代码手与论文手运行接入

**当前使用入口（2026-11-19）**：[使用指南](user-guide.md)与[兼容范围](compatibility.md)汇总当前操作；G已按既有本地DSH实测范围验收，干净设备按用户决定在开源后补测。本页下方带日期的实施/验收段落保留历史时点含义，正文与配图的当前交互以合并审阅规则为准。


**当前进度（2026-11-15）**：F6.1—F6.6 已按首发范围完成技术验收与收口。当前代码重新构建 wheel/sdist，源码目录外的安装、七类检索、三手路由及真实导出验证通过；既有 M1/P1/P2/W1/W2 和用户成品确认均已复核。当前以[收口报告](internal-routing-closure.md)为准，下列带日期段落保留当时状态。G 的 DeepSeek Harness 接入尚未开始，F5 暂缓及全新 Windows 验证例外继续保留。


2026-11-15 检索入口收口：新业务默认使用包内七类算法及几何补充，建模手、协作函数和MCP algorithm_search已统一。默认无需旧catalog、BGE权重或Qdrant算法集合；查询方式为ID/名称/类别字面匹配，尚未重建113算法向量语义索引。显式指定旧配置仍严格核验旧来源，不静默切换。见[入口收口说明](algorithm-entrypoint-closure.md)。

2026-11-14 F6.6 定点修复完成：JSON数组映射、对偶浮点判定、基准最小范围和失败退出均已修复；受控人工代码导入已接通Python/HTTP/CLI。原任务新增一次真实Docker最小执行及一次独立P1，五项全部PASS，现停在GENERATE_FULL；原三次自动返工预算、旧P1 FAIL和模型批准均保留。全量/P2、结果确认、写作及导出仍未完成。见[修复验收](coding-repair-validation.md)。

2026-11-14 修复前历史状态：真实用户已批准未变的版本2模型，新M1通过，代码手完成真实最小执行；独立P1为FAIL，自动返工达到3次后停在NEEDS_HUMAN，尚未全量/P2/写作。当前需定点修复JSON输入映射、对偶浮点判定和最小阶段范围，并补齐耗尽后的受控修复接续。见[当前证据与边界](three-hand-live-validation.md)。

2026-11-14 F6.6 实时联调：新合成任务已实际调用配置模型并完成独立 M1 六项 PASS；建模手四项范围确认待用户答复，运行保持 blocked、无用户批准和求解。已核验引用/格式失败阻断、同请求不重发及重连恢复；代码手/P1/P2、论文手/W1/W2及后续用户确认仍待推进。见[本次范围与证据](three-hand-live-validation.md)。

2026-11-14 F6 首批：已接入新三手运行的程序资料路由与冻结、PDF/XLSX/DOCX 受控只读工具及幂等恢复；当前 227 项包资源。新建模直接读取包内七类算法，旧目录/冻结回执保留。独立安装下三手上下文与工具探针已验证；真实模型三手和 Harness 端到端尚未整体验收，见[路由范围](resource-routing.md)。

实现入口为 `modelcrew.hand_runtime`、`Workflow.start_hand/advance_hand/hand_status/hand_decision/recheck_hand/repair_hand`；HTTP与CLI复用同一实现。程序管理状态和路由，不增加常驻业务Agent。结构化阶段使用JSON，Writer正文阶段返回Markdown原文；生成的数值代码不在宿主导入或执行。

数据库迁移010保存运行快照和不可变状态事件。部署先执行 `python -m modelcrew init-db`。不替换历史D3/D5脚本、已通过论文或模型。

## HTTP与CLI

| 操作 | HTTP |
|---|---|
| 创建代码手/论文手运行 | `POST /tasks/{task}/hands/{coding|writing}/runs` |
| 查看状态 | `GET /tasks/{task}/hand-runs/{run_id}` |
| 执行一个持久化步骤/恢复 | `POST /tasks/{task}/hand-runs/{run_id}/advance` |
| 一次有理由的独立只读复核 | `POST /tasks/{task}/hand-runs/{run_id}/recheck`，正文含rationale |
| 耗尽后显式导入最小修复代码 | `POST /tasks/{task}/hand-runs/{run_id}/repair` |
| 用户正文/选图决定 | `POST /tasks/{task}/hand-runs/{run_id}/decisions` |

CLI：

```powershell
python -m scripts.run_hand start TASK --hand coding --request request.json
python -m scripts.run_hand advance TASK --run-id RUN_UUID
python -m scripts.run_hand status TASK --run-id RUN_UUID
python -m scripts.run_hand recheck TASK --run-id RUN_UUID --request recheck.json
python -m scripts.run_hand repair TASK --run-id RUN_UUID --request repair.json
python -m scripts.run_hand decision TASK --run-id RUN_UUID --request decision.json
```

创建请求至少包括 `version`、`actor`、`request_id`、`guidance`。同一task/request_id与同一请求幂等；复用键但改变参数拒绝。每次advance只执行当前阶段的一步，外部调用已成功且状态落盘后，不因重复恢复重新生成或重新派发。同一任务以数据库锁串行推进；不同任务独立。

## 代码手

新任务选择`pending-code`执行后端；模型确认仍走既有用户action，设置`defer_execution=true`（CLI为`--defer-execution`），避免确认后派发未登记代码。API与主CLI已允许这两个参数。模型批准/M1、输入哈希和契约数学绑定在创建及每步恢复时重验。

运行顺序：

`GENERATE_MINIMAL → EXECUTE_MINIMAL → REVIEW_P1 → GENERATE_FULL → EXECUTE_FULL → REPRODUCE_FULL → REVIEW_P2 → READY_TO_ATTACH → ATTACHED`

`minimal_scope`明确最小切片；P1不冒充全量检查。`full_scope`始终受已确认契约约束，不能弱化验收要求。代码手走项目配置供应商`JsonModel`生成Python，AST仅作语法预检，随后注册为不可变Docker任务，经既有MCP派发。输入在容器`MODELCREW_INPUT_DIR/input-N`，输出在`MODELCREW_OUTPUT_DIR`。

必须生成可读`result.json`供独立语义审查；全量还必须交付契约声明的文件及绑定当前结果的`figure-catalog.json`。候选图及格式遵守现有政策；现有资源上限不放宽。当前默认最多32个文件以容纳九图三格式及结果文件，仍不超过执行器支持的上限。完整复跑使用第二个真实注册任务，比较全部输出相对路径及字节哈希；生成器须固定种子、抑制PDF/SVG动态时间元数据。

P1/P2使用新的只读无作者聊天历史请求。D1票据检查独立身份、作者贡献链、版本、完整检查项、原始状态、JSON Pointer和问题路由。程序不能截断、重写或猜测审查意见以获得PASS。格式不合法也阻断。P2按真实代码、JSON数据、图目录和复跑证据检查图意；文本API不冒称实际目视PNG或最终版式，最终渲染/目视仍属E/W2。

通过P2后登记到`mc_executions`和`mc_results`，状态为等待结果确认。用户结果action会再次验证本运行及P2，Agent不批准结果。现有已确认结果不被此入口覆盖。

## 论文手

只有当前模型及结果均已确认且P2有效时才能启动。支持本次通用P2结果及已有受控D4/P2结果；未知/仅执行成功的结果不能进入写作。创建请求还需给出绑定当前结果的`figure_catalog`，可给出实际读取的文献`sources`和当前执行中的`result_evidence`路径。

每次实际读取`writing_context()`，保存规范、来源与哈希。引用文件必须在项目内，完整数值产物仍固定哈希；发送模型的JSON数值证据过大时要求显式选择`result_evidence`，不静默截断或伪造摘要。原产物与图复制到新的运行目录；新稿不继承旧稿正文批准，也不撤销旧稿批准。

运行顺序：

`PLAN → REVIEW_W1 → DRAFT → WAITING_MANUSCRIPT_AND_FIGURES → READY_FOR_E_EXPORT`

Writer-plan由配置供应商生成；严格Schema包括论断及真实JSON证据指针、章节、已读引用路径和每幅正式图的论断/章节映射。W1在长正文前读取原契约、数学材料、执行、结果、论断、引用和图目录。通过后才调用供应商Writer展开中文Markdown，再运行既有体裁、中文、图片和引用机械检查。

2026-11-10正文传输更新：新DRAFT操作声明`raw_markdown_v1`，供应商直接返回Markdown原文，适配层只包装为内部`markdown`字段，不经过正文JSON字符串解码，不修补LaTeX、不剥代码围栏或重写内容。HTTP原响应与协议元数据保存；缓存恢复使用同一解码规则，截断/空回复拒收。大纲、代码与所有独立审查回执仍严格JSON。正文请求同时从冻结政策与图目录派生明确的章节标题、图片嵌入和图注格式；前次正文机械检查发现独立持久化，不会被中间大纲错误覆盖。格式要求不预先认定科学结论，也不自动改写作者正文。旧操作请求哈希不修改，失败运行保留，新联调使用新运行目录。

供应商作者正文允许`markdown`或`manuscript_markdown`两种明确字段；同时返回时必须字节一致。原始回复保留，正文文本不因字段适配改写。此兼容层不适用于独立审查回执，不会修正Reviewer的状态、问题或证据。

正文与选图通过两个独立用户决定保存；请求必须含`actor=user`、明确原话/理由、决定、request_id和当前文件`artifact_sha256`。`kind=manuscript`绑定Markdown，`kind=figures`绑定当前目录及正式图内容。只确认一项不能导出。替换图/改正文需新运行/审阅版本，已交付文件不覆盖；拒绝后保留原记录并允许新运行。节点不生成正式PDF/Word，`READY_FOR_E_EXPORT`只说明可交给后续E导出。

## 恢复、返工和边界

- 供应商调用在发出前保存claim；响应与元数据已完整落盘但业务未提交时，可以恢复同一响应。无法证明返回内容的传输中断只恢复缓存，不自动重发；输入或缓存字节变化拒绝。
- Docker派发claim在调用前提交；未知执行只调用`code_execution_status`。每次核对已注册任务、授权、输入、代码及限额。基础设施/授权故障不消耗代码重试预算，不以重复求解代替恢复。
- 实现/写作问题最多初次加三次返工，使用新attempt、新作者身份和新快照，原代码、回复与失败保留；预算耗尽进入`NEEDS_HUMAN`。
- 模型问题进入`NEEDS_MODEL_REVISION`，交建模手并要求新版本/M1/用户确认；同版本新请求不能绕过此阻断。涉及已确认结果的实现或解释问题分别暂停到`NEEDS_CODE_REVISION`/`NEEDS_RESULT_INTERPRETATION`，交代码手或既有解释修订入口，保留执行/审批历史，不自动覆盖已批准数值。
- 已拒收/失败的审查最多一次明确有理由的独立只读复核。按当前轮次最后被拒的实际关口定位，不能因旧全量包误选P2，也不能复核已PASS关口以扩充作者预算。原回应和回执不变；复核使用新身份与新票据，不提供作者聊天。不因复核申请预设PASS；复核仍FAIL时按实际领域返工或人工处理。
- 来源、契约、执行或结果revision变化会使旧运行失效。既有审批属于具体字节与版本，运行状态不能替用户授予批准。

目前覆盖受限Python任务的最小/全量/复跑，以及已有图目录与JSON证据的写作。任意长任务的自动分片、其他语言/任意文件语义解码、多题并行调度及通用正式导出不在本次完成范围。供应商能力可能导致格式失败、证据错误或语义FAIL；应保留并阻断，不能为工程演示“刷通过”。本机HTTP的actor仍为受信任本地审计标签，不是新增身份认证系统。

具体实测、失败历史和D阶段复验状态见`stage-d/runtime-integration/20261110-v1/implementation-report.md`；不得把实现本入口直接记为用户通过整个D阶段。

正文协议修复及新联调记录见 `stage-d/runtime-integration/writer-fix-20261110-v1/repair-report.md`；上一批次报告保留当时真实失败状态。

## E1 汇编交接（2026-11-10）

`READY_FOR_E_EXPORT` 现可交给通用 `Workflow.start_assembly/assembly_status`，复用真实上游批准与独立 W1 门禁，冻结多题输入并在查询时报告过期及影响范围。入口和未实现边界见 [通用汇编运行](assembly-runtime.md)。本入口不重写论文、不生成新正式导出，也不把既有案例 W2 自动授予新冻结运行。

### 解释 revision 的受控继承补充

对于同 execution 的解释修订，Writer 不再要求把 `interpretation_review` 伪装成完整数值 P2。新增 `result_lineage` 校验新结果用户确认、完整结构化主张的独立 P2 解释审查和原数值 P2 快照/冻结包，再沿用原 M1 的只读策略重验当前数学绑定。实际调用独立 W1 后才能进入正文/选图关卡。任何原数值文件、契约、执行、原 P2 或新独立审查输入发生变化，均拒绝继承。此入口是 Python 工作流内的显式本地接纳，不新增任意外部审查导入 HTTP API。

F0路径更新（2026-11-11）：新建三手运行写入 `runs/hands/<uuid>`，建模运行写入 `runs/modeling/<uuid>`；历史运行按集中兼容表读取原目录，拒绝新旧位置冲突。详见[迁移与恢复](repository-migration.md)。


## F6.6 未接纳M1回执的受控复核补充（2026-11-14）

现有recheck_modeling除已接纳FAIL回执外，也允许对一个已完整收到但Schema/证据Pointer不合法、未获接纳的M1响应申请一次明确有理由的独立只读复核。须有完整stop响应、HTTP200、响应哈希、已冻结快照及未变的契约/数学/输入；没有唯一完整响应的未知传输不得重发，合法缓存应恢复原接纳而非重新分类。原响应不裁剪、不删字段、不修Pointer，新的独立请求只给原验证错误与响应哈希，原始响应仍存档。

从不可变proposal重新读取questions，避免M1解码早于状态保存时丢失待答问题；有问题仍blocked。复核格式再次不合格记NOT_ADMITTED与needs_human，保持一次预算；与传输未知分别处理，重复查询不新调用供应商。证据导航按广度保留顶层路径，并按artifact_id/selector配对给出Schema提示；JSON模式不宣称服务器执行了Schema校验。此改动不授予用户批准，也不提供代码手预算耗尽后的人工代码导入/恢复能力。

## 最小代码人工修复接续（2026-11-14）

`Workflow.repair_hand` 只接受已耗尽三次自动返工、停在 `NEEDS_HUMAN` 的代码手最小实现故障；模型、输入、冻结规范及历史文件哈希仍须全部有效。模型问题、未知供应商结果、审查格式错误、已有全量作业或已接纳结果不能借此恢复。此入口为受信任本地操作者提交，不向模型开放，不新增身份认证。

请求须含 `version`、`actor`、`request_id`、真实修复请求原话 `statement`、`rationale`、工作区POSIX相对路径 `code_path`、`code_sha256` 和 `previous_code_sha256`。只静态解析语法，将提交代码和修复来源以新不可变文件保存，登记为 `operator_supplied_code`，不冒充供应商生成。新的 `attempt` 用于区分作业、作者身份与审查快照，`retries` 保持3，原失败及操作记录不变。相同请求幂等，参数冲突拒绝。

接续只到 `EXECUTE_MINIMAL`，沿原授权、输入、限额实际在Docker执行，并使用新独立上下文审P1。修复仍失败则重新停在 `NEEDS_HUMAN`，不自动增加返工；再次人工修复须有新的显式请求。P1通过只进入 `GENERATE_FULL`，不登记完整结果，不产生用户批准。当前实测及工程负例边界见[修复验收](coding-repair-validation.md)。


## 全量代码定点修复接续（2026-11-15）

原 `repair_hand` 请求增加可选 `stage`，默认 `minimal`，既有请求指纹与幂等记录保持兼容。显式 `stage="full"` 只接纳预算耗尽后的全量实现故障；须保留有效独立P1、原最小源码、当前模型批准和全部冻结哈希，已有业务结果、未知供应商或审查格式故障均不可借此恢复。全量修复登记新操作者作者/不可变源码/来源，保留旧作业和失败记录，`retries` 不重置；仅清除当前全量包及P2准入指针，原P1继续绑定原最小产物。新代码必须重新真实执行全量、逐文件字节复跑、全部候选PDF全页机械检查和新独立P2，之后才可登记待用户确认结果。该接续不生成用户批准，也不把操作者修复标为供应商代码生成。


## 非有限数值输出与历史误分类恢复（2026-11-16）

代码生成和操作者代码导入同时执行静态 AST 解析和 Python compile 检查；不导入、不执行生成代码。这样可提前发现 `global` 声明顺序等 AST 解析未覆盖的编译错误。

执行产物中的 JSON 若含 NaN、Infinity 或数值溢出成无穷大，按代码实现失败返工，在写入执行证据包之前拒绝；预算耗尽后仍停在 NEEDS_HUMAN，目标为 coding。进程正常退出不代表数值或 P1 通过。

此前这类输出可能在保存证据包时触发 ValueError，被误记为 infrastructure/recovery。受信任本地操作者可调用 `modelcrew.hand_repair.recover_nonfinite_output(w, task, run_id, version=..., actor=..., request_id=..., statement=...)`：只接纳已耗尽预算、尚无全量作业的最小代码运行，并核对当前冻结模型、全部封存文件、已派发作业、完成且清理成功的执行回执、源码及产物哈希；必须实际证明原 JSON 含非有限数值。生成新的恢复证据，仅将故障归回 implementation/coding，保持 NEEDS_HUMAN、attempt 和 retries 不变，随后才能通过既有 repair_hand 导入实际修正代码。此接口不向模型开放；不重发作业、不修改旧产物、不自动生成修复代码、不授予任何通过或用户批准。不满足证据条件的其他基础设施故障拒绝恢复。

执行镜像由受信任宿主的 `MODELCREW_EXECUTION_IMAGE` 或 `configs/local/settings.json` 中 execution.image 设置；环境变量优先。MCP 客户端每次派发启动执行子进程时读取配置。旧作业仍保留已声明的不可变 image_id，新镜像仅用于新作业。绘图所需库应在 Docker 内实际探测并验证输出格式；不得仅凭镜像名称宣称依赖齐备。


## 已用复核额度的预检与未接纳 P1 接续（2026-11-16）

`hand_recheck` 的适配层和核心复用同一只读资格检查，在持久派发 claim 前核对运行状态、当前被拒关口、完成的原回应和全运行一次的复核额度。确定不具备资格时直接返回 workflow_conflict，不再生成 outcome_unknown 围栏。不能将所有派发后的 ValueError 一概视为明确拒绝；其他可能已有副作用的未知操作仍须保留围栏。

历史第二次复核围栏可经受信任本地 `python -m modelcrew.business_recovery --kind used-hand-recheck --task TASK --request-id REQUEST` 只读核对，证据满足后加 `--apply`。要求原业务请求哈希正确、先前成功复核回执早于该 claim，且 claim 前不可变运行事件已经 recheck_used=true、与当前核心状态完全一致；冻结模型和所有封存文件仍通过 guard。只把已证明未派发的新复核记为失败，保留原请求与状态事件。当前状态已变化、证据缺失或真正未知的请求拒绝恢复。

一次复核已用、P1 完整回应又因缺少 FAIL/BLOCKED 对应 issues 或无效证据指针而未接纳时，受信任本地操作者可显式调用 `modelcrew.hand_repair.retry_after_invalid_p1(w, task, run_id, version=..., actor=..., request_id=..., statement=..., rationale=...)`。仅用于尚有作者返工预算的最小代码运行；须先解除业务围栏，核对原回应哈希、独立票据、快照和实际准入缺陷。原回应保持 NOT_ADMITTED，不补写 issues、不修指针、不产生接受的 FAIL/PASS。此操作消耗一次已有作者返工额度，增加 attempt/retries，不新增复核，不重置 recheck_used；接续到 GENERATE_MINIMAL，仍须新实际执行与独立 P1。剩余额度耗尽时拒绝此接续，使用既有显式操作者代码导入规则。新接口不向模型开放。

新运行及上述显式接续给后续审查提供实际存在的 artifact_id/selector 配对，以及每条 FAIL/BLOCKED 必须配对应 issues 的要求；服务器未执行 Schema 时不宣称强制模型遵守，最终仍做真实准入校验。历史已派发的缓存请求不更改协议或输入哈希。

同一任务和版本已存在代码手运行时，新增 request_id 不得另起代码手重置作者/复核预算；核心及适配层预检均拒绝。原 request_id 的幂等恢复保持可用，历史已有多条运行不删除、不追改。当前程序补丁需重启已有常驻 workflow_mcp 连接加载；数据库恢复不依赖重启，也不重新授予用户批准。


## 用户授权代码手修复接续（2026-11-16）

用户明确授权后，受信任本地宿主可调用 `Workflow.authorize_coder_repair(task, run_id, version=..., actor=..., request_id=..., statement=..., max_repairs=3)`，冻结真实授权原话、当前运行/模型绑定、原代码哈希及单独的修复预算。此处最多 3 轮，记录于不可变授权文件和状态事件；不重置原自动 retries、不新建运行。授权只作用于该运行及冻结版本，模型/输入/规范变化仍由原 guard 阻断。当前 API 沿用本机操作系统信任边界和本地 actor 标签，不宣称新增身份认证。

模型通过已有 `hand_advance` 消耗授权，不再要求用户复制本机 repair 命令。程序在调用供应商前持久登记一次修复额度和新 attempt，使用新 Coder 操作生成代码，来源标记 delegated_coder_repair；不冒称 operator_supplied_code。生成代码只做宿主静态编译，实际执行仍进入现有受限 Docker。P1 通过后才进入全量；全量修复保留已接受 P1，必须重新执行、字节复跑和独立 P2。当前允许的阶段为 minimal/full，合计共用这一份修复额度。

授权接口不在模型业务工具目录中，现有 wire contract 1.0.0 及旧冻结文件不改写。模型不能经 MCP 创建或扩大授权，也不能通过手工具代用户批准模型、结果或论文。授权只适用于已耗尽自动额度的 implementation/coding 故障，不覆盖 review_output、供应商结果未知、基础设施故障或模型修订。没有授权时保持原暂停行为；有授权时已知代码失败可自动领取下一修复额度，额度耗尽后停下并保留失败。重复查询和同键授权幂等，不重复领取额度；当前授权不允许换键自动扩容。

状态返回 coder_repair 的 used/remaining，已有 DSH/MCP 进程需重新启动以加载新程序。不能把工程测试当实际业务通过：候选代码宣称 passed 不授予准入，独立 P1/P2 和用户结果确认仍分别记录。

为满足已冻结的多图三格式交付，受信任授权按 `计划图数×3+声明输出数+2` 核算新全量作业文件个数，写入授权证据；原请求及旧作业限额不变。当前执行器文件数硬上限从32提高到64，默认仍为16；本次运行的新全量文件额度为46，最小作业仍为32。内存、运行时间、单文件/总字节等限制不变。超过硬上限仍拒绝，不删减确认的图清单来凑额度。该额度是工程资源安排，不是数值阈值调整。


## 可信宿主长期代码修复权限（2026-11-16）

本机用户已明确要求 DSH/宿主自行处理任务内修复，不再逐轮申请额度。宿主配置 `configs/local/settings.json` 支持 `autonomy: {"coder_repairs":"standing", "statement":"用户明确授权原文"}`；默认 `off`，不随发行包开启。配置由可信本机维护，不接受模型工具参数。`capabilities_read.host_autonomy` 报告是否启用及 `hand_advance` 入口。

启用后，在已批准模型内、自动重试已到3次、实现失败且无已附加结果的代码运行，通过原有 `hand_advance` 自动登记绑定当前版本的长期修复授权，历史有限授权和每次使用记录保持不变。长期授权不设修复次数上限，每次调用仍只推进一个状态转换，不在单次调用中无限循环。源码、Docker执行、独立P1/P2和最终结果确认沿用原流程。旧自动重试计数不清零，完整图件配额按冻结计划计算，不放宽数值阈值。

配置每次安排修复时重新读取；将 `coder_repairs` 设为 `off` 后不再安排新的长期修复尝试，已经开始的一次仍保留日志。审查协议错误、未知派发、基础设施故障及需要模型变更的情况不伪装成可重试的实现失败。该权限不登记模型/结果/正文/图片批准，不绕过独立审查，也不将生成代码标成人工提供。已运行的MCP后端须重连以加载此次Python代码；此后无需逐轮重启或续授权。


## DSH提交现成代码修订（2026-11-16）

`hand_advance` 增加可选 `arguments.code_revision`：`stage`（minimal/full）、`code_path`（工作区内UTF-8完整源码）、`code_sha256`、`previous_code_sha256` 和 `rationale`。外层继续使用原 `request_id` 和当前 `expected_binding`。这是运行时兼容扩展；原G1请求/响应/工具目录资源、50项操作名称和旧请求字节均不改写，不新增批准或人工修复工具。

仅已取得委托修复尝试、尚未派发生成器的 `GENERATE_MINIMAL/GENERATE_FULL` 接受该参数；普通 `hand_advance` 行为不变。模型不能通过修订增加权限或额度，长期宿主权限已撤销时拒绝。完整阶段需独立P1已通过。代码路径、源码哈希、旧代码哈希、大小上限256KiB及Python解析/编译在业务派发登记前核验；拒绝不产生结果未知fence。宿主绝不执行源码。

提交成功将核验过的字节快照保存为新的修订文件，以 `dsh_submitted_coder_revision` 记录来源并登记新的代码作者上下文；沿用已领取的attempt，不再消耗一次修复、不清零自动retries，不登记为 `operator_supplied_code`。DSH工作文件之后的编辑不改变已提交快照。下一次普通 `hand_advance` 通过原Docker执行链运行该快照，再走新独立P1；完整阶段仍需全量复跑和独立P2。没有任何用户批准。相同请求键可重放；换内容复用键拒绝。未知派发沿用原 `operation_status` 对账，不盲目重发。

`capabilities_read.host_autonomy.code_revision_submission` 和MCP `hand_advance` 输入schema公开入口。已启动的MCP进程需重新连接才能发现此次新增参数。


## P2准备失败与审查回答错误的区别（2026-11-17）

图目录的category、formal及正式图number在调用独立审查器之前验证。缺失或非法时返回具体catalog_defects，按全量代码实现问题返工；不得将这种本地KeyError称为“审查回答不可解析”，也不消耗独立复核机会。P2尚未派发时没有审查回答可重跑。历史误分类应核验原始目录、复跑一致性、无P2调用及当前绑定后保留纠错记录再恢复准备阶段，不能伪造FAIL/PASS回执。

中文图件需执行镜像实际包含并可选择简体中文字体。新增configs/executor/Dockerfile.figures-cjk安装Debian fonts-noto-cjk，保留其许可证，并从TTC集合导出Noto Sans CJK SC供Matplotlib正常发现。历史镜像不覆盖；本机切换新tag时登记image ID、字体包版本及中文探针。字体变化必须重新全量与字节复跑；探针可读不等于全部候选图审阅通过。


## 首次源码提交与已证实未送达的审查恢复（2026-11-17）

已获当前版本模型批准、M1 有效且尚无代码/操作/作业/审查的首个 `GENERATE_MINIMAL`（attempt=0、retries=0），可用现有 `hand_advance.arguments.code_revision` 原样提交工作区完整源码，`previous_code_sha256` 取 64 个零。入口核验文件哈希与 Python 静态语法，不执行宿主求解；来源登记为 `prepared_coder_source`，不冒充供应商生成或人工提供。只进入 `EXECUTE_MINIMAL`，仍须新 Docker 执行与独立 P1；任何已领取的作者操作不得覆盖。

本机显式维护函数 `modelcrew.hand_delivery.recover_reviewer_delivery(w, task, run, original_request_id, retry_id=..., reason=..., apply=False)` 只检查当前未完成的 P1/P2/W1 审查：唯一原调用须有 ConnectError/ConnectTimeout 元数据、无 HTTP 状态、无模型响应、原输入摘要匹配；真正未知的读写中断、已有响应或证据不全均拒绝。检查通过后显式 `apply=True` 保留原失败记录，将原业务操作结清为已知依赖失败并登记一次性送达重试授权；后续正常 advance 在网络前持久化消耗该授权，仍对同一冻结产物做独立审核。此函数不向模型暴露，不删除原操作，不改作者 attempt/retries，不给予任何审核通过或用户批准。首次恢复调用若又不确定，不再借本入口反复重发。


## 全量生成长度截断与首次全量文件接续（2026-11-17）

已有有效独立 P1、当前版本已批准、尚无 full 源码/作业且当前生成操作未领取的 `GENERATE_FULL`，现在也可经 `hand_advance.arguments.code_revision` 提交首份 full 文件；`previous_code_sha256` 绑定当前 minimal 文件，不使用全零，不要求先耗尽作者预算。prepare 与 submit 均重验阶段、哈希、P1 与未领取状态，只静态编译源码并登记来源为 prepared_coder_source，提交后进入 EXECUTE_FULL。后续代码更新仍走既有授权修复规则；本扩展不能覆盖已派发操作、现有 full 源码或作业。MCP 常驻进程需重连，capabilities_read 的 first_full_source 描述可核对新入口是否加载。

已知不完整/非法作者输出的返工使用原调用阶段，避免 provider 临时 PROVIDER_UNKNOWN 使全量误回最小。只有全量生成失败且原 P1 仍有效时保持 P1、回 GENERATE_FULL；执行/复跑/P2 的失败策略不在本次改动范围。全量文件容量按冻结数学包候选数×3+契约输出数+2 派生，与原限制取大值，不改最小阶段、运行时限及字节限制。

历史误退回可由本机显式 `modelcrew.full_generation_recovery.recover(w, task, run, request_id=..., reason=..., apply=False)` 检查，核验通过后才 apply=True。须有持久化的全量入口和 P1、之后每次生成均为 HTTP200/finish_reason=length 的可校验原响应、未变的最小源/产物/作者/封存/作业、未领取的当前尝试及无未知业务围栏；不接纳已执行或产出过新源码的情况。恢复只新增证据并回到 GENERATE_FULL，保留 attempt、retries 与原记录，绝不制造 PASS 或用户批准。

## 全时段诊断派生输入与 P2 证据体量（2026-11-17）

受控执行器可显式声明最多4个 `authorization.derived_inputs`，仅接受同一任务/版本/契约、已成功执行的生产者真实产物。每项绑定 input_id（derived:前缀）、job_id、artifact_path、SHA256；核对生产者登记作业、代码/作业哈希、成功回执、实际产物字节和当前全部原输入。不能替代/覆盖冻结原输入，跨模型、失败生产者、未声明附加输入、变更检查点均拒绝。用于受控诊断的精确状态衔接，不意味着正式全量可跳过从初值独立执行或把缓存诊断冒充生产结果。

P2上下文只读投影仅省略明确编码的无损float64二进制trace.data字符串，保留原不可变文件和哈希，并逐指针告知审查器未解码。数值摘要、FAIL、代码、阈值及来源证据不截断、不改写。不能由投影自动授予数值/审查/用户通过。

全页PDF报告新增嵌入字形程序类型不匹配警告（例如CFF被声明为TrueType FontFile2），候选目录机械报告把逐页字体/警告摘要直接附给独立审查。部分渲染器能显示不等于字体兼容合格；机械通过和实际读图/独立P2/用户确认仍分别处理。历史封存报告不追改。

## 已披露误差的用户接受补充（2026-11-17）

`modelcrew.deviation_acceptance.adopt` 为可信本地用户决定入口，不向模型MCP暴露。显式捕获本次用户原话、完整绑定、原P2回执/快照与已失败检查哈希，保存不可变版本化验收补充。当前仅适用误差/收敛类自定检查，不能免除执行、字节复跑、题目输出或其他检查；不修改原数值FAIL/阈值、不创建模型或结果批准。只在被拒P2后尚未领取新作者生成/执行、已完成真实全量和全文件一致复跑、原P1仍可重验的同一运行上重新打开独立P2，保留attempt/retries和历史回执，不是作者预算重置。

补充与原完整执行证据共同封入新的P2快照；审查应明确区分“原精度未达标但用户接受的偏差”和“数值达到原阈值”。所有其他问题照常判定。每次guard核对补充原件、原证据、数值配置和全部检查哈希及未舍入T/C指纹；纯导出修复可在这些数值完全不变时沿用接受，新数值须重新披露沟通。hand_status返回user_accepted_deviations路径、哈希和范围，DSH必须读取并沿用该记录，不能把它扩大成其他批准。

`register_author_visual_evidence` 只在尚未派发的新P2前封存作者实际全页读图缺陷、各PDF与预览哈希。它不是独立读图或用户选图PASS。独立P2应检查本次实际证据；pre-review的independent_review=NOT_RUN不能单独构成当前审核永远无法通过的循环理由。字体兼容缺陷、缺页或其他真实问题仍应失败/阻塞并明确定位。

## hand_recheck 按 attempt 计额及诊断后恢复（2026-11-18）

本节按用户决定替代此前“全运行一次”限制，旧描述和历史记录保留。P1/P2/W1的hand_recheck每个attempt合计最多一次；适配层预检和核心都按当前attempt验证，持久登记recheck_attempts后进入新的审查阶段。recheck_used继续保留为历史“曾经使用”标记，不再单独据此拒绝后续attempt。旧payload从原ops/reviews的关口-attempt-recheck名称归属已用attempt，不能归属的旧true标记保守拒绝。状态接口review_recheck显示scope、当前attempt是否已用及历史各attempt；同attempt换关口/请求键不扩额，claim未完成也已占用。原作者attempt/retries、旧响应、冻结字节和批准均不重置。

处置顺序是先读原响应/HTTP元数据及实际校验异常，再决定恢复。HTTP200完整合法JSON也可能因artifact_id/JSON Pointer配对无效而未获接纳；此时原回答的内容结论只能视作未接纳的原意见，不能改指针后冒充原正式回执。先补齐确实缺少的证据，用当前attempt尚未使用的一次独立复核重新判定。已存在HTTP回答不能调用仅支持已证实未送达的hand_delivery恢复。新的作者返工不因为上一attempt复核已用就失去自己的复核机会。

## P2实际全页图像输入（2026-11-18）

P2现在在同一次独立审查调用里附带全部PDF物理页的真实PNG字节，冻结图片manifest/图片哈希并记录发送字节、模型、请求/响应哈希；审查器逐页返回稳定image_id和实际观察，由程序绑定源图SHA256，不要求模型抄加密摘要。完整覆盖、发送清单与独立视觉回执均参与本地准入校验，缺页、变图或实际未发送不能登记结果。独立质检和用户结果/配图批准继续分开；不把作者自检转成独立PASS。原产物和复跑目录不追加报告、不改字节。实现与真实模型探针/13页P2实测边界见docs/p2-vision.md；常驻MCP重连加载新代码后适用，不追改旧回执。

## 已完成数值任务的论文承接（2026-11-18）

COMPLETED表示原数值/确认主流程完成；execution.mode=solver是计算来源，不是禁止writing hand的任务模式。原任务在当前版本模型/结果均获批准、独立P2有效且非numeric-only特例时，允许只读承接写作子运行，不需要新建任务、复制契约或撤销原完成/批准记录。

writing_handoff在适配层持久claim前和核心创建目录/行前都核验：当前模型/结果、原P2及图目录绑定、原字节和所选数值证据。hand_runtime_P2结果可自动找到同一批准执行的figure-catalog与主result JSON，明确携带接受偏差；已登记输出只在这个批准结果范围内成为写作资料，不扩大为任意新输入权限。未批准、过期版本、numeric-only或缺关键材料的请求在预检明确失败，不一律outcome_unknown。

写作目录复制原图字节，文件名使用安全序号而非可能含冒号的逻辑figure_id；逻辑ID/原图/编号保留，单题question_id及figure_contract用途在新写作目录规范化为现有选图接口的question_ids/purpose，不改旧图目录或批准。Writer的result证据包含原已接受误差处置，不能将原FAIL写为阈值达成。正文和选图仍分别等待用户确认，正式导出不提前。

历史漏传figure_catalog且已形成unknown的旧请求，只能经writing_handoff.recover_legacy_missing_catalog明确核验原请求摘要、缺字段、历史核心guard早于首次writer INSERT、无匹配写作运行、原批准结果及P2未变后结清为已知失败。保留原请求/事件/孤立文件，不能凭没有新事件就断定任何unknown都可重发。新有效请求使用新正常幂等键承接，不重置旧记录。

## 写作图序矛盾的定点修复（2026-11-18）

Writer-plan现在前置检查正式图按目录编号映射的章节位置是否非递减，避免把图5映射到图6—10之后的章节，再让Writer反复服从矛盾的已审提纲。此检查不保证模型每次生成都正确，仍做真实Markdown校验。

本机writing_layout_repair仅针对未获任何用户正文/配图批准、作者自动额度已尽、唯一机械问题是正式图序的稿件：原样移动一个完整小节，并只改该图在提纲中的章节映射。原文、数值、公式、题注、编号和图片字节保留；旧稿/提纲/回执保留，新增作者修复记录并增加attempt，原retries不清零。必须把新提纲和已修稿作为新快照交独立W1；通过后使用已校验的准备稿发布，不再让模型整篇重写。无新W1或已有用户决定时拒绝发布；最终仍停在正文/配图分别待确认，不能当作正式论文导出或用户批准。

