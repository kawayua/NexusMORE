# 枢模 · 统计论证与检验决策

版本1.0.0；2026-11-14；项目独立编写。数学资料用于建模论证、推导和核对，不替代中文建模论文结构，不自动证明、选检验或批准结果。先读本目录index，再按问题读取相关小节；保存来源/版本/哈希、假设、未满足条件和open_gaps。旧21份collaboration指南及冻结任务保持字节。

每节区分完整的文字论证与有限软件核对：符号恒等式检查仅针对已定义表达式；有限例、数值误差和统计量计算不构成通用定理证明、真实设计前提核验或独立审查。所有数值来自固定教学输入，不复制进业务结论。统计区间明确目标/水平/方法，假设未验证时不默认成立。

## 阅读与建模交接

先把本节结论绑定当前模型/数学包的符号、假设、版本和证据，指出是精确等式、界、近似或统计推断。条件未知或关键逻辑缺步记open_gaps，不补造结果。整篇只有一张全局符号表；推导细节可进附录。作者核对、独立M1/P1/P2/W1/W2与用户模型/结果确认分别执行。

<a id="design-estimand"></a>
## 估计目标、实验单位与采样设计 · design-estimand

**对象、命题与核心公式**：$DEFF=1+(m-1)\rho,\quad n_{eff}\approx n/DEFF$。

**条件与符号**：先定义目标总体、均值/均值差/风险差/关联或因果估计量；m等簇大小且交换型ICCρ时才用该方差膨胀近似；不是通用自由度公式。

**逐步推导/论证与使用规则**：按分配与采样机制识别独立单位，同一个人的前后测是配对，不是两独立组；重复/时间/空间/簇观测保留ID和对应关系。对m个同方差、组内相关ρ的观测和，方差=mσ²+m(m−1)ρσ²，相比独立情况得到DEFF。推断自由度依实际设计，不拿n_eff替换检验样本数。

**失败边界与反例**：3人前后各一行共6行，独立受试者仍3；随机截距模型/配对差/簇重采样各有条件，不能逐行打乱；非概率抽样不自动代表总体。

**可复算案例与目标量**：3个受试者各2次，行数6/受试者3；若m2,ICC.5，则DEFF1.5,近似有效数4，仅示范设计效应。预期输出：`[6, 3, 1.5, 4]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id design-estimand` 调用包内固定可信函数`modelcrew.mathematical_examples.case_design_estimand`；以下片段的辅助函数同包提供，不执行资料文本：

```python
ids=['a','a','b','b','c','c'];deff=1+(2-1)*.5;return [len(ids),len(set(ids)),deff,len(ids)/deff]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="welch-inference"></a>
## 独立两组Welch、效应与区间 · welch-inference

**对象、命题与核心公式**：$t={\bar x-\bar y\over\sqrt{s_x^2/n_x+s_y^2/n_y}},\quad \nu={(a+b)^2\over a^2/(n_x-1)+b^2/(n_y-1)}$。

**条件与符号**：两组独立观测，均值是目标，方差有限；小样本正态模型下使用近似Welch自由度，a=sx²/nx,b=sy²/ny，n各≥2；双侧α=.05先声明。

**逐步推导/论证与使用规则**：Δ估计为均值差，SE=sqrt(a+b)，按H0:Δ=0计算t与Welch–Satterthwaite ν；区间Δ±t_(.975,ν)SE。效应同时报原单位Δ，可补Cohen d=Δ/合并样本SD，但它非Welch检验量且其区间需另法；不把d点估计当已完成其区间。不可由一个正态性p值自动认可前提。

**失败边界与反例**：配对数据不能当独立；零总SE为退化情况，需明确模型/精确策略；p≥.05不证明等效，异常极值和重尾会影响小样本结果。

**可复算案例与目标量**：x1,2,3与y2,3,4，Δ−1,ν4,t−1.2247448714,p.2878641347；Δ的95%CI[−3.2669579355,1.2669579355]，d−1。预期输出：`[-1, -1.224744871391589, 0.2878641347266908, -3.266957935527523, 1.2669579355275231, -1]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id welch-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_welch_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
return welch_summary([1,2,3],[2,3,4])
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="paired-inference"></a>
## 配对差值与配对t推断 · paired-inference

**对象、命题与核心公式**：$d_i=y_{i,after}-y_{i,before},\quad t={\bar d\over s_d/\sqrt n}$。

**条件与符号**：配对ID一一匹配，不同受试者之间独立；小样本精确t要求差值正态，检验的是差值而非两边边际；df=n−1且s_d>0。

