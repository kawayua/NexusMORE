# 枢模算法体系：综合评价

版本1.0.0；2026-11-14；项目独立编写。范围依据用户提供的算法主题清单，原始全文不随包复制。先读取算法索引，再按问题结构读取本章相关条目，不把算法清单当成已接通的业务求解器。

每条给核心公式、符号、准入条件、失败边界、步骤、成本和固定可复算案例。案例层级必须保留：small_complete_solution为限定小问题的完整解；single_update为一步机制；core_equation_check为公式组件；stochastic_estimate为固定种子估计。组件核算不等于完整训练、全局最优或后端安装通过。

训练拟合的预处理、特征、调参和组合权重不得使用测试或未来信息；模型、数值方法与Python API分开说明。所有新任务继续模型/结果用户确认与独立M1/P1/P2/W1/W2；阅读资料和工程案例不授予批准。

## 本体系重点补充

先给每个指标定义、单位、方向（收益/成本/目标区间）、缺失策略与对象集合；任何标准化都不得混淆方向。权重表达主观偏好或样本信息量，熵权大不代表业务重要，相关性也不能直接等同冗余。AHP先验正互反性、RI版本和CR门槛依问题说明，n≤2无需机械套用未定义RI。

TOPSIS先固定标准化及正负理想点，再算距离；不同方案集可能导致秩逆转。熵权零列和全部常量列、CRITIC零方差、VIKOR极差为0都必须显式处理。DEA区分投入/产出导向及CRS/VRS，效率不是因果收益；Malmquist固定距离函数的倒数约定。至少做权重扰动、标准化替代、对象增删与排名稳定性，交付评价敏感性而非单一总分作为绝对真理。

<a id="ahp"></a>
## 层次分析法 · ahp

**模型与核心公式**：$Aw=\lambda_{\max}w,\ \mathrm{CI}=(\lambda_{\max}-n)/(n-1),\ \mathrm{CR}=\mathrm{CI}/\mathrm{RI}$。

**符号与输入输出**：A为正互反判断矩阵，w为归一权，RI为所采用随机一致性基准。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：判断来源/尺度和RI版本明确；正互反与维度先检查。

**失败边界**：不一致需回访判断；CR小不证明偏好客观正确；n≤2的退化情况另处置。反例/拒绝情形：A_12=2而A_21=2不互反，不能直接接受权重。

**步骤与成本**：构造层级→正互反核对→求主特征向量→一致性→敏感性。稠密特征分解O(n³)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：w=(1,2,4)/7，A_ij=w_i/w_j；λmax=3，CI=0。期望核对量：`[0.14285714285714285, 0.2857142857142857, 0.5714285714285714, 0]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id ahp`。固定案例实现为`modelcrew.algorithm_examples.case_ahp`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
w=np.array([1.,2.,4.]); A=w[:,None]/w[None,:]; vals,vec=np.linalg.eig(A); k=np.argmax(vals.real); v=abs(vec[:,k].real); return [*(v/v.sum()),(vals[k].real-3)/2]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="entropy-weight"></a>
## 熵权法 · entropy-weight

**模型与核心公式**：$p_{ij}=z_{ij}/\sum_i z_{ij},\ e_j=-\sum_i p_{ij}\ln p_{ij}/\ln n,\ w_j=(1-e_j)/\sum_k(1-e_k)$。

**符号与输入输出**：z为同向且非负处理后指标，n为对象数，0ln0定义为0。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：n>1，列质量/方向和零列策略明确，分母非零。

**失败边界**：常量列无区分；全列无差异权重未定义；离散程度不等于价值重要性。反例/拒绝情形：所有指标列均为常量，差异和为0，必须返回缺乏区分信息。

**步骤与成本**：清洗同向化→归一概率→熵→差异权→权重扰动检验。O(nm)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：z=[[1,1],[0,1]]，第一列有差异第二列常量；w=(1,0)。期望核对量：`[1, 0]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id entropy-weight`。固定案例实现为`modelcrew.algorithm_examples.case_entropy_weight`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return entropy_weights(np.array([[1.,1.],[0.,1.]]))
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="topsis"></a>
## TOPSIS · topsis

**模型与核心公式**：$v_{ij}=w_jr_{ij},\ D_i^\pm=\|v_i-v^\pm\|_2,\ C_i=D_i^-/(D_i^++D_i^-)$。

**符号与输入输出**：r为明确标准化后同向指标，v±为正负理想点，w为权重。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：方向、权重、标准化口径与对象集合固定。

