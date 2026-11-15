# 多宿主适配与自有业务 JS

2026-11-11 用户修正：枢模面向 Codex、DSH、Claude Code 等宿主；DSH 接入重新设计，三手/质检等业务能力以枢模自有 JS 实现入口。此前将 11 项一概按非运行资源排除的处置不足，已由[重设计记录](host-plugin-redesign-20261111.json)替代。原[静态审查回执](host-plugin-review-20261111.json)及[251项初筛快照](resource-disposition-20261111.json)保留，不能把旧建议当成用户批准。

**当前决定是保留并重设计所需能力，不照搬上游 11 个文件，也不以 Python 包不需要这些文件为由取消宿主适配、界面或自有 JS。** 其中 10 项对应宿主加载、看板、模块清单及安装说明，另 1 项对应枢模业务能力 JS。

| 上游文件（仅作为需求审查对象） | 枢模自主设计的内容 |
|---|---|
| `math-modeling-agent/agent.cordis.yml` | DSH 宿主注册与能力组合。G：按选定 DSH 版本设计注册配置，只暴露枢模能力，业务流程复用枢模。 |
| `math-modeling-agent/package.json` | 自有 JS 模块与发行清单。本轮建立 src/harness/package.json 开发清单；F2/G 再决定正式分发形式。 |
| `math-modeling-agent/plugins/dsh-math-modeling-ui/client/client.js` | DSH 进度与待确认看板。G/H4：自主设计阶段、进度、下一动作和用户确认呈现，不复制上游 UI。 |
| `math-modeling-agent/plugins/dsh-math-modeling-ui/cordis.patch.yml` | DSH 插件加载配置。G：以实测宿主接口设计并验证，不直接搬原补丁。 |
| `math-modeling-agent/plugins/dsh-math-modeling-ui/lib/index.js` | DSH 宿主服务端适配。G：把宿主交互映射到枢模权威接口，不读旧插件 state.json。 |
| `math-modeling-agent/plugins/dsh-math-modeling-ui/package.json` | DSH 看板模块依赖与发布清单。G：按新实现和宿主版本编写依赖清单，不沿用上游依赖通配或许可证声明。 |
| `math-modeling-agent/plugins/math-modeling.js` | 枢模自有业务能力 JS。本轮原创基础入口 src/harness/nexusmore-workflow.js；后续 F6/G 完善能力注册、传输及宿主绑定，不复制旧业务引擎。 |
| `math-modeling-agent/preset.yml` | 枢模预设标识与元数据。G：使用枢模产品标识和已验证的能力描述。 |
| `math-modeling-agent/ui-dock/UI设计与现状.md` | 枢模 DSH 界面设计说明。G/H4：按真实产品交互设计，进度展示与真实用户确认分别处理。 |
| `math-modeling-agent/ui-dock/安装说明.md` | DSH 安装与诊断文档。F3/G/H4：基于固定宿主版本、实际安装及恢复测试编写。 |
| `README.md` | 多宿主安装与使用导航。G/H4：分别记录 Codex、DSH、Claude Code 的配置和兼容边界。 |

本轮已原创 [nexusmore-workflow.js](../../src/harness/nexusmore-workflow.js) 和局部私有模块清单。它提供创建项目/任务、状态、显式恢复、建模运行、代码手/论文手启动和单步推进、产物列表共 10 个操作，逐项映射现有 Python HTTP 业务接口。传输由宿主适配层注入；当前未实现 HTTP/MCP 连接、宿主注册或看板，不能直接宣称已接通任一宿主。

业务分层为：宿主负责工具暴露与真实用户交互；自有 JS 提供统一业务能力入口与宿主交互约束；现有 Python Workflow 维护唯一权威状态、版本、确认、执行及质检。JS 不重建 `.math-modeling/state.json`、不自行判定质检通过，不复制已有编排。未来如确需迁移核心实现，应另立状态与兼容迁移任务，不能在宿主适配中暗中形成第二个权威状态源。

三种宿主共用业务能力契约，分别编写配置/适配与交互层；具体宿主版本和首个验收顺序尚未冻结。DSH 的界面可以自主设计；Codex 与 Claude Code 的工具、交互和确认能力须分别核对并实测，不能假定支持同一套 UI 插件。

本轮基础 JS 不暴露用户批准或正式导出操作。后续可信用户通道接通后，继续保留方案、结果、正文与选图的相应确认，以及独立 M1/P1/P2/W1/W2。模型发起工具调用不等于真实用户批准；actor 字符串仅为审计标签。完整知识路由仍由 F6 完成，正式导出仍按当前审批与同源要求接通。

验证：Node 24.15.0 下 5 项注入传输测试通过，覆盖原样返回待确认状态、请求/版本绑定、未知结果不重试、路径拒绝和单步推进。没有安装外部宿主、调用模型或改变业务数据库；新 JS 尚未加入 wheel/sdist。Node 清单的最低版本声明仍需后续兼容验证。

原始 38 项初筛现在细分为：11 项转为自主重设计范围、27 项待逐类审查（上游测试12、演示图片9、维护文件6）。139 项其他待解决资料本轮未处理。

2026-11-12 优先级更新：用户选定 DeepSeek harness 为首个目标，暂沿用DSH目标键，具体项目身份/版本仍待核验；Codex、Claude Code保留后续，先后未定。此前“首个验收顺序未冻结”是历史状态；本次未实现新传输或宿主绑定。见[当前范围](../model-interface-scope.md)。