**逐步推导/论证与使用规则**：先按ID对齐再作差，H0:E d=0；SE=sd/sqrt(n)，CI=均值差±t_(.975,n−1)SE；标准化配对效应dz=均值差/sd，明确与独立组d定义不同。缺一侧的对象不静默错配，完整配对与缺失机制/敏感性留痕。

**失败边界与反例**：配对被打乱会改变sd和p；重复多时点不能反复套独立配对检验而不校正/建相关模型；全同差值的SE0须单独解释。

**可复算案例与目标量**：before1,2,3,4；after2,4,4,6，差1,2,1,2；Δ1.5,t5.1961524,p.013846833,95%CI[.58130688,2.41869312],dz2.5980762。预期输出：`[1.5, 5.196152422706632, 0.013846832988859047, 0.5813068844813005, 2.4186931155186997, 2.598076211353316]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id paired-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_paired_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
return paired_summary([1,2,3,4],[2,4,4,6])
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="anova-inference"></a>
## 多组均值、总体检验与事后比较 · anova-inference

**对象、命题与核心公式**：$F={SS_B/(k-1)\over SS_W/(N-k)},\quad \eta^2=SS_B/(SS_B+SS_W)$。

**条件与符号**：k独立组，经典ANOVA要求独立正态误差与同方差，df=k−1,N−k；不等方差、重复/簇设计须用适配替代；α=.05。

**逐步推导/论证与使用规则**：按组均值与总均值拆平方和，总体H0为全部均值相同；F检验拒绝只说明至少一组不同。η²是解释样本总平方和比例的点估计，有偏且非因果。预设对比或事后比较另定检验族并校正；示例组均值CI是边际区间，不是η²区间，也不是全组同时区间。

**失败边界与反例**：总体显著不意味着每对显著；重复测量不能用独立ANOVA；n2各组无法凭数据确认正态/同方差，本例条件为教学假设，不自动验真。

**可复算案例与目标量**：组[1,2]/[3,4]/[5,6]，F16,p.0250945733,η².9142857143；第一组均值1.5的边际95%t区间[−4.85310237,7.85310237]，展示小样本不确定性。预期输出：`[16, 0.02509457330439086, 0.9142857142857143, -4.853102368216048, 7.853102368216048]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id anova-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_anova_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
g=[np.array(a,float) for a in [[1,2],[3,4],[5,6]]];r=stats.f_oneway(*g);mu=np.concatenate(g).mean();ssb=sum(len(a)*(a.mean()-mu)**2 for a in g);ssw=sum(((a-a.mean())**2).sum() for a in g);q=stats.t.ppf(.975,1)*.5;return [r.statistic,r.pvalue,ssb/(ssb+ssw),1.5-q,1.5+q]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="fisher-inference"></a>
## 稀疏独立列联表与Fisher检验 · fisher-inference

**对象、命题与核心公式**：$P(A=a\mid\text{边际})={\binom{r_1}{a}\binom{r_2}{c_1-a}\over\binom N{c_1}}$。

**条件与符号**：独立单位计数2×2表，非负整数，条件于边际使用超几何模型；不是重复配对数据。双侧采用SciPy概率不大于观察表概率的求和定义。

**逐步推导/论证与使用规则**：边际固定后枚举可行左上角a，计算H0:OR=1的超几何概率；双侧汇总同等或更极端表。效应可报样本交叉比，也可报条件OR，但区间须与估计定义一致。本例同时使用条件OR估计和条件精确95%CI，不与样本OR=ad/bc混为一个估计量。

**失败边界与反例**：零边际会让部分效应不可识别；不同软件双侧定义可能不同需版本留痕；稀疏不意味着任意设计都用Fisher，配对另用McNemar。