**失败边界**：所有点相同分母零；加入对象会引发名次反转；距离不是因果价值。反例/拒绝情形：全体同点时D+与D−皆0，不能声称都有完美得分。

**步骤与成本**：标准化→权重→理想点→距离→排序/敏感性。O(nm)，成对稳健比较额外计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：已归一r=[[1,0],[0,1]]，w=(.75,.25)，贴近度(.75,.25)。期望核对量：`[0.75, 0.25]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id topsis`。固定案例实现为`modelcrew.algorithm_examples.case_topsis`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
v=np.array([[1.,0.],[0.,1.]])*np.array([.75,.25]); plus=v.max(axis=0); minus=v.min(axis=0); dp=np.linalg.norm(v-plus,axis=1); dm=np.linalg.norm(v-minus,axis=1); return dm/(dp+dm)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="weighted-score"></a>
## 加权评分法 · weighted-score

**模型与核心公式**：$s_i=\sum_jw_jz_{ij},\ w_j\ge0,\sum_jw_j=1$。

**符号与输入输出**：z为已同向/可比尺度指标，w为有依据的权重。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：可加补偿假设与尺度合理，权重来源可解释。

**失败边界**：不可补偿安全指标不能被其他高分抵消；同量纲不自动可加。反例/拒绝情形：把费用原值当越大越好评分会逆转评价目标。

