# 检索语料与最小闭环

默认工作方式已按用户最新决定调整为外部参考辅助建模，允许同题解答、方法推导和类似案例，要求引用链接、外部来源标注，以及modeler与用户讨论并确认最终方案。[paper-search MCP](paper-search-mcp.md)现提供本地检索、公开搜索、原文读取与引用恢复；完整规则见[外部参考规范](../archive/research/stages/stage-c/external-reference-policy.json)。

## 本地索引

使用本地BAAI/bge-base-zh-v1.5，768维、归一化、CPU离线加载；Qdrant只绑定127.0.0.1:56333。不调用收费向量或LLM API。当前活跃来源仍为[原清单](../archive/research/stages/stage-c/corpus/sources.json)：题面前两页6个片段、SciPy brentq文档14个、solve_ivp文档60个，共3份来源、80片段。未将网络查询结果自动加入索引。

来源准备和入库允许same_problem_reference=true或false，拒绝缺失分类；同题标签用于来源披露，不再意味着禁止入库。检索与HTTP API默认include_same_problem=true；false过滤同题和未分类片段，CLI对应--independent。此分类过滤不能证明没有隐藏的相似解答，也不保证模型预训练未见题。

```powershell
docker compose -p modelcrew-stage-c -f configs/services/qdrant.yaml up -d
python -m modelcrew.retrieval search "brentq区间端点是否需要异号？" --kind algorithm
python -m modelcrew.retrieval search "brentq区间端点是否需要异号？" --kind algorithm --independent
python -m uvicorn modelcrew.api:app --host 127.0.0.1 --port 8000
```

API POST /search支持query、limit（1至20）、filters（doc_id/case_id/kind/year）、score_threshold和严格布尔include_same_problem。响应保留来源、位置、原文、解析器、哈希与相似度；相似度不是正确概率。空命中HTTP200，索引不匹配或后端不可用HTTP503。HTTP/CLI直接查询只提供原始来源定位；可存档的引用编号由MCP层附加。

PDF按页抽取文字层，HTML取main正文；每段最多360字符、重叠60字符，编码前检查512 token上限。题面官方URL未核实，保留本地来源哈希，不伪造地址。添加有审核分类的新来源后，可创建新版本索引：

```powershell
python -m modelcrew.retrieval prepare --manifest stage-c/corpus/sources.json --output stage-c/runs/corpus-new
python -m modelcrew.retrieval index stage-c/runs/corpus-new/corpus.json --model D:/hf_cache/hub/models--BAAI--bge-base-zh-v1.5/snapshots/f03589ceff5aac7111bd60cfc7d497ca17ecac65 --config stage-c/runs/retrieval-index-new.json
```

输出目录与配置必须是新路径，不覆盖旧证据。模型文件、配置、查询前缀、维度与语料哈希绑定collection，重复入库不重复增加片段，全部写入后发布ready标记。换机器需提供本地题面并调整路径。

## 联网、引用与历史证据

联网工具及调用示例见[MCP说明](paper-search-mcp.md)：web_search可搜索公开网页，或检索指定目录的链接；web_read读取原文；reference_get恢复引用。搜索摘要与原文分开，网页内容是参考数据。图片论文尚未OCR，不能从展示页文字推断已读正文。最终采用外部方法仍须引用，外部结果不能充当本项目执行结果。

早期含A163的4来源/82片段验证，以及后续排除同题的3来源/80片段验证均保留为历史。原[排除记录](../archive/research/stages/stage-c/same-problem-exclusion-20261106.json)不改写，也不再代表默认政策；活跃索引内容未变，仅解除代码阻断并新增独立联网能力。不能把任何一次工具联调重新标为未受提示的独立建模实验。用户已取消C验收后强制新任务和空白会话的要求，见[更新后的阶段门槛](../archive/research/stages/stage-c/next-stage-entry-requirements.json)。

回归命令：`python -m pytest tests --integration -q --basetemp=stage-c/runs/pytest-new --junitxml=stage-c/runs/regression-new.xml`。临时目录选择新路径。真实MCP验证脚本为scripts.verify_paper_search_mcp及scripts.verify_web_reference_mcp；摘要见[最新验收记录](../archive/research/stages/stage-c/web-reference-verification-summary.json)。这些固定检索测试不评估modeler的建模质量，C5工作流和任务/版本引用讨论绑定已完成，见[说明](mcp-workflow.md)；C6故障验证已完成，阶段C用户验收待记录，见[恢复说明](failure-recovery.md)。
