# 阶段 C 交接与实施范围

> 当前状态（最新）：C1至C6工程检查已完成，本次15项证据与状态核查全部通过，用户已明确验收通过，见[验收确认](user-acceptance-20261106.json)。C6故障与清理24项检查通过，完整回归151项通过；详见[阶段C验收材料](stage-c-acceptance-report-20261106.md)、[C6摘要](c6-failure-verification-summary.json)与[恢复说明](../docs/failure-recovery.md)。下文各阶段记录保留为历史。D未启动，用户已取消新任务/空白上下文的强制门槛，C验收审阅已开始。OCR暂缓，多模态识图、真实角色协作和论文引用位置未实现。

启动日期：2026-11-06（北京时间）。用户已指示进入阶段 C。依据为原计划阶段 C“工具协议与受控执行”。

## 接收的阶段 B 基线

阶段 B 功能验收通过，既有验收记录为 76 项测试、5 次数据库重启。当前正式任务 dragon-q1 为 v2、结果 revision 2、COMPLETED；这是交接文档中的状态，本次不替用户重新确认。H1 历史固定样例原字节缺失已按用户意见停止追查，保留原哈希和异常，不作为继续搜索任务。H2 历史档案补录、真实模型草稿质量与干净部署范围仍按原报告保留。

复用现有 modelcrew/ 下的 Workflow、版本化契约、两个人工关卡、执行后端、持久回执及内容寻址归档。数据库仍使用现有迁移和 PostgreSQL checkpointer；不创建另一套状态机，不覆盖正式求解目录。

## 本阶段顺序与验收

| 顺序 | 工作 | 验收证据 |
|---|---|---|
| C1 | FastAPI 项目、小题、方案/结果/版本/产物查询，动作与恢复 | HTTP 经真实工作流完成测试任务；重复及过期确认不错误推进 |
| C2 | 少量有公开来源与使用范围的语料，解析切分、向量化、Qdrant | 固定查询命中预期片段，能回溯来源及位置 |
| C3 | 独立 paper-search MCP server | 查询、过滤、分数、来源返回；空结果与服务故障分开 |
| C4 | 独立 code-executor MCP server 与 Docker 约束 | 非特权、禁网、只读输入、独立输出、CPU/内存/进程/超时/产物限制 |
| C5 | 工作流经 MCP 调用工具，关联任务、契约版本和回执 | 未确认方案不能执行，工具记录及产物可追溯，未知执行结果先恢复 |
| C6 | 正常与失败演练 | 语法错、缺依赖、超时、内存超限、输出过大和非法路径有实测记录；基础设施故障不计入代码重试 |

C1 先沿用 B 的显式 fixture/reviewed-run 后端；这不代表 MCP 或自动执行已经完成。C2–C6 完成并验证前，阶段 C 保持进行中。结果确认后的小论文及多 Agent 拆分属于阶段 D。

## 本地 API

安装：`python -m pip install -r requirements-stage-c.txt`。初始化沿用 `python -m modelcrew init-db`。启动：`python -m uvicorn modelcrew.api:app --host 127.0.0.1 --port 8000`。交互文档：<http://127.0.0.1:8000/docs>。

API 为可信本地接口，actor 是审计标签。每请求独立数据库连接，服务导入不自动连接或迁移数据库。`GET /health` 仅检查 HTTP 进程。现阶段动作同步推进工作流，后续真实长耗时工具需要有运行标识与恢复机制，不能通过 HTTP 重试盲目重复派发。

先 `POST /projects` 传 `id,title`，再 `POST /projects/{project_id}/tasks` 传 `id,contract,executor_key,executor_config`。明确指定后端，禁止静默选择真实执行。项目同 ID 同标题可重放，同 ID 不同标题冲突；小题重复创建返回冲突，不覆盖原记录。

`GET /projects`、`GET /projects/{project_id}/tasks` 支持 limit/offset。`GET /tasks/{task_id}` 查整体状态；`/proposal`、`/result`、`/versions`、`/versions/{version}`、`/artifacts?version=...` 查交接物和带完整性检查的产物元数据。API 不提供任意宿主机路径下载。

`POST /tasks/{task_id}/actions` 与 B 的 action 字段保持一致，必须提交 actor、request_id、version、kind。模型/结果确认需 decision；结果相关动作需 result_revision；模型修改需完整新 contract；恢复需 source_version；拒绝/修改/恢复需 reason。`POST /tasks/{task_id}/resume` 仅按已持久化的确认恢复，不视为授权。

未知实体返回 404；业务冲突返回 409；字段/契约错误返回 422；数据库或执行服务不可用返回 503 且不透传连接信息。确认请求失败时应先查询状态，再以原 request_id 重试或恢复，不换新键推断未执行。

## C1 本次验证记录

2026-11-06：完整回归 **84 passed，0 failed，0 skipped，29.98 秒**。命令为 `python -m pytest tests --integration -q --junitxml=stage-c/runs/c1-api-verification-20261106.xml`。原始 JUnit 证据位于该路径，机器可读状态见 [progress.json](progress.json)。运行目录按既有 Git 规则忽略，原始 XML 目前是本地证据。

新增 8 项用例覆盖无需数据库的 health/OpenAPI、非法动作与额外字段阻断、异常连接信息隐藏，以及经 FastAPI TestClient 与真实 PostgreSQL/checkpointer 的完整 HTTP 工作流。实测项目幂等和冲突、小题创建、等待点恢复、双确认、重复与过期动作、契约新版本、历史版本及归档完整性查询。首次运行发现测试清单缺少必需的 description（83 通过、1 失败），补齐后完整重跑通过，未降低执行后端校验。

