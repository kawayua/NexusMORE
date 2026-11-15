# 新旧算法检索入口收口

2026-11-15完成开发源码环境下的入口统一。新业务默认使用安装包内七类算法规范目录（113个去重算法）与项目几何补充；旧六卡向量目录保留为显式历史后端。之前3项旧协作入口回归失败已修复，旧catalog、配置、来源、批准和P1回执不改写。

## 当前入口

| 调用 | 当前默认行为 | 历史调用行为 |
|---|---|---|
| 建模手 | `algorithm_lookup.builtin_context`，使用当前内置目录，按规划选中章节 | 既有运行读取原冻结algorithm-context及来源，不重新生成 |
| `collaboration_retrieval.algorithm_context` | 委托同一内置上下文 | 显式catalog_path进入旧核验，不重签旧哈希 |
| `AlgorithmRetriever` / MCP `algorithm_search` | 内置ID/中英文名称匹配或显式类别浏览，无嵌入模型/向量集合 | 显式config或MODELCREW_ALGORITHM_CONFIG选择LegacyAlgorithmRetriever，失败明确返回错误 |
| full诊断 | 校验包内算法资源并报告installed_literal_lookup | 显式旧配置仍核查其catalog/index/embedding绑定 |
| 旧向量维护脚本 | 不作为默认入口 | index_algorithms、prepare_algorithm_catalog和verify_cplus_retrieval须显式提供相应输入/新输出 |

`retrieval_paths`保留的algorithm-retrieval默认路径仅用于旧文件维护和精确迁移映射。没有显式配置时，即使此处残留旧文件，也不会被默认查询加载；显式配置缺失/过期/损坏时同样不会偷偷换后端。项目未替用户清除设置或重建历史集合。

## 返回与准入

查询先读包内索引，再按真实规范ID、名称或类别选择资料，最多返回请求限额内的完整章节，并记录文件/章节哈希和真实行范围。分值仅是字面匹配权重，不是语义相似概率；无匹配成功返回空列表，资源损坏/归档或审计失败返回错误。旧verification状态不授予新算法版本，新版未认证的旧状态过滤要求明确返回排除原因。

明确错误的前提会排除候选，例如连续性为假拒绝带括求根，连续变量为假或存在整数变量时拒绝连续LP。自然语言数学条件即使收到“已核实”布尔声明，也仍保留needs_review，不能当作已证明。规模、示例依赖和固定案例不登记为通用业务求解器。

内置资料引用标记为 `builtin_project_reference`，中文标签为枢模内置算法资料；网页/论文继续 `external_reference`。两类均保留真实来源、原文摘要、reference_id、bound_call_id和modeler_generated=false。reference_get恢复原引用及原来源类型；旧档案不改写。工作流只对算法/引用恢复入口允许内置类型，网页/论文入口不借此改称自有资料。

## 实测与恢复边界

回归包括七类覆盖、旧函数默认迁移、错误前提排除、空结果/资源失败区别、旧配置坏时不回退、当前索引先读、引用署名与恢复、无旧索引的工作区stdio查询和诊断。向量层保留独立的合成夹具测试：测试内临时绑定当前索引验证向量/防篡改行为，不改磁盘上的历史catalog，不冒充历史材料重新验收通过。

`python -m scripts.validate_algorithm_entrypoints --output NEW_WORKSPACE_DIRECTORY`提供真实stdio、引用归档、真实PostgreSQL工作流和幂等验证；不调用模型、不求解、不创建任何用户批准。真实业务任务仍停在 `GENERATE_FULL`，既有批准、M1和P1状态保持。完整机器证据见[收口回执](release/algorithm-entrypoint-closure-20261115.json)。

本批没有建立覆盖113个算法的向量语义索引，也没有开始全量情景、候选图、P2或论文手。独立安装候选尚未重建，本结论限本机开发源码与已运行的入口测试；F5暂缓、全新Windows验证例外与公开发行门禁不变。

最终回归分组：相关入口205项通过、1项因系统符号链接权限跳过；真实PostgreSQL流程41项通过；113规范ID逐项定位与包资源组30项通过。组间存在重叠，不相加为总测试数。最终真实验证含11次stdio调用、1次工作流MCP调用及引用入库/幂等；七类均命中，错误前提和空结果按预期处理。173份受保护文件哈希一致，资源227项校验和目录最终检查通过。修复过程中的早期失败日志原样保留。
