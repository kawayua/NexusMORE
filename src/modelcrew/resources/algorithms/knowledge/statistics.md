# 枢模算法体系：统计与数据处理

版本1.0.0；2026-11-14；项目独立编写。范围依据用户提供的算法主题清单，原始全文不随包复制。先读取算法索引，再按问题结构读取本章相关条目，不把算法清单当成已接通的业务求解器。

每条给核心公式、符号、准入条件、失败边界、步骤、成本和固定可复算案例。案例层级必须保留：small_complete_solution为限定小问题的完整解；single_update为一步机制；core_equation_check为公式组件；stochastic_estimate为固定种子估计。组件核算不等于完整训练、全局最优或后端安装通过。

训练拟合的预处理、特征、调参和组合权重不得使用测试或未来信息；模型、数值方法与Python API分开说明。所有新任务继续模型/结果用户确认与独立M1/P1/P2/W1/W2；阅读资料和工程案例不授予批准。

## 本体系重点补充

明确观测单位、抽样设计、配对/重复/聚类、缺失机制、单位与取值范围，不能把一人的重复观测当独立样本扩增n。缺失不等于零，异常标记不授权删数据；训练期估计预处理参数，保留原值、变换、排除原因和敏感性。相关不证因果，差异检验不检验等效性。

先写原假设、效应量、显著性水平和检验族，再依设计核对独立性、分布/样本量与方差前提。独立两组可用Welch，配对先对差值推断，重复/簇设计用相应模型或重采样；报告效应、区间、p及样本数，不能只给p。m次比较可用Bonferroni阈值α/m或预先声明的BH-FDR：排序p后取最大k满足 $p_{(k)}\le k\alpha/m$，并说明其依赖条件。ANOVA拒绝不代表每对都不同，事后比较仍需校正。DID/PSM案例只复核估计量算术，不验证平行趋势或无未观测混杂；ADF临界分布不能用普通t分布替代。

<a id="descriptive"></a>
## 描述性统计 · descriptive

**模型与核心公式**：$\bar x=n^{-1}\sum_ix_i,\ s^2=(n-1)^{-1}\sum_i(x_i-\bar x)^2$。

**符号与输入输出**：n为有效观测数，s²为ddof=1样本方差。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：观测单位、权重、缺失和有限值规则明确，n≥2才算s²。

**失败边界**：分母n与n−1含义不同；聚合不能掩盖群体异质/依赖。反例/拒绝情形：n=1的样本方差未定义，不能填0伪装无变异。

**步骤与成本**：读全数据→核对缺失/单位→位置离散/分位数→按组诊断。均值方差O(n)，排序分位数常O(nlogn)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,2,3)，均值2、样本方差1、中位数2。期望核对量：`[2, 1, 2]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id descriptive`。固定案例实现为`modelcrew.algorithm_examples.case_descriptive`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([1.,2.,3.]); return [x.mean(),x.var(ddof=1),np.median(x)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="minmax"></a>
## Min-Max标准化 · minmax

**模型与核心公式**：$z=(x-a)/(b-a),\ a=\min X_{train},b=\max X_{train}$。

**符号与输入输出**：a/b为训练参考极值；z无量纲。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：参考范围和成本/收益方向明确，b>a。

**失败边界**：常量列分母0；测试值超训练范围可以超[0,1]，不能自动裁切丢信息。反例/拒绝情形：a=b=2必须拒绝除零或显式常量列策略。

**步骤与成本**：训练拟合极值→保存→转换验证/测试→记录超界。O(n)拟合，O(n)转换。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：训练极值2/6，数据(2,4,6)归一为(0,.5,1)。期望核对量：`[0, 0.5, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id minmax`。固定案例实现为`modelcrew.algorithm_examples.case_minmax`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return scale_minmax(np.array([2.,4.,6.]),2,6)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="zscore"></a>
## Z-score标准化 · zscore

**模型与核心公式**：$z_i=(x_i-\mu_{train})/\sigma_{train}$。

**符号与输入输出**：μ/σ为训练均值和指定ddof标准差。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：缩放参数训练内估计，明确总体或样本标准差约定。

**失败边界**：常量列σ=0；依赖异常极值会扭曲；标准化不使数据正态。反例/拒绝情形：在测试集重新计算μ/σ会改变预测时特征含义。

**步骤与成本**：训练估计μ/σ→冻结→转换→检查离群/漂移。O(n)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,2,3)，训练μ=2且ddof=1时σ=1；z=(−1,0,1)。期望核对量：`[-1, 0, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id zscore`。固定案例实现为`modelcrew.algorithm_examples.case_zscore`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([1.,2.,3.]); return (x-x.mean())/x.std(ddof=1)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="imputation"></a>
## 均值/中位数填补 · imputation

