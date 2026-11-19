# 本地 DeepSeek Harness 接入

**当前使用入口（2026-11-19）**：[使用指南](user-guide.md)与[兼容范围](compatibility.md)汇总当前操作；G已按既有本地DSH实测范围验收，干净设备按用户决定在开源后补测。本页下方带日期的实施/验收段落保留历史时点含义，正文与配图的当前交互以合并审阅规则为准。


2026-11-15 更新：**G3 的 DSH 原生可信决定桥接已接通本机 Windows / DSH Desktop 0.2.2-rc.1**。日常可在 DSH 使用 `/nexusmore-review` 完成同一笔业务内容的原生审阅与决定，用 `/nexusmore-review-status` 查询原回执。真实宿主工程流程已验证；尚未替代真实用户业务验收或完整 G5 故障矩阵。新记录见 `docs/release/dsh-trusted-bridge-20261115.json`，下方 G4 与首轮 G4.1 记录按原验证范围保留。

2026-11-15，G4 完成本机 DeepSeek Harness Desktop **0.2.2-rc.1 / Windows** 的实际连接。DSH 自带的 `@deepseek-ai/dsh-mcp-client` 通过 stdio 启动 `modelcrew.workflow_mcp`，在实际 ToolRuntime 中注册 40 项业务工具；两项只读操作已从 DSH 经 MCP 到达 Python 和本地 PostgreSQL。连接及 `/nexusmore` 命令不调用大模型、不运行求解器，也不产生业务批准。工程结果见 `docs/release/dsh-local-connection-20261115.json`。

本次为现有本地开发安装接入，不代表全新 Windows 安装、全部工具的真实模型调用或完整建模任务已验收。Codex、Claude Code 等其他宿主尚未联调。本文后续命令均由本地操作者执行，不登记为模型工具。

## 日常使用

正常打开 DSH，在会话输入 `/nexusmore`，使用命令候选或发送该完整斜杠命令。它由 DSH 人类命令注册表执行，不将该命令作为提示词送给模型；返回注册数量、`capabilities_read` / `projects_list` 调用状态和 G3 确认入口提示。`projects_list` 检查只读取默认上限 50 条的第一页，不把返回数量解释为项目总量。命令不接收参数、附件、工具名、任意 URL 或批准内容。DSH 记录的命令生命周期属于宿主操作日志，不是枢模业务用户事件。

普通聊天可要求 DSH 使用 `mcp__nexusmore__...` 工具开展业务，例如读取能力、项目或任务状态。实际推进仍受版本、幂等、证据及既有质检关卡约束。遇到 `needs_user_input`，在 DSH 输入原生命令（正文和图目录分别选中、分别决定）：

```text
/nexusmore-review --project PROJECT_ID --task TASK_ID
/nexusmore-review --project PROJECT_ID --task TASK_ID --run RUN_ID
/nexusmore-review --project PROJECT_ID --build BUILD_ID
```

也可继续在自己的交互式本地终端回退：

```powershell
python -m modelcrew.trusted_decisions pending --project PROJECT_ID --task TASK_ID
python -m modelcrew.trusted_decisions review --project PROJECT_ID --task TASK_ID
```

论文手可增加 `--run RUN_ID`；汇编用 `--project PROJECT_ID --build BUILD_ID`。正文和选图分别确认，不把聊天中的“同意”、DSH 工具权限弹窗、连接成功或命令执行成功当成批准。`trusted_host_ui` 现仅由下述私有宿主桥接签发；具体边界见[可信用户决定](trusted-user-decisions.md)。DSH 原有 shell / 插件等工具仍由宿主管理，本次不声称将同一 OS 账号下的任意 shell 隔离为不可信主体，也不改动用户的宿主权限偏好。

## G3：原生可信决定桥接（2026-11-15）

新增两个 DSH **人类命令** `/nexusmore-review` 与 `/nexusmore-review-status`。命令仅接收 `--project`、`--task`、`--run`、`--build` 组成的明确对象范围，不能传入决定、理由、身份、事件 ID、原文摘要或任意工具/脚本。原生插件从唯一的既有 `nexusmore-workflow` MCP 注册读取 Python 与工作区配置，固定启动 `python -m modelcrew.dsh_decisions --private-stdio`；不经过模型返回文本，不另开 TCP/HTTP 审批端点，模型 MCP 仍为 40 项工具。

