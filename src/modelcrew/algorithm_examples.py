# NexusMORE independently authored, bounded educational computations.
# These fixed examples are not general task solvers or proof of backend readiness.
import itertools
import math
import numpy as np
from scipy import optimize as opt, stats, special, integrate, sparse
from scipy.sparse import csgraph
from scipy.cluster import hierarchy

def require(condition, message):
    if not condition:raise ValueError(message)

def nondominated(a):
    return [i for i in range(len(a)) if not any(np.all(b<=a[i]) and np.any(b<a[i]) for b in a)]

def knapsack(weights, gains, capacity):
    values=[0]*(capacity+1)
    for w,g in zip(weights,gains):
        require(w>0,'Positive integer weights required')
        for c in range(capacity,w-1,-1):values[c]=max(values[c],values[c-w]+g)
    return values[capacity]

def dfs_order(graph,start):
    seen=set();order=[];stack=[start]
    while stack:
        v=stack.pop()
        if v in seen:continue
        seen.add(v);order.append(v);stack.extend(reversed(graph[v]))
    return order

def bfs_dist(graph,start):
    from collections import deque
    d=[-1]*len(graph);d[start]=0;q=deque([start])
    while q:
        v=q.popleft()
        for w in graph[v]:
            if d[w]<0:d[w]=d[v]+1;q.append(w)
    return d

def shortest(a,method):
    a=np.asarray(a,float)
    require(np.isfinite(a).all(),'Finite adjacency required')
    if method=='D':require(np.all(a>=0),'Dijkstra requires nonnegative edge weights')
    # In this bounded fixture dense zero means no edge; zero-cost edges require an explicit sparse edge representation.
    return csgraph.shortest_path(sparse.csr_matrix(a),method=method,directed=True,indices=0)

def prim_weight(a):
    a=np.asarray(a,float);require(np.allclose(a,a.T),'Undirected graph required')
    seen={0};total=0.
    while len(seen)<len(a):
        edges=[(a[u,v],v) for u in seen for v in range(len(a)) if v not in seen and a[u,v]!=0]
        require(bool(edges),'Graph disconnected')
        cost,v=min(edges);total+=cost;seen.add(v)
    return total

def scale_minmax(x,low,high):
    require(np.isfinite([low,high]).all() and high>low,'Nonconstant finite reference range required')
    x=np.asarray(x,float);require(np.isfinite(x).all(),'Finite inputs required')
    return (x-low)/(high-low)

def entropy_weights(x):
    x=np.asarray(x,float);require(x.ndim==2 and len(x)>1 and np.isfinite(x).all() and np.all(x>=0),'Nonnegative finite matrix with n>1 required')
    mass=x.sum(axis=0);require(np.all(mass>0),'Zero-mass column requires an explicit policy')
    p=x/mass;e=-special.xlogy(p,p).sum(axis=0)/math.log(len(x));d=1-e
    require(d.sum()>1e-12,'No distinguishing information')
    return d/d.sum()

def lof_1d(values,k):
    x=np.asarray(values,float);require(1<=k<len(x),'k must be within training size')
    d=abs(x[:,None]-x[None,:]);np.fill_diagonal(d,np.inf)
    kd=np.sort(d,axis=1)[:,k-1];neighbors=[np.flatnonzero(d[i]<=kd[i]) for i in range(len(x))]
    meanreach=np.array([np.maximum(kd[nb],d[i,nb]).mean() for i,nb in enumerate(neighbors)])
    require(np.all(meanreach>0),'Duplicate-point zero-density denominator')
    lrd=1/meanreach
    return np.array([np.mean(lrd[nb])/lrd[i] for i,nb in enumerate(neighbors)])

def affine_steps(initial,a,b,count):
    out=[];value=initial
    for _ in range(count):value=a*value+b;out.append(value)
    return out

def mm1(arrival,service):
    require(np.isfinite([arrival,service]).all() and 0<=arrival<service,'M/M/1 requires 0 <= lambda < mu')
    w=1/(service-arrival)
    return [w,arrival*w,arrival/(service*(service-arrival))]