**模型与核心公式**：$\hat x_{ij}=\bar x_{j,train,obs}\ \text{或}\ \operatorname{median}(x_{j,train,obs})$。

**符号与输入输出**：obs表示已观察值；策略由变量类型/缺失机制决定。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：区分缺失与零，填补值仅训练估计；记录缺失比例/机制与指示变量。

**失败边界**：全列缺失无法估计；均值填补压缩方差且不能消除MNAR偏差。反例/拒绝情形：分类编码不能随意均值填补成1.5；全缺列nanmean不是有效值。

**步骤与成本**：先分析机制→训练估计→填补并标记→验证敏感性。均值O(nm)，中位数依选择/排序实现。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：训练观测1、3，均值和中位数皆2；[1,NaN,3]填补为[1,2,3]。期望核对量：`[1, 2, 3]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id imputation`。固定案例实现为`modelcrew.algorithm_examples.case_imputation`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([1.,np.nan,3.]); return np.where(np.isnan(x),np.nanmean(x),x)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="knn-imputation"></a>
## KNN填补 · knn-imputation

**模型与核心公式**：$\hat x_{ij}=\frac{\sum_{k\in N_i}w_{ik}x_{kj}}{\sum_{k\in N_i}w_{ik}}$。

**符号与输入输出**：N为在共有已观测特征上找的有该列值的训练邻居。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：距离、尺度、共有特征数量及零距规则明确；无测试标签参与。

**失败边界**：无共有特征或无有效供体不能胡填；高维距离/小样本不稳。反例/拒绝情形：与所有训练行都无共有特征时距离无定义，不能当零距离。

