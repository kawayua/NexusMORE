# B1—B3数学论证资料与案例

2026-11-14：独立编写数学资料1.0.0，共39个专题和39个固定案例，新增5项包资源，当前总数219。本批补齐原15项清单中B1—B3的声明范围基线；不是所有数学教材、自动证明器或任意数据的统计推断服务。原三份collaboration约束指南、旧冻结运行和历史批准保持字节，新的知识正文按需读取。

| 资料 | 专题/案例 | 核心补充 |
|---|---|---|
| B1 数学形式化与推导 | 12 | 定义域/符号/量纲/形状，秩与最小二乘，梯度/Hessian，Taylor与积分交换，概率、误差传播、ODE、KKT及数值误差 |
| B2 证明方法与反例 | 13 | 量词与条件，直接/反证/归纳/逆否/分类/构造，存在唯一、凸性、下降和固定点、有限样本泛化界、复杂度 |
| B3 统计论证与检验决策 | 14 | 实验单位/配对/重复/簇，Welch/ANOVA/Fisher/McNemar/秩，效应与区间、回归、重采样、FWER/FDR、等效/非劣、缺失及泄漏 |

入口为[包内数学索引](../src/modelcrew/resources/mathematics/index.md)与[结构化目录](../src/modelcrew/resources/mathematics/catalog.json)。每节给对象和公式、显式条件、逐步论证、反例、案例输入/预期目标/容差及固定可信代码。符号统一进入实际论文唯一全局表，数学资料不接管中文建模论文结构。未满足条件和未证缺口须绑定实际模型/数学包，不因读了资料自动变真。

## 实际调用

核心安装只读资料，不要求NumPy、SciPy、SymPy、数据库、Docker或API key：

```powershell
python -m modelcrew.mathematical_knowledge list --group B2
python -m modelcrew.mathematical_knowledge read --id descent-convergence
python -m modelcrew.mathematical_knowledge read --id paired-inference
```

读取返回章首约束和单节正文，以及资料版本、章节路径、章节/目录/选中段落SHA256；各harness共用同一Python入口，实际宿主调用/自动路由另验。

已有evidence组提供NumPy2.3.1、SciPy1.16.0和SymPy1.13.1，无新增依赖。安装候选wheel的evidence组后：

```powershell
python -m modelcrew.mathematical_knowledge check-examples --group B1
python -m modelcrew.mathematical_knowledge check-examples --id fisher-inference
python -m modelcrew.mathematical_knowledge check-examples --output mathematical-examples.json
```

输出路径须不存在。只执行包内固定函数，不解析用户表达式，不执行Markdown/JSON里的代码；非有限数值、维度错或计算异常均失败，检查结果可保存为严格JSON。复算依赖未安装时明确提示evidence组。

## 证据解释与边界

本版案例层级计数：{"finite_example": 21, "symbolic_identity_check": 5, "numerical_error_check": 3, "statistical_calculation": 10}。文字证明给限定假设下的完整论证；有限搜索只检查有限范围，SymPy只核对列明表达式，数值收敛核对不是物理模型证明。39例各有文档反例，另实际执行16项数值拒绝检查，不能把全部文档反例说成已程序检验。

统计先定义估计目标、抽样/实验单位和检验族，再考虑方法。给出原单位效应及对应置信区间，标准化效应点估计与区间分开，不以其他目标的区间代替。例中ANOVA给η²点估计及第一组均值边际CI，未实现η²区间；McNemar给净风险差点估计及不一致者方向概率区间，后者不是风险差CI。n=m=3的精确秩位置平移95%反演区间无有限端点；代码保留明确标记，不伪造窄区间。TOST对应两个单侧α=.05与90%双侧区间，差异不显著不能推出等效。所有教学样本的分布/设计假设都未由案例本身验证，实际任务仍须审查。

正常核算只属于作者工程自检。独立M1/P1/P2/W1/W2、用户模型/结果确认、中文Markdown审阅与选图、同源正式导出和全页PDF检查继续分别执行。本批不生成论文或PDF，不宣称形式化证明助手、通用符号求解器、自动统计选型、全部混合模型/复杂抽样实现或F6自动接通。

## 验证与原记录

构建wheel、源码包及源码包重建wheel；在源码目录外的独立环境验证核心读取，并在单独evidence环境复算数学39例及此前算法113例。候选为tmp/mathematical-knowledge-validation-20261114/validated-build，详见[本批回执](release/mathematical-knowledge-supplement-20261114.json)。最初包审核、前两批候选/回执和原251项来源账本/15项盘点不追改。资料是自行编写的声明范围基线，不等于原始受限来源已获公开发行授权；F2整体、F3/F4/F5/F6和真实harness/干净机器端到端验收仍分别跟踪。
