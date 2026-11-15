# 枢模算法体系：优化

版本1.0.0；2026-11-14；项目独立编写。范围依据用户提供的算法主题清单，原始全文不随包复制。先读取算法索引，再按问题结构读取本章相关条目，不把算法清单当成已接通的业务求解器。

每条给核心公式、符号、准入条件、失败边界、步骤、成本和固定可复算案例。案例层级必须保留：small_complete_solution为限定小问题的完整解；single_update为一步机制；core_equation_check为公式组件；stochastic_estimate为固定种子估计。组件核算不等于完整训练、全局最优或后端安装通过。

训练拟合的预处理、特征、调参和组合权重不得使用测试或未来信息；模型、数值方法与Python API分开说明。所有新任务继续模型/结果用户确认与独立M1/P1/P2/W1/W2；阅读资料和工程案例不授予批准。

## 本体系重点补充

先把连续/整数/二元变量、目标方向、单位、硬约束与软目标分开；可行性优先于目标值。线性与凸二次问题须区分不可行、无界、最优及预算停止，非凸或启发式通常只能报告当前最好可行解。KKT只有在相应约束资格下才是局部必要条件；凸性等附加条件未满足时不能当全局最优证明。

复核不等式残差 $r_{ineq}=\max_i\max(0,g_i(x))$、等式残差 $r_{eq}=\max_i|h_i(x)|$ 和整性误差 $r_{int}=\max_j|x_j-\operatorname{round}(x_j)|$，容差需随量纲设置。最小化问题有合法下界L和可行上界U时报告 $gap=(U-L)/\max(1,|U|,|L|)$，没有界就标未知，不用多次随机成功替代界。敏感性分析固定可行域/活跃集解释范围，扰动约束后重新求解；多目标须交付可行Pareto候选及用户偏好，不能把任意加权解当完整前沿。

<a id="lp"></a>
## 线性规划 · lp

**模型与核心公式**：$\min c^Tx,\ Ax\le b,\ Ex=d,\ l\le x\le u$。

**符号与输入输出**：x为决策向量，c为单位成本，A/E和b/d为约束系数及右端，l/u为界。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：目标和约束线性；连续变量；单位一致，给出可行域。

**失败边界**：不可行、无界、病态缩放及迭代中断分别报告；只有成功且残差合格才接收。反例/拒绝情形：x≥1且x≤0无可行解，不能回传迭代末值作答案。

**步骤与成本**：建模→消除单位冲突→linprog→核对原约束、目标、状态和可得对偶界。内点法多项式算术复杂度依规模/精度；不承诺固定秒数。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：max x+2y，0≤x,y≤1且x+y≤2；解(1,1)，最大值3。期望核对量：`[1, 1, 3]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id lp`。固定案例实现为`modelcrew.algorithm_examples.case_lp`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
r=opt.linprog([-1.,-2.],A_ub=[[1,1]],b_ub=[2],bounds=[(0,1),(0,1)],method='highs'); require(r.success,'LP failed'); return [*r.x,-r.fun]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="ip"></a>
## 整数规划 · ip

**模型与核心公式**：$\min c^Tx,\ Ax\le b,\ x\in\mathbb Z^p$。

**符号与输入输出**：x为整数决策，c/A/b为目标与线性约束。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：离散决策和整数域明确；搜索界与资源预算可追溯。

**失败边界**：LP松弛后四舍五入会破坏可行性；超时可有可行解但未证最优。反例/拒绝情形：把离散人数1.5直接作解或把松弛上界当可实现收益均不准入。