**步骤与成本**：训练内缩放→按可比特征找邻居→按列有效供体加权→留出检验。朴素约O(n²p)，近邻索引受缺失/维度限制。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：观测特征q=1，供体q=(0,2)，待填列(10,20)，两邻居等权填15。期望核对量：`15`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id knn-imputation`。固定案例实现为`modelcrew.algorithm_examples.case_knn_imputation`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
q=np.array([0.,2.]); v=np.array([10.,20.]); idx=np.argsort(abs(q-1))[:2]; return v[idx].mean()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="three-sigma"></a>
## 3σ原则 · three-sigma

**模型与核心公式**：$|x-\mu|>3\sigma$。

**符号与输入输出**：μ/σ为给定总体或稳健核对后的参考参数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：近似正态且过程稳定时作筛查参考，参数估计方法需说明。

**失败边界**：重尾、偏态、混合群体会误报；异常标记不自动删除。反例/拒绝情形：收入重尾数据不因超过3σ就视作录入错误删掉。

**步骤与成本**：核对分布/分组→定参考→标记→回溯来源与敏感性。O(n)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：参考μ=0,σ=1，观测(0,2,4)；仅4越3σ，标记(0,0,1)。期望核对量：`[0, 0, 1]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id three-sigma`。固定案例实现为`modelcrew.algorithm_examples.case_three_sigma`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return (abs(np.array([0.,2.,4.]))>3).astype(int)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="iqr"></a>
## IQR · iqr

**模型与核心公式**：$\mathrm{IQR}=Q_{.75}-Q_{.25};\ [Q_{.25}-1.5\mathrm{IQR},Q_{.75}+1.5\mathrm{IQR}]$。

**符号与输入输出**：Q为按指定插值定义的分位数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：连续/有序数据、分位数方法和分组口径明确。

**失败边界**：IQR=0在离散集中数据常见；筛查阈值不证明异常原因。反例/拒绝情形：零膨胀计数的IQR可为0，不能因此删除所有正数。

**步骤与成本**：计算分位数→围栏标记→源数据核查→记录保留/排除。排序O(nlogn)，选择算法可线性。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(0,1,2,3,100)，线性分位数Q1=1,Q3=3，围栏[−2,6]。期望核对量：`[-2, 6]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id iqr`。固定案例实现为`modelcrew.algorithm_examples.case_iqr`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
q1,q3=np.quantile([0,1,2,3,100],[.25,.75],method='linear'); return [q1-1.5*(q3-q1),q3+1.5*(q3-q1)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="lof"></a>
## LOF · lof

**模型与核心公式**：$\operatorname{reach}_k(p,o)=\max(kdist(o),d(p,o));\ \operatorname{LOF}_k(p)=\frac1{|N_k(p)|}\sum_{o\in N_k(p)}\frac{lrd_k(o)}{lrd_k(p)}$。

**符号与输入输出**：lrd为邻域可达距离均值的倒数，kdist为第k邻距。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：距离/尺度、k与并列邻域定义明确，密度估计可用。

**失败边界**：重复点产生零距退化；高维密度及新颖性检测/训练内离群接口有别。反例/拒绝情形：大量重复同点导致局部距离0，不能用无穷密度直接作可靠排序。

**步骤与成本**：近邻→可达距离→局部密度→LOF→领域核查。朴素邻域O(n²p)，索引复杂度依维数。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：点(0,1,10)，k=1，按确定并列规则；LOF分别(1,1,9)。期望核对量：`[1, 1, 9]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id lof`。固定案例实现为`modelcrew.algorithm_examples.case_lof`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return lof_1d([0.,1.,10.],1)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="pearson"></a>
## Pearson相关系数 · pearson

**模型与核心公式**：$r=\frac{\sum_i(x_i-\bar x)(y_i-\bar y)}{\sqrt{\sum_i(x_i-\bar x)^2\sum_i(y_i-\bar y)^2}}$。

**符号与输入输出**：x/y为配对数值，r量化线性关联。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：成对观察、非零方差；显著性推断需相应独立/分布或重采样假设。

**失败边界**：离群和非线性可误导；常量列无定义；相关不证因果。反例/拒绝情形：x全为1时分母0，不能将NaN解释为无关联。

**步骤与成本**：配对/缺失核对→散点关系审查→r及适当区间/检验→分组稳健性。O(n)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,2,3)，y=(2,4,6)；Pearson r=1。期望核对量：`1`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id pearson`。固定案例实现为`modelcrew.algorithm_examples.case_pearson`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return stats.pearsonr([1,2,3],[2,4,6]).statistic
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="spearman"></a>
## Spearman相关系数 · spearman

**模型与核心公式**：$\rho=\operatorname{Corr}(\operatorname{rank}(x),\operatorname{rank}(y))$。

**符号与输入输出**：rank按并列平均秩定义，ρ为秩相关。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：至少有变化的有序数据；并列和样本依赖处理清楚。

**失败边界**：不能无并列时的简式硬用于并列样本；单调不等于线性或因果。反例/拒绝情形：所有x相同的秩相关未定义。

