# 完整业务工具契约

2026-11-15：G1 的业务契约冻结为 **1.0.0**，为首个 DeepSeek Harness（DSH）接入提供实现基线。冻结的是业务接口、状态/版本绑定、幂等、错误和人工关卡要求。本轮没有实现完整工作流 MCP、启动真实宿主联调、调用模型或提交用户决定；G2—G5 仍待实施。本轮工程冻结不代签用户阶段验收。

## 冻结文件与核验

包内 `resources/contracts/` 新增以下文件，均按显式允许清单进入 wheel/sdist，使用 `importlib.resources` 定位，不依赖仓库目录：

| 文件 | 用途 |
|---|---|
| `business-tools-1.0.0.json` | 50 项业务操作、核心映射、实际缺口、通道与幂等策略、18 类错误 |
| `business-request-1.0.0.schema.json` | Draft 2020-12 请求联合类型；各操作参数及现有核心请求模型快照 |
| `business-response-1.0.0.schema.json` | 稳定回执、待确认项、登记产物、分块读取及派发记录 |
| `business-examples-1.0.0.json` | 19 个请求、4 个响应的合成样例；没有执行或提交决定 |

`python -m modelcrew.business_contract` 离线检查契约。Python 入口 `load_contract()`、`validate_request()`、`validate_response()`、`request_digest()`、`pending_id()` 仅加载/校验；它们不分配运行、不保存请求账本、不认证调用者。请求内部一致不等于与数据库当前状态一致。业务仍由 `Workflow` 和 PostgreSQL 维护；checkpointer 是可恢复投影，宿主缓存不得成为第二个状态源。

冻结哈希、代码依据及本次实际检查见 [G1 冻结回执](release/business-tool-contract-freeze-20261115.json)。后续发现不兼容字段/语义变化须新增契约版本及对应测试，不能悄改 1.0.0 冻结文件、旧运行或用户批准；兼容适配仍须保留原请求及回执。契约版本、产品开发版 `0.1.0.dev0`、整数模型方案版本、结果 revision、run/build ID、collaboration 规范版本及 MCP 协议版本是不同维度。

## 请求和返回

请求固定为 `{contract_version, operation, arguments}`。所有写操作显式带 `request_id`；除创建项目/任务和题目导入外还必须带 `expected_binding`。已有 HTTP 操作的路径/查询参数放在 `arguments`，原请求模型放在 `arguments.body`，不能新增任意 URL、命令、镜像或执行目录参数。JSON 必须有限值，拒绝 NaN、非整数业务版本、未知字段、路径注入和同名字段冲突。嵌套建模契约/数学包、执行限制及文件语义仍由已有核心校验器检查，线格式合法不代表可执行业务。

- 任务写操作绑定 `task_id + version + contract_sha256`；运行和汇编操作另外绑定实际 `run_id/build_id`，项目级绑定 `project_id`。结果确认还绑定 `execution_id + result_revision`，正文/选图决定绑定精确 `artifact_sha256`。
- 包络与 body 的 request_id/version、目标标识必须一致。G2 必须在已有核心锁内比较全部绑定字段和当前事实状态，版本或哈希已变则拒绝。仅调用线格式校验器不能完成这一点。
- 精确修订稿与选图修改须唯一指定单题任务/run 或汇编 build，并绑定旧内容 `source_sha256`；新运行/构建保留旧字节，不能覆盖已通过稿。
- 返回固定有 `contract_version, operation, request_id, status, binding, phase, replayed, pending, artifacts, data, chunk, error, receipt`。状态为 `ok/running/needs_user_input/blocked/outcome_unknown/error`。`binding` 反映操作后的当前状态，修订后可与请求中的旧版绑定不同。
- `data` 仅承载脱敏的原生核心诊断 JSON，不保证其内部字段稳定；自动化依赖稳定的 `pending/artifacts/receipt/binding`。`phase` 保留原生阶段名，不据字符串推断批准。
- 成功接收的修改（含 running/needs_user_input）必须返回持久化 `receipt`；账本状态为 `claimed/dispatched/succeeded/failed/outcome_unknown`。operation_status 查询成功仅表示找到了该记录，不代表原修改成功。

## 操作映射和缺口

50 项中，39 项能映射到已有核心方法，5 项仅部分具备，6 项缺少通用核心操作。**全部 50 项的 1.0.0 宿主适配器均未实现**；“mapped”只说明核心依据存在。旧 JS 桥仍是 0.1.0 的 10 项有限入口，原文件及其包内副本保持原字节；不可把下面的冻结清单直接当作 MCP 可发现工具清单。

