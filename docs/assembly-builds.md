# 通用汇编构建与局部更新

2026-11-10 接入 `modelcrew.assembly_builds` 与 `modelcrew.assembly_compose`。本页承接 [E1 输入冻结](assembly-runtime.md)，不把既有具体论文的W2授予新构建。

## 共用入口

| 操作 | HTTP | CLI operation |
|---|---|---|
| 从冻结输入汇编新稿 | `POST /projects/{project}/assembly-runs/{run}/builds` | `compose --run-id UUID --request request.json` |
| 查询构建及实时依赖 | `GET /projects/{project}/assembly-builds/{build}` | `build-status --build-id UUID` |
| 正文/选图分别确认 | `POST /projects/{project}/assembly-builds/{build}/decisions` | `decision --build-id UUID --request request.json` |
| 正式导出 | `POST /projects/{project}/assembly-builds/{build}/exports` | `export --build-id UUID --request request.json` |
| 实际渲染与机械检查 | `POST /projects/{project}/assembly-builds/{build}/renders` | `render --build-id UUID --request request.json` |
| 核验中断产物并恢复 | `POST /projects/{project}/assembly-builds/{build}/recover` | `recover --build-id UUID` |

CLI 前缀为 `python -m scripts.run_assembly <operation> PROJECT`。HTTP/CLI 使用同一 Workflow 方法和数据库状态，不转发完整聊天历史。

汇编请求含 `request_id`、`actor`、`title`；多题汇编还必须提供整篇 `abstract` 与一行 `keywords`。可提供 `question_titles`、`patches`、`cross_references` 与 `previous_build_id`。所有请求严格拒绝未知字段。`patches` 是显式、逐项留痕的文字/符号编辑，每项含 question_id、before、after、expected_count、reason；匹配次数不符即失败。此入口不判定任意编辑在数学上成立，涉及新模型或新数值结果仍应回上游确认，不能用文字编辑绕过模型/结果门禁。最终机械检查和用户审阅也不能替代科学终检。

## 全局组织与证据

确定性汇编复用冻结的中文单题章节，按当前建模论文规范组织各节，不调用LLM补造摘要、结论或数值。摘要必须基于同一输入集合提供统一全文，禁止将各小题摘要直接堆叠；结论与正文从同一输入集合组织。全局符号、术语和单位调整以明确补丁记录；不以符号同名推断其含义相同。已有标题、参考文献与图表作用保留，数学语义冲突仍须作者处理及重新审阅。

图号按入文顺序排列，所有图文件逐字节匹配冻结来源；不入文的重复候选不混入合编图目录，原候选集仍保留。表和公式分配连续全局编号；未编号的Markdown表格自动生成有记录的题注。LaTeX label/ref 按题隔离。跨题图/表/公式短语需显式映射且实际命中，未知引用或重复定义拒绝。相同文献条目去重；措辞不同但同源的条目必须显式统一，不能仅凭相似文字合并。

`assembly-map.json` 保存映射及编辑记录；`input-binding.json` 绑定各题契约、执行、结果和原W1；`claim-evidence-map.json` 保留原论断、确切冻结文件及JSON Pointer并逐项核验。它是原W1证据的交接，不宣称新编辑已通过W2。每次实际读取并封存写作规范。

## 审阅、导出和恢复

迁移012保存构建状态和不可修改事件。汇编在外部副作用前登记COMPOSING，完成后进入 `WAITING_ASSEMBLY_REVIEW`。正文、选图分别由明确的用户决定绑定当前字节，只有两项均通过才进入 `READY_TO_EXPORT`。不继承原单题或旧合编批准，不代用户提交决定。批准入口沿用本地可信操作者约定，不新增身份认证保证。

导出前再次核验当前上游、源文件与批准，写入持久化EXPORTING声明，再调用已有Pandoc/Tectonic导出器。输出使用新的固定目录，保存PDF、Word、LaTeX、工具/资源/编译记录和完整来源；`assembly-provenance` 同时携带原论断、来源绑定及变换映射。相同请求幂等，不重复执行编译；新请求键才表示明确的新尝试。

成功导出进入 `WAITING_RENDER`。原生Word隐藏实例生成QA PDF，两个格式均实际栅格化，检查边界、字号、缺字/溢出、图号、中文段落和Word原图哈希。记录源PDF/DOCX及适配器哈希，机械通过后进入 `WAITING_W2`，视觉审阅和W2仍标PENDING/NOT_RUN。Windows本机需可用Word；缺失或渲染失败保留日志并停在RENDER_FAILED，不伪造检查通过。

进程中断后查询会显示RECOVERY_REQUIRED。恢复只核验已完成构建清单及其源绑定，完成确定性的来源复制和状态提交，不重发不确定的编译。产物不完整时保留失败现场，使用新导出请求键重试。汇编或渲染中断同样保留现场，明确结束失败尝试后用新请求创建新尝试，不覆盖旧目录。源修改、上游过期或封存字节变化一律拒绝下游推进。