**步骤与成本**：配对→平均秩→相关→合适置换/区间。排序O(nlogn)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,2,3)，y=(30,20,10)，反向秩相关−1。期望核对量：`-1`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id spearman`。固定案例实现为`modelcrew.algorithm_examples.case_spearman`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return stats.spearmanr([1,2,3],[30,20,10]).statistic
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="kendall"></a>
## Kendall相关系数 · kendall

**模型与核心公式**：$\tau_b=(C-D)/\sqrt{(C+D+T_x)(C+D+T_y)}$。

**符号与输入输出**：C/D为一致/不一致对，T_x/T_y为仅在各变量打结的对数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：配对有序数据，明确tau-a/b/c和并列处理。

**失败边界**：双变量皆常量分母0；独立性/簇结构影响推断。反例/拒绝情形：把有大量并列数据当完全无并列会得到错误标准化。

**步骤与成本**：统计成对顺序→并列修正→τ及相应检验/区间。朴素O(n²)，高效算法常O(nlogn)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,2,3),y=(1,3,2)，C=2,D=1，τb=1/3。期望核对量：`0.3333333333333333`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id kendall`。固定案例实现为`modelcrew.algorithm_examples.case_kendall`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return stats.kendalltau([1,2,3],[1,3,2],variant='b').statistic
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="ttest"></a>
## t检验 · ttest

**模型与核心公式**：$t=(\bar x-\bar y)/\sqrt{s_x^2/n_x+s_y^2/n_y};\ \mathrm{CI}=\Delta\pm t_{1-\alpha/2,\nu}\mathrm{SE}$。

**符号与输入输出**：此为Welch独立两样本；ν为Satterthwaite自由度，Δ为均值差。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：先区分独立/配对/重复；配对时应对差值作单样本检验；按分布/样本量核对前提。

**失败边界**：小样本严重偏态/依赖会破坏推断；p大不证明等价；多检验需FDR或Bonferroni等预定族控制。反例/拒绝情形：同一受试者前后测量当独立两组，会丢配对结构并误算SE。

**步骤与成本**：明确单位/假设→选检验→t/自由度/p→效应量/CI→多重校正。基本统计O(n)，重采样另计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,2,3),y=(2,3,4)，Welch t=−sqrt(1.5),df=4，双侧p≈.287864，标准化均差−1。期望核对量：`[-1.224744871391589, 0.2878641347266908, -1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id ttest`。固定案例实现为`modelcrew.algorithm_examples.case_ttest`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
a=np.array([1.,2.,3.]); b=np.array([2.,3.,4.]); r=stats.ttest_ind(a,b,equal_var=False); d=(a.mean()-b.mean())/math.sqrt((a.var(ddof=1)+b.var(ddof=1))/2); return [r.statistic,r.pvalue,d]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="chi-square"></a>
## 卡方检验 · chi-square

**模型与核心公式**：$\chi^2=\sum_{ij}(O_{ij}-E_{ij})^2/E_{ij},\ E_{ij}=O_{i+}O_{+j}/N$。

**符号与输入输出**：O为独立分类单位的计数，E为独立性零假设期望。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：计数而非比例/重复测量，期望计数条件足够；稀疏时用适配精确/模拟检验。

**失败边界**：结构零/小E或依赖会失效；显著关联非因果。反例/拒绝情形：把同一人多次选择当独立人数，会虚增样本量。

**步骤与成本**：建列联表→核对期望→选择是否连续性校正→统计/p/效应量。表大小O(rc)，精确法成本另计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：O=[[10,10],[10,10]]，不作Yates校正，χ²=0、p=1。期望核对量：`[0, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id chi-square`。固定案例实现为`modelcrew.algorithm_examples.case_chi_square`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
r=stats.chi2_contingency([[10,10],[10,10]],correction=False); return [r.statistic,r.pvalue]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="anova"></a>
## 方差分析 · anova

**模型与核心公式**：$F=\frac{\sum_gn_g(\bar x_g-\bar x)^2/(k-1)}{\sum_g\sum_i(x_{gi}-\bar x_g)^2/(N-k)}$。

**符号与输入输出**：k为组数，N为总数；此为经典单因素独立样本ANOVA。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：独立误差、方差同质及适当分布；重复测量/不等方差须换对应方法。

**失败边界**：显著F仅说明至少一个均值不同，不说明哪组；事后比较需控制检验族。反例/拒绝情形：重复受试者三个时间点不能直接当三独立组ANOVA。