| 操作 | 核心依据 | 核心状态 | 通道 |
|---|---|---|---|
| `project_create` | `Workflow.create_project` | mapped | model |
| `projects_list` | `Workflow.list_projects` | mapped | model |
| `tasks_list` | `Workflow.list_tasks` | mapped | model |
| `task_create` | `Workflow.create` | partial | model |
| `task_status` | `Workflow.inspect` | mapped | model |
| `versions_list` | `Workflow.versions` | mapped | model |
| `version_read` | `Workflow.version_dossier` | mapped | model |
| `proposal_read` | `Workflow.inspect` | mapped | model |
| `modeling_start` | `Workflow.run_modeling` | mapped | model |
| `modeling_recheck` | `Workflow.recheck_modeling` | mapped | model |
| `modeling_status` | `Workflow.modeling_status` | mapped | model |
| `assembly_start` | `Workflow.start_assembly` | mapped | model |
| `assembly_status` | `Workflow.assembly_status` | mapped | model |
| `assembly_rebind` | `Workflow.rebind_assembly` | mapped | model |
| `assembly_compose` | `Workflow.compose_assembly` | mapped | model |
| `assembly_build_status` | `Workflow.assembly_build_status` | mapped | model |
| `assembly_decide` | `Workflow.assembly_build_decision` | mapped | trusted_user |
| `assembly_bind_reviews` | `Workflow.bind_assembly_reviews` | mapped | local_operator |
| `assembly_export` | `Workflow.export_assembly` | mapped | model |
| `assembly_render` | `Workflow.render_assembly` | mapped | model |
| `assembly_review_w2` | `Workflow.review_assembly_w2` | mapped | model |
| `assembly_retry_w2_delivery` | `Workflow.retry_assembly_w2_delivery` | mapped | local_operator |
| `assembly_recover` | `Workflow.recover_assembly` | mapped | model |
| `hand_start` | `Workflow.start_hand` | mapped | model |
| `hand_status` | `Workflow.hand_status` | mapped | model |
| `hand_advance` | `Workflow.advance_hand` | mapped | model |
| `hand_repair` | `Workflow.repair_hand` | mapped | local_operator |
| `hand_recheck` | `Workflow.recheck_hand` | mapped | model |
| `hand_decide` | `Workflow.hand_decision` | mapped | trusted_user |
| `result_read` | `Workflow.inspect` | mapped | model |
| `artifacts_list` | `Workflow.version_dossier` | partial | model |
| `mathematics_read` | `Workflow.mathematical_proposal` | mapped | model |
| `mathematics_publish` | `Workflow.publish_mathematics` | mapped | model |
| `task_decide` | `Workflow.action` | mapped | trusted_user |
| `task_revise` | `Workflow.action` | mapped | model |
| `task_restore` | `Workflow.action` | mapped | model |
| `task_resume` | `Workflow.resume` | mapped | model |
| `references_retrieve` | `Workflow.retrieve_references` | mapped | model |
| `references_discuss` | `Workflow.discuss_references` | mapped | model |
| `tool_evidence_read` | `Workflow.tool_evidence` | mapped | model |
| `capabilities_read` | `modelcrew.business_contract.load_contract` | partial | model |
| `project_read` | `Workflow.require_project` | mapped | model |
| `question_import` | `Workflow.question_intake` | partial | local_operator |
| `pending_list` | `无通用服务` | missing | model |
| `operation_status` | `无通用服务` | missing | model |
| `artifact_read` | `无通用服务` | missing | model |
| `manuscript_register_revision` | `无通用服务` | missing | local_operator |
| `figures_select` | `无通用服务` | missing | model |
| `final_decide` | `无通用服务` | missing | trusted_user |
| `assembly_artifacts_list` | `Workflow.assembly_build_status` | partial | model |

具体 HTTP method/path 和 body 模型见机器清单；`task_decide/task_revise/task_restore` 有意复用同一 `/actions` 核心，不创建平行状态机。题面导入复用 `Workflow.question_intake`，其现有路径参数需由登记输入解析器从 artifact ID 解析，当前没有通用 HTTP 导入入口；导入题面不等于有了建模契约，也不代表题面所有附件已解析。原 `Workflow.create` 仍要求有效契约，不能用题目文字直接调用。

