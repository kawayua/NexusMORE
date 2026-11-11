# 通用代码手与论文手运行接入

实现入口为 `modelcrew.hand_runtime`、`Workflow.start_hand/advance_hand/hand_status/hand_decision/recheck_hand`；HTTP与CLI复用同一实现。程序管理状态和路由，不增加常驻业务Agent。结构化阶段使用JSON，Writer正文阶段返回Markdown原文；生成的数值代码不在宿主导入或执行。

数据库迁移010保存运行快照和不可变状态事件。部署先执行 `python -m modelcrew init-db`。不替换历史D3/D5脚本、已通过论文或模型。

## HTTP与CLI

| 操作 | HTTP |
|---|---|
| 创建代码手/论文手运行 | `POST /tasks/{task}/hands/{coding|writing}/runs` |
| 查看状态 | `GET /tasks/{task}/hand-runs/{run_id}` |
| 执行一个持久化步骤/恢复 | `POST /tasks/{task}/hand-runs/{run_id}/advance` |
| 一次有理由的独立只读复核 | `POST /tasks/{task}/hand-runs/{run_id}/recheck`，正文含rationale |
| 用户正文/选图决定 | `POST /tasks/{task}/hand-runs/{run_id}/decisions` |

CLI：

```powershell
python -m scripts.run_hand start TASK --hand coding --request request.json
python -m scripts.run_hand advance TASK --run-id RUN_UUID
python -m scripts.run_hand status TASK --run-id RUN_UUID
python -m scripts.run_hand recheck TASK --run-id RUN_UUID --request recheck.json
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
