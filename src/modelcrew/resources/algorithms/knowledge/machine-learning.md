# 枢模算法体系：机器学习

版本1.0.0；2026-11-14；项目独立编写。范围依据用户提供的算法主题清单，原始全文不随包复制。先读取算法索引，再按问题结构读取本章相关条目，不把算法清单当成已接通的业务求解器。

每条给核心公式、符号、准入条件、失败边界、步骤、成本和固定可复算案例。案例层级必须保留：small_complete_solution为限定小问题的完整解；single_update为一步机制；core_equation_check为公式组件；stochastic_estimate为固定种子估计。组件核算不等于完整训练、全局最优或后端安装通过。

训练拟合的预处理、特征、调参和组合权重不得使用测试或未来信息；模型、数值方法与Python API分开说明。所有新任务继续模型/结果用户确认与独立M1/P1/P2/W1/W2；阅读资料和工程案例不授予批准。

## 本体系重点补充

先给目标、数据单位、时间/分组边界、业务成本、简单基线与资源预算；拟合填补/尺度、特征选择、采样、调参和早停均在训练折内。独立测试只用于最后评估；时序用时间切分，同主体跨行用分组切分。Stacking元学习器只接折外预测，不能直接用训练拟合值制造泄漏。

回归报告绝对/平方误差，分类按成本报告混淆矩阵、召回/精确率、PR-AUC或ROC-AUC与概率校准；类别极不平衡不能只看准确率，阈值须训练/验证期确定。解释工具不能自动给因果，PCA/聚类须交代尺度、随机初态、空簇/噪声及稳定性；t-SNE/UMAP二维图不作为类别分离或跨次距离的证明。神经网络与提升库的固定组件案例只核对方程，完整训练、调参、生产性能与Windows/Docker后端均需后续具体任务实测。推荐库不是已安装能力，模型服务只提供建议不能替代数值求解器。

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

<a id="decision-tree"></a>
## 决策树 · decision-tree

**模型与核心公式**：$\mathrm{Gini}(S)=1-\sum_kp_k^2,\ \Delta I=I(S)-\sum_b|S_b|I(S_b)/|S|$。

**符号与输入输出**：S为节点样本，p为训练类频率，b为子节点。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：监督标签、分裂候选/缺失语义、停止和剪枝规则明确；回归树用相应损失。

**失败边界**：深树高方差，小样本叶、泄漏特征；训练纯度高不代表泛化。反例/拒绝情形：用目标值派生的特征可得到纯叶，却是泄漏。