**步骤与成本**：建立整数模型→分支定界/割平面→检查整性残差与界/gap。一般NP难，最坏指数；小例枚举仅为独立校验。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：max 3x+2y，2x+y≤4，x∈{0,1,2},y∈{0,1,2,3}；最优(1,2)值7。期望核对量：`7`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id ip`。固定案例实现为`modelcrew.algorithm_examples.case_ip`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return max(3*x+2*y for x in range(3) for y in range(4) if 2*x+y<=4)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="milp"></a>
## 混合整数线性规划 · milp

**模型与核心公式**：$\min c^Tx+d^Ty,\ Ax+By\le b,\ x\in\mathbb Z^p,y\in\mathbb R^q$。

**符号与输入输出**：x为整数，y为连续变量，A/B/b为耦合约束。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：整性只施加在指定变量；Big-M须有合法上界。

**失败边界**：过大M数值失稳、过小M裁掉可行解；未证最优的gap不能省略。反例/拒绝情形：把连续运输量也设为整数会改变原问题，不能当无损简化。

**步骤与成本**：声明整性→求解→同时核对连续约束和整数容差。一般最坏指数；松弛质量影响分支规模。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：min x+0.2y，x+y≥2.5，x整数0..3，y∈[0,2]；解(1,1.5)值1.3。期望核对量：`1.3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id milp`。固定案例实现为`modelcrew.algorithm_examples.case_milp`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
r=opt.milp([1,.2],integrality=[1,0],bounds=opt.Bounds([0,0],[3,2]),constraints=opt.LinearConstraint([[1,1]],[2.5],[np.inf])); require(r.success,'MILP failed'); return r.fun
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="nlp"></a>
## 非线性规划 · nlp

**模型与核心公式**：$\min f(x),\ g(x)\le0,h(x)=0;\ \nabla_xL=0$。

**符号与输入输出**：f为目标，g/h为约束，L=f+λ^Tg+μ^Th。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：函数有效域已知；梯度/光滑性和约束资格按所选法核对。

**失败边界**：KKT在合适条件下仅必要；非凸局部极小或驻点不是全局证据。反例/拒绝情形：f(x)=x^3在0梯度为0却非极小；梯度小不能单独证明最优。

**步骤与成本**：选初值与尺度→局部求解→约束/梯度核对→多初值比较及边界分析。依算法/光滑性而异；非凸全局搜索通常难。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：min (x−2)^2且x≥0；解析驻点2、目标0，与数值解核对。期望核对量：`[2, 0]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id nlp`。固定案例实现为`modelcrew.algorithm_examples.case_nlp`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
r=opt.minimize(lambda x:(x[0]-2)**2,[0.],jac=lambda x:np.array([2*(x[0]-2)]),bounds=[(0,None)]); require(r.success,'NLP failed'); return [r.x[0],r.fun]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="binary-ip"></a>
## 0-1规划 · binary-ip

**模型与核心公式**：$\max\sum_jv_jz_j,\ \sum_jw_jz_j\le C,\ z_j\in\{0,1\}$。

**符号与输入输出**：z表示是否选择，v为收益，w为资源需求，C为容量。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：不可分割选择且容量/互斥等业务约束完整。

**失败边界**：放松到[0,1]后所得分数解不能代二元决策；容量零/负值须判合法。反例/拒绝情形：选择两件的收益7违反容量5>3，目标高也必须拒绝。

**步骤与成本**：建二元约束→分支搜索→直接复算原容量及收益。背包一般NP难；本例2^n穷举。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：w=(2,3)，v=(3,4)，C=3；四种选择的可行最大收益4。期望核对量：`4`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id binary-ip`。固定案例实现为`modelcrew.algorithm_examples.case_binary_ip`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return max(3*a+4*b for a,b in itertools.product([0,1],repeat=2) if 2*a+3*b<=3)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="dynamic-programming"></a>
## 动态规划 · dynamic-programming

**模型与核心公式**：$V_t(s)=\max_{a\in A_t(s)}\{r_t(s,a)+V_{t+1}(T_t(s,a))\}$。

**符号与输入输出**：t为阶段，s为充分状态，a为动作，r为收益，T为转移。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：具有可分解阶段和最优子结构，状态保留未来所需信息。

**失败边界**：遗漏路径依赖会使Bellman递推失效；状态爆炸或错误终值。反例/拒绝情形：0-1背包正序更新会重复选同一物品，变成另一模型。