**步骤与成本**：核对设计→组间/组内平方和→F/p→效应量/CI和预定比较。O(N)，事后比较额外计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：三组(1,2),(3,4),(5,6)；SSB=16,SSW=1.5，F=(16/2)/(1.5/3)=16。期望核对量：`16`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id anova`。固定案例实现为`modelcrew.algorithm_examples.case_anova`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return stats.f_oneway([1,2],[3,4],[5,6]).statistic
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="bootstrap"></a>
## Bootstrap · bootstrap

**模型与核心公式**：$\hat\theta^{*(b)}=T(X^{*(b)}),\ \mathrm{SE}_{boot}=\operatorname{sd}(\hat\theta^{*(1:B)})$。

**符号与输入输出**：X*从适当抽样单位重采样，T为估计量。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：独立、配对、簇或时间块的抽样单位与设计匹配；种子/重复数/区间法明确。

**失败边界**：小样本尾部、边界/非光滑估计或错误单位会失真；多次重采样不补信息。反例/拒绝情形：对纵向记录逐行独立重采样会破坏受试者/时间依赖。

**步骤与成本**：定义统计量→合法重采样→分布/SE/区间→重复数敏感性。O(B×T计算成本)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：总体经验样本(0,2)，每次抽2有放回；穷举4次样本均值0,1,1,2，精确bootstrap方差.5。期望核对量：`0.5`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id bootstrap`。固定案例实现为`modelcrew.algorithm_examples.case_bootstrap`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
means=np.array([(a+b)/2 for a,b in itertools.product([0.,2.],repeat=2)]); return means.var(ddof=0)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="linear-regression"></a>
## 线性回归 · linear-regression

**模型与核心公式**：$\hat\beta=\arg\min_\beta\|X\beta-y\|_2^2;\ \hat y=X\hat\beta$。

**符号与输入输出**：X为含截距设计矩阵，y为响应，β为系数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：目标在特征上可线性表示；推断另需误差/设计假设，预测需外样本检查。

**失败边界**：秩亏系数不唯一；高杠杆/共线性、遗漏变量；相关回归不证因果。反例/拒绝情形：重复常量列使X秩亏；能预测某些点也不说明系数可识别。

**步骤与成本**：只在训练集构建设计→QR/SVD最小二乘→残差/稳定性→独立验证。稠密n≥p时常O(np²)，避免直接求逆。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(0,1,2)，y=(1,3,5)，拟合截距/斜率=(1,2)，在3预测7。期望核对量：`[1, 2, 7]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id linear-regression`。固定案例实现为`modelcrew.algorithm_examples.case_linear_regression`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
X=np.c_[np.ones(3),np.arange(3)]; b=np.linalg.lstsq(X,[1,3,5],rcond=None)[0]; return [*b,np.array([1,3])@b]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="logistic-regression"></a>
## Logistic回归 · logistic-regression

**模型与核心公式**：$p(y=1|x)=\sigma(x^T\beta),\ \sigma(z)=(1+e^{-z})^{-1};\ L=-\sum[y\ln p+(1-y)\ln(1-p)]$。

**符号与输入输出**：β为含截距系数，p为概率，分类阈值需另定。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：二元标签、设计/正则和训练验证合理；概率校准与决策成本明确。

**失败边界**：完全分离使无正则MLE发散；概率非因果；阈值.5非业务必然。反例/拒绝情形：完全分离样本不能把无限大系数当稳定可解释效应。

