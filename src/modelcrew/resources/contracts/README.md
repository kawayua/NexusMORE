# 版本化契约与Schema

本目录保存枢模的模型、输入、数学交接、协作和业务接口格式。JSON Schema检查结构、类型与必需字段；语义、数值正确性、证据身份和用户批准由对应业务检查另行验证，不能凭JSON合法直接放行。

| 格式 | 作用 |
|---|---|
| [模型契约1.1](model-contract-1.1.0.schema.json) | 描述问题、输入、单位、变量、假设、方法、输出和检查；旧1.0格式继续兼容 |
| [输入模板](input-templates-1.0.0.json) | 描述表格/数组等观测结构、单位、来源和待澄清项 |
| [数学交接](mathematical-package-1.0.0.schema.json) | 绑定方法选择、论证材料及其业务版本，不能自动证明任意命题 |
| [协作绑定](collaboration-binding-1.0.0.schema.json) | 作者/审查职责、工件、快照及跨版本交接的公共基础 |
| [建模提案](modeling-proposal-1.0.0.schema.json) | 保存建模说明、假设、检验计划及可审阅材料 |
| [业务请求](business-request-1.0.0.schema.json) / [响应](business-response-1.0.0.schema.json) | 业务工具包络、版本绑定、幂等与结构化错误 |

模型契约中应写清输入来源及哈希、约定与单位、给定/派生/假设参数、变量定义域、方法、输出和稳定检查ID。派生值需有依据，字段含义不确定时保留待澄清项。公式是描述性文本，程序不eval公式。

模型或输入变更创建新业务版本并按影响重新确认；解释修订可形成同版本的新结果revision，但结果批准仍绑定实际当前内容。业务版本、请求、执行和结果revision各自关联，不把“用户已确认”作为任意数学JSON字段。

可用`python -m modelcrew validate <模型契约.json>`核对适用结构和关系；数学/物理正确性还需要独立检验。`business-examples-1.0.0.json`为明确未执行的合成请求/响应示例，不是用户批准或真实运行记录。

冻结契约描述格式，不以其中历史适配状态代替当前运行能力；实际工具可用性从`capabilities_read`与MCP工具发现读取。[业务架构](../../../../docs/architecture.md)、[使用指南](../../../../docs/user-guide.md)和[支持范围](../../../../docs/compatibility.md)提供当前产品说明。