def markov_step(p,P):
    p=np.asarray(p,float);P=np.asarray(P,float)
    require(P.ndim==2 and P.shape==(len(p),len(p)),'Transition shape differs')
    require(np.isfinite(P).all() and np.isfinite(p).all() and np.all(P>=0) and np.all(p>=0),'Finite nonnegative probabilities required')
    require(np.allclose(P.sum(axis=1),1,atol=1e-12,rtol=0) and abs(p.sum()-1)<1e-12,'Probabilities must sum to one')
    return p@P

def fcfs_wait(arrivals,services):
    require(len(arrivals)==len(services) and len(arrivals)>0,'Arrival/service shape differs')
    require(all(b>=a for a,b in zip(arrivals,arrivals[1:])) and all(t>=0 for t in services),'Arrival order or service time invalid')
    end=0.;wait=[]
    for arrival,service in zip(arrivals,services):
        start=max(arrival,end);wait.append(start-arrival);end=start+service
    return np.asarray(wait)

def dbscan_1d(values,eps,min_samples):
    x=np.asarray(values,float);require(eps>0 and 1<=min_samples<=len(x),'Invalid density parameters')
    nbs=[np.flatnonzero(abs(x-a)<=eps).tolist() for a in x];core=[len(nb)>=min_samples for nb in nbs]
    labels=[-1]*len(x);cluster=0
    for i in range(len(x)):
        if not core[i] or labels[i]>=0:continue
        todo=[i];labels[i]=cluster
        while todo:
            j=todo.pop()
            for k in nbs[j]:
                if labels[k]<0:
                    labels[k]=cluster
                    if core[k]:todo.append(k)
        cluster+=1
    return labels


def case_lp():
    r=opt.linprog([-1.,-2.],A_ub=[[1,1]],b_ub=[2],bounds=[(0,1),(0,1)],method='highs'); require(r.success,'LP failed'); return [*r.x,-r.fun]

def case_ip():
    return max(3*x+2*y for x in range(3) for y in range(4) if 2*x+y<=4)

def case_milp():
    r=opt.milp([1,.2],integrality=[1,0],bounds=opt.Bounds([0,0],[3,2]),constraints=opt.LinearConstraint([[1,1]],[2.5],[np.inf])); require(r.success,'MILP failed'); return r.fun

def case_nlp():
    r=opt.minimize(lambda x:(x[0]-2)**2,[0.],jac=lambda x:np.array([2*(x[0]-2)]),bounds=[(0,None)]); require(r.success,'NLP failed'); return [r.x[0],r.fun]

def case_binary_ip():
    return max(3*a+4*b for a,b in itertools.product([0,1],repeat=2) if 2*a+3*b<=3)

def case_dynamic_programming():
    return knapsack([2,3],[3,4],5)

def case_multi_objective():
    x=np.array([0.,1.,2.]); a=np.c_[x*x,(x-2)**2]; return [len(nondominated(a)),x[np.argmin(a.sum(axis=1))]]

def case_qp():
    return np.linalg.solve(2*np.eye(2),[2,4])

def case_goal_programming():
    x=min([0,2,4,5],key=lambda t:abs(t-2)+2*abs(t-4)); return [x,abs(x-2)+2*abs(x-4)]

def case_robust_optimization():
    x=1/max([1.,2.]); return [x,max(u*x for u in [1.,2.])]

def case_ga():
    pop=np.array([-2.,1.,3.]); parent=pop[np.argmin(pop**2)]; child=.5*parent+.5*pop[0]; return child**2

def case_pso():
    x=2.; v=.5*0+.5*(1-x)+.5*(0-x); return [v,x+v]

def case_sa():
    p=math.exp(-2/2); return [p,int(.2<p)]

def case_aco():
    w=np.array([1.,1.])*np.array([1.,2.]); return w/w.sum()

def case_de():
    candidate=1+.5*(2-0); chosen=candidate if candidate**2<3**2 else 3; return [chosen,chosen**2]

def case_tabu():
    allowed=[x for x in [1,3] if x not in {1}]; chosen=min(allowed,key=lambda x:x*x); return [chosen,chosen**2]

def case_nsga2():
    return nondominated(np.array([[0,4],[1,1],[4,0],[3,3]],float))

def case_linear_regression():
    X=np.c_[np.ones(3),np.arange(3)]; b=np.linalg.lstsq(X,[1,3,5],rcond=None)[0]; return [*b,np.array([1,3])@b]

