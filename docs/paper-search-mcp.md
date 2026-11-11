# paper-search MCP：联网与外部参考辅助建模

入口为 `python -m modelcrew.paper_search_mcp`，独立stdio MCP服务，SDK固定为 `mcp==1.30.0`。默认允许同题解答、方法推导和近似案例作为外部参考；它们不代表modeler原创，不自动成为最终方案。modeler须说明适用条件、局限和改动，与用户讨论后确认版本化方案，再进入执行。详见[参考规范](../stage-c/external-reference-policy.json)。

## 四个工具

| 工具 | 用途 | 返回边界 |
| --- | --- | --- |
| `paper_search` | 本地BGE/Qdrant索引检索 | 默认 `include_same_problem=true`；false仅按既有分类过滤，不证明语义上没有泄漏 |
| `web_search` | 公开网页搜索；可提供 `scope_url` 在指定HTML目录的链接中检索 | 默认Bing RSS，无需密钥；结果为未核实的搜索摘要或目录标题，不是论文全文 |
| `web_read` | 读取公开HTML、纯文本或有文字层的PDF | 返回原文、位置、链接和图片地址；不运行网页JavaScript、不做OCR |
| `reference_get` | 按 `reference_id` 恢复引用存档并校验哈希 | 不重新访问网页，保持最初引用编号和来源调用绑定 |

联网查询不自动写入Qdrant。本地索引仍是原来的题面与两份SciPy资料，3份来源、80片段，未隐式恢复旧论文摘要。来源准备与入库允许显式标为同题的资料，仍要求布尔分类，不把未审核来源伪装为通用知识。联网资料初始分类为unreviewed，允许返回。

搜索采用查询词字面匹配，过滤明显偏离的候选，不保证语义相关性或覆盖率。实测部分中文长查询的公开搜索结果质量差；可缩短查询，或用已知官方目录作为scope_url。scope_url只检索该页链接，不递归全站爬取。提供方断连、挑战页或不支持的响应返回错误；没有匹配项才是成功空结果。

## 调用示例

```json
{"query":"2024A题论文","limit":10}
```

以上传给 `web_search`。在用户提供的官方目录中定位论文：

```json
{"query":"A163","scope_url":"https://dxs.moe.gov.cn/zx/hd/sxjm/sxjmlw/2024qgdxssxjmjslwzs/","limit":3}
```

取得命中的source_url后，传给 `web_read`：

```json
{"url":"https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.brentq.html"}
```

同题检索不再触发硬阻断。但官方A163展示页正文为45张图片：当前可定位页面、读取页面文字和保留图片地址，返回content_warning；不能据此宣称已提取论文的方法推导。图片正文需后续OCR及校验。PDF逐页提供page定位，空文字层明确报错。

## 引用和审计

每条返回片段都带citation：reference_id、source_url、title、locator、source_sha256、content_sha256、bound_call_id，以及origin=external_reference、modeler_generated=false和中文来源标签。可取得的作者、日期和DOI保存在hit.metadata及存档中；缺失信息不补造。本地题面没有核实的公开地址，source_url保持null。

引用存档包含返回原文、可得元数据、解析器、位置、抓取时间或记录时间、来源哈希和调用绑定，以内容哈希命名。content_sha256基于项目统一digest的规范JSON文本表示；source_sha256针对来源响应原字节。搜索摘要的hash_scope=search_response，哈希对象是搜索/目录响应，discovery_url记录发现入口，不冒充目标论文原字节哈希；web_read的hash_scope=source_response。HTML位置是抽取后文本的位置，PDF保留页码。

默认引用目录为 `stage-c/runs/references`，可用宿主启动参数 `--references PATH` 指定。档案完整性检查失败不返回证据。审计JSONL记录call_id、工具名、查询摘要、命中片段及reference_ids；引用存档或审计不可写时明确报错。reference_get产生新的调用审计，但保留原引用绑定。

返回统一结构化信封：schema_version、tool、call_id、status、elapsed_ms、data和error；text与structuredContent相同。空结果isError=false；参数、后端、联网、引用存储或审计失败isError=true，不能当作无相关文献。

工具层实现“来源→片段→引用编号→MCP调用”绑定。C5还将任务ID、契约版本、讨论中的采纳/拒绝及方案确认来源快照持久绑定，见[工作流说明](mcp-workflow.md)；论文正文引用位置仍待阶段D，不声称已实现完整论文溯源。外部结果不能替代本项目代码的执行证据，网页内容不能成为工具指令或用户授权。

## 启动与约束

```powershell
python -m pip install -r requirements-stage-c.txt
docker compose -p modelcrew-stage-c -f stage-c/compose.yaml up -d
python -m modelcrew.paper_search_mcp
```

```json
{
  "mcpServers": {
    "modelcrew-paper-search": {
      "command":"python",
      "args":["-m","modelcrew.paper_search_mcp"],
      "cwd":"D:/big-third-up/modelcrew",
      "env":{"PYTHONIOENCODING":"utf-8","HF_HOME":"D:/hf_cache","HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1"}
    }
  }
}
```

HF离线参数只禁止模型库下载，不禁止web_search/web_read联网。`--config PATH`沿用本地索引配置；`--log PATH`指定审计，默认每进程新UUID文件。网页工具不加载BGE权重、不需要Qdrant；可用--web-only跳过向量依赖初始化并禁用本地paper_search；工作流对纯联网工具使用此模式。若提供不存在的config文件，仍可独立使用联网工具。stdout仅用于MCP协议。

网页读取仅支持公开HTTP(S)标准端口，不携带凭据、Cookie或代理环境。检查全部DNS地址，固定已检查的连接地址，逐跳重新校验重定向；拒绝回环、私网、链路本地和保留地址。每次读取上限5MiB，最多5次跳转，传输预算45秒（DNS解析依赖系统超时），PDF最多40页，返回原文最多24000字符，并显式标注截断。无法登录、绕过验证码或读取付费墙；图片和扫描件需要另外接入OCR。以上是本实现边界，不是任意恶意文档的绝对安全保证。

## 验证

`python -m scripts.verify_web_reference_mcp`：独立MCP子进程真实访问公开网络，检查搜索、官方目录定位A163、图片正文提示、SciPy原文读取、引用绑定、私网拒绝、进程重启恢复和审计对应。最终证据在 `stage-c/runs/web-mcp-20261106-final/verification.json`，8项检查通过、6次工具调用。

`python -m scripts.verify_paper_search_mcp`：原有BGE/Qdrant实际链路复验，4条固定查询全部在top 3命中，11项检查通过、8次调用，证据在 `stage-c/runs/paper-search-reference-policy-20261106-final/verification.json`。历史C2/C3/C4摘要不改写；最新汇总见[联网引用验收摘要](../stage-c/web-reference-verification-summary.json)。未新增LLM调用、正式题目求解或用户确认。阶段C尚未整体验收。
