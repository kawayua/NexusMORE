# 枢模 · 证明方法与反例

版本1.0.0；2026-11-14；项目独立编写。数学资料用于建模论证、推导和核对，不替代中文建模论文结构，不自动证明、选检验或批准结果。先读本目录index，再按问题读取相关小节；保存来源/版本/哈希、假设、未满足条件和open_gaps。旧21份collaboration指南及冻结任务保持字节。

每节区分完整的文字论证与有限软件核对：符号恒等式检查仅针对已定义表达式；有限例、数值误差和统计量计算不构成通用定理证明、真实设计前提核验或独立审查。所有数值来自固定教学输入，不复制进业务结论。统计区间明确目标/水平/方法，假设未验证时不默认成立。

## 阅读与建模交接

先把本节结论绑定当前模型/数学包的符号、假设、版本和证据，指出是精确等式、界、近似或统计推断。条件未知或关键逻辑缺步记open_gaps，不补造结果。整篇只有一张全局符号表；推导细节可进附录。作者核对、独立M1/P1/P2/W1/W2与用户模型/结果确认分别执行。

<a id="quantifiers"></a>
## 命题、量词与否定 · quantifiers

**对象、命题与核心公式**：$\forall x\in\mathbb R\ \exists y\in\mathbb R:y>x;\quad \neg\exists y\in\mathbb R\ \forall x\in\mathbb R:y>x$。

**条件与符号**：对象域是全体实数；第一句允许y依赖x，第二句要求固定y适配所有x。

**逐步推导/论证与使用规则**：对任意给定x构造y=x+1得到第一句；若假设第二句中存在固定y，则取x=y+1即有y>x和x>y矛盾，因此该存在句为假。否定∀x∃y P应写∃x∀y ¬P，不能仅给谓词加“不”。常数与概率事件的依赖关系写清。

**失败边界与反例**：在有限网格逐点找到不同y不产生统一y；“对每个数据集存在参数”不等于“存在一组参数适配全部数据集”。

**可复算案例与目标量**：x1000构造y1001；给固定y−2取x−1反驳上界，两项差都是1。预期输出：`[1, 1]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id quantifiers` 调用包内固定可信函数`modelcrew.mathematical_examples.case_quantifiers`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x=1000.;y=x+1;fixed=-2.;witness=fixed+1;return [y-x,witness-fixed]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="direct-proof"></a>
## 直接证明与非负证书 · direct-proof

**对象、命题与核心公式**：$\forall a,b\in\mathbb R,\quad (a+b)^2-4ab=(a-b)^2\ge0$。

**条件与符号**：a,b为任意实数，实数平方非负；若由此开方推a+b≥2sqrt(ab)，还需a,b≥0。

**逐步推导/论证与使用规则**：展开左式a²+2ab+b²−4ab=a²−2ab+b²，配方为(a−b)²，由实平方非负得不等式，等号当且仅当a=b。附加a,b≥0后两侧非负，才可合法开方得到算术/几何平均不等式。

**失败边界与反例**：a=b=−1时a+b=−2<2sqrt(ab)=2，说明非负假设不能从平方不等式中省去；数值吻合不是任意实数证明。

**可复算案例与目标量**：SymPy核对两多项式恒等差0；a1,b3时非负差4。预期输出：`[0, 4]`。证据层级`symbolic_identity_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id direct-proof` 调用包内固定可信函数`modelcrew.mathematical_examples.case_direct_proof`；以下片段的辅助函数同包提供，不执行资料文本：

```python
a,b=sp.symbols('a b',real=True);expr=(a+b)**2-4*a*b;return [float(sp.expand(expr-(a-b)**2)),float(expr.subs({a:1,b:3}))]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="contradiction"></a>
## 反证法与不可约表示 · contradiction

**对象、命题与核心公式**：$\sqrt2\notin\mathbb Q$。

**条件与符号**：反设sqrt2=p/q，其中p,q互质整数且q≠0；使用整数平方奇偶性引理。

**逐步推导/论证与使用规则**：平方得p²=2q²，因此p²偶从而p偶，写p=2r；代回得q²=2r²，所以q偶，与p,q互质矛盾。奇偶引理由奇数2k+1的平方仍奇给出，不把待证结论作为引理循环引用。

**失败边界与反例**：没有互质条件时“p,q皆偶”本身不是矛盾；有限分母搜索失败不能证明无穷多个有理数均不等于sqrt2。

**可复算案例与目标量**：只枚举1≤p≤30,1≤q≤20，等式p²=2q²的命中数0，仅作有限校验，完整证明是上段逻辑。预期输出：`0`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id contradiction` 调用包内固定可信函数`modelcrew.mathematical_examples.case_contradiction`；以下片段的辅助函数同包提供，不执行资料文本：