5 项部分具备：`task_create`（同任务ID重试目前冲突，缺统一幂等账本）、`artifacts_list`（现有接口未覆盖全部三手/汇编产物）、`capabilities_read`（只有本地契约读取）、`question_import`（核心已有、登记输入解析和对外入口缺失）、`assembly_artifacts_list`（现有 status 有嵌套产物信息，缺统一索引）。

6 项缺失须显式拒绝或保留可信本地替代路径：`pending_list`、`operation_status`、`artifact_read`、`manuscript_register_revision`、`figures_select`、`final_decide`。前两项需要现有各域事实记录的统一投影/索引；产物读取需要按归属校验的登记解析器。F6 精确修订稿登记和正式成品确认用过可审计本地专用操作，尚无通用服务；不得拿该次成功记录冒充本批 API 已接通。

## 幂等、重连与错误

外部请求身份为“归属范围 + operation + request_id”。指纹对完整请求采用 UTF-8、键排序、无多余分隔空白、`ensure_ascii=False/allow_nan=False` 的 JSON 后计算 SHA-256，不做 Unicode 归一化；包括 expected_binding 和用户事件引用。参数键顺序不同不产生新请求，内容变化须明确使用新请求键。重复原请求读取已存响应/当前权威状态，`replayed=true`，不再次执行。

现有各核心幂等域不完全相同，不能统一假称支持。项目按 ID/title 自然幂等，题目按 target/revision 自然幂等；模型 action 在 task 下共享 request_id 域，三手、汇编和导出有各自回执。G2 必须兼容更宽的历史幂等域，预留/检查冲突，不能让跨 operation 同键误命中旧回执。`task_create/hand_advance/task_resume/assembly_recover/hand_recheck` 等须补持久化外层 claim 与状态对账；单靠宿主进程内 Map 或新增 UUID 不能满足恢复要求。

先提交 claim，再发生外部 I/O；不持久化则不派发。丢失响应、超时、连接关闭和 503 均可能已产生修改：用原 project/目标/operation/request_id 查询，不新建任务、不自动重发求解、不换键绕过。`outcome_unknown` 固定要求 `query_operation_status`。已知未派发也必须由权威回执证实；代码执行的未知状态沿用已有 status-only 恢复。W2 的受控重取交付仍走独立 local_operator 操作，必须保留理由及旧请求关系，不能泛化成模型自动重试。

HTTP 已有 `not_found/workflow_conflict/invalid_request/service_unavailable/retrieval_unavailable`，其余细分错误需 G2 按结构化事实映射；禁止仅凭异常消息子串猜测“已过期”或“未执行”。稳定错误及唯一恢复方向见机器清单。缺依赖、检索空结果/部分/失败、代码错误、实现失败与独立质检 FAIL/BLOCKED 各保留真实含义。对外错误不得含连接串、密钥、绝对本机路径或原始后端异常；异常详情仅写可信本地日志。

## 人工确认、修订及正式成品

`pending_list` 只读现有事实，分别产生 model/result/manuscript/figures/final 待办，不创建决定。`pending_id = pending_ + SHA256(canonical({kind,binding,artifact_ids:sort(...)}))`，是展示定位标识；哈希或 actor 字符串均不能充当用户认证。待办缺失、模型说“用户已同意”、工具返回成功或阶段名变化都不是批准。

模型只可获得已实现的 `model` 通道操作；`trusted_user` 决定和 `local_operator` 修复/本地登记不进入模型工具清单。`user_event` 仅引用由可信 CLI/UI 独立捕获的真实事件（event_id/channel/statement_sha256）。G3 必须验证事件存在、原始表达、当前待办、绑定、单次消费及回放关系；调用者自行提交相同 JSON 或 actor=user 仍不可信。宿主不具备可信用户事件转交能力时，继续用本地可信入口决定，宿主只展示待办和读取状态，不能降低关卡。

方案确认后才启动代码手，结果确认后才写作。首个宿主的生产任务使用 `pending-code` 和空 executor_config，测试夹具后端不进入生产工具许可；方案批准明确带 `defer_execution=true` 后再启动代码手，不能静默改写用户已确认的请求。三手内部复用 F6 资料路由及已有独立 M1/P1/P2/W1/W2，不再起一套宿主编排器。

正文确认和选图确认独立。现有 `hand_decide` 只能确认图目录已有 formal 标记，不能当成任意图ID选择接口。新增未入文候选不撤销字节未变正文的批准；真正改变正文或入文图，按影响范围新建版本并重新审阅。恢复旧模型创建新的待确认版本，不移动 current_version 回旧值，也不继承旧版批准。有限编辑规范 rebind 及既有审阅绑定继续受原有核心范围限制，不等于任意正文导入。

