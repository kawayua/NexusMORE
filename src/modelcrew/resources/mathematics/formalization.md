# 枢模 · 数学形式化与推导

版本1.0.0；2026-11-14；项目独立编写。数学资料用于建模论证、推导和核对，不替代中文建模论文结构，不自动证明、选检验或批准结果。先读本目录index，再按问题读取相关小节；保存来源/版本/哈希、假设、未满足条件和open_gaps。旧21份collaboration指南及冻结任务保持字节。

每节区分完整的文字论证与有限软件核对：符号恒等式检查仅针对已定义表达式；有限例、数值误差和统计量计算不构成通用定理证明、真实设计前提核验或独立审查。所有数值来自固定教学输入，不复制进业务结论。统计区间明确目标/水平/方法，假设未验证时不默认成立。

## 阅读与建模交接

先把本节结论绑定当前模型/数学包的符号、假设、版本和证据，指出是精确等式、界、近似或统计推断。条件未知或关键逻辑缺步记open_gaps，不补造结果。整篇只有一张全局符号表；推导细节可进附录。作者核对、独立M1/P1/P2/W1/W2与用户模型/结果确认分别执行。

<a id="domains"></a>
## 符号、定义域与等价变换 · domains

**对象、命题与核心公式**：$x\in\mathbb R\setminus\{1\},\quad (x^2-1)/(x-1)=x+1$。

**条件与符号**：x为实标量，分母x−1非零；整数/实数/随机变量、参数/观测值分别登记，公式注明适用题目和单位。

**逐步推导/论证与使用规则**：由平方差x²−1=(x−1)(x+1)，在x≠1上约去x−1；等式只在共同定义域成立，不能据化简给原式补上x=1。设u为实数，sqrt(u²)=|u|，仅u≥0时等于u。每个新记号先定义对象、索引、维度和范围，再使用；整篇符号仍归唯一全局表。

**失败边界与反例**：在x=1约分掩盖未定义；u=−2时sqrt(u²)=2≠u。平方/开方会引入或丢失分支，除变量前检查是否为0，log要求正实数。