原生问答依次显示“选择待办 → 后端生成的完整审阅与 approve/reject → 理由和原始决定陈述 → 核对对象/版本/哈希/原文并最终确认”。正文与图目录使用不同待办、哈希和用户事件；图目录同意/退回不等同于任意子集选图，尚未实现的 `figures_select`、`final_decide` 没有被此入口补成可用。完整 JSON 审阅投影上限 2 MiB，私有协议帧上限 8 MiB，超过即拒绝并回退本地终端，不截断后继续批准。图文件位置、图目录和正文原文会随既有 G3 投影提供；实际打开图片/PDF、全页检查和独立质检仍须分别完成，不宣称已新增原生全图/PDF 审阅器。

Python 子进程验证私有管道、实际 DSH 父进程、父 PID、安装的适配器哈希和 Python 3.13；主体使用 G3 的实际 OS 进程令牌身份，不读取环境姓名充当身份。宿主实例、原生会话、四轮唯一挑战、后端问题摘要及原始回答链与请求/审阅哈希共同保存在不可变 `mc_trusted_host_captures`，并与 `mc_trusted_user_events` 原子写入。迁移 015 只追加新表和通道约束，不改写旧事件及迁移 014。整轮原生对话最多十分钟；最终捕获前再次加锁核对当前待办、版本与实际字节，提交时再走原 G3 的身份、捕获链、过期、M1 等门禁、单次占用与业务围栏。模型批准保持 `defer_execution=true`，不自动启动求解。

捕获成功不等于业务批准：事件只有在 G3 原生服务通过并提交后，才有对应成功业务回执。最终确认前的跳过、关闭、空陈述、自由文字冒充选项、跨问题/帧回答、取消、超时或内容变化均不提供批准。最终确认后若进程中断或超时，不能据此推断未提交，必须按原请求对账。回调 JSON 本身不是身份认证；该能力仍以可信本地安装、宿主和同一 OS 账号为边界，不能防御已经拥有同账号任意 Python/SQL/安装修改权限的主体，也不是远程多租户身份协议。普通聊天“同意”、模型 `ask_user_question` 的结果和工具权限“始终允许”都不能代替此路径。

发生断连或不确定结果，先用相同对象范围查询：

```text
/nexusmore-review-status --project PROJECT_ID --task TASK_ID
/nexusmore-review-status --project PROJECT_ID --task TASK_ID --run RUN_ID
/nexusmore-review-status --project PROJECT_ID --build BUILD_ID
```

状态命令仅查询当前 OS 主体在该范围最近十笔原生捕获与各自原请求，返回原确认绑定、事件/请求 ID、`authorization_state` 和原业务回执。`captured_unclaimed` 只说明捕获尚未占用，不表示业务已批准；命令不会提交它。已派发但结果不明时，复用 G2/G3 对不可变业务记录的核对，可能补记既有提交的回执，绝不重新派发；确认过期也不撤销已提交决定的历史回执。不得因看到断连而换请求键重复执行。更早记录可按已知事件用 `python -m modelcrew.trusted_decisions status --event-id EVENT_ID` 查询。

实测使用临时固定范围工程插件和隔离数据库，原生 UI 的明确合成“退回修改”两次到达真实 G3/原生核心并各自只产生一条决定；最终取消没有捕获/决定；合成批准因缺独立 M1 被阻断、无求解。宿主重启后经原生状态命令取回原成功回执，事件和占用数量不增加。所有陈述均标注 `TEST_SIMULATED_USER`，捕获元数据标注 `engineering_only`；这不是用户业务批准或独立 M1/P2/W1/W2 验收。临时插件、隔离数据库及临时数据库凭据文件已移除，原 profile 恢复原哈希；日常只保留正式命令。专项覆盖结果执行/修订绑定、正文/选图分别决定、变更/过期/身份和回调篡改、并发与三个真实子进程退出断点；完整宿主故障矩阵仍由 G5 继续。

## G4.1：DSH 原生交互兼容性（2026-11-15）

结论为 **本机 DSH Desktop 0.2.2-rc.1 / Windows 的原生问答机制可以适配**。自编插件可以在 DSH 人类斜杠命令中直接调用 `ctx.userQuestions.ask`，在真实宿主显示中文问题、详细内容、单选与补充文字，并接收返回或取消；无需把指令发送给模型，也不必新增业务网页。首轮只完成交互兼容性验证，当时尚未接通正式用户决定；后续已按上节完成 G3 桥接，首轮记录不充当业务批准。工程记录见 `docs/release/dsh-native-ui-compatibility-20261115.json`。