## 局部更新

上游版本变化先由D形成新的有效批准，再用E1 `previous_run_id` 创建新输入快照。新构建通过 `previous_build_id` 引用旧构建。每题缓存身份覆盖完整来源、绑定、编辑补丁和汇编器版本；身份和字节均一致才复用规范化章节。改变一题时只重建该题的规范化内容，无关题的缓存字节保持一致；摘要、结论、编号和引用从同一新版本重新组织，最终整篇排版重新编译，旧通过版本及其批准不覆盖。

`update-report.json` 给出复用题、重建题和需重做的全局产物。旧W2不授予新构建；未变的来源仍可作为证据，受影响检查在新构建上重新完成。当前实现未增加通用W2供应商调用或自动视觉语义审查，不宣称整个E阶段已经验收。


## 摘要单页验收

正式排版实际读取五份章节/格式/中文模板文档并保存设置映射。标题、整篇摘要、关键词应在第一页完整呈现，正文从第二页起。LaTeX 编译后及原生 Word 渲染后分别检查，超页失败，不以缩小字号或字符数估计替代验收。`stage-e/reviews/abstract-one-page-20261110-v1` 是本次新摘要审阅版本；实际新分页与独立 W2 尚未完成。配置/汇编器变化后须按当前绑定新建有效构建，不改写历史批准。


## 全局符号表约束

整篇汇编论文只设置一个全局“符号说明”章节和一张统一符号表，集中放在模型假设之后、各题模型建立之前；不得按“问题一／问题二”分设符号子表。表中列明符号、含义、单位及适用范围，必要时补充维度、下标或定义域。相同含义且单位一致的符号核对后合并；同名异义或单位冲突必须先明确重命名或作用域映射，并同步更新正文、公式、图表及引用，不能仅凭符号同名自动合并。题目专用符号也收入同一表，用适用范围列区分；模型附近可解释局部新记号，但不得再重复铺设小题符号表。

这是正式汇编验收要求。汇编器现已生成一张全局符号表，并将各题原符号表的表号引用映射到该表；相同定义原文可确定性合并，定义措辞不同或组合符号有重叠时要求显式映射。单位冲突、来源不全、未处理分量或重复符号会拒绝汇编。映射包含来源行、处理理由与适用题目；它不能代替独立数学审查。既有通过稿和来源材料保留。


`symbol_table` 是可选的显式全局行列表；需要处理非完全相同的定义时必须提供。每行含 `symbol`、`meaning`、`unit`、`sources`（每项为 `question_id` 与原始 `symbol` 单元格）、`reason`，可加 `applicable_questions`。组合行可拆分，同一来源定义可支持多个分量，但每个分量必须覆盖，单位逐项核对。新符号或重命名须先通过有记录的源章节 `patches` 修改，不能只改表头掩盖正文冲突。含额外定义说明的原符号节需先显式整理，不能静默丢弃。

多题 Markdown 检查及正式导出门禁已增加全局符号表结构检查：只能有一个符号说明章节、一张含适用范围的逻辑表，不得含小题子标题或重复符号。缓存和构建身份同时绑定汇编器、符号适配器、版式辅助及机械检查实现，相关代码变化后旧绑定不能推进。

本次新审阅稿及来源核验见 `stage-e/reviews/global-symbol-table-20261110-v3`。该稿从冻结来源重组，未向旧上下文绑定的数据库构建写入新批准；重新绑定、当前正文/选图决定、正式导出和 W2 仍按原门禁执行。

## 通用独立 W2 派发（2026-11-10）

`Workflow.review_assembly_w2` / `POST /projects/{project_id}/assembly-builds/{build_id}/w2-reviews` 接收 `request_id`、`actor`、`export_request_id`、`render_request_id`。只有当前正文和选图批准仍有效、指定正式导出已完成、同一导出的 LaTeX/Word 实际渲染均机械通过，才能进入独立 W2。状态从 `WAITING_W2` 推进到持久化的 `REVIEWING_W2`，再按实际回执进入 `W2_PASSED`、`W2_FAILED`、`W2_BLOCKED` 或 `W2_INVALID_RESPONSE`，不会替用户接受新导出。

程序创建新的审查身份和上下文、只读快照及 W2 票据，封存正文、图目录、两个正式文件、所有实际页面图片、编排映射及原 W1 论断的精确 JSON 证据值。供应商请求是新的无历史请求，使用原生 `image_url` 多模态内容逐张传入实际页面，不把路径字符串当成看过图片。`MODELCREW_W2_MODEL` 可显式指定视觉审查模型；未配置时沿用既有模型。接口只证明真实发送了图片并校验回执覆盖，不保证供应商的视觉理解或科学判断总是正确。

回执必须完整覆盖 claims、figures、citations、layout、snapshot_consistency 五项，逐页列出两个格式的每一页，证据 ID 及 JSON Pointer 必须实际存在；漏页、重复页、矛盾状态、看不清却报告布局通过、未知证据或未处理 error/blocking 问题均拒收。供应商原始 FAIL/BLOCKED 和不合法回复均保留；程序不修补它们来得到 PASS。失败问题按原始领域给出返工目标；原响应、票据、快照、请求及页面哈希保留，后续篡改使构建失效。