**可复算案例与目标量**：x=2原式与化简式都3；u=−2时sqrt(u²)=2。预期输出：`[3, 3, 2]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id domains` 调用包内固定可信函数`modelcrew.mathematical_examples.case_domains`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x=2.; return [(x*x-1)/nonzero(x-1),x+1,math.sqrt((-2.)**2)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="dimensions"></a>
## 量纲、维度与无量纲化 · dimensions

**对象、命题与核心公式**：$\rho=m/V,\quad v=L/T,\quad \Pi=vT/L$。

**条件与符号**：m为质量，V为体积，L为长度，T为时间；单位需转换至共同体系，L/T中T非零；向量n×1与矩阵m×n区分。

**逐步推导/论证与使用规则**：质量守恒量纲给[ρ]=M L^−3，速度给[v]=L T^−1，故Π无量纲；量纲相同只是可相加的必要条件，物理含义也须一致。矩阵Ax需A列数等于x长度；指数/对数的自变量应是无量纲比值，温度零点等非纯乘法换算单独说明。

**失败边界与反例**：不能相加3米与2秒；不能对带单位长度直接写log L；单看数值相同不合并同名异义符号；量纲正确不证明模型正确。

**可复算案例与目标量**：m=2kg,V=4m³,L=3m,T=2s，ρ=.5，v=1.5，Π=1。预期输出：`[0.5, 1.5, 1]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id dimensions` 调用包内固定可信函数`modelcrew.mathematical_examples.case_dimensions`；以下片段的辅助函数同包提供，不执行资料文本：

```python
m,V,L,T=2.,4.,3.,2.; return [m/V,L/T,(L/T)*T/L]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="linear-system"></a>
## 线性方程、秩与可识别性 · linear-system

**对象、命题与核心公式**：$Ax=b,\quad \operatorname{rank}(A)=\operatorname{rank}([A|b])$。

**条件与符号**：A为m×n实矩阵，x为n维未知向量，b为m维已知向量；数据有限且单位相容。

**逐步推导/论证与使用规则**：行消元是可逆的初等行变换，故不改解集；一致性要求增广前后秩相同；一致时自由度为n−rank(A)，唯一解还需rank(A)=n。方阵满秩才可写A^−1b；实际用分解求解而非显式求逆。小残差不保证小前向误差，需条件数与输入误差。

**失败边界与反例**：A=[[1,1],[2,2]],b=[1,3]无解；b=[1,2]有无穷解。病态矩阵虽可逆仍会放大测量误差，不凭机器阈值给精确秩定理。

**可复算案例与目标量**：A=[[2,1],[1,3]],b=(1,2)，解(.2,.6)，残差0。预期输出：`[0.2, 0.6, 0]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id linear-system` 调用包内固定可信函数`modelcrew.mathematical_examples.case_linear_system`；以下片段的辅助函数同包提供，不执行资料文本：

```python
A=np.array([[2.,1.],[1.,3.]]);b=np.array([1.,2.]);x=solve_unique(A,b);return [*x,np.linalg.norm(A@x-b)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="least-squares"></a>
## 最小二乘推导与投影 · least-squares

**对象、命题与核心公式**：$\min_\beta\|X\beta-y\|_2^2,\quad X^TX\hat\beta=X^Ty$。

**条件与符号**：X为n×p设计矩阵，y为n维响应；最小二乘有最小范数解，系数唯一需列满秩；统计推断额外需要误差假设。

**逐步推导/论证与使用规则**：展开J=βᵀXᵀXβ−2βᵀXᵀy+yᵀy，求导得2Xᵀ(Xβ−y)=0；Hessian=2XᵀX半正定，故正规方程解为全局极小。列满秩时正定且唯一；残差与列空间正交。计算优先QR/SVD，正规方程会平方条件数。

**失败边界与反例**：共线列使系数不唯一，但拟合投影仍唯一；正规方程不是因果识别；截距/权重/正则化改变目标和推断，不机械套同一公式。

**可复算案例与目标量**：x=0,1,2，y=1,3,5，截距1、斜率2，x=3预测7，正交残差0。预期输出：`[1, 2, 7, 0]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id least-squares` 调用包内固定可信函数`modelcrew.mathematical_examples.case_least_squares`；以下片段的辅助函数同包提供，不执行资料文本：

```python
X=np.c_[np.ones(3),[0.,1.,2.]];y=np.array([1.,3.,5.]);b=np.linalg.lstsq(X,y,rcond=None)[0];return [*b,np.array([1.,3.])@b,np.linalg.norm(X.T@(X@b-y))]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="differentiation"></a>
## 链式法则、梯度与Hessian · differentiation

**对象、命题与核心公式**：$f(x,y)=x^2y+\sin y,\quad \nabla f=(2xy,x^2+\cos y)^T$。

**条件与符号**：x,y为实数，f二次连续可微；多元复合g∘h要求相应点可微且Jacobian形状可乘。

**逐步推导/论证与使用规则**：分别固定另一变量求偏导；再对梯度逐项求导得到H=[[2y,2x],[2x,−sin y]]。复合映射h:Rⁿ→Rᵐ、g:Rᵐ→R时列梯度为J_hᵀ∇g；混合偏导相等需正则条件。数值差分是近似核对，不能替代可微性假设。

**失败边界与反例**：|x|在0不可微；只存在各方向导数不必全微分；梯度转置/矩阵形状错误会给错链式法则。

**可复算案例与目标量**：在(2,0)梯度(0,5)，H按行展开为(0,4,4,0)，SymPy仅核对该显式函数。预期输出：`[0, 5, 0, 4, 4, 0]`。证据层级`symbolic_identity_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id differentiation` 调用包内固定可信函数`modelcrew.mathematical_examples.case_differentiation`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x,y=sp.symbols('x y',real=True);f=x*x*y+sp.sin(y);subs={x:2,y:0};return [float(sp.diff(f,v).subs(subs)) for v in [x,y]]+[float(a.subs(subs)) for a in sp.hessian(f,(x,y))]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="taylor"></a>
## Taylor余项与近似范围 · taylor

**对象、命题与核心公式**：$e^h=1+h+h^2/2+e^\xi h^3/6,\quad \xi\in(0,h)$。

**条件与符号**：此式取h>0且exp在[0,h]三次可微；一般Taylor需展开点到目标点之间相应阶导数存在并有余项条件。

**逐步推导/论证与使用规则**：从带Lagrange余项的二阶展开写出精确等式；因exp单调，0<R≤exp(h)h³/6；若忽略R才改用近似号。一般多变量需方向导数/高阶张量或范数界，不能把一维余项无条件照抄。

**失败边界与反例**：h很大时局部展开误差可能过大；只给O(h³)而无常数/范围不能给具体误差保证；渐近展开不总是收敛级数。

**可复算案例与目标量**：h=.1，二阶近似1.105，实际余项.0001709180756477302且不超过exp(.1)*.001/6。预期输出：`[1.105, 0.0001709180756477302, 1]`。证据层级`numerical_error_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id taylor` 调用包内固定可信函数`modelcrew.mathematical_examples.case_taylor`；以下片段的辅助函数同包提供，不执行资料文本：

```python
h=.1;p=1+h+h*h/2;r=math.exp(h)-p;return [p,r,int(0<=r<=math.exp(h)*h**3/6)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="integration-limits"></a>
## 积分、求导与极限交换 · integration-limits

**对象、命题与核心公式**：$F(a)=\int_0^1e^{ax}\,dx,\quad F'(a)=\int_0^1xe^{ax}\,dx$。

**条件与符号**：a为实参数，在任意有界邻域|a|≤A上，e^(ax)及参数导数由可积常数exp(A)控制；积分限固定。

**逐步推导/论证与使用规则**：先核对可测、可积和统一支配，再用积分下求导定理交换；在a=0，F(0)=∫1dx=1，F′(0)=∫x dx=1/2。Tonelli允许非负函数交换积分（结果可无穷），Fubini通常要求绝对可积；条件不同不能混用。

**失败边界与反例**：f_n=n·1_(0,1/n)在(0,1)逐点趋0但积分恒1，缺统一可积支配时极限与积分不能随便交换；边界随参数变还需端点项。

**可复算案例与目标量**：符号积分在a=0的函数和导数分别1与.5；反例单列分析不由软件证明定理。预期输出：`[1, 0.5]`。证据层级`symbolic_identity_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id integration-limits` 调用包内固定可信函数`modelcrew.mathematical_examples.case_integration_limits`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x,a=sp.symbols('x a',real=True);return [float(sp.integrate(sp.exp(a*x).subs(a,0),(x,0,1))),float(sp.integrate(sp.diff(sp.exp(a*x),a).subs(a,0),(x,0,1)))]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="probability"></a>
## 条件概率、期望与方差 · probability

**对象、命题与核心公式**：$P(D|+)={P(+|D)P(D)\over P(+|D)P(D)+P(+|\neg D)P(\neg D)}$。

**条件与符号**：D为事件，+为阳性事件，分母P(+)>0；概率在[0,1]；期望存在、方差有限时才谈对应运算。

**逐步推导/论证与使用规则**：从联合概率P(D,+)=P(+|D)P(D)，按D/非D分割全概率，再除以P(+)得Bayes。E(aX+b)=aEX+b只需可积；独立和的方差可相加，相关时补2Cov。二项n次独立同率Bernoulli给EX=np，Var=np(1−p)。

**失败边界与反例**：高灵敏度不代表高后验概率；概率为0的条件事件需更精细定义；Var(X+Y)在X=Y时不是2Var(X)，而是4Var(X)。

**可复算案例与目标量**：患病率.01、灵敏度.9、假阳性率.05时后验2/13；二项n10,p.2均值2、方差1.6。预期输出：`[0.15384615384615385, 2, 1.6]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id probability` 调用包内固定可信函数`modelcrew.mathematical_examples.case_probability`；以下片段的辅助函数同包提供，不执行资料文本：

```python
prior=.01;sens=.9;fpr=.05;return [sens*prior/nonzero(sens*prior+fpr*(1-prior)),10*.2,10*.2*.8]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="sensitivity-errors"></a>
## 误差传播与局部敏感性 · sensitivity-errors

**对象、命题与核心公式**：$\operatorname{Var}(f(\hat\theta))\approx g^T\Sigma g,\quad g=\nabla f(\theta)$。

**条件与符号**：θ为实参数向量，f在附近可微，估计误差足够小；Σ为同一尺度下协方差，必须包含相关项。

**逐步推导/论证与使用规则**：一阶Taylor给f(θ+δ)≈f(θ)+gᵀδ；线性组合方差为gᵀΣg。确定性误差若|δ_j|≤ε_j，局部最坏一阶界为Σ|g_j|ε_j；这是局部近似，不等于严格有限区间界。有限区间需控制全邻域导数/余项。

**失败边界与反例**：分母靠近0、阈值不连续或误差大时线性化失效；相关误差不能当独立；数值误差、参数不确定性与模型误差分别报。

**可复算案例与目标量**：f=x/y，x6,y2，独立标准差.1/.05；值3，一阶SE sqrt(.008125)，一阶绝对界.125。预期输出：`[3, 0.09013878188659974, 0.125]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id sensitivity-errors` 调用包内固定可信函数`modelcrew.mathematical_examples.case_sensitivity_errors`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x,y=6.,2.;g=np.array([1/y,-x/y**2]);S=np.diag([.1**2,.05**2]);return [x/y,math.sqrt(g@S@g),abs(g)@np.array([.1,.05])]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="ode-conditions"></a>
## 初值问题的存在唯一与解析核对 · ode-conditions

**对象、命题与核心公式**：$y'=-2y,\quad y(0)=3,\quad y(t)=3e^{-2t}$。

**条件与符号**：t≥0，f(t,y)=−2y连续且对y全局Lipschitz常数2；一般局部Lipschitz只先给局部唯一，延拓需排除爆破。

**逐步推导/论证与使用规则**：分离变量或积分因子给d(e^(2t)y)/dt=0，初值决定常数3；代回导数和初值核对。Picard–Lindelöf需相关矩形内连续和对状态局部Lipschitz；连续本身给适当条件下存在，不保证唯一或全局时间存在。

**失败边界与反例**：y′=sqrt(|y|),y(0)=0有零解及延迟启动解，唯一性失败；y′=y²,y(0)=1在t=1爆破，不能从局部存在跳到全局。

**可复算案例与目标量**：solve_ivp在t1应接近3exp(−2)=.4060058497098381，保留数值容差不是形式证明。预期输出：`0.4060058497098381`。证据层级`numerical_error_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id ode-conditions` 调用包内固定可信函数`modelcrew.mathematical_examples.case_ode_conditions`；以下片段的辅助函数同包提供，不执行资料文本：

```python
r=integrate.solve_ivp(lambda t,y:-2*y,(0,1),[3.],rtol=1e-11,atol=1e-13);require(r.success,'ODE failed');return r.y[0,-1]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="constrained-optimality"></a>
## 拉格朗日、KKT与充分必要条件 · constrained-optimality

**对象、命题与核心公式**：$L=f+\lambda^Tg+\nu^Th,\quad \nabla_xL=0,\ g\le0,\ h=0,\lambda\ge0,\lambda_i g_i=0$。

**条件与符号**：x连续，目标/约束可微，局部最优点满足相应约束资格才保证KKT必要；凸f/g及仿射h时满足KKT可给全局充分性。

**逐步推导/论证与使用规则**：原始可行、对偶可行、互补与站立四类条件逐一列出；例如min x²且1−x≤0，边界候选x1，站立2x−λ=0给λ2，互补为0。凸性给f(z)≥f(x)+∇f(x)ᵀ(z−x)，结合可行性与乘子符号可推出所有可行z目标不小于f(x)。

**失败边界与反例**：非凸站立点可为极大；min x且x²≤0的唯一可行最优x0却无满足站立的λ，显示约束资格不能省；离散决策不套连续KKT。

**可复算案例与目标量**：符号求解站立与活跃约束得x1,λ2,互补0。预期输出：`[1, 2, 0]`。证据层级`symbolic_identity_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id constrained-optimality` 调用包内固定可信函数`modelcrew.mathematical_examples.case_constrained_optimality`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x,l=sp.symbols('x l',real=True);s=sp.solve([2*x-l,1-x],[x,l]);return [float(s[x]),float(s[l]),float(s[l]*(1-s[x]))]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="numerical-error"></a>
## 截断、舍入、残差与收敛阶 · numerical-error

**对象、命题与核心公式**：$I=\int_0^1x^2dx=1/3,\quad T_h-I=h^2/6$。

**条件与符号**：复合梯形法等距h=1/n，函数二阶连续；精确算术下此多项式误差等式成立，浮点会叠加舍入。

**逐步推导/论证与使用规则**：每段积分二次函数与梯形面积相差h³/6，n段累加为h²/6；网格减半误差缩至1/4，由此核对二阶。对一般二阶光滑函数，|T_h−I|≤(b−a)h²max|f″|/12。报告输入误差、离散误差、停止容差和浮点误差，不把求解器success当精确结论。

**失败边界与反例**：足够小h会遭遇舍入/消去，不能无限外推阶数；收敛到离散模型不代表物理模型正确；残差小可能因病态仍解误差大。

**可复算案例与目标量**：n10/20梯形误差分别1/600、1/2400，比值4。预期输出：`[0.0016666666666666668, 0.0004166666666666667, 4]`。证据层级`numerical_error_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id numerical-error` 调用包内固定可信函数`modelcrew.mathematical_examples.case_numerical_error`；以下片段的辅助函数同包提供，不执行资料文本：

```python
errs=[]
    for n in [10,20]:
        x=np.linspace(0,1,n+1);errs.append(np.trapezoid(x*x,x)-1/3)
    return [*errs,errs[0]/errs[1]]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