def case_polynomial_regression():
    x=np.array([-1.,0.,1.]); b=np.linalg.lstsq(np.c_[np.ones(3),x,x*x],[1,0,1],rcond=None)[0]; return np.array([1,2,4])@b

def case_exponential_smoothing():
    level=10.; level=.5*12+.5*level; return .5*14+.5*level

def case_gm11():
    x=np.array([1.,2.,4.,8.]); acc=np.cumsum(x); z=(acc[:-1]+acc[1:])/2; return np.linalg.lstsq(np.c_[-z,np.ones(3)],x[1:],rcond=None)[0]

def case_arima():
    return 1+.5*4

def case_sarima():
    return .8*10

def case_var():
    A=np.diag([.5,.25]); return [*(np.array([1,0])+A@np.array([2,4])),max(abs(np.linalg.eigvals(A)))]

def case_prophet():
    t=4.; return 2+.5*t+3*math.cos(2*math.pi*t/4)

def case_xgboost():
    G,H,lam=-4.,2.,2.; w=-G/(H+lam); return [w,G+(H+lam)*w]

def case_lightgbm():
    return (-2)**2/(1+1)+2**2/(1+1)-0**2/(2+1)

def case_catboost():
    return (sum([1.,0.])+2*.5)/(2+2)

def case_lstm():
    c=.5*0+.5*.8; return [c,.5*np.tanh(c)]

def case_gru():
    return (1-.25)*.8+.25*.4

def case_tcn():
    x=[1,2,3,4,5]; return x[4]+2*x[2]

def case_transformer():
    return special.softmax(np.array([0.,math.log(3)]))@np.array([2.,6.])

def case_ahp():
    w=np.array([1.,2.,4.]); A=w[:,None]/w[None,:]; vals,vec=np.linalg.eig(A); k=np.argmax(vals.real); v=abs(vec[:,k].real); return [*(v/v.sum()),(vals[k].real-3)/2]

def case_entropy_weight():
    return entropy_weights(np.array([[1.,1.],[0.,1.]]))

def case_topsis():
    v=np.array([[1.,0.],[0.,1.]])*np.array([.75,.25]); plus=v.max(axis=0); minus=v.min(axis=0); dp=np.linalg.norm(v-plus,axis=1); dm=np.linalg.norm(v-minus,axis=1); return dm/(dp+dm)

def case_weighted_score():
    return np.dot([.8,.4],[.25,.75])

def case_critic():
    X=np.array([[0.,1.],[1.,0.]]); c=X.std(axis=0,ddof=1)*(1-np.corrcoef(X,rowvar=False)).sum(axis=1); return c/c.sum()

def case_pca():
    X=np.array([[-1.,-1.],[0,0],[1,1]]); v=np.linalg.eigvalsh(np.cov(X,rowvar=False))[::-1]; return [*v,v[0]/v.sum()]

def case_factor_analysis():
    L=np.array([[1.],[2.]]); return L@L.T+np.eye(2)

def case_grey_relation():
    d=np.array([0.,2.]); return np.mean((d.min()+.5*d.max())/(d+.5*d.max()))

def case_fuzzy_evaluation():
    return np.array([.25,.75])@np.array([[1.,0.],[.2,.8]])

def case_vikor():
    d=np.array([[0.,0.],[1.,1.]]); S=(d*.5).sum(axis=1); R=(d*.5).max(axis=1); return .5*(S-S.min())/np.ptp(S)+.5*(R-R.min())/np.ptp(R)

def case_promethee():
    x=np.array([1.,2.,3.]); P=(x[:,None]>x[None,:]).astype(float); return (P.sum(axis=1)-P.sum(axis=0))/2

def case_electre():
    a=np.array([2.,0.]); b=np.array([1.,1.]); c=np.array([.6,.4])[a>=b].sum(); return [c,int(c>=.6 and np.all(b-a<=.5))]

def case_dea():
    r=opt.linprog([1,0,0],A_ub=[[-2,1,2],[0,-1,-1]],b_ub=[0,-1],bounds=[(0,None)]*3,method='highs'); require(r.success,'DEA failed'); return r.fun

def case_malmquist():
    Dt0,Dt1,Dn0,Dn1=1.,2.,.5,1.; return math.sqrt((Dt1/Dt0)*(Dn1/Dn0))

