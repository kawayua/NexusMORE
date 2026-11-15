# 模型接口与首个宿主范围

2026-11-12 用户选定 DeepSeek、ChatGPT 等模型接口，首个 harness 为 DeepSeek harness。机器范围见 [接口范围配置](../configs/model-interface-scope.json)，总范围见 [发布范围](release-scope.md)。本次冻结目标与优先级，不登记供应商或宿主兼容性通过。

## 模型接口

首发采用现有 HTTPS JSON Chat Completions 路线，客户端在配置的 base URL 后追加 `/chat/completions`。目标为 DeepSeek、OpenAI 模型 API，以及逐端点核验的其他兼容服务。用户所述 ChatGPT 在项目范围中登记为 OpenAI 模型 API，不以网页账号、订阅或浏览器操作替代 API 配置。模型 ID、端点和密钥由用户配置；本次不读取或修改真实密钥，不发起收费调用，不默选具体模型版本。

当前客户端接收非流式文本响应，按阶段解析 JSON 或 Markdown，并由本地契约校验。供应商 JSON/schema 模式、图像输入、上下文及输出限制需要按模型验证；不能把协议名称等同于全部参数兼容。当前 `model_client.py` 与 `drafts.py` 无条件发送 `enable_thinking`、`thinking` 扩展字段，仍需供应商请求适配。该问题保留为明确实施待办，本次不把配置登记描述为已接通。

P2/W2 的图像证据与全页审图要求不因模型选择而取消。所选模型缺少相关能力时应明确阻断，或使用用户显式配置并验证的审查模型；不得静默切换供应商、伪装读图或省略独立审查。本范围不接通 Responses API、流式输出或原生模型工具调用；它们与宿主 MCP 工具协议分别处理。

## 首个 harness

首个目标为 **DeepSeek harness**，已通过本机安装包确认对应此前 **DSH** 目标键，Codex、Claude Code 保留为后续目标，二者先后顺序未定。DeepSeek 模型服务与 DeepSeek harness 是两个独立适配面，不能凭模型请求成功宣称宿主接入成功。

已只读检查用户指定桌面安装：`@deepseek-ai/dsh-desktop`，版本 `0.2.2-rc.1`，构建 `c59d10aff167ad7eefead4b3a9082fb57c8fbfe8`，nightly 通道；包内 MCP 客户端包含 stdio 和 Streamable HTTP 实现。首个目标固定为该桌面版本，真实协议联调与用户确认仍待 G 验收；更新桌面版本需重新记录兼容证据。仓库地址尚未独立核验。详见[本机安装核验](release/deepseek-harness-desktop-review-20261112.json)。DSH 入口及界面按枢模重设计，不复制原插件；业务状态、三手、独立只读质检和用户确认继续由枢模权威业务层维护。

后续验收须分别记录供应商/模型的请求与失败分类、结构化输出与图像能力，以及首个宿主的工具发现、可信用户确认、暂停恢复和产物读取。用户选定目标不替代这些实测，F1 整体尚未验收。

桌面端附带Python 3.12环境，不能作为枢模后端解释器。接入配置必须显式使用枢模的CPython 3.13路径，宿主内置Node 24.21.0与Python环境独立。安装目录只是本机发现依据，不写入其他用户的必需运行路径；本次未修改桌面端或用户配置、未启动模型会话。
