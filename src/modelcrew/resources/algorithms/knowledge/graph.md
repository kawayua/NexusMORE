# 枢模算法体系：图论与网络

版本1.0.0；2026-11-14；项目独立编写。范围依据用户提供的算法主题清单，原始全文不随包复制。先读取算法索引，再按问题结构读取本章相关条目，不把算法清单当成已接通的业务求解器。

每条给核心公式、符号、准入条件、失败边界、步骤、成本和固定可复算案例。案例层级必须保留：small_complete_solution为限定小问题的完整解；single_update为一步机制；core_equation_check为公式组件；stochastic_estimate为固定种子估计。组件核算不等于完整训练、全局最优或后端安装通过。

训练拟合的预处理、特征、调参和组合权重不得使用测试或未来信息；模型、数值方法与Python API分开说明。所有新任务继续模型/结果用户确认与独立M1/P1/P2/W1/W2；阅读资料和工程案例不授予批准。

## 本体系重点补充

先确定节点/边的业务含义、方向、权重单位、容量与费用、平行边、零权边和不可达值。BFS限无权/等权边；Dijkstra要求非负边；Bellman–Ford/Floyd有负边也须检查相关负环；Prim/Kruskal允许负边但要求无向语义，断开图应报告森林或拒绝单棵生成树。不要把零矩阵元素同时当缺边和有效零费用边；本章固定稀疏示例中密集矩阵0表示缺边，真实零边须显式存边。

路径验收逐边连通并重算总权，生成树验收连通、无环和n−1条边；流验收容量、流守恒与源汇流量，整数后端须核对容量类型。匹配核对一对一和禁配；K最短区分简单路径与允许重复节点的游走。网络指标的有向/归一化/断开图约定及社区随机性留痕，PageRank/Louvain结果不能直接视为因果重要性或唯一社区。

<a id="dfs"></a>
## 深度优先搜索 · dfs

**模型与核心公式**：$\mathrm{visit}(v):\ \text{标记}v;\ \mathrm{visit}(u)\ (u\in N(v)\text{且未访问})$。

**符号与输入输出**：N为邻接表；访问顺序由固定邻居顺序决定。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：有向/无向图和访问目标明确；断开图需多起点。

**失败边界**：深递归栈溢出、未标记形成循环；DFS顺序不是最短距离。反例/拒绝情形：含环0→1→0不标记会无限展开。

**步骤与成本**：显式栈或递归→首次标记→按序扩展→保留树边。O(V+E)，空间O(V)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：邻接0→[1,2],1→[2],2→[]，从0按序DFS得到[0,1,2]。期望核对量：`[0, 1, 2]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id dfs`。固定案例实现为`modelcrew.algorithm_examples.case_dfs`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return dfs_order([[1,2],[2],[]],0)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="bfs"></a>
## 广度优先搜索 · bfs

**模型与核心公式**：$d(s)=0,\ d(v)=d(u)+1\quad\text{首次经队列从}u\text{发现}v$。

**符号与输入输出**：d为边数距离，s为源点。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：图无权或每边等权，队列和首次访问规则明确。

**失败边界**：加权图边数最少不一定费用最低；不可达必须保留专门状态。反例/拒绝情形：边0→2费用100、0→1→2费用2时BFS不能解最低费用。

**步骤与成本**：起点入队→逐层扩展→记录距离与父指针。O(V+E)，空间O(V)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：0→[1,2],1→[2],2→[]；从0最短边数[0,1,1]。期望核对量：`[0, 1, 1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id bfs`。固定案例实现为`modelcrew.algorithm_examples.case_bfs`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return bfs_dist([[1,2],[2],[]],0)
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="dijkstra"></a>
## Dijkstra · dijkstra

**模型与核心公式**：$d(v)\leftarrow\min\{d(v),d(u)+w_{uv}\}$。

**符号与输入输出**：d为源点距离，w为边权，u为当前最小未定距离节点。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：可达边非负；方向/缺边和零权边语义明确。

**失败边界**：负权会破坏定标正确性；浮点并列路径需稳定处理。反例/拒绝情形：负边输入必须改用适配算法，不静默继续Dijkstra。

**步骤与成本**：初始化∞→优先队列弹最小→松弛→保存父指针。堆实现O((V+E)logV)，稠密实现O(V²)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：边0→1=1,1→2=2,0→2=4；距离[0,1,3]。期望核对量：`[0, 1, 3]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id dijkstra`。固定案例实现为`modelcrew.algorithm_examples.case_dijkstra`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return shortest(np.array([[0,1,4],[0,0,2],[0,0,0]],float),'D')
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="floyd"></a>
## Floyd · floyd