def case_dfs():
    return dfs_order([[1,2],[2],[]],0)

def case_bfs():
    return bfs_dist([[1,2],[2],[]],0)

def case_dijkstra():
    return shortest(np.array([[0,1,4],[0,0,2],[0,0,0]],float),'D')

def case_floyd():
    A=np.array([[0,1,4],[0,0,2],[0,0,0]],float); return csgraph.shortest_path(sparse.csr_matrix(A),method='FW',directed=True)[0,2]

def case_bellman_ford():
    return shortest(np.array([[0,1,4],[0,0,-2],[0,0,0]],float),'BF')

def case_prim():
    return prim_weight(np.array([[0,1,4],[1,0,2],[4,2,0]],float))

def case_kruskal():
    A=sparse.csr_matrix([[0,1,4],[1,0,2],[4,2,0]]); return csgraph.minimum_spanning_tree(A).sum()

def case_dinic():
    A=sparse.csr_matrix(np.array([[0,2,1],[0,0,2],[0,0,0]],dtype=np.int64)); return csgraph.maximum_flow(A,0,2,method='dinic').flow_value

def case_min_cost_flow():
    r=opt.linprog([1,1,5],A_eq=[[1,0,1],[1,-1,0]],b_eq=[3,0],bounds=[(0,2),(0,2),(0,1)],method='highs'); require(r.success,'flow infeasible'); return r.fun

def case_hungarian():
    C=np.array([[4,1],[2,3]]); rows,cols=opt.linear_sum_assignment(C); return C[rows,cols].sum()

def case_pagerank():
    P=np.array([[0.,1.],[1.,0.]]); p=np.array([.5,.5]); return .85*P.T@p+.15*np.array([.5,.5])

def case_louvain():
    A=np.array([[0,1,0,0],[1,0,0,0],[0,0,0,1],[0,0,1,0]],float); k=A.sum(axis=1); B=A-np.outer(k,k)/A.sum(); c=np.array([0,0,1,1]); return B[c[:,None]==c[None,:]].sum()/A.sum()

def case_k_shortest():
    return sorted([1+2,4])

def case_graph_coloring():
    return min(k for k in [1,2,3] if any(all(c[u]!=c[v] for u,v in [(0,1),(1,2),(0,2)]) for c in itertools.product(range(k),repeat=3)))

def case_centrality():
    return [2/(3-1),1/1]

def case_descriptive():
    x=np.array([1.,2.,3.]); return [x.mean(),x.var(ddof=1),np.median(x)]

def case_minmax():
    return scale_minmax(np.array([2.,4.,6.]),2,6)

def case_zscore():
    x=np.array([1.,2.,3.]); return (x-x.mean())/x.std(ddof=1)

def case_imputation():
    x=np.array([1.,np.nan,3.]); return np.where(np.isnan(x),np.nanmean(x),x)

def case_knn_imputation():
    q=np.array([0.,2.]); v=np.array([10.,20.]); idx=np.argsort(abs(q-1))[:2]; return v[idx].mean()

def case_three_sigma():
    return (abs(np.array([0.,2.,4.]))>3).astype(int)

def case_iqr():
    q1,q3=np.quantile([0,1,2,3,100],[.25,.75],method='linear'); return [q1-1.5*(q3-q1),q3+1.5*(q3-q1)]

def case_lof():
    return lof_1d([0.,1.,10.],1)

def case_pearson():
    return stats.pearsonr([1,2,3],[2,4,6]).statistic

def case_spearman():
    return stats.spearmanr([1,2,3],[30,20,10]).statistic

def case_kendall():
    return stats.kendalltau([1,2,3],[1,3,2],variant='b').statistic

def case_ttest():
    a=np.array([1.,2.,3.]); b=np.array([2.,3.,4.]); r=stats.ttest_ind(a,b,equal_var=False); d=(a.mean()-b.mean())/math.sqrt((a.var(ddof=1)+b.var(ddof=1))/2); return [r.statistic,r.pvalue,d]

def case_chi_square():
    r=stats.chi2_contingency([[10,10],[10,10]],correction=False); return [r.statistic,r.pvalue]

def case_anova():
    return stats.f_oneway([1,2],[3,4],[5,6]).statistic

