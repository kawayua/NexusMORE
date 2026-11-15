# 枢模 · NexusMORE 算法知识索引

索引版本1.3.1；算法资料版本1.0.0；2026-11-14。按用户提供的七类主题，项目已独立编写七章逐算法说明和固定案例，覆盖123条来源条目、113个去重规范算法。原始来源全文不随包复制，旧冻结索引/卡片/批准不改写。覆盖范围是这份主题清单，不能称为所有算法百科或113个通用求解器。

## 先索引，后匹配章节

先记录题目结构、数据/单位、变量、目标、约束、规模及依赖，再读匹配章的重点补充与相应条目。每条含公式、符号、适用前提、失败边界、反例、步骤/成本及固定可复算案例；保存所读路径、版本、哈希及前提满足/不满足/未知。不一次加载全部算法，不以API名替代模型。

| 类别ID | 实际章节 | 条目数（跨类可重复） |
|---|---|---|
| optimization | [优化](knowledge/optimization.md) | 17 |
| prediction | [预测](knowledge/prediction.md) | 15 |
| evaluation | [综合评价](knowledge/evaluation.md) | 14 |
| graph | [图论与网络](knowledge/graph.md) | 15 |
| statistics | [统计与数据处理](knowledge/statistics.md) | 21 |
| simulation | [综合与仿真](knowledge/simulation.md) | 13 |
| machine-learning | [机器学习](knowledge/machine-learning.md) | 28 |

[规范目录与来源条目映射](knowledge/catalog.json)用于精确定位，跨类算法共用规范ID与固定案例；[组合与交接边界](knowledge/combinations.md)说明20种跨领域组合及失效条件。案例分为65个限定小问题完整解、23个单步更新、24个核心公式核验、1个固定种子估计。所有算法有文档反例，程序拒绝边界只覆盖实际测试的子集。组件不代表完整训练、已安装生产库或全局最优证明。

## 当前读取与复算入口

`python -m modelcrew.algorithm_knowledge list --category optimization`

`python -m modelcrew.algorithm_knowledge read --id lp`

`python -m modelcrew.algorithm_knowledge check-examples --id lp`

只读入口使用核心安装即可；固定计算需要evidence组的NumPy/SciPy，代码为包内可信函数，不执行Markdown或目录中的任意代码。选型事实标记是待证前提，不会自动判断真实任务准入。共享入口可供各harness调用，宿主实际路由及运行时M1/P1/P2/W1/W2需分别验证。

## 继续复用与未完成范围

[本地选型建议](modelcrew-notes.md)、[几何数值补充](numerical-geometry.md)、[旧卡片适配](hand-card-profiles-1.0.0.json)继续按各自覆盖范围使用。已有向量检索目录与旧卡片不因本批新资料而自动增量索引；新资料的精确读取已提供，语义索引重建和F6自动选择/执行另验。三份[数学形式化](../collaboration/mathematical-reasoning.md)、[统计核验](../collaboration/statistical-validation.md)、[证明审查](../collaboration/proof-review.md)仍是冻结约束指南，字节不改；B1—B3的独立知识正文与39个固定案例另见[数学论证资料](../mathematics/index.md)。正式论文审批、全页PDF与独立审查约束不变。