在 DSH 新会话输入 `/nexusmore-ui-check`，选择命令候选后发送，即可运行固定合成内容的原生卡片。命令不接受参数、不读取待审业务内容、不访问业务决定服务，也不创建可信事件或批准；两分钟仍未完成或会话信号中止时停止等待。可选择“结束检查”或“取消检查”，也可跳过或关闭。只有明确选择“结束检查”才记录工程检查返回成功；自由文字不是该选项的替代。已有 `/api/nexusmore/status` 增加临时 `native_ui_check` 摘要，供检查回读；仅含工程状态与时间，不保存/回显回答或补充文字，重启即清空，不是业务状态源。更新插件文件后需完整退出并重启 DSH，无需改写既有 profile。

真实页面实测覆盖明确选择、取消选项、跳过、补充文字和关闭整组问题；已查看原生卡片截图。页面操作由工程自动化完成，使用 `TEST_ENGINEERING_ONLY` / `TEST_SIMULATED_USER` 标记，不能当作真实用户业务批准。超时、中断、错问题 ID、缺失/多选/未知答案等另有插件测试；没有把单元测试写成真实宿主故障验收。未验证超长正文、完整图集/PDF 审阅或真实用户正式确认。

正式桥接采用原生问答作为表现与回答回调渠道，但需由可信宿主插件直接取得并展示后端生成的完整待办与审阅快照，绑定项目/任务/运行/版本、正文或图目录哈希、决定、理由和原始陈述；正文与选图分别确认。回调还需结合本地 OS 主体、宿主实例/会话、一次性挑战及有效期生成独立捕获证据，最后复用 G3 的再校验、单次占用、幂等及未知结果对账。上述桥接现已按前节实现；任意模型工具结果、聊天“同意”、`actor=user`、自报会话 ID 或普通回答 JSON 均不能签发用户事件。DSH 卡片本身也不是远程身份签名，同 OS 账号任意代码执行的既有信任边界保持不变。

DSH 的工具权限批准服务 `approval.request` 另有权限策略和活动模型 turn 要求，解决的是工具执行许可。正式业务确认不复用其自动允许/始终允许设置；原生模型工具 `ask_user_question` 的返回也不能直接作为业务批准。人类命令直连原生问答经本机实测可用，业务内容和可信证据仍由枢模后端校验。

## 安装与注册

前置条件是项目现有安装、工作区配置与 PostgreSQL 已就绪。完整环境按[安装说明](package-installation.md)准备。此版本 DSH 携带 Python 3.12，不能作为枢模后端；必须选择单独安装的 **CPython 3.13**。枢模仍统一使用 Python，不增加其他数值后端。

在已有项目环境中安装接入依赖（仅新增操作者配置解析所需的 PyYAML）：

```powershell
python -m pip install '.[workflow,dsh]'
python -m modelcrew.workflow_mcp migrate
python -m modelcrew.dsh_integration render --workspace 'D:\big-third-up\modelcrew'
python -m modelcrew.dsh_integration install --workspace 'D:\big-third-up\modelcrew' --profile "$env:USERPROFILE\.dsh\profiles\desktop"
```

以上 `python` 必须是选定的 Python 3.13；可显式增加 `--python 'C:\Program Files\Python313\python.exe'`。更换机器、工作区或虚拟环境时使用本机真实绝对路径，不能复制本机路径后声称适用于所有安装。wheel 安装使用对应 wheel 的 `[workflow,dsh]` extras，接入模块和宿主资源均随包携带。MCP 子进程使用所选 Python 环境内的安装；源码外安装已单独验证资源定位。

`migrate` 只增加缺少的迁移，并报告数据库实际最高版本；当前为 15，不签发用户事件。注册程序先探测所选 Python 是否为 3.13、能否导入工作流/可信桥接服务并核对宿主适配器资源哈希，不连接模型。它只向现有 profile 的 `cordis.patch.yml` 追加带标记的 `insert`，分别登记：

- `nexusmore-workflow`：DSH 自带 MCP 客户端，`serverName=nexusmore`，stdio，无 HTTP 业务代理。
- `nexusmore-connection-panel`：项目自编的只读连接检查、人类斜杠命令及工程检查页。它不注册额外业务 MCP 工具，不提供审批或通用工具代理。