def case_bootstrap():
    means=np.array([(a+b)/2 for a,b in itertools.product([0.,2.],repeat=2)]); return means.var(ddof=0)

def case_logistic_regression():
    p=special.expit(math.log(3)); return [p,-math.log(p)]

def case_vif():
    return 1/(1-.75)

def case_adf():
    return -.2/.1

def case_did():
    return (15-10)-(10-8)

def case_psm():
    pt=np.array([.2,.8]); pc=np.array([.21,.79]); matches=np.argmin(abs(pt[:,None]-pc[None,:]),axis=1); return np.mean(np.array([5.,9.])-np.array([3.,6.])[matches])

def case_monte_carlo():
    return np.random.default_rng(2026).uniform(0,1,100000).mean()

def case_difference_equation():
    return affine_steps(0,.5,1,3)

def case_ode():
    r=integrate.solve_ivp(lambda t,y:-y,[0,1],[1.],rtol=1e-10,atol=1e-12); require(r.success,'ODE failed'); return r.y[0,-1]

def case_queueing():
    return mm1(2,3)

def case_markov():
    P=np.array([[.8,.2],[.1,.9]]); return [*markov_step([1,0],P),1/3,2/3]

def case_cellular_automata():
    s=np.array([0,1,0,0],int); return np.bitwise_xor(np.roll(s,1),np.roll(s,-1))

def case_system_dynamics():
    return affine_steps(10,.8,3,2)

def case_discrete_event():
    return fcfs_wait([0,1,2],[2,2,1]).mean()

def case_stochastic_process():
    rate=2*.5; return [rate,rate,stats.poisson.pmf(0,rate)]

def case_bayesian_network():
    joint=.2*.8; evidence=joint+.8*.1; return [evidence,joint/evidence]

def case_abm():
    x=np.array([0.,2.,4.]); return x+.5*(x.mean()-x)

def case_sensitivity():
    t=2.; h=.001; return ((t+h)**2-(t-h)**2)/(2*h)

def case_sobol():
    v=np.array([1.,4.])/12; return v/v.sum()

def case_decision_tree():
    p=np.array([.5,.5]); return 1-np.sum(p*p)

def case_svm():
    w=max(1/1,1/1); return [w,2/abs(w)]

def case_knn():
    x=np.array([0.,2.,5.]); y=np.array([0,0,1]); order=np.argsort(abs(x-4)); return [y[order[0]],int(y[order[:3]].mean()>.5)]

def case_random_forest():
    p=np.mean([0.,1.,1.]); return [p,int(p>=.5)]

def case_naive_bayes():
    w=np.array([.5,.5])*np.array([.2,.8]); return w/w.sum()

def case_adaboost():
    a=.5*math.log(3); w=np.ones(4)*.25*np.exp(-a*np.array([1,1,1,-1])); return w/w.sum()

def case_gbdt():
    y=np.array([1.,3.]); F=np.zeros(2); leaf=np.mean(y-F); return F+.5*leaf

def case_stacking():
    return np.array([1.,3.])@np.array([.25,.75])

def case_kmeans():
    x=np.array([0.,2.,8.,10.]); labels=np.argmin(abs(x[:,None]-np.array([0.,10.])),axis=1); c=np.array([x[labels==j].mean() for j in range(2)]); return [*c,np.sum((x-c[labels])**2)]

def case_hierarchical():
    Z=hierarchy.linkage(np.array([[0.],[1.],[4.]]),method='single'); return Z[:,2]

def case_dbscan():
    labels=dbscan_1d([0.,.1,5.],.2,2); return [len(set(labels)-{-1}),sum(t==-1 for t in labels)]

def case_gmm():
    w=np.array([.5,.5])*stats.norm.pdf(1,loc=[0,2],scale=1); return w/w.sum()

def case_mean_shift():
    x=np.array([0.,2.,10.]); neighbors=x[abs(x-1)<=3]; return neighbors.mean()

def case_tsne():
    y=np.array([0.,1.,2.]); w=1/(1+(y[:,None]-y[None,:])**2); q=w[~np.eye(3,dtype=bool)]; q=q/q.sum(); p=np.ones(6)/6; return np.sum(p*np.log(p/q))

def case_umap():
    return [.2+.5-.2*.5,1/(1+2**2)]