**步骤与成本**：训练内搜索分裂→递归→剪枝/叶约束→外样本评估。依候选切分；排序缓存下常O(nplogn)，不作通用上界承诺。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：父标签(0,0,1,1)，按前后两样本纯分裂，Gini下降.5。期望核对量：`0.5`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id decision-tree`。固定案例实现为`modelcrew.algorithm_examples.case_decision_tree`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
p=np.array([.5,.5]); return 1-np.sum(p*p)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="svm"></a>
## 支持向量机 · svm

**模型与核心公式**：$\min_{w,b,\xi}\tfrac12\|w\|^2+C\sum_i\xi_i,\ y_i(w^Tx_i+b)\ge1-\xi_i,\xi_i\ge0$。

**符号与输入输出**：w/b为分隔超平面，ξ为软间隔，C为惩罚；核须适配半正定条件。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：训练内尺度/超参，标签约定明确；核/样本预算可承受。

**失败边界**：未缩放距离支配、核病态；边距不是概率，需额外校准。反例/拒绝情形：非线性不可分样本硬间隔不可行，不应删除样本以假装可分。

**步骤与成本**：选核/尺度→训练内调C等→求解→间隔/KKT与外样本核验。核法存储常O(n²)，求解实现/容差影响更大。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：一维两点x=−1/+1，标签−1/+1，硬间隔解w=1,b=0，总间隔2。期望核对量：`[1, 2]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id svm`。固定案例实现为`modelcrew.algorithm_examples.case_svm`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
w=max(1/1,1/1); return [w,2/abs(w)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="knn"></a>
## K近邻 · knn

**模型与核心公式**：$\hat y(x)=\operatorname{mode}\{y_i:i\in N_k(x)\}$。

**符号与输入输出**：N为给定距离下训练k近邻，回归改用邻居均值/加权均值。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：距离/尺度、k≤有效训练量、并列和权重规则明确。

**失败边界**：高维距离集中、噪声敏感；相同实体跨集合会泄漏。反例/拒绝情形：k=4而训练仅3行不合法；不能重复最后邻居凑数。

**步骤与成本**：训练缩放→近邻查询→投票/回归→独立验证。朴素查询O(np)另加选邻成本，索引受维数限制。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：训练x=(0,2,5),标签(0,0,1)，query=4；k=1预测1,k=3预测0。期望核对量：`[1, 0]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id knn`。固定案例实现为`modelcrew.algorithm_examples.case_knn`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([0.,2.,5.]); y=np.array([0,0,1]); order=np.argsort(abs(x-4)); return [y[order[0]],int(y[order[:3]].mean()>.5)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="random-forest"></a>
## 随机森林 · random-forest

**模型与核心公式**：$\hat p_k(x)=B^{-1}\sum_{b=1}^B\hat p_{bk}(x)$。

**符号与输入输出**：B为树数，p_b为各树类别概率，回归为树预测均值。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：训练bootstrap/特征随机化和树约束固定；独立测试与OOB用途区分。

**失败边界**：树相关性高限制方差收益；OOB不是任意时间/分组任务的无泄漏验证。反例/拒绝情形：把树数量当作独立实验重复数来缩小CI，忽略了相关训练数据。

**步骤与成本**：训练抽样/特征子集→多树→聚合→外样本/校准与稳定性。B倍树构建成本，可并行但记录总预算。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：三个固定树的类别1概率0/1/1，平均2/3，阈值.5预测1。期望核对量：`[0.6666666666666666, 1]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id random-forest`。固定案例实现为`modelcrew.algorithm_examples.case_random_forest`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
p=np.mean([0.,1.,1.]); return [p,int(p>=.5)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="naive-bayes"></a>
## 朴素贝叶斯 · naive-bayes

**模型与核心公式**：$P(c|x)\propto P(c)\prod_jP(x_j|c)$。

**符号与输入输出**：c为类别，x_j为特征；乘积来自给定类的条件独立假设。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：按特征类型选Bernoulli/Multinomial/Gaussian模型并设平滑。

**失败边界**：相关特征可重复计证据；零频使后验归零，概率校准未必好。反例/拒绝情形：所有类对观测组合概率0时后验分母0，不能任意归一。

**步骤与成本**：训练类先验/条件分布→对数后验→归一→独立评估。拟合/预测常O(np)，参数随模型形式不同。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：两类先验各.5，观测二元特征1，条件概率(.2,.8)，后验(.2,.8)。期望核对量：`[0.2, 0.8]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id naive-bayes`。固定案例实现为`modelcrew.algorithm_examples.case_naive_bayes`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
w=np.array([.5,.5])*np.array([.2,.8]); return w/w.sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="adaboost"></a>
## AdaBoost · adaboost

**模型与核心公式**：$\alpha_t=\tfrac12\ln[(1-\epsilon_t)/\epsilon_t],\ w_i'\propto w_i e^{-\alpha_ty_ih_t(x_i)}$。

**符号与输入输出**：此为二分类离散AdaBoost，y/h∈{−1,1}，ε为加权错误率。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：弱学习器有优于随机的加权表现；边界ε=0需明确提前停止。

**失败边界**：ε≥.5不具本条正向提升意义；噪声高时反复加权离群点。反例/拒绝情形：ε=0直接代log会发散，应按完美弱器停止规则处理。

**步骤与成本**：带权拟合→算ε→弱器权→样本更新归一→验证/早停。轮数×弱学习器成本。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：四样本初权.25，前三判对最后判错，ε=.25；更新权(1/6,1/6,1/6,1/2)。期望核对量：`[0.16666666666666666, 0.16666666666666666, 0.16666666666666666, 0.5]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id adaboost`。固定案例实现为`modelcrew.algorithm_examples.case_adaboost`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
a=.5*math.log(3); w=np.ones(4)*.25*np.exp(-a*np.array([1,1,1,-1])); return w/w.sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="gbdt"></a>
## GBDT · gbdt

**模型与核心公式**：$r_{it}=-\partial L(y_i,F(x_i))/\partial F,\ F_t=F_{t-1}+\eta h_t$。

**符号与输入输出**：r为负梯度，h为拟合负梯度的回归树，η为学习率。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：损失/树复杂度/停止按训练内验证选择，时序与分组正确。

**失败边界**：梯度符号错会增损；训练轮数过多过拟合；残差仅平方损失时直接等同。反例/拒绝情形：用正梯度而非负梯度拟合并相加，可能使损失上升。

**步骤与成本**：初始化常数→负梯度→拟合树→收缩更新→验证早停。轮数×树训练成本，直方图/排序实现不同。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：平方损失1/2(y−F)²，y=(1,3)，F0=(0,0)，单叶负梯度均值2，η=.5；预测更新(1,1)。期望核对量：`[1, 1]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id gbdt`。固定案例实现为`modelcrew.algorithm_examples.case_gbdt`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
y=np.array([1.,3.]); F=np.zeros(2); leaf=np.mean(y-F); return F+.5*leaf
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="xgboost"></a>
## XGBoost · xgboost

**模型与核心公式**：$w_j^*=-G_j/(H_j+\lambda);\ \mathcal L\simeq\sum_j[G_jw_j+\tfrac12(H_j+\lambda)w_j^2]+\gamma T$。

**符号与输入输出**：G/H为一叶梯度/Hessian和，λ为L2，γ为叶数惩罚。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：损失可提供有效梯度/Hessian，正则/抽样训练内选择。

**失败边界**：叶数/深度过大会过拟合；H+λ≤0不合法；公式不等于全后端接通。反例/拒绝情形：H+λ=0时除零，不能加任意小数掩盖无定义目标。

**步骤与成本**：梯度统计→候选分裂增益→正则化叶值→收缩更新→外样本检验。直方图/精确分裂实现不同，按树数、深度、特征/样本预算记录。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：一叶G=−4,H=2,λ=2；最优增量w=1，并核对二次近似导数为0。期望核对量：`[1, 0]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id xgboost`。固定案例实现为`modelcrew.algorithm_examples.case_xgboost`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
G,H,lam=-4.,2.,2.; w=-G/(H+lam); return [w,G+(H+lam)*w]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="lightgbm"></a>
## LightGBM · lightgbm

**模型与核心公式**：$\operatorname{Gain}=G_L^2/(H_L+\lambda)+G_R^2/(H_R+\lambda)-G^2/(H+\lambda)$。

**符号与输入输出**：G/H为梯度统计；叶优先生长与直方图/采样是实现策略。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：正确处理类别/缺失语义，叶数/最小叶样本等约束需训练内选择。

**失败边界**：本增益约定省略公共1/2及分裂罚项，不能跨约定直接比较日志；小样本叶过拟合。反例/拒绝情形：把预测目标编码直接计算在全数据上会泄漏，叶值再准也无效。

**步骤与成本**：直方图统计→择叶分裂→二阶叶值→收缩迭代→时间/分组验证。与分箱数、树数、叶数及样本相关；后端另验。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：G_L=−2,H_L=1,G_R=2,H_R=1,λ=1；父G=0,H=2，未含1/2增益4。期望核对量：`4`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id lightgbm`。固定案例实现为`modelcrew.algorithm_examples.case_lightgbm`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return (-2)**2/(1+1)+2**2/(1+1)-0**2/(2+1)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="catboost"></a>
## CatBoost · catboost

