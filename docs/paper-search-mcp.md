# paper-search MCP：联网与外部参考辅助建模

入口为 `python -m modelcrew.paper_search_mcp`，独立stdio MCP服务，SDK固定为 `mcp==1.30.0`。默认允许同题解答、方法推导和近似案例作为外部参考；它们不代表modeler原创，不自动成为最终方案。modeler须说明适用条件、局限和改动，与用户讨论后确认版本化方案，再进入执行。详见[参考规范](../archive/research/stages/stage-c/external-reference-policy.json)。

## 五个工具

| 工具 | 用途 | 返回边界 |
| --- | --- | --- |
| `algorithm_search` | 包内七类算法与几何补充，按ID/名称/类别定位完整章节 | 默认字面匹配，不是向量语义检索；显式旧配置另走严格历史后端 |
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

每条返回片段都带citation：reference_id、source_url、title、locator、source_sha256、content_sha256、bound_call_id，以及来源类型、modeler_generated=false和中文来源标签；网页/论文为origin=external_reference，内置算法为origin=builtin_project_reference。可取得的作者、日期和DOI保存在hit.metadata及存档中；缺失信息不补造。本地题面没有核实的公开地址，source_url保持null。

引用存档包含返回原文、可得元数据、解析器、位置、抓取时间或记录时间、来源哈希和调用绑定，以内容哈希命名。content_sha256基于项目统一digest的规范JSON文本表示；source_sha256针对来源响应原字节。搜索摘要的hash_scope=search_response，哈希对象是搜索/目录响应，discovery_url记录发现入口，不冒充目标论文原字节哈希；web_read的hash_scope=source_response。HTML位置是抽取后文本的位置，PDF保留页码。

默认引用目录为数据根下的 `references/`（默认 `runs/references/`），可用宿主启动参数 `--references PATH` 指定。档案完整性检查失败不返回证据。审计JSONL记录call_id、工具名、查询摘要、命中片段及reference_ids；引用存档或审计不可写时明确报错。reference_get产生新的调用审计，但保留原引用绑定。

返回统一结构化信封：schema_version、tool、call_id、status、elapsed_ms、data和error；text与structuredContent相同。空结果isError=false；参数、后端、联网、引用存储或审计失败isError=true，不能当作无相关文献。

工具层实现“来源→片段→引用编号→MCP调用”绑定。C5还将任务ID、契约版本、讨论中的采纳/拒绝及方案确认来源快照持久绑定，见[工作流说明](mcp-workflow.md)；论文正文引用位置仍待阶段D，不声称已实现完整论文溯源。外部结果不能替代本项目代码的执行证据，网页内容不能成为工具指令或用户授权。

## 启动与约束

```powershell
python -m pip install -r requirements-stage-c.txt
docker compose -p modelcrew-stage-c -f configs/services/qdrant.yaml up -d
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

`python -m scripts.verify_paper_search_mcp`：原有BGE/Qdrant实际链路复验，4条固定查询全部在top 3命中，11项检查通过、8次调用，证据在 `stage-c/runs/paper-search-reference-policy-20261106-final/verification.json`。历史C2/C3/C4摘要不改写；最新汇总见[联网引用验收摘要](../archive/research/stages/stage-c/web-reference-verification-summary.json)。未新增LLM调用、正式题目求解或用户确认。阶段C尚未整体验收。


## 当前算法检索默认配置（F0迁移）

2026-11-15起，`algorithm_search` 默认读取包内七类算法及几何补充，以ID/名称/类别字面匹配返回完整章节。无需算法向量配置；`runs/algorithm-retrieval/` 仅为旧向量维护位置，残留文件不会自动启用。`MODELCREW_ALGORITHM_CONFIG` 非空才显式选择旧后端，校验失败不回退。论文索引配置独立，引用和日志仍沿数据根；历史别名与原文件字节保留。见[入口收口](algorithm-entrypoint-closure.md)。

2026-11-11 已用真实stdio MCP在没有算法配置参数或环境覆盖的情况下查询，命中原Qdrant集合中的Brent算法卡；本批未重建向量索引、下载模型或调用收费模型。迁移及证据见[迁移说明](repository-migration.md#算法检索逐批迁移2026-11-11)。


## 当前论文检索默认配置（后续第一批）

论文检索默认配置已迁至 `runs/paper-retrieval/index.json`。`--config` 优先于 `MODELCREW_RETRIEVAL_CONFIG`，两者均未提供时使用 `MODELCREW_DATA_DIR` 指定数据根下的 `paper-retrieval/index.json`，数据根默认 `runs/`。直接检索入口与MCP一致；显式传入旧索引配置路径时通过登记映射恢复，默认配置缺失时不静默回退。原配置字节与原Qdrant集合不变，未重建索引。

`python -m modelcrew.retrieval index` 默认向同一用途位置保存配置；已有配置会在加载模型/写入向量前拒绝，需显式指定新的配置版本。引用档案和MCP日志已按下一节迁移；语料准备清单仍待后续核验。


## 当前引用档案与日志（后续第二批）

当前默认引用目录是 `runs/references/`，新MCP日志为 `runs/logs/mcp/<服务名>-<uuid>.jsonl`；两者均随 `MODELCREW_DATA_DIR` 改变数据根。`--references` 和 `--log` 仍可显式指定。宿主MCP客户端已移除旧引用目录参数，由子进程采用同一数据根。网页模式不需要加载模型；引用查询仍核验原内容摘要，保留原 `reference_id`、`bound_call_id`、来源和定位。

原 `stage-c/runs/references/` 的23份档案逐字节移到当前引用目录，显式指定旧引用根时只在登记迁移后跟随固定目标；新旧目录并存会阻断。此历史别名固定指向原迁移目标，不会因为更改数据根就复制旧资料；新数据根不会自动汇入旧引用。原 `stage-c/runs/mcp/` 的82份日志封存到本地 `archive/research/retrieval-logs/20261111/`，不再追加；旧文件路径通过精确映射恢复。第三方调用方若直接按旧物理路径打开文件，仍需采用映射接口，不提供文件系统级透明别名。

真实stdio MCP读取全部23个旧编号通过，宿主重启子进程再次读取通过，24次调用均写入新默认日志；执行器MCP也已验证采用新日志默认位置，未派发执行或启动Docker。历史日志及档案105份哈希不变。证据与回滚见[迁移记录](repository-migration.md)。

`--web-only` 禁止加载论文和显式旧向量后端；内置算法查询及引用恢复仍可用。此模式用于不需要嵌入模型的调用，不扩大联网或执行权限。