def case_mlp():
    x=np.array([1.,-1.]); h=np.maximum(np.array([[1.,1.],[1.,-1.]])@x,0); return np.array([1.,2.])@h

def case_cnn():
    return np.correlate([1.,2.,3.],[1.,-1.],mode='valid')

def case_rnn():
    return np.tanh(1*1+.5*0)

def case_autoencoder():
    x=np.array([1.,3.]); z=x.mean(); rec=np.repeat(z,2); return [z,np.mean((x-rec)**2)]

EXAMPLES={
'lp':case_lp,
'ip':case_ip,
'milp':case_milp,
'nlp':case_nlp,
'binary-ip':case_binary_ip,
'dynamic-programming':case_dynamic_programming,
'multi-objective':case_multi_objective,
'qp':case_qp,
'goal-programming':case_goal_programming,
'robust-optimization':case_robust_optimization,
'ga':case_ga,
'pso':case_pso,
'sa':case_sa,
'aco':case_aco,
'de':case_de,
'tabu':case_tabu,
'nsga2':case_nsga2,
'linear-regression':case_linear_regression,
'polynomial-regression':case_polynomial_regression,
'exponential-smoothing':case_exponential_smoothing,
'gm11':case_gm11,
'arima':case_arima,
'sarima':case_sarima,
'var':case_var,
'prophet':case_prophet,
'xgboost':case_xgboost,
'lightgbm':case_lightgbm,
'catboost':case_catboost,
'lstm':case_lstm,
'gru':case_gru,
'tcn':case_tcn,
'transformer':case_transformer,
'ahp':case_ahp,
'entropy-weight':case_entropy_weight,
'topsis':case_topsis,
'weighted-score':case_weighted_score,
'critic':case_critic,
'pca':case_pca,
'factor-analysis':case_factor_analysis,
'grey-relation':case_grey_relation,
'fuzzy-evaluation':case_fuzzy_evaluation,
'vikor':case_vikor,
'promethee':case_promethee,
'electre':case_electre,
'dea':case_dea,
'malmquist':case_malmquist,
'dfs':case_dfs,
'bfs':case_bfs,
'dijkstra':case_dijkstra,
'floyd':case_floyd,
'bellman-ford':case_bellman_ford,
'prim':case_prim,
'kruskal':case_kruskal,
'dinic':case_dinic,
'min-cost-flow':case_min_cost_flow,
'hungarian':case_hungarian,
'pagerank':case_pagerank,
'louvain':case_louvain,
'k-shortest':case_k_shortest,
'graph-coloring':case_graph_coloring,
'centrality':case_centrality,
'descriptive':case_descriptive,
'minmax':case_minmax,
'zscore':case_zscore,
'imputation':case_imputation,
'knn-imputation':case_knn_imputation,
'three-sigma':case_three_sigma,
'iqr':case_iqr,
'lof':case_lof,
'pearson':case_pearson,
'spearman':case_spearman,
'kendall':case_kendall,
'ttest':case_ttest,
'chi-square':case_chi_square,
'anova':case_anova,
'bootstrap':case_bootstrap,
'logistic-regression':case_logistic_regression,
'vif':case_vif,
'adf':case_adf,
'did':case_did,
'psm':case_psm,
'monte-carlo':case_monte_carlo,
'difference-equation':case_difference_equation,
'ode':case_ode,
'queueing':case_queueing,
'markov':case_markov,
'cellular-automata':case_cellular_automata,
'system-dynamics':case_system_dynamics,
'discrete-event':case_discrete_event,
'stochastic-process':case_stochastic_process,
'bayesian-network':case_bayesian_network,
'abm':case_abm,
'sensitivity':case_sensitivity,
'sobol':case_sobol,
'decision-tree':case_decision_tree,
'svm':case_svm,
'knn':case_knn,
'random-forest':case_random_forest,
'naive-bayes':case_naive_bayes,
'adaboost':case_adaboost,
'gbdt':case_gbdt,
'stacking':case_stacking,
'kmeans':case_kmeans,
'hierarchical':case_hierarchical,
'dbscan':case_dbscan,
'gmm':case_gmm,
'mean-shift':case_mean_shift,
'tsne':case_tsne,
'umap':case_umap,
'mlp':case_mlp,
'cnn':case_cnn,
'rnn':case_rnn,
'autoencoder':case_autoencoder,
}