配置固定后端工作区和 UTF-8，工具调用超时 900000 ms；不向 DSH 配置复制数据库口令或模型密钥，也不重写用户的提供商、模型、凭据或其他插件。后端按现有工作区配置读取数据库等设置。DSH 会清理继承环境中的部分凭据变量，不能假设宿主 shell 的全部环境变量必然传给 MCP；需要的配置应按项目工作区配置机制准备。

保存配置不等于已连通。注册结果始终标记 `host_connection_verified=false`。退出并重新打开 DSH 后，通过 `/nexusmore` 实际检查；插件页面可见 `include:nexusmore-workflow` 与自编连接插件，均应为 active。不要仅关闭到托盘后误以为宿主已经重启。

## 保留与回退

注册保留已有 block YAML 条目及其原字节，使用与已核对 DSH 版本一致的 `package.json.lock` 排他创建协议；已有写锁不会被截断、删除或抢占。配置及父目录经过符号链接/junction 时拒绝自动操作。重复注册完全相同的配置不追加；同名 ID / serverName、已更改的管理块、重复 YAML 键、别名、`!!js` / 不支持的标签和非空 flow-list 均拒绝自动覆盖。复杂配置由操作者先检查，不尝试执行 YAML 中的表达式。

写入前在 profile 的 `nexusmore-backups/` 保存原始配置和回退回执，使用临时文件及原子替换，并读回核对。该目录位于用户本地 profile，不纳入本仓库或发行包。返回的 receipt 可用于：

```powershell
python -m modelcrew.dsh_integration rollback --receipt '本地返回的回执绝对路径.json'
```

只有当前完整配置仍与本次安装后的哈希一致，且备份哈希正确时才自动回退；后来存在用户或宿主改动时拒绝覆盖，需人工比较管理块与备份。回退不删除保留的原始备份，也不回滚业务数据库迁移或旧批准。回退后同样需要完整重启 DSH。

## 排错与复验边界

- 找不到工具：检查上述插件是否 active、所选 Python 和工作区是否仍存在、该 Python 是否安装 workflow extra；然后完整退出重启 DSH。不要改成 DSH 自带 Python 3.12。
- 能列出工具但数据库读取失败：检查项目 PostgreSQL 及工作区连接配置，并执行缺失迁移；不把口令粘贴进会话或 Cordis 插件配置。
- `/nexusmore` 不出现：检查自编连接插件的文件是否存在且 active，以及所用 profile 是否为实际运行的 profile。删除安装环境、移动源码目录或只复制一份旧配置会使文件 URL 失效。
- 结果为 `outcome_unknown`：按原请求查询 `operation_status`，禁止换幂等键重发。DSH 的连接重试不等于业务操作重试，断连/故障完整矩阵由 G5 继续验证。

自编工程页位于已认证 DSH 页面同源的 `/api/nexusmore/panel`，按钮调用固定的只读诊断；同源 `/status` 只列注册工具，`POST /diagnose` 通过实际 Host ToolRuntime 执行上述两项读取，并仅返回状态、耗时、数量与摘要。接口继承 DSH Connection 的 owner admission，不绑定新的网络端口、不建立业务状态源。日常入口是 `/nexusmore`，不要求开启 Chromium 调试端口。本次工程自动化通过临时 loopback CDP 驱动真实页面/Remote，核验后关闭调试入口并正常启动 DSH；没有替换、修改或分发 DSH 安装文件，也没有将自编测试替身当作真实宿主结果。

当前已验证 40 项发现、两项实际读取、会话作用域命令和正常重启持久注册；尚未声明其余 38 项经真实模型逐项执行，未发送任何真实模型请求。原生可信桥接的工程实测另见前节，不等同于真实用户验收。G5 将继续验证真实宿主断连、过期/重复调用、故障与产物边界；H 阶段再用真实用户确认完成端到端建模验收。G1—G3 历史记录按当时范围保留，不追改旧结论。


## G4.2 原生连续会话（2026-11-16）

新增无需手填 ID 的原生审阅/回执/下一题按钮，工具回执绑定会话、原生右侧独立输入框、受控继续及导航恢复；见 [说明与验收边界](dsh-conversation-workspace.md)。上文 G3/G4.1 命令与工程页继续保留用于诊断。安装器同时检查 package.json、主插件、可信桥接、会话协调和浏览器资源与所选 Python 安装一致。Windows 首次业务变更的科学依赖初始化已有冷启动回归。