派发前先提交 operation claim。进程中断时同请求及 `/recover` 只读取已有完整原响应和其哈希，不重发不明结果。ReadTimeout 等可能已交付的情况停在 `W2_RECOVERY_REQUIRED`。ConnectError/ConnectTimeout 只有在持久元数据证明没有 HTTP 交付时，可调用 `/w2-reviews/{request_id}/retry-delivery`，携带新的重试键、actor 和理由，显式恢复一次交付；普通重复请求不自动重试。旧未知状态仅在同样证据证明未连接时允许此路径。

已拒收、FAIL 或 BLOCKED 的完整回复最多允许一次独立只读复核：新请求明确提供 `recheck_of` 和 `rationale`，目标须为同一导出及渲染，新审查身份、新上下文，原结论不变。不允许复核 PASS，不允许用新键无限发送，也不能借复核重发未知传输。复核再次不合格后明确保留 `W2_recheck_exhausted=true`，交人工处理或修订后的新构建。

本次真实联调使用 `f1439991-85bd-4f8c-b753-c69010d4ff91` 的新通用导出及两个格式各 27 页。首次服务端回执与唯一复核均因引用不存在的证据或无法解析的指针而拒收，不能登记 W2 PASS。此结果证明派发及阻断实际运行，不代表供应商已经通过最终论文质量审查。原用户验收的 `global-symbols-20261110-v6` 与其独立 W2 不受影响。实际记录见 `stage-e/implementation/20261110-w2-v1/`。


## W2 证据协议修复

新操作默认使用2.2版登记引用协议，证据和页码由程序编号，模型只选择编号；程序精确验证后生成原生回执，问题类别按预先声明的映射路由。当前服务不支持json_schema，默认发送其支持的json_object，仍执行全部本地约束，失败后不静默切换模式重发。详见[证据引用协议](w2-evidence-protocol.md)。54页真实协议资格验证通过，供应商原结论FAIL完整保留；资格验证不创建正式W2回执、不重置旧复核次数，不改变已验收论文。

## 已验收交付的显式登记与局部复审绑定

2026-11-10新增一次实际登记：新构建 `10e0161b-7d8a-4bf6-bdac-f2c39943d80a` 通过现有compose生成（Q1 rebuilt、Q2 reused），以 `ACCEPTED_DELIVERY_REGISTERED` 状态关联已验收Word和其直接导出PDF、真实用户决定及独立局部W2。实现与审计见 `stage-e/implementation/20261110-runtime-registration-v1/register_accepted_delivery.py`；这是可信本地专用操作，不是已发布的通用HTTP/CLI导入API。

登记使用独立 `accepted_deliveries` 命名空间和不可修改构建事件，严格核对批准文件和W2哈希。构建正文与用户批准稿只允许CRLF/LF规范化差异；全部图条目和资产必须相同，图来源证据仅允许缓存身份及有记录的正文编辑差别。保存原决定和转换证明，不创建新用户批准或供应商回执。当前 `/build-status` 返回新阶段、审阅有效性与复用情况；完整接受交付详情保存在数据库payload和登记文件，尚未增加专用通用API响应。

局部W2记录范围为新Word及Word直接导出的PDF，绑定旧全篇独立PASS；专用统一72/144dpi比较仅第13、16、27页变化，未变页依旧审查与一致性证据继承。不得将该结论用于未生成的新LaTeX，不改变父构建W2失败或复核次数。E剩余验收以 `stage-e/implementation/20261110-runtime-registration-v1/e-stage-acceptance-checklist.json` 为准，上文旧案例中的“尚未接入/完成”描述仅反映当时范围。

### 解释修订后的上游版本继承

解释修订使用真实的结果 revision，不改写 execution 或原数值 P2。`modelcrew.result_lineage` 只在新 revision 已获用户确认、结构化主张重新核验、独立 P2 解释审查精确绑定完整主张集，以及原数值 P2 的快照/冻结包/契约绑定均有效时接纳继承。登记是追加的本地审计事件，不伪造原始结果的 review kind 或供应商回执。Writer 仍需重新完成相应 W1。

当后续题引用了旧结果，不能将其当成无关题。`modelcrew.reference_lineage` 在独立 M1 影响审查通过、源 execution/契约及历史材料逐项未变时显式保留原引用；不改写原引用绑定，不授予新的下游模型或结果批准。否则普通失效规则继续生效。

E1 对旧版已审章节与当前章节混合汇编时，按 `snapshot/<question_id>/...` 分别冻结同名资源；`snapshot_root` 统一解析，旧版共享目录仍兼容。新结果必须进入新 E1 和新 build，历史版本不覆盖。实测链见 `stage-e/implementation/20261110-upstream-continuation-v1`。
