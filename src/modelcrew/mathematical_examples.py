"""Fixed NexusMORE mathematical checks; not a theorem prover or task inference API."""
import itertools
import math
import numpy as np
import sympy as sp
from scipy import stats, integrate

def require(condition,message):
    if not condition:raise ValueError(message)

def nonzero(value):
    require(np.isfinite(value) and value!=0,'Finite nonzero denominator required')
    return value

def log_positive(value):
    require(np.isfinite(value) and value>0,'Positive real logarithm input required')
    return math.log(value)

def compatible_sum_units(a,b):
    require(a==b,'Cannot add unlike dimensions')
    return dict(a)

def solve_unique(A,b):
    A=np.asarray(A,float);b=np.asarray(b,float)
    require(A.ndim==2 and A.shape[0]==A.shape[1] and b.shape==(A.shape[0],),'Square consistent system required by this fixture')
    require(np.isfinite(A).all() and np.isfinite(b).all(),'Finite linear inputs required')
    require(np.linalg.matrix_rank(A)==A.shape[1],'Unique solution requires full rank')
    return np.linalg.solve(A,b)

def observations(values):
    x=np.asarray(values,float)
    require(x.ndim==1 and len(x)>=2 and np.isfinite(x).all(),'At least two finite scalar observations required')
    return x

def welch_summary(x,y):
    x=observations(x);y=observations(y);a=x.var(ddof=1)/len(x);b=y.var(ddof=1)/len(y)
    require(a+b>0,'Degenerate zero standard error requires a separate policy')
    delta=x.mean()-y.mean();se=math.sqrt(a+b);df=(a+b)**2/(a*a/(len(x)-1)+b*b/(len(y)-1))
    q=stats.t.ppf(.975,df);pooled=math.sqrt(((len(x)-1)*x.var(ddof=1)+(len(y)-1)*y.var(ddof=1))/(len(x)+len(y)-2))
    return [delta,delta/se,2*stats.t.sf(abs(delta/se),df),delta-q*se,delta+q*se,delta/nonzero(pooled)]

def paired_summary(before,after):
    x=observations(before);y=observations(after);require(x.shape==y.shape,'Complete aligned pairs required')
    d=y-x;sd=d.std(ddof=1);require(sd>0,'Degenerate paired differences require a separate policy')
    se=sd/math.sqrt(len(d));q=stats.t.ppf(.975,len(d)-1);r=stats.ttest_1samp(d,0)
    return [d.mean(),r.statistic,r.pvalue,d.mean()-q*se,d.mean()+q*se,d.mean()/sd]

def valid_pvalues(p):
    p=np.asarray(p,float);require(p.ndim==1 and len(p)>0 and np.isfinite(p).all() and np.all((p>=0)&(p<=1)),'Nonempty valid p-values required; missing tests need explicit family policy')
    return p

def bonferroni(p):
    p=valid_pvalues(p);return np.minimum(1,len(p)*p)

def bh_adjust(p):
    p=valid_pvalues(p);order=np.argsort(p,kind='stable');ranked=p[order];adjusted=np.minimum.accumulate((len(p)*ranked/np.arange(1,len(p)+1))[::-1])[::-1];out=np.empty_like(p);out[order]=np.minimum(1,adjusted);return out

def tost_summary(delta,se,df,margin,alpha):
    require(np.isfinite([delta,se,df,margin,alpha]).all() and se>0 and df>0 and margin>0 and 0<alpha<.5,'Valid TOST summary and prespecified positive margin required')
    pL=stats.t.sf((delta+margin)/se,df);pU=stats.t.cdf((delta-margin)/se,df);q=stats.t.ppf(1-alpha,df)
    return [pL,pU,delta-q*se,delta+q*se,int(pL<alpha and pU<alpha)]


def case_domains():
    x=2.; return [(x*x-1)/nonzero(x-1),x+1,math.sqrt((-2.)**2)]

def case_dimensions():
    m,V,L,T=2.,4.,3.,2.; return [m/V,L/T,(L/T)*T/L]

def case_linear_system():
    A=np.array([[2.,1.],[1.,3.]]);b=np.array([1.,2.]);x=solve_unique(A,b);return [*x,np.linalg.norm(A@x-b)]

def case_least_squares():
    X=np.c_[np.ones(3),[0.,1.,2.]];y=np.array([1.,3.,5.]);b=np.linalg.lstsq(X,y,rcond=None)[0];return [*b,np.array([1.,3.])@b,np.linalg.norm(X.T@(X@b-y))]

