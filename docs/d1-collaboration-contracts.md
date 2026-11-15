# D1：三手交接与独立质检基础接口

2026-11-15 检索入口收口：新业务默认使用包内七类算法及几何补充，建模手、协作函数和MCP algorithm_search已统一。默认无需旧catalog、BGE权重或Qdrant算法集合；查询方式为ID/名称/类别字面匹配，尚未重建113算法向量语义索引。显式指定旧配置仍严格核验旧来源，不静默切换。见[入口收口说明](algorithm-entrypoint-closure.md)。

下文六卡片及uncovered描述是D1历史范围，不能作为当前默认入口说明。

D1 实现范围是交接契约、能力准入、上下文组装、质检派发记录及回执准入。实际建模手、代码手、论文手的 LLM 调用、LangGraph 节点和数据库用户审批分别在 D2—D5 接入。本模块不推进既有正式任务，不创建用户批准，不把结构检查称为数学审核。

## 三手交接

| 主 Agent | 输入与输出 | 允许请求的能力 |
|---|---|---|
| 建模手 modeling | 原题/输入、依赖已满足的结果 → 小题依赖图、来源采纳、选法、契约、数学包 | 算法/资料检索、提出契约、请求 M1 |
| 代码手 coding | 已确认且 M1 有效的契约、冻结输入、必要来源 → 代码、执行回执、结果、候选图、复现信息 | 算法检索、代码登记、受控执行/状态查询、请求 P1/P2 |
| 论文手 writing | 已确认且 P2 有效的结果、契约、引用/图件 → 大纲、Markdown、选图清单、排版输入 | 加载写作上下文、生成 Markdown、请求 W1/W2 |
| 临时质检 quality | 冻结证据快照与必查项 → 只读审核回执 | 读取快照、提交回执 |

`modelcrew.collaboration` 从现有 workflow.json 校验三手职责映射和独立质检政策。`require_tool` 提供拒绝未授权能力的接口，包括拒绝任何 Agent 代替用户确认。它是供工具适配器调用的准入函数，不是操作系统沙箱；后续真实节点必须在工具分发处调用，不能只把权限写入提示词。

`Binding` 绑定 task_id、contract_version、contract_sha256，结果阶段增加 execution_id 与 result_revision。同一 context_id 只能属于同一组绑定，调用身份注册后不可修改；不同 call_id 复用作者上下文也不能通过独立质检。

`Artifact` 记录 workspace 相对路径、类型、字节 SHA-256 及作者调用；`Snapshot` 保存明确的工件列表和完整作者/修改者 lineage。上游契约作者可使用无 execution_id 的模型阶段绑定；有执行/结果绑定的贡献者必须与当前快照一致。后续编排器负责从实际调用自动登记完整身份与 lineage，不能信任模型自报。此接口不认证模型供应商身份，也不证明隐藏上下文或供应商端会话确实隔离。

`handoff` 只允许建模手→代码手、代码手→论文手的正常前向交接；返工由后续程序路由处理。代码手输入至少包含 contract/input，论文手至少包含 contract/execution/result。`context` 只返回清单列明的工件，不收集周边目录或聊天历史。它始终标记 `requires_authoritative_user_approval=true`：D1 清单既不是方案批准，也不是结果批准；实际执行/写作入口必须在后续节点连接 B/C 权威记录复核。

## 质检与回执

`dispatch_review` 保存 Ticket，并校验检查点所属手、最低证据种类、任务/版本绑定、作者/修改者上下文隔离。M1 需要契约/数学包；P1 需要代码/输入/执行/结果；P2 还需图件/复现；W1 需要大纲/契约/执行/结果；W2 需要正文/图件/实际渲染。除 M1 外均需 execution_id 和 result_revision。

派发记录绑定当前 workflow.json 哈希和固定必查项。它是程序派发契约，不会自行调用模型。后续适配器实际执行独立调用后，才能生成真正的语义审核结果。

`accept_review(receipt, current_snapshot_key)` 重新检查任务绑定、文件字节、质检身份、政策和当前快照，再验证：

- 检查项齐全且不重复；PASS 必须有来自快照的 artifact_id 和非空位置选择器。
- 总状态与逐项状态一致；FAIL 优先于 BLOCKED；不能带未解决 error/blocking 问题声称 PASS。
- FAIL/BLOCKED 必须记录问题、责任目标和复验入口；模型→建模手，实现→代码手，写作→论文手，基础设施→恢复路径。
- 拒绝过期快照、旧政策、错题错版本、错审查者、文件变化和空报告。实际选择器的语义及证据是否足以支持结论由独立审查负责，D1 不伪称已验证任意 JSON 路径、表格坐标或数学论断。

相同审查者可以复验，但其上下文一旦加入作者/修改者 lineage 就不能继续独立审查。能力表禁止质检修改权威工件。审查者实际读写隔离由 D2+ 调用与工具适配器实现。

## 保存与恢复

`CollaborationStore` 在调用者指定的新工作区目录内，以内容哈希保存 JSON。原子发布、不覆盖已存在对象；每次加载重验 JSON 哈希。调用标识和上下文绑定通过原子链接登记，避免并发重复身份声明。重新创建 Store 可以加载已保存清单和回执。

这是 D1 的本地审计记录层，不是 PostgreSQL 业务迁移或 LangGraph 等待节点恢复；相应持久工作流集成在 D2—D6。旧契约 1.0.0/1.1.0、旧审核 unknown 规则和历史事件不改写。新契约使用独立的 `contracts/collaboration-*-1.0.0.schema.json`。

## 算法上下文

`modelcrew.collaboration_retrieval.algorithm_context` 先实际读取算法索引，再读取现有 C+ 卡片对应的原文范围，复用 `verify_sources` 与 `assess` 检查来源、公式前提、规模和依赖。返回卡片哈希、原文位置、来源核验状态、引用标识、适配条件及待建模手采纳状态。

当前保留 6 张卡片：几何模型、带括标量求根、连续 LP、整数 LP、初值积分、brentq API。新增 `resources/algorithms/hand-card-profiles-1.0.0.json` 作为兼容补充，绑定每张原卡哈希，记录输入/单位、步骤、停止条件、失败状态、最小示例规格及验证方法；不改写原 catalog、索引和 Qdrant 内容。示例和补充资料明确未在 D1 执行，既有核验状态保持原口径。

几何/优化/仿真有卡，其余五类明确返回 uncovered；条件失败返回 no_applicable_cards，未知前提保留 needs_review。资料全文已内置不表示已拥有该类结构化卡片。10—20 张是工作量参考，本轮复用 6 张直接相关卡片，不以扩充数量充当验收。

此入口是显式类别/卡片选择，未实现自主题型判断或新的语义排序。现有 paper-search MCP 的 algorithm_search 继续承担向量检索，D2 将接通建模手调用及采纳/拒绝讨论。

## 使用与复核

```python
from modelcrew.collaboration import CollaborationStore
from modelcrew.collaboration_retrieval import algorithm_context

references = algorithm_context('geometry', card_ids=['bracketed-root'])
# 未提供连续性等事实时，前提状态为 needs_review。
```

```powershell
python -m scripts.verify_d1_collaboration --output stage-d/d1/new-verification
python -m pytest tests/test_collaboration.py -q --basetemp=tmp/new-d1-tests -p no:cacheprovider
```

演示输出目录拒绝覆盖。演示实际读取项目算法资料，但所有调用身份、契约和审核结论均为明确标注的合成样例，用于验证结构、拒收和返工记录；没有真实独立 LLM 质检、付费模型调用、新题求解或用户批准。