**步骤与成本**：定义状态/边界→按依赖拓扑递推→保存决策并回溯。状态数×动作数；0-1背包常用O(nC)伪多项式。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：容量5，重量2/3、收益3/4；倒序容量更新得到7。期望核对量：`7`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id dynamic-programming`。固定案例实现为`modelcrew.algorithm_examples.case_dynamic_programming`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return knapsack([2,3],[3,4],5)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="multi-objective"></a>
## 多目标规划 · multi-objective

**模型与核心公式**：$\min (f_1(x),\ldots,f_m(x));\ y\prec z\iff y_j\le z_j\ \forall j,\exists k:y_k<z_k$。

**符号与输入输出**：f_j为同向化目标，x为可行决策，≺表示支配。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：目标尺度/方向和可行性明确；偏好由用户/业务决定。

**失败边界**：加权和在非凸前沿可能漏解；一组Pareto解不等于唯一最优。反例/拒绝情形：未同向化成本与收益会把错误方向当改善。

**步骤与成本**：先筛可行→算支配→报告前沿→在明确偏好下选折中。朴素非支配筛选O(mN²)，连续求解依子问题。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=0,1,2，目标(x²,(x−2)²)均非支配；等权目标在1最小。期望核对量：`[3, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id multi-objective`。固定案例实现为`modelcrew.algorithm_examples.case_multi_objective`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([0.,1.,2.]); a=np.c_[x*x,(x-2)**2]; return [len(nondominated(a)),x[np.argmin(a.sum(axis=1))]]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="qp"></a>
## 二次规划 · qp

**模型与核心公式**：$\min\tfrac12x^THx+c^Tx,\ Ax\le b;\ H\succeq0$。

**符号与输入输出**：H为对称Hessian，c为线性项，A/b为约束。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：凸QP要求H半正定；严格正定且无冗余自由方向可给唯一性。

**失败边界**：H不定时局部求解无全局保证；奇异H可能多解或无界。反例/拒绝情形：H=[−1]时驻点0是极大点，不能套凸QP结论。

**步骤与成本**：检查对称/谱→求解→核对可行性及KKT残差。稠密线性代数常O(n³)每步；规模/稀疏性决定成本。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：H=2I，c=(−2,−4)，无约束；Hx=−c解(1,2)。期望核对量：`[1, 2]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id qp`。固定案例实现为`modelcrew.algorithm_examples.case_qp`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return np.linalg.solve(2*np.eye(2),[2,4])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="goal-programming"></a>
## 目标规划 · goal-programming

**模型与核心公式**：$\min\sum_i(w_i^+d_i^++w_i^-d_i^-),\ f_i(x)+d_i^--d_i^+=g_i,\ d_i^\pm\ge0$。

**符号与输入输出**：g为目标水平，d±为超额/不足偏差，w为优先或加权偏好。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：软目标和硬约束区分；惩罚单位及权重有依据。

**失败边界**：不同量纲直接加总会误导；加权目标与字典序优先不等价。反例/拒绝情形：把必须满足的安全约束仅设低权软目标可能产生危险“最优”。

**步骤与成本**：写偏差平衡→给偏好→求解→分别报告达标量和违约量。线性形式可转LP；含整数时一般NP难。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：min |x−2|+2|x−4|，x∈[0,5]；折点枚举得x=4、损失2。期望核对量：`[4, 2]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id goal-programming`。固定案例实现为`modelcrew.algorithm_examples.case_goal_programming`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=min([0,2,4,5],key=lambda t:abs(t-2)+2*abs(t-4)); return [x,abs(x-2)+2*abs(x-4)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="robust-optimization"></a>
## 鲁棒优化 · robust-optimization

**模型与核心公式**：$\min_x\max_{u\in\mathcal U}f(x,u),\ g(x,u)\le0\ \forall u\in\mathcal U$。

**符号与输入输出**：u为不确定量，U为有依据的集合。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：集合含义、同时性及决策时序明确；区分静态/可调鲁棒。

**失败边界**：集合过大极保守，集合不覆盖实际风险则无保障；不等于概率保证。反例/拒绝情形：只按均值u=1.5选x=2/3，在u=2时违反约束。

**步骤与成本**：给不确定集合→推鲁棒对应→求解→在边界和外样本检查。依集合及对应模型；不可任意用角点替代非凸最坏情形。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：max x≥0，ux≤1对u∈[1,2]；最坏u=2，所以x=0.5。期望核对量：`[0.5, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id robust-optimization`。固定案例实现为`modelcrew.algorithm_examples.case_robust_optimization`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=1/max([1.,2.]); return [x,max(u*x for u in [1.,2.])]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="ga"></a>
## 遗传算法 · ga

**模型与核心公式**：$P_{t+1}=\operatorname{select}(\operatorname{mutate}(\operatorname{cross}(P_t)));\ f(x)=x^2$。

**符号与输入输出**：P为种群，f为最小化适应度，选择/交叉/变异由编码定义。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：编码、约束修复、随机种子及评估预算明确。

**失败边界**：早熟、不可行后代、随机波动；有限运行不保证全局最优。反例/拒绝情形：受约束x≥0时该后代−0.5不可行，必须先修复/拒绝。

**步骤与成本**：初始化→评估→选择→交叉/变异→修复→按预算停止，多种子对照。约O(GPF)，G代数、P种群量、F评估成本。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：种群(−2,1,3)，锦标赛选1；固定另一亲本−2，算术交叉后代−0.5，平方适应度0.25。期望核对量：`0.25`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id ga`。固定案例实现为`modelcrew.algorithm_examples.case_ga`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
pop=np.array([-2.,1.,3.]); parent=pop[np.argmin(pop**2)]; child=.5*parent+.5*pop[0]; return child**2
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="pso"></a>
## 粒子群算法 · pso

**模型与核心公式**：$v'=\omega v+c_1r_1(p-x)+c_2r_2(g-x),\ x'=x+v'$。

**符号与输入输出**：x/v为位置速度，p/g为个体/群体最优，r为固定随机数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：连续编码、边界策略、目标预算及参数定义明确。

**失败边界**：越界、爆速、早熟；无一般有限步全局最优保证。反例/拒绝情形：边界[1,3]下x'=.5越界，不能仅凭目标下降接受。

**步骤与成本**：评价→更新p/g→更新速度位置→边界修复→再评价。O(GPF)，另存位置/速度及历史最优。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=2,v=0,p=1,g=0，ω=.5,c1=c2=1,r1=r2=.5；v'=−1.5,x'=.5。期望核对量：`[-1.5, 0.5]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id pso`。固定案例实现为`modelcrew.algorithm_examples.case_pso`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=2.; v=.5*0+.5*(1-x)+.5*(0-x); return [v,x+v]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="sa"></a>
## 模拟退火 · sa

**模型与核心公式**：$P(\mathrm{accept})=\min(1,e^{-\Delta f/T})$。

**符号与输入输出**：Δf为候选减当前能量，T>0为温度。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：邻域连通性、温度/降温和随机源有记录。

**失败边界**：过快冷却困局部；温度零导致公式非法；理论渐近条件非有限保证。反例/拒绝情形：T=0不可作分母；不得把拒绝一次解释成收敛。

**步骤与成本**：生成邻域→算Δf→按概率接受→降温→预算停止。O(KF)，K为邻域评估次数。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：Δf=2,T=2；劣解接受概率e^(−1)=.3678794412；固定u=.2时接受。期望核对量：`[0.36787944117144233, 1]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id sa`。固定案例实现为`modelcrew.algorithm_examples.case_sa`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
p=math.exp(-2/2); return [p,int(.2<p)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="aco"></a>
## 蚁群算法 · aco

**模型与核心公式**：$p_{ij}=\tau_{ij}^{\alpha}\eta_{ij}^{\beta}/\sum_{k\in A_i}\tau_{ik}^{\alpha}\eta_{ik}^{\beta},\ \tau'=(1-\rho)\tau+\Delta\tau$。

**符号与输入输出**：τ为信息素，η为启发值，A为可行动作，ρ为挥发率。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：可行邻接/禁忌表及正分母明确，路线目标与业务约束一致。

**失败边界**：信息素垄断、可行路线不存在；不能替代时窗/容量核验。反例/拒绝情形：无可行动作或全零权时不能除零后随机伪造路线。

**步骤与成本**：构造路线→验证可行→评价→挥发/增量→多种子对照。O(G×蚂蚁数×构造成本)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：τ=(1,1)，η=(1,2)，α=β=1；选择概率(1/3,2/3)。期望核对量：`[0.3333333333333333, 0.6666666666666666]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id aco`。固定案例实现为`modelcrew.algorithm_examples.case_aco`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
w=np.array([1.,1.])*np.array([1.,2.]); return w/w.sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="de"></a>
## 差分进化 · de

**模型与核心公式**：$v=a+F(b-c),\ u_j=\begin{cases}v_j&r_j<CR\text{或}j=j_*\\x_j&\text{其他}\end{cases}$。

**符号与输入输出**：a/b/c为不同供体，F为缩放，CR为交叉概率，x为目标向量。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：种群足以取互异供体，至少一维强制交叉，边界策略明确。

**失败边界**：同一供体退化、越界、种群坍缩；局部改进不证明全局。反例/拒绝情形：供体不能全部使用同一向量，否则差分为零导致假进化。

**步骤与成本**：变异→二项交叉→修复→与目标一对一贪婪选择。O(GPF)，每代每目标通常一次候选评价。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：一维目标x=3，a=1,b=2,c=0,F=.5，强制交叉得2，平方损失从9降4。期望核对量：`[2, 4]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id de`。固定案例实现为`modelcrew.algorithm_examples.case_de`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
candidate=1+.5*(2-0); chosen=candidate if candidate**2<3**2 else 3; return [chosen,chosen**2]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="tabu"></a>
## 禁忌搜索 · tabu

**模型与核心公式**：$x'=\arg\min_{y\in N(x),\,y\notin T\ \mathrm{or\ aspiration}} f(y)$。

**符号与输入输出**：N为邻域，T为禁忌记忆，特赦与任期预先定义。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：解编码/邻域和可行性明确，可复核禁忌属性而非只记录目标值。

**失败边界**：任期不当循环或封死邻域；放行禁忌必须满足明确特赦。反例/拒绝情形：邻域全被禁且无特赦时明确停止/调整策略，不返回禁解作合法移动。

**步骤与成本**：枚举邻域→排禁忌→特赦检查→择优移动→更新记忆。O(K×邻域数×F)，内存依任期。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：当前x=2，邻域1/3，损失x²，1在禁忌且无特赦；必须选择3，损失9。期望核对量：`[3, 9]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id tabu`。固定案例实现为`modelcrew.algorithm_examples.case_tabu`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
allowed=[x for x in [1,3] if x not in {1}]; chosen=min(allowed,key=lambda x:x*x); return [chosen,chosen**2]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="nsga2"></a>
## NSGA-II · nsga2

**模型与核心公式**：$\operatorname{rank}=\text{非支配层};\ d_i=\sum_j(f_{j,i+1}-f_{j,i-1})/(f_j^{\max}-f_j^{\min})$。

**符号与输入输出**：rank为层号，d为拥挤距离，f_j为同向目标。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：约束支配规则明确；常量目标的零分母单独处理。

**失败边界**：有限种群仅近似前沿；拥挤距离不是不确定性或最优性证明。反例/拒绝情形：将收益目标误当成本，支配关系和最终选择都会逆转。

**步骤与成本**：父子代合并→非支配分层→按拥挤距离截断→生成后代。经典非支配排序O(mN²)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：候选(0,4),(1,1),(4,0),(3,3)，前三个非支配，最后一个被(1,1)支配。期望核对量：`[0, 1, 2]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id nsga2`。固定案例实现为`modelcrew.algorithm_examples.case_nsga2`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return nondominated(np.array([[0,4],[1,1],[4,0],[3,3]],float))
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。