**模型与核心公式**：$\operatorname{TS}_i=(\sum_{j\prec i,\,c_j=c_i}y_j+a p)/(\#\{j\prec i:c_j=c_i\}+a)$。

**符号与输入输出**：TS为有序类别统计，≺为训练置换次序，a>0为先验强度，p为先验。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：仅使用该样本之前的训练标签；与有序提升/对称树等后端机制区分。

**失败边界**：全量目标编码含自身标签会泄漏；本例只核对有序统计组件。反例/拒绝情形：先前为空且a=0使分母零；把当前y_i加入分子不符合有序定义。

**步骤与成本**：训练内置换→有序统计→提升建树→独立验证；保留类别语义。依树深/轮数及类别统计实现；库版本另验。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：同类先前标签=(1,0)，a=2,p=.5；新样本有序统计(1+1)/(2+2)=.5。期望核对量：`0.5`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id catboost`。固定案例实现为`modelcrew.algorithm_examples.case_catboost`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return (sum([1.,0.])+2*.5)/(2+2)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="stacking"></a>
## Stacking · stacking

**模型与核心公式**：$z_{ib}=f_b^{(-fold(i))}(x_i),\ \hat y=g(z_1,\ldots,z_B)$。

**符号与输入输出**：z为基模型折外预测，g为元学习器。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：折划分遵守时间/分组；元学习器只接折外预测，最终测试不参与调参。

**失败边界**：训练内拟合预测喂元模型会泄漏；不同折时间边界要一致。反例/拒绝情形：若1/3来自各模型对自身训练样本的预测，则不能称作OOF。

**步骤与成本**：生成OOF→拟合元模型→训练基模型最终版→独立测试。各基模型多折训练成本加元模型成本，不能当免费增益。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：两基模型已合法获得折外预测(1,3)，元线性权(.25,.75)无截距；融合2.5，仅核对聚合。期望核对量：`2.5`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id stacking`。固定案例实现为`modelcrew.algorithm_examples.case_stacking`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return np.array([1.,3.])@np.array([.25,.75])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="kmeans"></a>
## K-Means · kmeans

**模型与核心公式**：$\min_{z,\mu}\sum_i\|x_i-\mu_{z_i}\|^2$。

**符号与输入输出**：z为簇标，μ为中心，k为簇数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：欧氏数值特征/尺度和k明确，初始中心及空簇策略记录。

**失败边界**：非凸局部极小、非球形/异密度不适配；簇编号任意。反例/拒绝情形：k>样本数或出现空簇而不处理，会产生无定义均值。

**步骤与成本**：初始化→最近中心分配→均值更新→多初值/停止核验。Lloyd每轮O(nkp)，轮数不作固定保证。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(0,2,8,10)，初中心(0,10)，一次分配后中心(1,9)，SSE=4。期望核对量：`[1, 9, 4]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id kmeans`。固定案例实现为`modelcrew.algorithm_examples.case_kmeans`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([0.,2.,8.,10.]); labels=np.argmin(abs(x[:,None]-np.array([0.,10.])),axis=1); c=np.array([x[labels==j].mean() for j in range(2)]); return [*c,np.sum((x-c[labels])**2)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="hierarchical"></a>
## 层次聚类 · hierarchical

**模型与核心公式**：$D(A,B)=\min_{a\in A,b\in B}d(a,b)\quad\text{单链接示例}$。

**符号与输入输出**：A/B为簇；complete/average/Ward有不同距离定义。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：距离与链接准则明确；Ward要求其平方欧氏方差解释对应的输入。

**失败边界**：单链接链化、尺度敏感；不能把任意距离的Ward当欧氏方差法。反例/拒绝情形：把相关距离直接传Ward但仍解释为原坐标方差最小化，含义不符。

**步骤与成本**：距离→最小簇对合并→更新距离→树切割/稳定性检查。多数实现O(n²)存储，时间随链接算法而异。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：点0、1、4，单链接第一次合并距离1，第二次距离3。期望核对量：`[1, 3]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id hierarchical`。固定案例实现为`modelcrew.algorithm_examples.case_hierarchical`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
Z=hierarchy.linkage(np.array([[0.],[1.],[4.]]),method='single'); return Z[:,2]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="dbscan"></a>
## DBSCAN · dbscan

**模型与核心公式**：$N_\epsilon(p)=\{q:d(p,q)\le\epsilon\},\ |N_\epsilon(p)|\ge m\Rightarrow\text{核心点}$。

**符号与输入输出**：ε为邻域半径，m为min_samples，本条计入自身。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：尺度/距离、边界点并列归属和含自身规则明确。

**失败边界**：异密度难用单ε；高维退化；边界点可能依遍历序归簇。反例/拒绝情形：m=2但忘记自身会把本例前两点错判为非核心。

**步骤与成本**：找核心→连通核心分量→附边界→噪声；不把标签编号当含义。有索引时常较快，最坏O(n²)时间/存储依实现。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：一维点(0,.1,5)，ε=.2,m=2含自身；前两点成簇，5为噪声；簇数1、噪声数1。期望核对量：`[1, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id dbscan`。固定案例实现为`modelcrew.algorithm_examples.case_dbscan`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
labels=dbscan_1d([0.,.1,5.],.2,2); return [len(set(labels)-{-1}),sum(t==-1 for t in labels)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="gmm"></a>
## GMM · gmm

**模型与核心公式**：$p(x)=\sum_k\pi_k\mathcal N(x|\mu_k,\Sigma_k),\ r_{ik}=\frac{\pi_k\mathcal N_k(x_i)}{\sum_j\pi_j\mathcal N_j(x_i)}$。

**符号与输入输出**：π为混合权，r为责任度，Σ为协方差。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：成分/协方差类型、可识别性及正定正则明确。

**失败边界**：似然可因协方差坍缩而无界；局部极大与标签置换；密度不是类别因果。反例/拒绝情形：任一协方差变0时普通高斯密度不合法，不能接受无穷似然。

**步骤与成本**：初始化→E责任度→M更新→正则/多初值→持出似然。全协方差每轮约O(nkp²+kp³)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：等权正态N(0,1)、N(2,1)，x=1对称，责任度(.5,.5)。期望核对量：`[0.5, 0.5]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id gmm`。固定案例实现为`modelcrew.algorithm_examples.case_gmm`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
w=np.array([.5,.5])*stats.norm.pdf(1,loc=[0,2],scale=1); return w/w.sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="mean-shift"></a>
## Mean Shift · mean-shift

**模型与核心公式**：$m(x)=\frac{\sum_iK_h(x_i-x)x_i}{\sum_iK_h(x_i-x)},\ x\leftarrow m(x)$。

**符号与输入输出**：K_h为非负带宽核，m为加权局部均值。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：核/带宽/停止和模式合并规则明确，分母正。

**失败边界**：带宽决定簇；空邻域分母0；局部模式不等于全局最大密度。反例/拒绝情形：种子离所有点远且紧支撑核为空时不能返回任意中心。

**步骤与成本**：设种子→加权均值移动→收敛→合并近模式→稳定性检查。朴素每轮每种子O(np)，总成本随种子数增长。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：点(0,2,10)，平顶核h=3，初x=1，邻域0/2，新均值1。期望核对量：`1`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id mean-shift`。固定案例实现为`modelcrew.algorithm_examples.case_mean_shift`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([0.,2.,10.]); neighbors=x[abs(x-1)<=3]; return neighbors.mean()
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

<a id="tsne"></a>
## t-SNE · tsne

**模型与核心公式**：$p_{j|i}\propto e^{-\|x_i-x_j\|^2/(2\sigma_i^2)},\ p_{ij}=(p_{j|i}+p_{i|j})/(2n),\ q_{ij}\propto(1+\|y_i-y_j\|^2)^{-1},\ L=\sum_{i\ne j}p_{ij}\ln(p_{ij}/q_{ij})$。

**符号与输入输出**：p为对称归一高维相似度，q为低维Student相似度，σ由perplexity约束。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：perplexity与样本规模、距离/随机种子明确；只作探索显示。

**失败边界**：非凸/种子敏感；簇间距离与大小未必保真；不能从二维分离直接推显著性。反例/拒绝情形：把t-SNE图中远近当原空间精确距离作回归解释不成立。

**步骤与成本**：高维邻域概率→对称化→低维优化→多种子/参数及邻域保真核对。精确O(n²)；近似实现复杂度另核验。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：三点低维坐标(0,1,2)，六个有序非对角项的p均为1/6；Student核归一q后KL=(2/3)ln(.8)+(1/3)ln2≈.082286693；仅核对目标组件。期望核对量：`0.08228669264325505`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id tsne`。固定案例实现为`modelcrew.algorithm_examples.case_tsne`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
y=np.array([0.,1.,2.]); w=1/(1+(y[:,None]-y[None,:])**2); q=w[~np.eye(3,dtype=bool)]; q=q/q.sum(); p=np.ones(6)/6; return np.sum(p*np.log(p/q))
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="umap"></a>
## UMAP · umap

**模型与核心公式**：$\mu_{ij}=e^{-\max(0,d_{ij}-\rho_i)/\sigma_i},\ \nu_{ij}=(1+a\|y_i-y_j\|^{2b})^{-1}$。

**符号与输入输出**：μ为有向模糊邻域成员度，ρ/σ为局部尺度，ν为低维成员度。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：邻居数、距离/局部连通和参数a/b明确，对称联合通常μ+μᵀ−μμᵀ。

**失败边界**：嵌入不保全局距离/密度；随机优化/超参敏感；本例不运行UMAP后端。反例/拒绝情形：二维孤岛不自动证明原空间存在独立真实类别。

**步骤与成本**：构造近邻→局部尺度→模糊联合→交叉熵优化→邻域/稳定性核对。依近邻搜索、维度和优化轮次，不承诺通用近线性。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：μ12=.2,μ21=.5，模糊联合.6；a=b=1且低维距离2，ν=.2。期望核对量：`[0.6, 0.2]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id umap`。固定案例实现为`modelcrew.algorithm_examples.case_umap`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return [.2+.5-.2*.5,1/(1+2**2)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="mlp"></a>
## MLP · mlp

**模型与核心公式**：$h=\sigma(W_1x+b_1),\ \hat y=W_2h+b_2$。

**符号与输入输出**：W/b为层参数，σ为明确定义激活；训练目标与输出链接另定。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：输入/隐藏/输出维度和损失匹配，训练验证隔离。

**失败边界**：过拟合、梯度消失/爆炸、死ReLU；前向例不证明训练/收敛。反例/拒绝情形：输出维度/标签不匹配时不能通过广播悄悄改变损失。

**步骤与成本**：初始化→前向→损失→反向/优化→验证早停/重复。每步约层间权重数×batch，训练乘轮次。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,−1)，隐藏W1=[[1,1],[1,−1]],b1=0，ReLU后(0,2)，输出权(1,2)得4。期望核对量：`4`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id mlp`。固定案例实现为`modelcrew.algorithm_examples.case_mlp`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([1.,-1.]); h=np.maximum(np.array([[1.,1.],[1.,-1.]])@x,0); return np.array([1.,2.])@h
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="cnn"></a>
## CNN · cnn

**模型与核心公式**：$y_t=\sum_{j=0}^{K-1}w_jx_{t+j}+b$。

**符号与输入输出**：此处采用深度学习库常用互相关约定，不翻转核；stride/padding另定。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：通道、核/步长、边界/填充和输入尺度明确。

**失败边界**：卷积与互相关符号差异；池化丢细节；不能默认适合无局部结构表格。反例/拒绝情形：若把核翻转计算却对照互相关API，会得到反号结果。

**步骤与成本**：设置局部结构→卷积/激活/池化→训练→外样本核验。1D约O(TKCinCout)，图像还乘空间位置数。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,2,3)，核(1,−1)，valid互相关输出(−1,−1)。期望核对量：`[-1, -1]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id cnn`。固定案例实现为`modelcrew.algorithm_examples.case_cnn`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return np.correlate([1.,2.,3.],[1.,-1.],mode='valid')
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="rnn"></a>
## RNN · rnn

**模型与核心公式**：$h_t=\tanh(W_xx_t+W_hh_{t-1}+b)$。

**符号与输入输出**：h为隐藏态，W为输入/递归权，b为偏置。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：序列顺序、状态初始化/截断及维度明确，训练/测试边界不串态。

**失败边界**：长期梯度消失/爆炸；隐藏态混用不同实体造成泄漏。反例/拒绝情形：不同患者序列共享未重置隐藏态会混入另一人的历史。

**步骤与成本**：逐时前向→截断或完整BPTT→梯度控制→时间/分组验证。每步O(h(h+d))，反向存储随截断长度增长。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：标量x=1,h_prev=0,Wx=1,Wh=.5,b=0；h=tanh1≈.761594。期望核对量：`0.7615941559557649`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id rnn`。固定案例实现为`modelcrew.algorithm_examples.case_rnn`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return np.tanh(1*1+.5*0)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="lstm"></a>
## LSTM · lstm

**模型与核心公式**：$c_t=f_t\odot c_{t-1}+i_t\odot\tilde c_t,\ h_t=o_t\odot\tanh(c_t)$。

**符号与输入输出**：f/i/o为sigmoid遗忘/输入/输出门，c为记忆，h为隐藏状态。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：输入与状态维度一致，序列边界/初始态明确；所有门含可训练仿射变换。

**失败边界**：前向门值正确不证明训练成功；长序列仍可能梯度/过拟合问题。反例/拒绝情形：把训练终态泄漏到独立测试序列的初态会污染评估。

**步骤与成本**：构造因果序列→门与记忆更新→反向传播→梯度控制→外样本检验。每步O(h(h+d))，序列长T时乘T；训练存储额外增长。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：固定f=i=o=.5，c_prev=0，候选记忆.8；c=.4,h=.5tanh(.4)。期望核对量：`[0.4, 0.18997448112761245]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id lstm`。固定案例实现为`modelcrew.algorithm_examples.case_lstm`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
c=.5*0+.5*.8; return [c,.5*np.tanh(c)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="gru"></a>
## GRU · gru

**模型与核心公式**：$h_t=(1-z_t)\odot n_t+z_t\odot h_{t-1}$。

**符号与输入输出**：z为保留旧态的更新门，n为经重置门r计算的候选态；约定与库接口需核对。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：明确更新门约定和重置施加位置，输入/隐藏维度匹配。

**失败边界**：不同文献对z含义相反；不能混用方程和权重；前向不等于训练。反例/拒绝情形：将z误当新态权重会算成.5，与本条约定不同。

**步骤与成本**：计算z/r→算候选n→混合旧态→训练/验证。每步O(h(h+d))；T步线性放大。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：z=.25，n=.8，h_prev=.4；本约定h=.7。期望核对量：`0.7`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id gru`。固定案例实现为`modelcrew.algorithm_examples.case_gru`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return (1-.25)*.8+.25*.4
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="transformer"></a>
## Transformer · transformer

**模型与核心公式**：$\operatorname{Attention}(Q,K,V)=\operatorname{softmax}(QK^T/\sqrt{d_k}+M)V$。

**符号与输入输出**：Q/K/V为查询键值，d_k为键维数，M为可见性掩码。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：维度和mask语义一致，预测任务使用因果mask，位置编码另定义。

**失败边界**：无mask会见未来；注意力权重非因果解释；完整模型还有多头/残差/前馈/归一化。反例/拒绝情形：掩码后一行全为负无穷，softmax无定义，应拒绝而非返回NaN。

**步骤与成本**：构造token/位置→多头注意力→残差前馈→训练/外样本检验。标准注意力O(T²d)算术和O(T²)注意力存储。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：Q=1，K=(0,ln3)，V=(2,6)，d_k=1；权重(.25,.75)，输出5。期望核对量：`5`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id transformer`。固定案例实现为`modelcrew.algorithm_examples.case_transformer`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return special.softmax(np.array([0.,math.log(3)]))@np.array([2.,6.])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="autoencoder"></a>
## Autoencoder · autoencoder

**模型与核心公式**：$z=f_\theta(x),\hat x=g_\phi(z),\min\sum_i\ell(x_i,\hat x_i)$。

**符号与输入输出**：z为瓶颈表示，f/g为编码解码，ℓ为重构损失。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：压缩/稀疏等约束与任务明确，训练/验证划分及异常阈值训练内校准。

**失败边界**：大容量可能学恒等映射；低重构误差不证明表示适合预测，也非异常真值。反例/拒绝情形：直接用含大量异常的测试集选阈值再报告检测率，会泄漏。

**步骤与成本**：设计瓶颈→训练重构→持出检验→下游/异常验证。依网络权数/批量/轮数，与MLP/CNN等架构相关。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=(1,3)，编码z=(x1+x2)/2=2，解码(z,z)=(2,2)，均方重构误差1。期望核对量：`[2, 1]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id autoencoder`。固定案例实现为`modelcrew.algorithm_examples.case_autoencoder`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([1.,3.]); z=x.mean(); rec=np.repeat(z,2); return [z,np.mean((x-rec)**2)]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

LightGBM条目中的Gain采用省略共同1/2因子的分裂评分；实际损失下降须使用相同的1/2及叶惩罚约定。