```python
return sum(p*p==2*q*q for p in range(1,31) for q in range(1,21))
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="induction"></a>
## 归纳法与递推不变量 · induction

**对象、命题与核心公式**：$\forall n\in\mathbb N_{\ge1},\quad \sum_{k=1}^n k=n(n+1)/2$。

**条件与符号**：n为正整数；基例、任意n的归纳假设与下一步必须齐全；程序循环不变量还需初始化/保持/终止。

**逐步推导/论证与使用规则**：n1时两边1；假设对某任意n成立，加n+1得n(n+1)/2+n+1=(n+1)(n+2)/2，因此对n+1成立，归纳得全体正整数。强归纳应明示使用哪些较小指标，不偷用n+1命题。

**失败边界与反例**：只有递推步没有基例不能推出任何起点；检查前100项也不能单独构成归纳证明；递推关系不必保证程序终止。

**可复算案例与目标量**：n10时直接求和55与闭式55，程序不据此声称任意n已自动证明。预期输出：`[55, 55]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id induction` 调用包内固定可信函数`modelcrew.mathematical_examples.case_induction`；以下片段的辅助函数同包提供，不执行资料文本：

```python
n=10;return [sum(range(1,n+1)),n*(n+1)//2]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="contrapositive"></a>
## 逆否、逆命题与必要充分 · contrapositive

**对象、命题与核心公式**：$n\in\mathbb Z:\quad n^2\text{为偶数}\Rightarrow n\text{为偶数}$。

**条件与符号**：整数可分为偶2k和奇2k+1；命题A⇒B等价于非B⇒非A，不等价于B⇒A。

**逐步推导/论证与使用规则**：以逆否证明：若n奇，n=2k+1，平方4k²+4k+1也是奇，故原命题成立。本题逆命题也成立但需要另证(2k)²偶，不能由逻辑形式直接取得。写iff时须分别证明两向或给等价变换链。

**失败边界与反例**：“下雨⇒地湿”的逆命题不成立；一个反例足以推翻全称命题，但任意多个正例仍不充分。

**可复算案例与目标量**：把奇数平方对2取多项式余数恒1；n7的平方也是奇数。预期输出：`[1, 1]`。证据层级`symbolic_identity_check`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id contrapositive` 调用包内固定可信函数`modelcrew.mathematical_examples.case_contrapositive`；以下片段的辅助函数同包提供，不执行资料文本：

```python
k=sp.symbols('k',integer=True);return [float(sp.expand((2*k+1)**2-4*k*k-4*k)),7**2%2]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="case-analysis"></a>
## 分类证明与边界覆盖 · case-analysis

**对象、命题与核心公式**：$\forall x,y\in\mathbb R,\quad |x+y|\le |x|+|y|$。

**条件与符号**：x,y为任意实数，分类包含零；绝对值/分段模型需覆盖所有边界及重叠处理。

**逐步推导/论证与使用规则**：若同号则|x+y|=|x|+|y|；若异号，按|x|≥|y|或相反，|x+y|等于较大绝对值减较小绝对值，必不超过两者之和。零可并入同号或任一边界，故分类穷尽。等号当xy≥0，包括零。

**失败边界与反例**：只检查两者都正遗漏异号和零；程序分支必须与数学分区一致，浮点近零策略不改变精确分区定理。

**可复算案例与目标量**：x取−2/+2、y取−3/+3，按笛卡尔序的松弛分别0,4,4,0。预期输出：`[0, 4, 4, 0]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id case-analysis` 调用包内固定可信函数`modelcrew.mathematical_examples.case_case_analysis`；以下片段的辅助函数同包提供，不执行资料文本：

```python
return [abs(x)+abs(y)-abs(x+y) for x in [-2,2] for y in [-3,3]]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="constructive-proof"></a>
## 构造性存在与可行见证 · constructive-proof

**对象、命题与核心公式**：$n\ge1,\ B\ge0,\quad x_i=B/n\Rightarrow x_i\ge0,\ \sum_{i=1}^n x_i=B$。

**条件与符号**：n正整数，B是同单位可分割资源；只要求非负与总和约束，不额外要求整性/上下界。

**逐步推导/论证与使用规则**：直接定义每个xi=B/n，由n>0与B≥0知非负；n项相加为nB/n=B，给出可执行可行见证。构造时逐条复核完整约束；存在一个见证只证明可行，不证明最优、唯一或公平公理均满足。

**失败边界与反例**：若B1且n2要求xi为整数，平均分配不合法；若每人容量小于B/n还需另构造；别把可行当最优。

**可复算案例与目标量**：B12,n3，分配4,4,4，总和12。预期输出：`[4, 4, 4, 12]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id constructive-proof` 调用包内固定可信函数`modelcrew.mathematical_examples.case_constructive_proof`；以下片段的辅助函数同包提供，不执行资料文本：

```python
B,n=12.,3;allocation=[B/n]*n;return [*allocation,sum(allocation)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="existence-uniqueness"></a>
## 存在、唯一与可计算性分离 · existence-uniqueness

**对象、命题与核心公式**：$f\text{连续于非空紧集}K\Rightarrow\exists x_*\in K:\ f(x_*)=\min_K f$。

**条件与符号**：有限维实空间中紧等价闭且有界；唯一性进一步可用凸域上的严格凸性，非凸域不能直接套该结论。

**逐步推导/论证与使用规则**：先由极值定理在紧集上取得最小值；若严格凸函数在凸域有不同极小点x,y，中点仍可行且值严格小于两最小值平均，矛盾，故至多一个。存在与至多一个结合才得唯一；存在定理不必提供有效算法或复杂度。

**失败边界与反例**：连续f(x)=x在开区间(0,1)只有下确界0未取到；常量函数在[0,1]极小点不唯一；严格凸函数在非凸集{−1,1}也可两点同小。

**可复算案例与目标量**：f=(x−2)²在[0,1]，驻点2不在域，比较端点得唯一解1、值1。预期输出：`[1, 1]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id existence-uniqueness` 调用包内固定可信函数`modelcrew.mathematical_examples.case_existence_uniqueness`；以下片段的辅助函数同包提供，不执行资料文本：

```python
candidates=[0.,1.];x=min(candidates,key=lambda z:(z-2)**2);return [x,(x-2)**2]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="convexity"></a>
## 凸性、一阶条件与Jensen · convexity

**对象、命题与核心公式**：$\theta x^2+(1-\theta)y^2-[\theta x+(1-\theta)y]^2=\theta(1-\theta)(x-y)^2\ge0$。

**条件与符号**：x,y实数，θ∈[0,1]，凸域内凸组合可行；严格凸在x≠y且θ∈(0,1)严格。

**逐步推导/论证与使用规则**：展开平方并合并同类项，得到非负系数乘平方，因此x²凸。一般可微凸函数满足f(y)≥f(x)+∇f(x)ᵀ(y−x)，在凸可行域上可用此支撑不等式证全局性；二阶可微且Hessian半正定是相应开凸域的凸性判据。

**失败边界与反例**：局部正定Hessian不证明整个域凸；凸性不等于强凸或严格凸；凹函数−x²在x−1,y1,θ.5时Jensen方向相反。

**可复算案例与目标量**：x0,y4,θ.25，Jensen差3，右端也3。预期输出：`[3, 3]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id convexity` 调用包内固定可信函数`modelcrew.mathematical_examples.case_convexity`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x,y,t=0.,4.,.25;return [t*x*x+(1-t)*y*y-(t*x+(1-t)*y)**2,t*(1-t)*(x-y)**2]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="descent-convergence"></a>
## 下降引理、求和界与收敛对象 · descent-convergence

**对象、命题与核心公式**：$f(x-\eta g)\le f(x)-\eta(1-L\eta/2)\|g\|^2,\quad g=\nabla f(x)$。

**条件与符号**：f在相关路径上梯度L-Lipschitz且L>0，0<η<2/L；谈累计界还需f有下界f_inf；精确梯度，无随机噪声。

**逐步推导/论证与使用规则**：光滑性给f(x+d)≤f(x)+gᵀd+(L/2)||d||²，代d=−ηg得单步式。对t0至T−1求和，下降望远镜，得Σ||g_t||²≤(f(x0)−f_inf)/[η(1−Lη/2)]，进而最小梯度范数平方≤右侧/T。它是驻点指标界，不自动给全局最优、迭代点收敛或随机梯度结论。

**失败边界与反例**：η=3且f=x²/2时更新x→−2x目标变4倍；f无下界时下降不保证有限极限；不能不核对L就套速率或常数。

**可复算案例与目标量**：f=x²/2,x2,L1,η.5，目标2→.5，理论下降界1.5且本例取等。预期输出：`[2, 0.5, 1.5]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id descent-convergence` 调用包内固定可信函数`modelcrew.mathematical_examples.case_descent_convergence`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x,L,eta=2.,1.,.5;new=x-eta*x;return [x*x/2,new*new/2,eta*(1-L*eta/2)*x*x]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="fixed-point"></a>
## 压缩映射与后验误差 · fixed-point

**对象、命题与核心公式**：$d(x_k,x_*)\le {q^k\over1-q}d(x_1,x_0),\quad 0\le q<1$。

**条件与符号**：(X,d)为非空完备度量空间，F:X→X且d(Fx,Fy)≤qd(x,y)；初点属于X。

**逐步推导/论证与使用规则**：连续两步距离≤q^k d(x1,x0)，三角不等式及几何级数使序列Cauchy；完备性给极限x*∈X，Lipschitz连续性令F(x*)=x*；若另一固定点y*，d(x*,y*)≤q d(x*,y*)迫使距离0。尾和给所列误差界。

**失败边界与反例**：X=(0,1),F=x/2为压缩但不完备，固定点0不在X；q=1的F=x+1无固定点；收敛数值曲线不代空间与不变性条件。

**可复算案例与目标量**：F=.5x+1从x0=0迭代3步得1.75，固定点2，误差.25，尾界.25。预期输出：`[1.75, 0.25, 0.25]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id fixed-point` 调用包内固定可信函数`modelcrew.mathematical_examples.case_fixed_point`；以下片段的辅助函数同包提供，不执行资料文本：

```python
x=0.
    for _ in range(3):x=.5*x+1
    return [x,abs(x-2),.5**3/(1-.5)]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="generalization"></a>
## 有限样本界与数据依赖 · generalization

**对象、命题与核心公式**：$P(|\hat R(f)-R(f)|>\epsilon)\le2e^{-2n\epsilon^2}$。

**条件与符号**：Z_i独立同分布，固定f的损失在[0,1]；f独立于用于估计风险的样本；有限预先固定类H可用|H|=M作并集界。

**逐步推导/论证与使用规则**：对固定f应用Hoeffding得尾界，令右端δ解ε=sqrt(log(2/δ)/(2n))。对预先固定M个函数并集界得同时事件概率≤2M exp(−2nε²)，故ε=sqrt(log(2M/δ)/(2n))。数据选择的f若属于该固定有限类，可在同时事件内使用；无限或数据依赖类需相应复杂度/独立测试等新论证。

**失败边界与反例**：用训练数据挑一个函数再套“固定函数”界会漏选择偏差；时序相关、无界重尾损失不满足本式；有限类M不能由训练后挑出的数量随意替换。

**可复算案例与目标量**：n100,δ.05，固定函数ε=.1358101516；预先固定M10同时界ε=.1730818383。预期输出：`[0.13581015157406195, 0.17308183826022852]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id generalization` 调用包内固定可信函数`modelcrew.mathematical_examples.case_generalization`；以下片段的辅助函数同包提供，不执行资料文本：

```python
n,delta,M=100,.05,10;return [math.sqrt(math.log(2/delta)/(2*n)),math.sqrt(math.log(2*M/delta)/(2*n))]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

<a id="complexity-proof"></a>
## 复杂度、递推上界与计算模型 · complexity-proof

**对象、命题与核心公式**：$C(1)=0,\quad C(n)=2C(n/2)+n-1\le n\log_2 n-n+1$。

**条件与符号**：n为2的幂，比较模型中合并两个已排序子表最多n−1次元素比较，递推C定义比较次数上界；单位代价假设需与数值位长/维度区分。

**逐步推导/论证与使用规则**：n1时闭式0；假定n/2的上界成立，代入2[(n/2)log2(n/2)−n/2+1]+n−1=nlog2n−n+1，故该递推上界为O(nlogn)。不同输入不必达到上界，常用归并还需O(n)辅助存储；若输入不是2的幂用上下取整递推再界定。迭代数依容差、矩阵维数、稀疏度和精度分别列明；最坏/平均/摊还口径不能交换。

**失败边界与反例**：比较次数不是浮点位复杂度；n维矩阵求逆不可因一次API调用记O(1)；数学实数循环x←x/2从1永不恰好为0，浮点下溢停机不能当精确终止证明。

**可复算案例与目标量**：按n2,4,8递推得比较次数上界17，与8log2(8)−8+1=17一致，只验证递推小例而非所有输入运行时间。预期输出：`[17, 17]`。证据层级`finite_example`；绝对容差1e-8，相对容差1e-6。

`python -m modelcrew.mathematical_knowledge check-examples --id complexity-proof` 调用包内固定可信函数`modelcrew.mathematical_examples.case_complexity_proof`；以下片段的辅助函数同包提供，不执行资料文本：

```python
c=0
    for n in [2,4,8]:c=2*c+n-1
    return [c,8*3-8+1]
```

本节文字论证与固定核算分别留痕；包内SymPy/NumPy/SciPy可核对这些固定输入，不验证任意用户命题或推断前提。未给出的效应区间和未适配设计明确保留缺口，不以其他目标区间替代。