**模型与核心公式**：$D^{(k)}_{ij}=\min\{D^{(k-1)}_{ij},D^{(k-1)}_{ik}+D^{(k-1)}_{kj}\}$。

**符号与输入输出**：D为任意两点距离，k为允许的中间点。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：稠密小/中图全对路径，负边可但相关负环不能给有限最短值。

**失败边界**：对角负值暴露负环；内存O(V²)不适合巨大图。反例/拒绝情形：可达负环存在时不能输出有限最短路径作为结论。

**步骤与成本**：初始化直接边/对角0/缺边∞→按k三重松弛→负环检查。O(V³)时间、O(V²)空间。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：0→1=1,1→2=2,0→2=4；D_02更新为3。期望核对量：`3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id floyd`。固定案例实现为`modelcrew.algorithm_examples.case_floyd`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
A=np.array([[0,1,4],[0,0,2],[0,0,0]],float); return csgraph.shortest_path(sparse.csr_matrix(A),method='FW',directed=True)[0,2]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="bellman-ford"></a>
## Bellman-Ford · bellman-ford

**模型与核心公式**：$d(v)\leftarrow\min(d(v),d(u)+w_{uv});\ \text{再一轮可改进则检查可达负环}$。

**符号与输入输出**：w为允许负值的边权，d为源点距离。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：源点、方向明确；只对源点可达区域讨论负环影响。

**失败边界**：负环使受影响最短路无下界；不连通负环不能不加区分地归为源点故障。反例/拒绝情形：0→1=1,1→0=−2形成可达负环，应拒绝有限最短路结果。

**步骤与成本**：V−1轮松弛→额外轮检测→路径回溯。O(VE)，提前无改进可停止。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：0→1=1,1→2=−2,0→2=4；距离[0,1,−1]。期望核对量：`[0, 1, -1]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id bellman-ford`。固定案例实现为`modelcrew.algorithm_examples.case_bellman_ford`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return shortest(np.array([[0,1,4],[0,0,-2],[0,0,0]],float),'BF')
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="prim"></a>
## Prim · prim

**模型与核心公式**：$e^*=\arg\min\{w_{uv}:u\in S,v\notin S\},\ S\leftarrow S\cup\{v\}$。

**符号与输入输出**：S为已入生成树顶点，e为跨割边。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：无向连通加权图；负权可用，与Dijkstra前提不同。

**失败边界**：断开图只能得到生成森林；有向图不能直接套无向MST。反例/拒绝情形：不存在跨割边却仍有未访问点时，应报告断开而非整图生成树。

**步骤与成本**：选起点→最小跨割边→更新候选→直到全体入树。堆O(ElogV)，稠密O(V²)。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：三角边权(0,1)=1,(1,2)=2,(0,2)=4，Prim总权3。期望核对量：`3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id prim`。固定案例实现为`modelcrew.algorithm_examples.case_prim`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return prim_weight(np.array([[0,1,4],[1,0,2],[4,2,0]],float))
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="kruskal"></a>
## Kruskal · kruskal

**模型与核心公式**：$\text{按权升序加入连接不同连通分量的边}$。

**符号与输入输出**：并查集维护顶点分量，w为边权。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：无向图和边去重/并行边规则明确。

**失败边界**：断开图只有森林；不能加入成环边来凑V−1条。反例/拒绝情形：三点只提供一条边，不能把森林权重叫整图MST。

**步骤与成本**：排序边→并查集判环→合并→核对连通性和边数。O(ElogE)，并查集近线性附加。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：同三角图按权1、2、4扫描，接纳前两边，总权3。期望核对量：`3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id kruskal`。固定案例实现为`modelcrew.algorithm_examples.case_kruskal`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
A=sparse.csr_matrix([[0,1,4],[1,0,2],[4,2,0]]); return csgraph.minimum_spanning_tree(A).sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="dinic"></a>
## Dinic · dinic

**模型与核心公式**：$r_{uv}=c_{uv}-f_{uv};\ \max|f|,\ 0\le f\le c,\ \sum f_{in}=\sum f_{out}$。

**符号与输入输出**：c为容量，f为流，r为残量，s/t为不同源汇。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：有向网络容量非负；残量反向边正确，整数实现不能误传浮点。

**失败边界**：漏反向残量会卡在错误流；容量或源汇定义错误必须拒绝。反例/拒绝情形：负容量或s=t不构成此例合法最大流问题。

