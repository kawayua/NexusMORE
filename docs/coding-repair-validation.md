# 最小代码定点修复验收

2026-11-15 检索入口收口：新业务默认使用包内七类算法及几何补充，建模手、协作函数和MCP algorithm_search已统一。默认无需旧catalog、BGE权重或Qdrant算法集合；查询方式为ID/名称/类别字面匹配，尚未重建113算法向量语义索引。显式指定旧配置仍严格核验旧来源，不静默切换。见[入口收口说明](algorithm-entrypoint-closure.md)。

2026-11-14，按用户“进入修复环节 按点修复”执行。任务 `production-allocation-live-20261114`、版本2、原代码手运行 `4b5d1f79-d7ef-4bb1-ba59-1706b4fbaa93` 保持不变。修复后真实Docker最小执行成功，新的独立P1五项PASS，运行停在 `GENERATE_FULL`。F6.6仍待全量、复跑/P2、真实用户结果确认、论文手及后续门禁。

| 问题 | 修复及实测 |
|---|---|
| JSON按不存在的parameters字段读取 | 使用products和三组实际数组按产品名映射；核对工作簿、题意、冻结契约及全部输入哈希，缺失/维度/不一致显式失败 |
| 对偶精确零比较误判 | 原样记录有符号松弛、单位和逐组件float64舍入界；不取绝对值、不夹零；保持原可行性1e-7和收益/间隙1e-6。真实负证书变异仍拒绝 |
| 最小阶段提前求解11情景 | 只读11情景输入作一致性核对，真实HiGHS仅求解一次基准；情景求解0、图片0，明确整体未完成 |
| 核验failed但退出0 | 持久化失败JSON并返回2；6个隔离Docker负例覆盖缺字段、错维度、跨文件数值冲突、重复产品、非有限输入及真实无效对偶，全部按预期拒绝 |
| 自动预算耗尽后没有正式接续 | 新增modelcrew.hand_repair，Python/HTTP/CLI共用显式本地人工导入；冻结新代码/来源、独立作者与新作业/审查，retries仍为3，旧记录不变 |

基准重新计算得到产量 `[40,20]`、收益 `[2200]`，未硬编码最优解。原约束回代资源松弛 `[0,0]`，收益回算和二维顶点枚举一致；对偶绝对间隙0。对偶原松弛第二项 `-3.552713678800501e-15 CNY/unit`，对应舍入界 `8.526512829121202e-13 CNY/unit`，作为同一数学检查的浮点实现处理，不更改已批准物理模型或检查容差。

新P1回执SHA256为 `7ec079431e76ba291792e8edaac7aa0a3598ac150eed77797f189cdfd38f1d8e`，execution/input_output/constraints/numerics/units五项PASS。本次仅一次真实模型调用，为新的无作者聊天只读P1；人工修复代码如实标记operator_supplied_code，不登记为新Coder供应商生成。生成时result.json中的pending_independent_P1标签保留原字节，实际P1通过状态另由新独立回执证明。

本地详细证据位于 `runs/acceptance/production-allocation-live-20261114/coding-repair-v001/`：原始修复请求、新代码、导入回执、真实Docker回执、最小输出、P1和保护核验。117份原代码/回应/输入/回执文件哈希一致，原数据库操作与审查记录保持相同；自动重试保持3，人工修复轮次单列，未重新登记模型批准，未产生业务完整结果/执行登记或结果批准。

流程测试使用真实PostgreSQL与明确合成供应商/执行器夹具，独立于上述真实Docker/P1；相关报告由[机器回执](release/coding-repair-validation-20261114.json)给出。旧失败与旧冻结报告不改判。当前仅开发源码环境验证，本批未重建私有发行包；F5暂缓、全新Windows验证例外及公开发行门禁不变。

本次完整运行流程回归34项通过（真实PostgreSQL、合成供应商/执行器），其中人工修复专项7项通过；相关程序回归68项通过。扩展协作/包资源测试65项通过、3项失败：旧 `collaboration_retrieval.algorithm_context` 仍读取 `runs/algorithm-retrieval/catalog.json`，其冻结index哈希与现行包内索引不同，被保护校验拒绝。新任务 `resource_routing.installed_algorithm_context` 路由的回归已通过；本批没有改写旧catalog、索引或历史冻结哈希，这3项单列遗留待修复，不将扩展回归标为全绿。