def case_differentiation():
    x,y=sp.symbols('x y',real=True);f=x*x*y+sp.sin(y);subs={x:2,y:0};return [float(sp.diff(f,v).subs(subs)) for v in [x,y]]+[float(a.subs(subs)) for a in sp.hessian(f,(x,y))]

def case_taylor():
    h=.1;p=1+h+h*h/2;r=math.exp(h)-p;return [p,r,int(0<=r<=math.exp(h)*h**3/6)]

def case_integration_limits():
    x,a=sp.symbols('x a',real=True);return [float(sp.integrate(sp.exp(a*x).subs(a,0),(x,0,1))),float(sp.integrate(sp.diff(sp.exp(a*x),a).subs(a,0),(x,0,1)))]

def case_probability():
    prior=.01;sens=.9;fpr=.05;return [sens*prior/nonzero(sens*prior+fpr*(1-prior)),10*.2,10*.2*.8]

def case_sensitivity_errors():
    x,y=6.,2.;g=np.array([1/y,-x/y**2]);S=np.diag([.1**2,.05**2]);return [x/y,math.sqrt(g@S@g),abs(g)@np.array([.1,.05])]

def case_ode_conditions():
    r=integrate.solve_ivp(lambda t,y:-2*y,(0,1),[3.],rtol=1e-11,atol=1e-13);require(r.success,'ODE failed');return r.y[0,-1]

def case_constrained_optimality():
    x,l=sp.symbols('x l',real=True);s=sp.solve([2*x-l,1-x],[x,l]);return [float(s[x]),float(s[l]),float(s[l]*(1-s[x]))]

def case_numerical_error():
    errs=[]
    for n in [10,20]:
        x=np.linspace(0,1,n+1);errs.append(np.trapezoid(x*x,x)-1/3)
    return [*errs,errs[0]/errs[1]]

def case_quantifiers():
    x=1000.;y=x+1;fixed=-2.;witness=fixed+1;return [y-x,witness-fixed]

def case_direct_proof():
    a,b=sp.symbols('a b',real=True);expr=(a+b)**2-4*a*b;return [float(sp.expand(expr-(a-b)**2)),float(expr.subs({a:1,b:3}))]

def case_contradiction():
    return sum(p*p==2*q*q for p in range(1,31) for q in range(1,21))

