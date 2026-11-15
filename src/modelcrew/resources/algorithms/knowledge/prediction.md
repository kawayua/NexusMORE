# 枢模算法体系：预测

版本1.0.0；2026-11-14；项目独立编写。范围依据用户提供的算法主题清单，原始全文不随包复制。先读取算法索引，再按问题结构读取本章相关条目，不把算法清单当成已接通的业务求解器。

每条给核心公式、符号、准入条件、失败边界、步骤、成本和固定可复算案例。案例层级必须保留：small_complete_solution为限定小问题的完整解；single_update为一步机制；core_equation_check为公式组件；stochastic_estimate为固定种子估计。组件核算不等于完整训练、全局最优或后端安装通过。

训练拟合的预处理、特征、调参和组合权重不得使用测试或未来信息；模型、数值方法与Python API分开说明。所有新任务继续模型/结果用户确认与独立M1/P1/P2/W1/W2；阅读资料和工程案例不授予批准。

## 本体系重点补充

按时间先后划分训练、滚动验证和最终测试，所有填补、缩放、特征、阶数、早停和组合权重只在当折训练中拟合。预测起点可获得的信息必须留痕，未来协变量若实际未知不得作为输入；多步递推与直接预测分别评估，与最后值、季节最后值等简单基线比较。

误差至少报告 $MAE=n^{-1}\sum|e_i|$、$RMSE=\sqrt{n^{-1}\sum e_i^2}$；MAPE在真实值0附近失效。预测区间覆盖率与宽度按时间外样本核对，置信区间不等于个体预测区间。ARIMA须交代差分、残差相关与参数化，季节/变点不能只看全样本拟合图。LSTM/GRU/TCN/Transformer案例是门、卷积或注意力组件，不是训练证据；不能据此声称优于统计基线或已装好生产后端。

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

<a id="polynomial-regression"></a>
## 多项式回归 · polynomial-regression

**模型与核心公式**：$\hat y=\sum_{j=0}^{d}\beta_jx^j$。

**符号与输入输出**：d为预定或训练内选择阶数，β为回归系数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：阶数/样本量与尺度匹配，使用训练内选择和可稳定求解的基。

**失败边界**：高阶振荡与外推爆炸；用测试集选阶会泄漏。反例/拒绝情形：三个点用十次多项式不能唯一识别全部系数。

**步骤与成本**：生成多项式设计→缩放/正则→拟合→训练内选阶→外样本检验。O(nd²+d³)级稠密拟合，特征组合会快速增长。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x=−1,0,1，y=1,0,1，二次模型在2预测4。期望核对量：`4`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id polynomial-regression`。固定案例实现为`modelcrew.algorithm_examples.case_polynomial_regression`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([-1.,0.,1.]); b=np.linalg.lstsq(np.c_[np.ones(3),x,x*x],[1,0,1],rcond=None)[0]; return np.array([1,2,4])@b
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="exponential-smoothing"></a>
## 指数平滑 · exponential-smoothing

**模型与核心公式**：$\ell_t=\alpha y_t+(1-\alpha)\ell_{t-1},\ \hat y_{t+h}=\ell_t$。

**符号与输入输出**：ℓ为水平项，α∈[0,1]为平滑系数，此处为简单指数平滑。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：无显著趋势/季节性时用简单形式；有趋势/季节改用对应状态模型。

**失败边界**：结构突变与长趋势会造成滞后；不能自动套季节结论。反例/拒绝情形：用未来14提前更新后再预测其自身，构成时间泄漏。

**步骤与成本**：给初始水平→训练内选α→逐时更新→滚动回测与区间校准。给α时O(n)，优化及多季节另计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：ℓ0=10，α=.5，观测12/14；更新11/12.5，下一期预测12.5。期望核对量：`12.5`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id exponential-smoothing`。固定案例实现为`modelcrew.algorithm_examples.case_exponential_smoothing`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
level=10.; level=.5*12+.5*level; return .5*14+.5*level
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="gm11"></a>
## 灰色预测 · gm11

**模型与核心公式**：$x^{(1)}_k=\sum_{i\le k}x^{(0)}_i,\ x^{(0)}_k+a z_k=b,\ z_k=(x^{(1)}_{k-1}+x^{(1)}_k)/2$。

**符号与输入输出**：x⁰为原序列，x¹为一次累加，a/b为最小二乘参数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：正值、近指数趋势及级比/背景值等适配性核对，平移须记录并还原。

**失败边界**：小样本不自动适用；a≈0解析式要稳定取极限；突变外推失真。反例/拒绝情形：含负值/强周期序列直接套GM(1,1)不因数据少而合理。

**步骤与成本**：累加→背景值→估计a/b→时间响应→还原与留后验证。两参数最小二乘O(n)，误差与稳定性比速度更关键。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：x⁰=(1,2,4,8)，背景值=(2,5,11)，估计a=−2/3,b=2/3；本例检查背景方程拟合，不宣称连续响应精确还原。期望核对量：`[-0.6666666666666666, 0.6666666666666666]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id gm11`。固定案例实现为`modelcrew.algorithm_examples.case_gm11`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=np.array([1.,2.,4.,8.]); acc=np.cumsum(x); z=(acc[:-1]+acc[1:])/2; return np.linalg.lstsq(np.c_[-z,np.ones(3)],x[1:],rcond=None)[0]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="arima"></a>
## ARIMA · arima