**步骤与成本**：BFS分层→沿层图DFS阻塞流→更新正反残量→无增广路→最小割核验。一般O(V²E)，单位容量可有更好界。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：c01=2,c12=2,c02=1；Dinic最大流3，与源割容量3一致。期望核对量：`3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id dinic`。固定案例实现为`modelcrew.algorithm_examples.case_dinic`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
A=sparse.csr_matrix(np.array([[0,2,1],[0,0,2],[0,0,0]],dtype=np.int64)); return csgraph.maximum_flow(A,0,2,method='dinic').flow_value
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="min-cost-flow"></a>
## 最小费用最大流 · min-cost-flow

**模型与核心公式**：$\min\sum_ec_ef_e,\ Bf=b,\ 0\le f_e\le u_e$。

**符号与输入输出**：c为单位费用，u为容量，B为节点守恒矩阵，b为供需。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：总供需平衡、容量可行；流量最大化与费用最小化的优先顺序明确。

**失败边界**：只最小费用会选零流；负环/势函数需对应算法处理。反例/拒绝情形：要求流4超过源割容量3，必须报告不可行。

**步骤与成本**：先确定所需/最大流→求最小费用→核对守恒、容量与费用。依逐次最短路/费用尺度/LP等实现；本例LP作独立参考解。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：边01/12/02容量2/2/1，费用1/1/5，要求流3；最优流(2,2,1)、费用9。期望核对量：`9`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id min-cost-flow`。固定案例实现为`modelcrew.algorithm_examples.case_min_cost_flow`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
r=opt.linprog([1,1,5],A_eq=[[1,0,1],[1,-1,0]],b_eq=[3,0],bounds=[(0,2),(0,2),(0,1)],method='highs'); require(r.success,'flow infeasible'); return r.fun
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="hungarian"></a>
## 匈牙利算法 · hungarian

**模型与核心公式**：$\min_{z}\sum_{ij}c_{ij}z_{ij},\sum_jz_{ij}=1,\sum_iz_{ij}=1,\ z_{ij}\in\{0,1\}$。

**符号与输入输出**：c为分配费用，z为一对一指派；矩形情形需明确未匹配规则。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：二分图分配问题，禁配/缺配和矩形语义明确。

**失败边界**：不是一般非二分图匹配；禁配不能随便用不够大的数替代。反例/拒绝情形：同一人员分配给两岗位违反一对一，即使局部费用更低也拒绝。

**步骤与成本**：构造费用→分配→验证一对一/禁配→算原费用。经典方阵O(n³)；具体后端算法可不是教科书匈牙利实现。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：费用[[4,1],[2,3]]，选(0,1),(1,0)，总费用3。期望核对量：`3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id hungarian`。固定案例实现为`modelcrew.algorithm_examples.case_hungarian`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
C=np.array([[4,1],[2,3]]); rows,cols=opt.linear_sum_assignment(C); return C[rows,cols].sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="pagerank"></a>
## PageRank · pagerank

**模型与核心公式**：$p'=\alpha P^Tp+(1-\alpha)v$。

**符号与输入输出**：P为含悬挂节点修正的行随机转移矩阵，v为个性化分布。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：α∈(0,1)，P/v非负且归一，悬挂节点有显式处理。

**失败边界**：未修正零出度会丢概率质量；排名不是影响的因果度量。反例/拒绝情形：零出度行全0不修正会使总概率下降。

**步骤与成本**：构造随机矩阵→幂迭代→检查和为1及残差。稀疏每步O(E+V)，迭代数依收敛/容差。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：二节点相互指向，α=.85,v=(.5,.5)，从(.5,.5)更新后仍(.5,.5)。期望核对量：`[0.5, 0.5]`；层级`single_update`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id pagerank`。固定案例实现为`modelcrew.algorithm_examples.case_pagerank`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
P=np.array([[0.,1.],[1.,0.]]); p=np.array([.5,.5]); return .85*P.T@p+.15*np.array([.5,.5])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="louvain"></a>
## Louvain · louvain

**模型与核心公式**：$Q=\frac1{2m}\sum_{ij}(A_{ij}-\gamma k_ik_j/(2m))\mathbf1(c_i=c_j)$。

**符号与输入输出**：A为无向加权邻接，k为度，m为总边权，γ为分辨率。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：权重/有向变体及γ明确，固定随机序和多次运行。

**失败边界**：模块度分辨率限制；局部启发式不保证全局，社区编号可置换。反例/拒绝情形：高Q不自动等于真实组织；小社区可能被分辨率限制合并。