**可复算案例与目标量**：表[[1,9],[11,3]]；条件OR .03720908483,p .002759456185，95%CI[.00063600295,.42586647570]。预期输出：`[0.03720908483238107, 0.0027594561852200836, 0.0006360029488741693, 0.4258664756963734]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id fisher-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_fisher_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
table=np.array([[1,9],[11,3]]);r=stats.contingency.odds_ratio(table,kind='conditional');ci=r.confidence_interval(confidence_level=.95);return [r.statistic,stats.fisher_exact(table,alternative='two-sided').pvalue,ci.low,ci.high]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="mcnemar-inference"></a>
## 配对二分类与精确McNemar · mcnemar-inference

**对象、命题与核心公式**：$B\mid(B+C=d),H_0\sim\operatorname{Binomial}(d,1/2)$。

**条件与符号**：同一批受试者两次二分类，B为+→−人数、C为−→+人数；受试者独立且配对完整；d=B+C>0。

**逐步推导/论证与使用规则**：在边际同质H0下，给定不一致总数d，两种改变方向概率各1/2；使用双侧精确二项检验，而非把前后当独立样本。报告净正率变化(C−B)/N；不一致者中B方向概率可给Clopper–Pearson区间，此区间不是总体净变化区间。

**失败边界与反例**：d0没有不一致变化，检验退化，不能给无穷效应；忽略配对会误估不确定性；不一致比例的CI不等于风险差CI。

**可复算案例与目标量**：配对表[[5,2],[8,5]]，B2,C8,N20；p .109375，净正率差.3；B方向条件概率.2及95%精确CI[.0252107263,.5560954623]。预期输出：`[0.109375, 0.3, 0.2, 0.025210726326833497, 0.5560954623076415]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id mcnemar-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_mcnemar_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
B,C,N=2,8,20;r=stats.binomtest(B,B+C,.5,alternative='two-sided');ci=r.proportion_ci(confidence_level=.95,method='exact');return [r.pvalue,(C-B)/N,B/(B+C),ci.low,ci.high]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="rank-inference"></a>
## 秩检验、效应方向与小样本分辨率 · rank-inference

**对象、命题与核心公式**：$U=\sum_{i,j}[\mathbf1(x_i>y_j)+\tfrac12\mathbf1(x_i=y_j)],\quad \delta_C=2U/(mn)-1$。

**条件与符号**：两独立连续组，无并列时本例用精确Mann–Whitney；一般目标是分布/排序关系，只有相同形状的平移族才解释为位置差。配对Wilcoxon须对差值，位置解释常需对称性。

**逐步推导/论证与使用规则**：U计数跨组胜出与并列，H0相同连续分布下排列给精确p；Cliff δ为P(X>Y)−P(X<Y)的样本估计，非均值差。若额外假设位置平移，可给Hodges–Lehmann位置估计。本例m=n3的最小双侧p为2/C(6,3)=.1，故按此非随机化精确检验反演的95%平移区间是全实数；不能硬填有限95%CI。

**失败边界与反例**：非正态不自动改检验目标；MW不是无条件中位数检验；并列需对应排列/渐近策略；小样本无显著不等价无分离。

**可复算案例与目标量**：x1,2,3；y4,5,6，U0,p.1,Cliff−1，y−x位置估计3；最后标记1表示95%精确反演区间无有限端点，非数值丢失。预期输出：`[0, 0.1, -1, 3, 1]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id rank-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_rank_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x=np.array([1,2,3]);y=np.array([4,5,6]);r=stats.mannwhitneyu(x,y,alternative='two-sided',method='exact');return [r.statistic,r.pvalue,2*r.statistic/(len(x)*len(y))-1,np.median(y[:,None]-x[None,:]),int(2/math.comb(6,3)>.05)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="regression-inference"></a>
## 回归系数、区间与模型依赖 · regression-inference

**对象、命题与核心公式**：$\hat\sigma^2={\|y-X\hat\beta\|^2\over n-p},\quad \operatorname{Var}(\hat\beta\mid X)=\sigma^2(X^TX)^{-1}$。

**条件与符号**：固定/条件设计X列满秩且n>p；经典小样本t区间假定条件独立正态同方差误差，E[ε|X]=0；预测性能与因果识别另验。

**逐步推导/论证与使用规则**：由βhat=β+(XᵀX)^−1Xᵀε得协方差式，用SSE/(n−p)估计σ²；单系数SE为对应对角元开方，t区间用df=n−p。异方差、簇或时序相关必须改变协方差/模型；均值响应CI与单个新观测预测区间不同，后者额外含σ²。

**失败边界与反例**：系数显著不代表因果；变量筛选后直接用未选择模型的p/CI忽略选择偏差；共线/自由度0/异方差不能用本例经典公式。

**可复算案例与目标量**：x0,1,2,3，y1,2,2,4；截距与斜率均.9，斜率SE .2645751311，95%CI[−.2383749101,2.0383749101]，df2。预期输出：`[0.9, 0.264575131106459, -0.2383749100649204, 2.0383749100649204, 2]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id regression-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_regression_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
X=np.c_[np.ones(4),[0.,1.,2.,3.]];y=np.array([1.,2.,2.,4.]);b=np.linalg.lstsq(X,y,rcond=None)[0];df=4-2;s2=((y-X@b)**2).sum()/df;se=math.sqrt((np.linalg.solve(X.T@X,np.eye(2))*s2)[1,1]);q=stats.t.ppf(.975,df);return [b[1],se,b[1]-q*se,b[1]+q*se,df]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="bootstrap-inference"></a>
## 重采样单位、精确枚举与区间 · bootstrap-inference

