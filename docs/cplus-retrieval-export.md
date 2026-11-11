# C+ 检索与导出接口

实现状态及完整验证见 [C+ 独立记录](../stage-c-plus/README.md)。新增工具通过既有 `paper-search` stdio MCP、`retrieve-references` API/CLI 和 Workflow 使用，不建立第三个 MCP server。

```json
{"tool":"algorithm_search","arguments":{"query":"连续资源分配线性规划","limit":3,"category":"optimization","layer":"model","facts":{"linear_objective_constraints":true,"continuous_variables":true},"variable_count":2,"available_dependencies":["scipy"]}}
```

任务检索仍须携带版本、actor 和 request_id，并限于尚未确认的模型版本。引用进入 `mc_references`，讨论理由进入 `mc_reference_discussions`；重复请求返回原记录。正式已完成任务不会因新检索悄悄改变方案。返回值包括 `index_read`、`hits`、`excluded`、`interpretation`；每个 hit 带算法卡片、前提检查、完整关联原文和引用收据，外部来源标记 `modeler_generated=false`。

当前算法资料集仅六卡，覆盖三类结构；其余算法不因七类原始资料内置就自动可检索。原始说明的公开再分发许可未建立，继续作为本地参考资料使用，不在本次发布中扩大传播。网络论文/网页入口不变，用户允许同题参考，仍需外部链接、讨论与最终方案确认。

导出器是独立可复现脚本，读取 B+ 审核基线并保持原公式和稳定 ID。绘图从已确认历史数组计算离散残差，不改变数学包或原确认；表达式和图均绑定来源哈希。结构合法与有限数学审查分别报告；任意新题目不能靠这两份固定导出探针自动判为数学通过。跨题动态 Writer、任意中文全文排版和多模态读图不在此次验证范围内。