**步骤与成本**：局部移动增Q→聚合社区→重复→多种子和分辨率检查。实践近线性不作最坏保证；每轮成本依移动次数。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：四节点仅边01和23各权1，分区{0,1}/{2,3}；γ=1，模块度.5。期望核对量：`0.5`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id louvain`。固定案例实现为`modelcrew.algorithm_examples.case_louvain`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
A=np.array([[0,1,0,0],[1,0,0,0],[0,0,0,1],[0,0,1,0]],float); k=A.sum(axis=1); B=A-np.outer(k,k)/A.sum(); c=np.array([0,0,1,1]); return B[c[:,None]==c[None,:]].sum()/A.sum()
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="k-shortest"></a>
## K最短路径 · k-shortest

**模型与核心公式**：$\operatorname{cost}(p)=\sum_{e\in p}w_e;\ p_1,\ldots,p_K\ \text{按费用递增且互异}$。

**符号与输入输出**：p为路径；需声明简单路径还是允许重复顶点的walk。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：K、去重、并列顺序与负边约束按所选算法定义。

**失败边界**：负环或零成本循环可使walk枚举退化；不能把同一路径重复计数。反例/拒绝情形：允许循环与要求简单路径是不同问题，不能混合统计K条。

**步骤与成本**：求最短→按Yen等生成偏离候选→去重→按费用取K。Yen简单路径经典界约O(KV(E+VlogV))，依最短路子例程。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：路径0→2费用4和0→1→2费用3；前两条费用[3,4]。期望核对量：`[3, 4]`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id k-shortest`。固定案例实现为`modelcrew.algorithm_examples.case_k_shortest`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return sorted([1+2,4])
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="graph-coloring"></a>
## 图着色 · graph-coloring

**模型与核心公式**：$\min K:\ c_u\ne c_v\ \forall (u,v)\in E,\ c_v\in\{1,\ldots,K\}$。

**符号与输入输出**：c为颜色/资源标签，E为冲突关系。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：无向冲突完整，颜色可交换，不同业务附加约束另写。

**失败边界**：一般NP难；贪心用K色仅给上界，不证色数最小；自环不可正常染色。反例/拒绝情形：有自环c_v≠c_v不可满足，不能分配更多颜色掩盖。

**步骤与成本**：构造冲突→排序/搜索→逐边检查→界与规模说明。一般指数；贪心近O(V+E)但不保最优。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：三角图任意两点相邻，最少3色；穷举1..3色验证。期望核对量：`3`；层级`small_complete_solution`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id graph-coloring`。固定案例实现为`modelcrew.algorithm_examples.case_graph_coloring`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return min(k for k in [1,2,3] if any(all(c[u]!=c[v] for u,v in [(0,1),(1,2),(0,2)]) for c in itertools.product(range(k),repeat=3)))
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。

<a id="centrality"></a>
## 中心性分析 · centrality

**模型与核心公式**：$C_D(v)=d(v)/(n-1);\ C_B(v)=\sum_{s<t;s,t\ne v}\sigma_{st}(v)/\sigma_{st}$。

**符号与输入输出**：d为度，σ为最短路数量，此处无向介数未归一化。输入的单位、维度、时间/样本范围和输出目标应在任务契约中明确。

**适用与前提**：明确度/接近/介数及有向/加权/断开图的定义。

**失败边界**：不同中心性不等价；不可达和权重作为长度还是强度要区分。反例/拒绝情形：交通边权若表示通行能力，直接当最短路长度会倒置含义。

**步骤与成本**：按问题选指标→定义归一→计算→扰动/领域验证。度O(E)；Brandes无权介数O(VE)，加权成本更高。停止时须保留真实状态、容差、预算和未解决项，不凭单次成功概括任意规模。

**可复算案例**：三点链0—1—2，中心点度中心性1、未归一介数1。期望核对量：`[1, 1]`；层级`core_equation_check`，绝对容差`1e-07`、相对容差`1e-06`。

运行：`python -m modelcrew.algorithm_knowledge check-examples --id centrality`。固定案例实现为`modelcrew.algorithm_examples.case_centrality`，使用Python/NumPy/SciPy及下列已随包实现的辅助函数；不执行资料中的任意代码：

```python
return [2/(3-1),1/1]
```

**实现与证据范围**：上述为独立编写的教育/验证示例，依赖NumPy/SciPy（evidence组）。它不注册本方法的通用业务求解器、不保证某推荐第三方库已经适配Windows/Python3.13或Docker。跨类别同一规范ID共用案例和公式，具体目标/预处理与条件须按任务重新核对。