**对象、命题与核心公式**：$\hat\theta^{*(b)}=T(X^{*(b)}),\quad SE_{boot}=\operatorname{sd}(\hat\theta^*)$。

**条件与符号**：独立数据按独立单位抽，配对同时抽配对，簇抽簇，时间数据用适当块；B、种子、区间方法及全部预处理重拟合规则留痕。

**逐步推导/论证与使用规则**：经验分布代替总体后，有放回抽同样样本量，重算统计量；有限枚举得到的是精确经验重采样分布，不是总体抽样分布。Monte Carlo版本用足够重复并检查端点稳定；百分位、basic、BCa等假设与偏差不同，不能统称万能区间。

**失败边界与反例**：逐行抽簇/重复测量会低估误差；小样本/极值/稀有事件的bootstrap可能失效；例中名义95%百分位区间不保证总体95%覆盖。

**可复算案例与目标量**：经验样本0,2，每次抽2有放回，四种有序样本均值0,1,1,2；精确bootstrap均值1、方差.5；inverted_cdf百分位名义95%区间[0,2]。预期输出：`[1, 0.5, 0, 2]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id bootstrap-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_bootstrap_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
means=np.array([np.mean(x) for x in itertools.product([0.,2.],repeat=2)]);q=np.quantile(means,[.025,.975],method='inverted_cdf');return [means.mean(),means.var(ddof=0),*q]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="multiple-testing"></a>
## 检验族、FWER与BH-FDR · multiple-testing

**对象、命题与核心公式**：$p_i^{Bonf}=\min(1,mp_i),\quad p_{(i)}^{BH}=\min(1,\min_{j\ge i}mp_{(j)}/j)$。

**条件与符号**：比较族与α/q预先定义，输入是有效p值；Bonferroni控制任意依赖FWER，经典BH需独立或相应正依赖等条件，不能承诺任意依赖。

**逐步推导/论证与使用规则**：Bonf由并集界得到族误报≤Σα/m=α；BH先稳定排序p，再从后往前取累积最小值并截到1，最后映射原顺序，拒绝调整p≤q。BH控制的是FDR，不是每组FWER或所有声明必真。缺失p不能静默缩小预设族，应说明未完成比较策略。

**失败边界与反例**：把BH写成统一α/m是错法；只对“显著者”事后组成族会低估错误率；无效p值校正后也不变有效。

**可复算案例与目标量**：p顺序.01,.04,.03,.2；Bonf .04,.16,.12,.8；BH .04,.0533333333,.0533333333,.2；α=q=.05仅第一项拒绝。预期输出：`[0.04, 0.16, 0.12, 0.8, 0.04, 0.05333333333333334, 0.05333333333333334, 0.2]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id multiple-testing` 调用包内固定可信函数`modelcrew.mathematical_examples.case_multiple_testing`；以下片段的辅助函数同包提供，不执行资料文本：

```python
p=np.array([.01,.04,.03,.2]);return [*bonferroni(p),*bh_adjust(p)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="equivalence-inference"></a>
## 等效、非劣与未拒绝差异的区别 · equivalence-inference

**对象、命题与核心公式**：$H_{0L}:\Delta\le-\delta,\quad H_{0U}:\Delta\ge\delta$。

**条件与符号**：等效边界δ>0有预先业务/临床依据，单位与Δ一致；两单侧TOST各α=.05，总体等效用交并检验；n、设计和t/正态假设适配。

**逐步推导/论证与使用规则**：分别用tL=(Δhat+δ)/SE和tU=(Δhat−δ)/SE计算上尾/下尾p，二者都小于α才拒绝等效的联合原假设，等价于同模型90%双侧区间严格落在(−δ,δ)。非劣只检一侧并固定方向；边界不能见数据后放宽。

**失败边界与反例**：差异p≥.05不证明等效；90%区间不冒充95%；TOST交并结构无需把两个单侧水平再除2，多个不同终点的族仍另处理。

**可复算案例与目标量**：给定合法t充分统计量Δhat .1,SE .1,df9,δ .5；两单侧p .00010124966/.00155521416，90%CI[−.08331129,.28331129]，等效标记1；实际数据前提并未由该例验证。预期输出：`[0.0001012496610338204, 0.0015552141551929267, -0.08331129326536332, 0.2833112932653633, 1]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id equivalence-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_equivalence_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
return tost_summary(.1,.1,9,.5,.05)
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="cluster-inference"></a>
## 重复与簇相关的方差核对 · cluster-inference

**对象、命题与核心公式**：$SE(\bar Z)=s_Z/\sqrt G,\quad Z_g=\text{第g簇均值}$。

**条件与符号**：G独立簇、等权簇均值是目标，例中簇大小相同；簇层t区间需独立近似正态簇均值且G>1；小G不保证稳健渐近。

**逐步推导/论证与使用规则**：先按独立簇聚合再对簇均值作均值推断，df=G−1；这是一种受限等权分析，不替代任意不等簇大小/簇随机设计的混合模型或稳健协方差。簇稳健SE需要足够簇和小样本修正；样本行数不是独立簇数。

**失败边界与反例**：把同一簇大量复制行会虚减逐行SE，但不增加独立信息；两簇教学例区间极宽，不声称真实数据可稳健估计任何ICC/处理效应。

**可复算案例与目标量**：两簇[0,0]与[2,2]，均值1；错误独立行SE .5773502692，簇均值SE1；条件t模型95%CI[−11.7062047364,13.7062047364]。预期输出：`[1, 0.5773502691896257, 1, -11.706204736432095, 13.706204736432095]`。证据层级`statistical_calculation`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id cluster-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_cluster_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
clusters=np.array([[0.,0.],[2.,2.]]);means=clusters.mean(axis=1);se=means.std(ddof=1)/math.sqrt(2);q=stats.t.ppf(.975,1);return [means.mean(),clusters.ravel().std(ddof=1)/2,se,means.mean()-q*se,means.mean()+q*se]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="missingness-inference"></a>
## 缺失机制、排除与敏感性 · missingness-inference

**对象、命题与核心公式**：$MCAR:\ R\perp(X_{obs},X_{mis});\quad MAR:\ P(R|X)=P(R|X_{obs})$。

**条件与符号**：R为观测/缺失模式，Xobs/Xmis为在该模式下观测/未观测部分；MAR需按模式理解，忽略机制用于特定推断还需参数可分等条件；MNAR依赖未观测量。

**逐步推导/论证与使用规则**：先列入组/缺失/排除/完整配对数量与原因，再据估计目标选择完整案例、插补/多重插补、加权或联合模型，并声明识别/模型假设。均值单次填补压缩方差且不能反映插补不确定性；多重插补需合并组内/组间不确定性，不把M次当M倍样本。

**失败边界与反例**：MCAR/MAR通常不能只凭观测数据完全证实；MNAR需敏感性或外部信息；异常值检测不是自动删点授权。只分析完整样本可能改变目标总体。

**可复算案例与目标量**：观测1,缺失,3，完整案例均值2、样本方差2；均值填补后均值2、样本方差1，说明均值相同仍会改变方差，不推断真实缺失值。预期输出：`[2, 2, 1]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id missingness-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_missingness_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x=np.array([1.,np.nan,3.]);obs=x[np.isfinite(x)];filled=np.where(np.isnan(x),obs.mean(),x);return [obs.mean(),obs.var(ddof=1),filled.var(ddof=1)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="validation-inference"></a>
## 验证划分、数据泄漏与证据报告 · validation-inference

**对象、命题与核心公式**：$z_{test}=(x_{test}-\mu_{train})/s_{train}$。

**条件与符号**：时间/主体/空间划分符合部署目标，训练、调参验证和最终测试职责分开；所有拟合型预处理在训练折内完成，测试只最后评估。

**逐步推导/论证与使用规则**：保存行ID/时间界/数据哈希，训练估计填补/缩放/特征与模型，验证调超参；报告最终测试误差和适配设计的不确定性。重复CV折分不等于多份独立数据；数据依赖结论区分探索/验证，选择/停止规则与多重比较留痕。

**失败边界与反例**：把全量数据标准化后再CV泄漏；同人跨折、未来特征、训练残差拟合Stacking都会夸大性能；固定几何问题不硬造统计CI。

**可复算案例与目标量**：训练1,2,3给均值2、样本SD1；测试4,5转为2,3，冻结训练参数，不在测试重估。预期输出：`[2, 3]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id validation-inference` 调用包内固定可信函数`modelcrew.mathematical_examples.case_validation_inference`；以下片段的辅助函数同包提供，不执行资料文本：

```python
train=np.array([1.,2.,3.]);test=np.array([4.,5.]);return (test-train.mean())/nonzero(train.std(ddof=1))
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