def case_induction():
    n=10;return [sum(range(1,n+1)),n*(n+1)//2]

def case_contrapositive():
    k=sp.symbols('k',integer=True);return [float(sp.expand((2*k+1)**2-4*k*k-4*k)),7**2%2]

def case_case_analysis():
    return [abs(x)+abs(y)-abs(x+y) for x in [-2,2] for y in [-3,3]]

def case_constructive_proof():
    B,n=12.,3;allocation=[B/n]*n;return [*allocation,sum(allocation)]

def case_existence_uniqueness():
    candidates=[0.,1.];x=min(candidates,key=lambda z:(z-2)**2);return [x,(x-2)**2]

def case_convexity():
    x,y,t=0.,4.,.25;return [t*x*x+(1-t)*y*y-(t*x+(1-t)*y)**2,t*(1-t)*(x-y)**2]

def case_descent_convergence():
    x,L,eta=2.,1.,.5;new=x-eta*x;return [x*x/2,new*new/2,eta*(1-L*eta/2)*x*x]

def case_fixed_point():
    x=0.
    for _ in range(3):x=.5*x+1
    return [x,abs(x-2),.5**3/(1-.5)]

def case_generalization():
    n,delta,M=100,.05,10;return [math.sqrt(math.log(2/delta)/(2*n)),math.sqrt(math.log(2*M/delta)/(2*n))]

def case_design_estimand():
    ids=['a','a','b','b','c','c'];deff=1+(2-1)*.5;return [len(ids),len(set(ids)),deff,len(ids)/deff]

def case_welch_inference():
    return welch_summary([1,2,3],[2,3,4])

def case_paired_inference():
    return paired_summary([1,2,3,4],[2,4,4,6])

def case_anova_inference():
    g=[np.array(a,float) for a in [[1,2],[3,4],[5,6]]];r=stats.f_oneway(*g);mu=np.concatenate(g).mean();ssb=sum(len(a)*(a.mean()-mu)**2 for a in g);ssw=sum(((a-a.mean())**2).sum() for a in g);q=stats.t.ppf(.975,1)*.5;return [r.statistic,r.pvalue,ssb/(ssb+ssw),1.5-q,1.5+q]

def case_fisher_inference():
    table=np.array([[1,9],[11,3]]);r=stats.contingency.odds_ratio(table,kind='conditional');ci=r.confidence_interval(confidence_level=.95);return [r.statistic,stats.fisher_exact(table,alternative='two-sided').pvalue,ci.low,ci.high]

def case_mcnemar_inference():
    B,C,N=2,8,20;r=stats.binomtest(B,B+C,.5,alternative='two-sided');ci=r.proportion_ci(confidence_level=.95,method='exact');return [r.pvalue,(C-B)/N,B/(B+C),ci.low,ci.high]

def case_rank_inference():
    x=np.array([1,2,3]);y=np.array([4,5,6]);r=stats.mannwhitneyu(x,y,alternative='two-sided',method='exact');return [r.statistic,r.pvalue,2*r.statistic/(len(x)*len(y))-1,np.median(y[:,None]-x[None,:]),int(2/math.comb(6,3)>.05)]

def case_regression_inference():
    X=np.c_[np.ones(4),[0.,1.,2.,3.]];y=np.array([1.,2.,2.,4.]);b=np.linalg.lstsq(X,y,rcond=None)[0];df=4-2;s2=((y-X@b)**2).sum()/df;se=math.sqrt((np.linalg.solve(X.T@X,np.eye(2))*s2)[1,1]);q=stats.t.ppf(.975,df);return [b[1],se,b[1]-q*se,b[1]+q*se,df]

def case_bootstrap_inference():
    means=np.array([np.mean(x) for x in itertools.product([0.,2.],repeat=2)]);q=np.quantile(means,[.025,.975],method='inverted_cdf');return [means.mean(),means.var(ddof=0),*q]

def case_multiple_testing():
    p=np.array([.01,.04,.03,.2]);return [*bonferroni(p),*bh_adjust(p)]

def case_equivalence_inference():
    return tost_summary(.1,.1,9,.5,.05)

def case_cluster_inference():
    clusters=np.array([[0.,0.],[2.,2.]]);means=clusters.mean(axis=1);se=means.std(ddof=1)/math.sqrt(2);q=stats.t.ppf(.975,1);return [means.mean(),clusters.ravel().std(ddof=1)/2,se,means.mean()-q*se,means.mean()+q*se]

def case_missingness_inference():
    x=np.array([1.,np.nan,3.]);obs=x[np.isfinite(x)];filled=np.where(np.isnan(x),obs.mean(),x);return [obs.mean(),obs.var(ddof=1),filled.var(ddof=1)]

def case_validation_inference():
    train=np.array([1.,2.,3.]);test=np.array([4.,5.]);return (test-train.mean())/nonzero(train.std(ddof=1))

def case_complexity_proof():
    c=0
    for n in [2,4,8]:c=2*c+n-1
    return [c,8*3-8+1]

EXAMPLES={
'domains':case_domains,
'dimensions':case_dimensions,
'linear-system':case_linear_system,
'least-squares':case_least_squares,
'differentiation':case_differentiation,
'taylor':case_taylor,
'integration-limits':case_integration_limits,
'probability':case_probability,
'sensitivity-errors':case_sensitivity_errors,
'ode-conditions':case_ode_conditions,
'constrained-optimality':case_constrained_optimality,
'numerical-error':case_numerical_error,
'quantifiers':case_quantifiers,
'direct-proof':case_direct_proof,
'contradiction':case_contradiction,
'induction':case_induction,
'contrapositive':case_contrapositive,
'case-analysis':case_case_analysis,
'constructive-proof':case_constructive_proof,
'existence-uniqueness':case_existence_uniqueness,
'convexity':case_convexity,
'descent-convergence':case_descent_convergence,
'fixed-point':case_fixed_point,
'generalization':case_generalization,
'design-estimand':case_design_estimand,
'welch-inference':case_welch_inference,
'paired-inference':case_paired_inference,
'anova-inference':case_anova_inference,
'fisher-inference':case_fisher_inference,
'mcnemar-inference':case_mcnemar_inference,
'rank-inference':case_rank_inference,
'regression-inference':case_regression_inference,
'bootstrap-inference':case_bootstrap_inference,
'multiple-testing':case_multiple_testing,
'equivalence-inference':case_equivalence_inference,
'cluster-inference':case_cluster_inference,
'missingness-inference':case_missingness_inference,
'validation-inference':case_validation_inference,
'complexity-proof':case_complexity_proof,
}