**步骤与成本**：同向化与尺度→给权→计算→敏感性和硬约束检查。O(nm)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：z=(.8,.4)，w=(.25,.75)，总分.5。期望核对量：`0.5`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id weighted-score`。固定案例实现为`modelcrew.algorithm_examples.case_weighted_score`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return np.dot([.8,.4],[.25,.75])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="critic"></a>
## CRITIC · critic

**模型与核心公式**：$C_j=\sigma_j\sum_k(1-r_{jk}),\ w_j=C_j/\sum_k C_k$。

**符号与输入输出**：σ为指定处理后列标准差，r为列相关系数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：指标有变异、标准化定义明确，相关矩阵估计有足够样本。

**失败边界**：常量列相关未定义；全列完全同向相关时C皆0；冲突权不等于政策偏好。反例/拒绝情形：复制两个完全同向指标会使两者信息量0，不能任意除以epsilon造权重。

**步骤与成本**：处理尺度→标准差/相关→信息量→归一权→稳健性。相关矩阵O(nm²)，缺失与小样本需额外检查。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：已处理矩阵[[0,1],[1,0]]，两列反向且标准差相等，CRITIC权(.5,.5)。期望核对量：`[0.5, 0.5]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id critic`。固定案例实现为`modelcrew.algorithm_examples.case_critic`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
X=np.array([[0.,1.],[1.,0.]]); c=X.std(axis=0,ddof=1)*(1-np.corrcoef(X,rowvar=False)).sum(axis=1); return c/c.sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="pca"></a>
## 主成分分析 · pca

**模型与核心公式**：$X_c=U\Sigma V^T,\ Z=X_cV_k,\ \lambda_j=\sigma_j^2/(n-1)$。

**符号与输入输出**：X_c为训练均值中心化数据，V为主轴，Z为得分。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：尺度/中心化来自训练集，维数和保留准则明确。

**失败边界**：大方差不代表预测/评价重要；主轴符号任意；近等特征值方向不稳定。反例/拒绝情形：在全数据上估计PCA再切分，测试集已经影响特征轴。

**步骤与成本**：训练拟合中心/尺度→SVD→选k→独立转换→重构/任务验证。稠密O(min(np²,n²p))，截断方法按实现计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：X=[(−1,−1),(0,0),(1,1)]，协方差特征值(2,0)，首轴解释率1。期望核对量：`[2, 0, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id pca`。固定案例实现为`modelcrew.algorithm_examples.case_pca`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
X=np.array([[-1.,-1.],[0,0],[1,1]]); v=np.linalg.eigvalsh(np.cov(X,rowvar=False))[::-1]; return [*v,v[0]/v.sum()]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="factor-analysis"></a>
## 因子分析 · factor-analysis

**模型与核心公式**：$x=\mu+\Lambda f+\epsilon,\ \operatorname{Cov}(x)=\Lambda\Lambda^T+\Psi$。

**符号与输入输出**：f为单位协方差潜因子，Ψ为特异方差对角阵，Λ为载荷。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：共同因子模型/因子数及识别约束适当，特异方差非负。

**失败边界**：旋转不唯一、Heywood负方差、样本不足；解释因子不能凭命名证明。反例/拒绝情形：特异方差−1不合法；不能用其补偿错误因子数。

**步骤与成本**：选因子数→拟合载荷/特异方差→旋转→残差和外部效度。依拟合/旋转/变量维数，稠密协方差O(np²)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：Λ=(1,2)^T，Ψ=I；模型协方差[[2,2],[2,5]]。期望核对量：`[[2, 2], [2, 5]]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id factor-analysis`。固定案例实现为`modelcrew.algorithm_examples.case_factor_analysis`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
L=np.array([[1.],[2.]]); return L@L.T+np.eye(2)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="grey-relation"></a>
## 灰色关联分析 · grey-relation

**模型与核心公式**：$\xi_{ij}=(\Delta_{\min}+\rho\Delta_{\max})/(\Delta_{ij}+\rho\Delta_{\max})$。

**符号与输入输出**：Δ为同尺度比较序列和参考序列差的绝对值，ρ∈(0,1]。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：参考序列、尺度/权重及全局极差范围事先说明。

**失败边界**：全差为0公式退化须约定全同得分；参考选择可改排名；关联非因果。反例/拒绝情形：混合米和千米未经统一尺度计算差，会产生任意排名。

**步骤与成本**：同向无量纲→计算Δ→关联系数→加权汇总→扰动分析。O(nm)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：Δ=(0,2)，Δmin=0,Δmax=2,ρ=.5；系数(1,1/3)，等权关联度2/3。期望核对量：`0.6666666666666666`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id grey-relation`。固定案例实现为`modelcrew.algorithm_examples.case_grey_relation`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
d=np.array([0.,2.]); return np.mean((d.min()+.5*d.max())/(d+.5*d.max()))
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="fuzzy-evaluation"></a>
## 模糊综合评价 · fuzzy-evaluation

**模型与核心公式**：$b=w^TR,\ w_j\ge0,\sum_jw_j=1,\ R_{jk}\ge0,\sum_kR_{jk}=1$。

**符号与输入输出**：R为指标对等级的隶属度，b为综合等级隶属向量。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：隶属函数、等级和权重来源明确；此条采用加权平均合成。

**失败边界**：不同合成算子不能混用；模糊隶属度不是抽样置信概率。反例/拒绝情形：行隶属度和为2却未解释归一化，不能直接当本条R。

**步骤与成本**：定义等级/隶属函数→构造R→权重合成→解释/敏感性。线性合成O(mk)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：w=(.25,.75)，R=[[1,0],[.2,.8]]；综合(.4,.6)。期望核对量：`[0.4, 0.6]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id fuzzy-evaluation`。固定案例实现为`modelcrew.algorithm_examples.case_fuzzy_evaluation`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return np.array([.25,.75])@np.array([[1.,0.],[.2,.8]])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="vikor"></a>
## VIKOR · vikor

**模型与核心公式**：$S_i=\sum_jw_jd_{ij},\ R_i=\max_jw_jd_{ij},\ Q_i=v\frac{S_i-S_*}{S^--S_*}+(1-v)\frac{R_i-R_*}{R^--R_*}$。

**符号与输入输出**：d为相对最优的标准化差距，v为群体效益权衡，*与−为最小/最大。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：方向、参考极值及v明确，零极差项有显式约定。

**失败边界**：Q排序不自动给单一折中解；另核验可接受优势/稳定性，退化情况单独处理。反例/拒绝情形：全部S相同分母0；不能靠浮点epsilon伪造区分。

**步骤与成本**：标准差距→S/R→Q→优势/稳定性→报告折中集合。O(nm)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：两个对象同向已归一损失d=[[0,0],[1,1]]，w=(.5,.5),v=.5；Q=(0,1)。期望核对量：`[0, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id vikor`。固定案例实现为`modelcrew.algorithm_examples.case_vikor`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
d=np.array([[0.,0.],[1.,1.]]); S=(d*.5).sum(axis=1); R=(d*.5).max(axis=1); return .5*(S-S.min())/np.ptp(S)+.5*(R-R.min())/np.ptp(R)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="promethee"></a>
## PROMETHEE · promethee

**模型与核心公式**：$\pi(a,b)=\sum_jw_jP_j(g_j(a)-g_j(b)),\ \phi(a)=\frac1{n-1}\sum_{b\ne a}[\pi(a,b)-\pi(b,a)]$。

**符号与输入输出**：P为指定偏好函数，g为同向指标，φ为净流。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：偏好阈值/函数、权重和对象集明确；n>1。

**失败边界**：净流受对象集合影响，PROMETHEE I偏序与II全序有别。反例/拒绝情形：阈值变化后不能沿用原排序批准或把平局强行打破。

**步骤与成本**：给偏好函数→成对偏好→流量→排序/阈值敏感性。O(n²m)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：单收益指标值(1,2,3)，严格更大偏好1否则0；净流(−1,0,1)。期望核对量：`[-1, 0, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id promethee`。固定案例实现为`modelcrew.algorithm_examples.case_promethee`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([1.,2.,3.]); P=(x[:,None]>x[None,:]).astype(float); return (P.sum(axis=1)-P.sum(axis=0))/2
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="electre"></a>
## ELECTRE · electre

**模型与核心公式**：$c(a,b)=\sum_{j:g_j(a)\ge g_j(b)}w_j;\ aSb\ \text{需一致性门槛且无否决}$。

**符号与输入输出**：c为一致性，S为超越关系，否决阈值体现不可补偿差距。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：明确采用哪一ELECTRE变体及阈值；本条用简化ELECTRE I机制示例。

**失败边界**：超越可循环/不可比，不天然为总分；不同变体阈值规则不同。反例/拒绝情形：只看一致性.6而忽略安全指标否决，会错判a优于b。

**步骤与成本**：算一致/不一致→判否决→建超越图→核/排序按变体解释。成对指标比较O(n²m)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：a=(2,0),b=(1,1)，w=(.6,.4)，一致性.6；第二指标差1超过否决.5，a不能超越b。期望核对量：`[0.6, 0]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id electre`。固定案例实现为`modelcrew.algorithm_examples.case_electre`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
a=np.array([2.,0.]); b=np.array([1.,1.]); c=np.array([.6,.4])[a>=b].sum(); return [c,int(c>=.6 and np.all(b-a<=.5))]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="dea"></a>
## DEA · dea

**模型与核心公式**：$\min\theta:\ \sum_j\lambda_jx_j\le\theta x_o,\ \sum_j\lambda_jy_j\ge y_o,\lambda_j\ge0$。

**符号与输入输出**：x/y为非负投入产出，θ为投入导向CCR效率，λ为参照组合。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：决策单元同质、同向数据与规模报酬假设明确；VRS另加Σλ=1。

**失败边界**：异常前沿、小样本多指标、零投入等会失真；效率为相对值非因果。反例/拒绝情形：不同业务类型DMU直接组成前沿，效率差未必可解释。

**步骤与成本**：选方向/CRS或VRS→逐DMU线性规划→松弛/参照集→稳健性。每DMU一个LP，复杂度依对象数/指标数及求解精度。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：DMU投入(1,2)产出(1,1)，评价第二个CCR投入效率θ=.5。期望核对量：`0.5`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id dea`。固定案例实现为`modelcrew.algorithm_examples.case_dea`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
r=opt.linprog([1,0,0],A_ub=[[-2,1,2],[0,-1,-1]],b_ub=[0,-1],bounds=[(0,None)]*3,method='highs'); require(r.success,'DEA failed'); return r.fun
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="malmquist"></a>
## Malmquist指数 · malmquist

**模型与核心公式**：$M=\sqrt{\frac{D_t(x_{t+1},y_{t+1})}{D_t(x_t,y_t)}\frac{D_{t+1}(x_{t+1},y_{t+1})}{D_{t+1}(x_t,y_t)}}$。

**符号与输入输出**：D为指定产出距离；本条D_s(x,y)=y/F_s(x)，M>1按此约定为生产率提高。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：两期可比技术、方向/距离定义和交叉期可行性明确。

**失败边界**：距离/倒数约定不同会逆转指数；交叉期LP不可行不得填常数。反例/拒绝情形：交叉期距离为0或未定义时不能计算/解释指数。

**步骤与成本**：估计两期技术→四距离→几何均值→效率/技术变化分解。多次DEA/距离求解；按样本与技术约束计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：固定投入，两期前沿F_t=1,F_(t+1)=2，实际产出1→2；四距离1,2,.5,1，M=2。期望核对量：`2`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id malmquist`。固定案例实现为`modelcrew.algorithm_examples.case_malmquist`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
Dt0,Dt1,Dn0,Dn1=1.,2.,.5,1.; return math.sqrt((Dt1/Dt0)*(Dn1/Dn0))
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。