**模型与核心公式**：$\phi(B)(1-B)^d y_t=c+\theta(B)\epsilon_t$。

**符号与输入输出**：B为滞后算子，φ/θ为AR/MA多项式，d为差分阶，ε为创新。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：差分后平稳性、可识别/可逆性及时间间隔核对；c参数化要固定。

**失败边界**：过差分、结构突变、未检验残差；软件趋势项与公式c可能不同。反例/拒绝情形：φ=1.1的无差分AR(1)非平稳，不能报告稳定长期均值。

**步骤与成本**：时间训练划分→训练内选阶→拟合→残差诊断→滚动预测。依阶数和状态空间实现，不能固定O(n)概括所有拟合。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：ARIMA(1,0,0)且c=1,φ=.5，y_t=4，未来创新均值0；一步预测3。期望核对量：`3`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id arima`。固定案例实现为`modelcrew.algorithm_examples.case_arima`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return 1+.5*4
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="sarima"></a>
## SARIMA · sarima

**模型与核心公式**：$\phi(B)\Phi(B^s)(1-B)^d(1-B^s)^D y_t=c+\theta(B)\Theta(B^s)\epsilon_t$。

**符号与输入输出**：s为周期，Φ/Θ为季节AR/MA，D为季节差分。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：周期来自领域和训练段；季节差分后诊断、时间验证。

**失败边界**：周期设错/样本不足、多重季节需额外模型；未来季节项泄漏。反例/拒绝情形：年度数据只有两期不能识别月度12期季节动态。

**步骤与成本**：确定s→差分/选阶→拟合→季节残差检查→滚动回测。依周期/阶数组成的状态维度；长周期成本可显著增大。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：仅季节AR项y_t=.8 y_(t−4)+ε_t，y_(t−4)=10，均值预测8。期望核对量：`8`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id sarima`。固定案例实现为`modelcrew.algorithm_examples.case_sarima`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return .8*10
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="var"></a>
## VAR · var

**模型与核心公式**：$y_t=c+\sum_{i=1}^{p}A_i y_{t-i}+\epsilon_t$。

**符号与输入输出**：y为k维序列，A为滞后系数，c为向量截距。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：变量时间对齐、样本足够、平稳或明确协整/VECM替代。

**失败边界**：维数高参数膨胀；伴随矩阵特征根模≥1时非稳定VAR。反例/拒绝情形：A=diag(1.2,.8)虽一步数值有限，却不具稳定长期分布。

**步骤与成本**：训练内选阶→多元回归→稳定性/残差→滚动预测。约kp+1个每方程回归量，稠密OLS按设计维度计。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：A=diag(.5,.25)，c=(1,0)，y=(2,4)；预测(2,1)，谱半径.5。期望核对量：`[2, 1, 0.5]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id var`。固定案例实现为`modelcrew.algorithm_examples.case_var`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
A=np.diag([.5,.25]); return [*(np.array([1,0])+A@np.array([2,4])),max(abs(np.linalg.eigvals(A)))]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="prophet"></a>
## Prophet · prophet

**模型与核心公式**：$y(t)=g(t)+s(t)+h(t)+\epsilon_t,\ s(t)=\sum_{k=1}^K[a_k\cos(2\pi kt/P)+b_k\sin(2\pi kt/P)]$。

**符号与输入输出**：g为趋势，s为周期，h为节假日，P/K为周期/阶数。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：趋势变点、节假日和可用未来协变量有依据，训练内选择超参数。

**失败边界**：加性形式不适合所有序列；本例仅分解，不是Prophet后端训练。反例/拒绝情形：未发生且预测时不可知的促销真实销量不能当未来特征。

**步骤与成本**：定义趋势/季节/事件→训练拟合→时间交叉验证→校准区间。依变点/谐波数及后端优化；Python库需另验环境。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：g=2+.5t，s=3cos(2πt/4)，h=0，t=4；组成预测7。期望核对量：`7`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id prophet`。固定案例实现为`modelcrew.algorithm_examples.case_prophet`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
t=4.; return 2+.5*t+3*math.cos(2*math.pi*t/4)
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

<a id="tcn"></a>
## TCN · tcn

**模型与核心公式**：$y_t=\sum_{k=0}^{K-1}w_k x_{t-dk};\ R=1+\sum_\ell(K_\ell-1)d_\ell$。

**符号与输入输出**：d为膨胀率，K为核宽，R为每层一个卷积的感受野。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：因果左填充、层数和残差维度明确；双卷积块应在R求和中计两层。

**失败边界**：使用右侧未来值会泄漏；感受野不足或边界填充未说明。反例/拒绝情形：以x_(t+2)计算当前预测违反因果卷积定义。

**步骤与成本**：构造因果卷积→残差/激活→训练→按时间评估。约O(TKdhid²)依通道，膨胀不直接增加核参数数。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：序列(1,2,3,4,5)，t=4,d=2,w=(1,2)；5+2×3=11。期望核对量：`11`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id tcn`。固定案例实现为`modelcrew.algorithm_examples.case_tcn`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
x=[1,2,3,4,5]; return x[4]+2*x[2]
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

LightGBM条目中的Gain采用省略共同1/2因子的分裂评分；实际损失下降须使用相同的1/2及叶惩罚约定。