正式导出必须有当前正文和最终配图的分别确认；批准 Markdown/AST 为共同内容源，沿用已支持的 Tectonic 0.17.0、Pandoc 3.6.4 及 Word 原生公式路径。导出完成、全部 PDF 全页数核对/预览/检查、独立 W2、真实用户成品最终确认是独立事实，不能互相替代。`final_decide` 绑定 build/export/render/W2 及全部成品字节，在通用实现前不可返回最终确认成功。本文工程契约没有生成正式论文或图片，不触发业务论文审阅。

## 产物边界

产物稳定描述为 `{artifact_id, owner, sha256, media_type, bytes, role, readable}`，owner 明确 project 与 task/version 或 assembly build，run 为可选进一步范围。任务与汇编列表都只给已登记对象；磁盘上“恰好有文件”不能作为登记或批准依据。下游只读准确 artifact_id，不把核心旧路径直接暴露为任意读取参数。

`artifact_read` 必须同时携带 owner、artifact_id、期望 sha256、offset、max_bytes；单次最多 262144 字节。读取前解析登记、核对归属、解析最终真实路径、拒绝符号链接/连接点逃逸并在返回数据时核对同一次文件读取的完整字节身份，不能先校验再读取可变路径。绝对路径、`..`、file/HTTP URL 和跨项目同哈希枚举都不授权。未登记、已变字节、跨任务/版本访问分别拒绝。

返回 chunk 统一 base64，含 bytes_returned/total_bytes/eof，以字节偏移分页，不按字符切分 UTF-8；PDF/Word/图片也不会被伪称已解析或审图。元数据及块长度/EOF 一致性由线格式校验器检查，真实归属、文件哈希和读取竞态由 G2 实现及实测。列表中未正式通过 W2/最终确认的导出需保留其实际阶段，不能标作用户已接收。

## G2 接入前后的验收边界

G1 完成标准为：完整生命周期有显式工具描述及机器 Schema；每项能追溯到当前核心或明确缺口；版本/幂等/错误/用户决定/产物边界写明；合成与拒绝用例、核心映射漂移及随包资源检查通过。它允许进入 G2 实现，不要求在 G1 冒称缺失服务已经存在。

G2 必须新增统一持久化派发账本/操作查询、可靠待办投影、owner-scoped 产物索引/读取及协议响应封装；只注册已经实现且通道许可的工具，未实现项稳定返回 unsupported_operation。题目入口需登记文件解析，不把原生路径能力透传给模型。对现有 body 中的 figure_catalog/sources/result_evidence/code_path/review_path/original_source 以及嵌套 contract 的输入路径，G2 同样必须逐字段做登记归属与真实路径校验；核心请求模型快照不是任意文件路径的宿主授权，无法安全解析的参数须拒绝。精确修订、任意选图和最终确认在实际实现前保留已有可信本地路径及明确缺口；完整业务端到端验收前须实现或明确验证可审计替代，不能省略步骤。G3 再实测可信事件转交；G4/G5 在真实 DSH 内验证展示、调用和故障恢复。MCP 协议/传输版本在 G2 选择，本次不从旧桌面版本推断兼容，也不新增供应商接口能力。

F5 暂缓、全新 Windows 环境验证例外及公开发布授权仍按既有记录处理。没有因为本次冻结更新历史业务批准、许可证决定或旧冻结规范。

## 本轮实际验证

契约专项 32 项全部通过；扩大到原建模契约、资料路由、包分发/资源、目录、文档边界和来源证据后，合计 **105 passed、1 skipped**。跳过项是既有官方 Word 评论 XML 校验缺少 documents 依赖，未记作通过；本轮没有扩大文档编辑能力。旧 JS 宿主桥 5 项全部通过，其接口与源码未改。

原始 wheel、sdist 及 sdist 重建 wheel 均完成构建审计；两个 wheel 分别安装到源码目录之外，以隔离启动验证全部 19 请求/4 响应样例和 231 项包资源，新模块不导入数据库/模型运行库。复用了已准备的基础依赖目录，不代表全新 Windows、首次联网或真实 DSH 验证。121 份原有发行证据、模型契约和 collaboration 文件哈希复核未变。完整命令、日志/候选哈希及范围见冻结回执；没有运行求解、生成正式论文或新增任何用户/独立质检批准。