**步骤与成本**：稳定对数损失→估计/正则→校准→独立评估与阈值选择。依优化轮数/特征数；稠密梯度每轮O(np)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：线性预测z=ln3，概率.75；真实y=1时对数损失−ln(.75)=.2876820725。期望核对量：`[0.75, 0.2876820724517809]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id logistic-regression`。固定案例实现为`modelcrew.algorithm_examples.case_logistic_regression`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
p=special.expit(math.log(3)); return [p,-math.log(p)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="vif"></a>
## VIF · vif

**模型与核心公式**：$\mathrm{VIF}_j=1/(1-R_j^2)$。

**符号与输入输出**：R_j²为用其余解释变量回归第j列所得决定系数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：辅助回归的截距/设计一致，不对常量截距列解释VIF。

**失败边界**：R²=1则无限，不能加epsilon伪装有限；高VIF不自动要求删掉因果混杂项。反例/拒绝情形：完全相同两列R²=1，系数无法分别识别。

**步骤与成本**：各列辅助回归→VIF→识别设计问题→按任务调整并检验。p次回归；稠密常近O(np³)朴素实现。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：若辅助R²=.75，VIF=4。期望核对量：`4`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id vif`。固定案例实现为`modelcrew.algorithm_examples.case_vif`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return 1/(1-.75)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="adf"></a>
## ADF检验 · adf

**模型与核心公式**：$\Delta y_t=\alpha+\beta t+\gamma y_{t-1}+\sum_{i=1}^p\delta_i\Delta y_{t-i}+\epsilon_t$。

**符号与输入输出**：γ=0为单位根零假设；统计量为γ估计/标准误。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：截距/趋势、滞后阶和样本区间明确，临界分布使用ADF对应分布。

**失败边界**：不能用普通t分布临界值；结构突变/低功效，未拒绝不证明单位根必真。反例/拒绝情形：把−2按常规t检验宣布平稳，是错误参考分布。

**步骤与成本**：选确定项/滞后→拟合差分回归→ADF专用p/临界值→残差和其他证据。依滞后设计回归成本；后端专用临界值另验。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：固定已估计γ=−.2,SE=.1，则ADF统计量−2；此例不生成伪造p或结论。期望核对量：`-2`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id adf`。固定案例实现为`modelcrew.algorithm_examples.case_adf`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return -.2/.1
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="did"></a>
## DID · did

**模型与核心公式**：$\hat\tau=(\bar Y_{T,post}-\bar Y_{T,pre})-(\bar Y_{C,post}-\bar Y_{C,pre})$。

**符号与输入输出**：T/C为处理/对照，pre/post为前后期，τ为二乘二DID效应。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：平行趋势、无预期、无相互干扰及组构成稳定等识别假设需领域依据；SE按处理分配层聚类。

**失败边界**：差值可算不等于因果成立；错位处理异质效应不能机械套双向固定效应。反例/拒绝情形：处理组无干预也会比对照多涨3时，观测DID混入趋势差。

**步骤与成本**：定义干预→前趋势/识别审查→差中差→聚类推断/安慰剂/稳健性。均值差O(N)，面板估计另计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：处理组均值10→15，对照组8→10，DID=3。期望核对量：`3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id did`。固定案例实现为`modelcrew.algorithm_examples.case_did`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return (15-10)-(10-8)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="psm"></a>
## 倾向得分匹配 · psm

**模型与核心公式**：$e(x)=P(T=1|X=x),\ \widehat{ATT}=n_T^{-1}\sum_{i:T_i=1}(Y_i-\sum_jw_{ij}Y_j)$。

**符号与输入输出**：e为倾向得分，w为匹配对照权且每个处理单位权和1。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：条件可交换性、重叠、处理前协变量和无干扰；平衡/卡钳及替换规则明确。

**失败边界**：不能消除未观测混杂；匹配失败不得硬配；匹配后SE需对应设计。反例/拒绝情形：某处理得分.99而所有对照≤.1，缺重叠时不可强配并声称已识别。

**步骤与成本**：训练估计倾向→检查共同支持→匹配→平衡→ATT与适当推断。近邻搜索依样本/维数；不保证一次匹配解决偏差。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：处理得分.2/.8、结果5/9，对照得分.21/.79、结果3/6；最近匹配后ATT=(2+3)/2=2.5。期望核对量：`2.5`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id psm`。固定案例实现为`modelcrew.algorithm_examples.case_psm`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
pt=np.array([.2,.8]); pc=np.array([.21,.79]); matches=np.argmin(abs(pt[:,None]-pc[None,:]),axis=1); return np.mean(np.array([5.,9.])-np.array([3.,6.])[matches])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。
