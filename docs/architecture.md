# 架构与职责

枢模 · NexusMORE 由宿主适配层、共享Python业务核心和受控能力/证据层组成。DSH负责原生对话、文件展示与真实用户消息转交；Python核心负责状态、版本、路由、审批校验和恢复。宿主不是第二套业务数据库。

## 三手与独立质检

| 职责 | 负责内容 | 相关实现入口 |
|---|---|---|
| 建模手 | 问题分析、资料、模型选择、假设与数学论证，包含Planner/Researcher/Modeler职责 | `modeling_hand.py`、`modeling_proposal.py` |
| 代码手 | 最小求解、全量执行、数值检验与结果证据 | `hand_runtime.py`、`docker_executor.py` |
| 论文手 | 经确认结果的中文Markdown、图文证据和修订 | `hand_runtime.py`、`modeling_paper.py`、`writing_handoff.py` |
| 独立质检 | M1/P1/P2/W1/W2各节点独立上下文只读审查当前证据 | 节点派发、快照及回执校验分布在业务核心 |
| 程序编排 | 冻结资料、状态/版本、幂等、暂停与恢复 | `workflow.py`、`business_store.py`、`assembly_builds.py` |

这些是职责与当前实现入口，不是七个常驻Agent，也不增加“总指挥”Agent。作者自检不能替代独立质检，独立质检也不能代用户批准。细节见[三手协作](three-hand-collaboration.md)和[运行接入](hand-runtime.md)。

## 入口与状态来源

DSH适配器位于 `src/harness/`，包内运行副本位于 `src/modelcrew/resources/harness/`。`dsh_integration.py`负责操作者注册和哈希回退，`workflow_mcp.py`提供标准stdio业务工具入口。`business_adapter.py`将工具调用映射到既有业务实现；`business_store.py`保存派发/对账等持久记录，PostgreSQL和业务登记为状态依据。当前MCP开放40项模型通道工具；契约中未开放的操作不能靠提示词变成可用工具。

Python CLI、HTTP和MCP复用核心业务规则，具体可信用户决定只走当前允许入口；不能因为旧HTTP/CLI含有actor或decision参数就当作身份凭证。DSH原生消息与宿主捕获经过版本/完整展示证据绑定，在后端再次检查。实现边界见[业务MCP](business-workflow-mcp.md)、[对话审阅](dsh-chat-review.md)与[可信决定](trusted-user-decisions.md)。

## 从输入到正式文件

用户题面/附件先登记来源与哈希，建模、代码、论文各阶段读取冻结的版本化规范和适用资料。运行通过受控工具读取文件，在Docker内执行Python任务；不在宿主导入模型生成的求解代码。所有状态推进均依赖当前版本与必要检查，人工确认覆盖明确对象和实际展示内容。

结果确认后才进入对应写作；同一run/build与版本的正文/配图可以一次合并确认，后台保存两个原子范围。正式汇编使用批准内容源与已登记图片，执行真实导出、完整页检查和独立W2。图表/正文/数值变更须按影响生成新版本并重新审阅，不覆盖历史成品。

资源入口以 `package_resources.py`、`resource_routing.py`、`hand_guidance.py`和包内清单为准，按需读取且记录内容身份。文件被打包、配置已声明与真正运行接通是不同证据；不把存在性当作功能验收。默认算法字面查询和需额外部署的论文向量检索分别处理。

## 故障与恢复

每次业务修改绑定请求、对象版本和证据身份。重复请求复用原回执；执行未知先查询原状态，不换键重发。响应结构错误、证据引用非法与有效FAIL分别处理，恢复不改写原响应。复核按每attempt一次计账，不增加作者重试或用户批准。

当前是本地单用户架构，非公网服务安全方案。完整审计、私有输入和原始凭据留在用户工作区；共享问题报告使用脱敏复现材料。[排错指南](troubleshooting.md)提供日常处置顺序，[兼容说明](compatibility.md)给出实际实测边界。
