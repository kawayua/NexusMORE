# 七类算法资料与复算入口

2026-11-14：依据用户提供的《算法知识库.md》主题清单，独立编写算法资料1.0.0，索引升至1.3.0。123条方法条目去重为113个规范算法，保留逐条来源映射和跨类归属；七章重点补充、公式、符号、适用条件、失败边界、反例、步骤/复杂度与Python固定案例已进入私有发行资源。该覆盖指用户清单的基础方法表，不是所有算法或推荐库的完整实现。

| 体系 | 条目数（含跨类） | 本批重点 |
|---|---|---|
| 优化 | 17 | 连续/整数与硬软约束、凸性/KKT范围、可行残差、整性、界与gap、多目标和敏感性 |
| 预测 | 15 | 时间验证、预测起点信息、季节/变点、基线、误差/区间与残差 |
| 评价 | 14 | 指标方向/标准化、权重依据、一致性、零分母、DEA导向/规模、排名扰动 |
| 图论与网络 | 15 | 有向/无向、负边/负环、零边、连通性、容量/守恒、匹配及路径还原 |
| 统计与数据处理 | 21 | 抽样/配对/重复/簇、缺失/异常、检验前提、效应量/区间、多重比较及因果边界 |
| 综合与仿真 | 13 | 初边值/守恒、稳定/收敛、随机误差、预热/重复、稳态与Sobol前提 |
| 机器学习 | 28 | 切分/折内预处理、折外融合、不平衡/校准、基线预算、降维解释和训练范围 |

逐算法内容位于[包内索引](../src/modelcrew/resources/algorithms/index.md)，目录见[规范算法与来源映射](../src/modelcrew/resources/algorithms/knowledge/catalog.json)。七章使用相同规范ID，重复算法不分别维护冲突公式。另有[组合交接说明](../src/modelcrew/resources/algorithms/knowledge/combinations.md)，适配20类跨域组合；SHAP、Optuna、贝叶斯优化、LDA/QDA等扩展名称不计入113个已复算案例，不据推荐登记已接通。

## 调用与证据

核心安装即可运行只读读取，不要求NumPy、数据库、Docker或模型key：

```powershell
python -m modelcrew.algorithm_knowledge list --category statistics
python -m modelcrew.algorithm_knowledge read --id ttest
python -m modelcrew.algorithm_knowledge read --id pca --category machine-learning
```

读取结果包含资料版本、实际章节路径、章节/目录/选中段落SHA256及未批准/未注册通用求解器状态。按题型只读匹配章节与条目；需要正文重点补充时读取索引所列章首。目录中的required_facts是待核验前提要求，不能当作自动条件判断或运行准入。

已有evidence组为固定案例提供NumPy/SciPy；当前Python3.13依赖版本沿用既有固定配置。安装私有wheel的evidence组后执行：

```powershell
python -m modelcrew.algorithm_knowledge check-examples --id lp
python -m modelcrew.algorithm_knowledge check-examples --category prediction
python -m modelcrew.algorithm_knowledge check-examples --output algorithm-example-check.json
```

输出文件须不存在，避免覆盖历史记录。执行仅调用包内固定可信函数，不执行来源Markdown或JSON中的任意代码。example_dependencies只说明固定示例依赖，不代表完整Prophet、LightGBM、CatBoost、深度网络等后端已安装或适配。

113例按范围分为65个限定小问题完整解、23个单步更新、24个核心公式核验、1个固定种子估计。各例保存输入/计算说明、预期量、实际值、误差和容差；Monte Carlo的0.006是该固定种子工程容差，不是统计置信保证。每算法给文档反例；本批实际执行20项数值拒绝边界，不把文档全部反例说成已自动执行。进一步用解析解、可行界、枚举、t统计量和对称t-SNE目标独立核对部分算例，失败/非有限值/维度不匹配均不能通过。

## 实现边界

本批入口可由任何harness调用，已注册为资料与固定算例能力，不代表宿主已自动调用。旧算法卡片、Qdrant语义目录和旧冻结运行保持原样；113条资料的语义增量索引、F6自动选型与业务求解分发仍需后续验收。三手和独立M1/P1/P2/W1/W2、模型与结果确认、中文审阅稿/选图及全页PDF要求继续适用，本批核算是作者工程验证，不是独立审查或用户批准。

七类A1—A7完成本清单范围的独立资料基线；数学B1—B3完整推导/证明/统计论证库仍待补，不能因算法中含公式而一并销项。原251项来源账本、15项最初缺口盘点、旧候选与用户批准不追改；原始文件仅作主题参照，不复制受限全文。当前资源214项，验证回执见[本批记录](release/algorithm-knowledge-supplement-20261114.json)。

后续更新：B1—B3声明范围的正文和39个固定案例已独立补充，见[数学论证资料](mathematical-knowledge.md)。上文214项/数学待补是算法批次当时状态；当前219项，旧算法候选与回执保持原字节。算法索引当前1.3.1仅增加数学入口，不改113算法正文与案例。