测试只创建 `test-api-*` 项目/任务，使用 TEST_SIMULATED_USER 和新固定证据；没有新增模型调用、真实求解或真实用户确认，也没有改写 dragon-q1。HTTP 验证使用进程内 TestClient，尚未另行做独立 Uvicorn 网络进程验证。C1 是本地业务接口最小实现，不代表阶段 C 整体验收通过；下一步为 C2 最小检索闭环。

## C2 最小检索闭环（已验证）

已复用本地 `BAAI/bge-base-zh-v1.5` 中文模型（768维）与独立Qdrant，完成4份来源、82个片段的解析、切分、入库和CLI/API查询。用户提供的公开论文目录已核对，本次纳入A163第8页人工摘要；同题论文默认排除，显式允许才返回。6条固定中文查询在top 3中均命中预期内容，真实闭环15项检查通过，完整回归90项通过。

启动、查询、重新入库和验证范围见[最小检索说明](../docs/minimal-retrieval.md)，机器可读证据见[C2验证摘要](c2-verification-summary.json)。原网页/PDF/论文图像与原始运行证据仍为本地缓存，不代表干净部署已完成；没有新增收费API调用、求解或真实用户确认。下一项为C3独立paper-search MCP。

## 用户明确独立建模边界后的修正（当前口径）

用户认为同题论文会泄漏答案并引导建模方向。已将A163移出活跃来源清单和默认索引，当前3份来源、80个片段；取消显式允许同题论文的路径，在来源准备、入库和查询阶段阻断。旧4份来源、82片段和6查询的验收仅作为历史检索联调记录，不代表当前独立建模语料或独立建模能力。详细规则与使用方式以[当前检索说明](../docs/minimal-retrieval.md)为准，变更见[排除记录](same-problem-exclusion-20261106.json)。当前对话已有论文暴露，新的严格独立试验必须使用新上下文，不带旧方案、摘要和结果。

## C3 与下阶段门槛

独立 `paper-search MCP` 已实现stdio协议服务；启动、工具契约、审计和验证方式见[接口说明](../docs/paper-search-mcp.md)。工具仅检索当前允许的资料，没有同题论文放行开关。当前开发上下文继续完成阶段C；开始D前必须核对[全新上下文独立实验清单](next-stage-entry-requirements.json)，该清单尚未完成，不能以工程测试替代。执行器MCP和工作流MCP接入仍分别属于后续C4/C5。


## C4 执行器MCP（已验证）

独立code-executor MCP提供code_execute与code_execution_status，仅执行服务端登记的不可变任务包；正式任务检查数据库中的当前方案确认、契约版本和输入哈希。禁网、非特权用户、只读输入、CPU/内存/进程/超时限制、临时输出上界、产物验证、幂等回执与清理已实测。真实MCP→Docker 24项检查通过，完整回归119项通过。使用及双MCP分工见[执行器接口说明](../docs/code-executor-mcp.md)，证据见[C4验收摘要](c4-executor-verification-summary.json)。没有新增正式题目求解或真实用户确认。下一步C5工作流MCP接入，C6整体验收仍待完成；C→D新上下文实验门槛仍pending。


## 联网与引用扩展（当前）

paper-search提供paper_search、web_search、web_read和reference_get。已从用户指定目录定位A163，正确标注45张论文图片未转写，读取SciPy原文并绑定引用，进程重启可恢复同一引用。代码解除来源准备、入库、查询、HTTP API的同题硬阻断；可用显式过滤排除已分类同题资料。本地活跃语料不变，旧验收不重写；新增验证未调用LLM或求解正式赛题。


## C5：工作流MCP与引用绑定（当前）

两个MCP经独立stdio子进程接入Workflow；来源、引用、工具记录、讨论和采纳决定绑定任务与契约版本，确认方案时保存来源快照。执行使用版本绑定的登记任务包，未知执行只查status，持久回执后发布结果，仍停在用户结果确认关卡。真实验收固定平方和输出14，仅一次代码派发，注入发布异常后新Workflow恢复无重复执行。17项检查通过，149项完整回归与20项最终针对性检查通过。测试批准均为TEST_SIMULATED_USER，不是用户真实确认；正式任务未改动。下一步C6。


## C6：故障恢复与清理（当前）

24项检查覆盖真实MCP进程退出、孤儿容器接管与超时、镜像/容器缺失、受控注入的清理失败和响应丢失、产物/回执损坏，以及测试数据库连接和checkpoint恢复。10个执行器案例、9个执行claim，另有1个检索故障场景；无本轮容器遗留。完整回归151项通过；本轮未使用LLM、OCR或视觉模型。阶段C可按验收材料审阅，最终用户验收未记录；最新决定已取消强制新任务/空白上下文，进入C验收审阅。


## 阶段C验收审阅（当前）

用户明确取消D前新任务和空白建模上下文的强制要求，论文及网络资料作为带出处的参考思路。已按最新口径完成15项只读证据/状态核查，全部通过，工程范围建议验收通过，无当前阻塞项。最终用户验收已明确通过，D未启动；详见[检查表](stage-c-acceptance-checklist-20261106.json)。历史新上下文要求不再生效，旧门槛已在policy-history保存。


## 用户验收确认

用户已明确回复“确认阶段C通过”，验收状态accepted，见[不可混同于测试模拟的用户确认记录](user-acceptance-20261106.json)。阶段D尚未启动，可沿用现有任务/上下文，保留外部引用与方案/结果双确认。
