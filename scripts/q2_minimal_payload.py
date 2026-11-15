"""Q2 controlled P1 numerical payload. Execute only in the registered Docker job."""
# The builder prepends the traceable, previously reviewed Q1 kinematic core.

def iv(x, y=None):
    return (np.asarray(x, dtype=float), np.asarray(x if y is None else y, dtype=float))
def down(x): return np.nextafter(x, -np.inf)
def up(x): return np.nextafter(x, np.inf)
def add(a,b): return down(a[0]+b[0]), up(a[1]+b[1])
def neg(a): return -a[1],-a[0]
def sub(a,b): return add(a,neg(b))
def mul(a,b):
    v=np.stack(np.broadcast_arrays(a[0]*b[0],a[0]*b[1],a[1]*b[0],a[1]*b[1]))
    return down(np.min(v,axis=0)),up(np.max(v,axis=0))
def div(a,b):
    if np.any((b[0]<=0)&(b[1]>=0)): raise ValueError('interval division through zero')
    return mul(a,(down(1/b[1]),up(1/b[0])))
def sqr(a):
    return down(np.where((a[0]<=0)&(a[1]>=0),0,np.minimum(a[0]**2,a[1]**2))),up(np.maximum(a[0]**2,a[1]**2))
def sqrtiv(a):
    if np.any(a[0]<0): raise ValueError('negative sqrt enclosure')
    return down(np.sqrt(a[0])),up(np.sqrt(a[1]))
def absiv(a):
    return np.where((a[0]<=0)&(a[1]>=0),0,np.minimum(abs(a[0]),abs(a[1]))),np.maximum(abs(a[0]),abs(a[1]))
def isum(a,axis): return down(np.sum(a[0],axis=axis)),up(np.sum(a[1],axis=axis))
# isum is used only for two-component sums, so one outward rounding suffices.
PI=iv(down(math.pi),up(math.pi))
BI=div(iv(.55-1e-16,.55+1e-16),mul(iv(2),PI))
INITI=mul(iv(32),PI)
LN2=iv(down(0.6931471805599453),up(0.6931471805599453))
def coeff(n):
    a=iv(1)
    for j in range(2,n+1): a=div(a,iv(j))
    return a
COEFF=[coeff(j) for j in range(64)]
def siniv(a):
    k=np.rint((a[0]+a[1])/(4*math.pi))
    r=sub(a,mul(iv(k),mul(iv(2),PI)))
    if np.any(np.maximum(abs(r[0]),abs(r[1]))>4): raise ValueError('trig enclosure too wide')
    z=sqr(r); v=neg(COEFF[63])
    for n in range(61,0,-2): v=add(mul(v,z),COEFF[n] if ((n-1)//2)%2==0 else neg(COEFF[n]))
    return add(mul(r,v),iv(-1e-30,1e-30))
def cosiv(a): return siniv(add(a,div(PI,iv(2))))
def logiv(a):
    if np.any(a[0]<=0): raise ValueError('log domain')
    k=np.floor(np.log2(a[0])).astype(int)
    scaled=div(a,iv(np.exp2(k)))
    if np.any(scaled[1]>2.01): raise ValueError('log range too wide')
    y=div(sub(scaled,iv(1)),add(scaled,iv(1))); z=sqr(y); term=y; total=iv(0)
    for j in range(64):
        total=add(total,div(term,iv(2*j+1))); term=mul(term,z)
    return add(add(mul(iv(2),total),mul(iv(k),LN2)),iv(-1e-50,1e-50))
def arciv(a):
    h=sqrtiv(add(iv(1),sqr(a)))
    return mul(div(BI,iv(2)),add(mul(a,h),logiv(add(a,h))))
def fiv(delta,prev,ell):
    bd=mul(BI,delta); r=mul(BI,prev)
    return sub(add(sqr(bd),mul(mul(iv(4),mul(r,add(r,bd))),sqr(siniv(div(delta,iv(2)))))),sqr(ell))
def root_enclosure(prev,ell):
    root=next_theta(prev,ell,5e-14)-prev
    e=2e-12
    elliv=iv(down(ell),up(ell))
    for unused in range(12):
        lo=down(root-e); hi=up(root+e)
        if fiv(iv(lo),iv(prev),elliv)[1]<0 and fiv(iv(hi),iv(prev),elliv)[0]>0:
            return down(prev+lo),up(prev+hi)
        e*=4
    raise ValueError('outward root enclosure unresolved')
def enclosed_state(t):
    q,p,v=solve(t)
    if t==0: head=INITI
    else:
        e=2e-11
        for unused in range(12):
            lo=down(q[0]-e); hi=up(q[0]+e)
            def h(x): return sub(sub(arciv(INITI),arciv(iv(x))),iv(t))
            if h(lo)[0]>0 and h(hi)[1]<0: break
            e*=4
        else: raise ValueError('head enclosure unresolved')
        head=iv(lo,hi)
    # For theta_head>=40, r>=3.50, F(pi/2)>ell_max^2 and N>0.
    # D-N=(1-cos(delta))*(b*b*delta+2*b*r)>0, so 0<dtheta_next/dtheta_prev<1.
    if head[0]<40: raise ValueError('monotonic-branch proof domain unavailable')
    # The outward implicit map is nonexpansive: 0<N/D<1.
    # Certify all local roots at the nominal predecessors in one interval batch;
    # accumulate local enclosure radii instead of recursively widening delta.
    delta=np.diff(q); e=2e-11
    ell=iv(down(ROD_L),up(ROD_L))
    for unused in range(12):
        lo=down(delta-e); hi=up(delta+e)
        if np.all(fiv(iv(lo),iv(q[:-1]),ell)[1]<0) and np.all(fiv(iv(hi),iv(q[:-1]),ell)[0]>0):break
        e*=4
    else:raise ValueError('batched roots unresolved')
    err0=up(max(q[0]-float(head[0]),float(head[1])-q[0]))
    err=np.empty(224);err[0]=err0
    for j in range(1,224):err[j]=up(err[j-1]+up(e+1e-13))
    qi=iv(down(q-err),up(q+err))
    return q,p,v,qi

def positions_iv(qi):
    r=mul(BI,qi)
    x=mul(r,cosiv(qi)); y=mul(r,siniv(qi))
    return np.stack((x[0],y[0]),axis=-1),np.stack((x[1],y[1]),axis=-1)
PAIR_I,PAIR_J=np.triu_indices(223,2)
HALF=np.full(223,1.1); HALF[0]=1.705
# Decimal dimensions are widened before interval use.
HALFI=iv(down(HALF),up(HALF)); WIDTHI=iv(down(.15),up(.15))
ELLI=iv(down(ROD_L[:,None]),up(ROD_L[:,None]))
def rectangles(p):
    c=(p[:-1]+p[1:])/2
    u=np.diff(p,axis=0)/ROD_L[:,None]
    n=np.stack((-u[:,1],u[:,0]),axis=1)
    return c,u,n

def sat_gap(c,u,n,half=HALF,width=.15,pairs=None):
    i,j=(PAIR_I,PAIR_J) if pairs is None else pairs
    axes=np.stack((u[i],n[i],u[j],n[j]),axis=1)
    d=c[j]-c[i]
    proj=abs(np.einsum('pkd,pd->pk',axes,d))
    r1=half[i,None]*abs(np.einsum('pkd,pd->pk',axes,u[i]))+width*abs(np.einsum('pkd,pd->pk',axes,n[i]))
    r2=half[j,None]*abs(np.einsum('pkd,pd->pk',axes,u[j]))+width*abs(np.einsum('pkd,pd->pk',axes,n[j]))
    return np.max(proj-r1-r2,axis=1)

def safe_interval(a,b,qa,qb):
    # All angles decrease, established by positive implicit derivative above.
    qi=iv(qb[0],qa[1]); p=positions_iv(qi)
    c=div(add((p[0][:-1],p[1][:-1]),(p[0][1:],p[1][1:])),iv(2))
    u=div(sub((p[0][1:],p[1][1:]),(p[0][:-1],p[1][:-1])),ELLI)
    n=(np.stack((-u[1][:,1],u[0][:,0]),axis=1),np.stack((-u[0][:,1],u[1][:,0]),axis=1))
    _,pm,_=solve((a+b)/2); cm,um,nm=rectangles(pm)
    axes=np.stack((um[PAIR_I],nm[PAIR_I],um[PAIR_J],nm[PAIR_J]),axis=1)
    def dot(x,idx):return isum(mul((x[0][idx,None,:],x[1][idx,None,:]),iv(axes)),2)
    d=sub((c[0][PAIR_J],c[1][PAIR_J]),(c[0][PAIR_I],c[1][PAIR_I]))
    center=absiv(isum(mul((d[0][:,None,:],d[1][:,None,:]),iv(axes)),2))
    def radius(idx):
        return add(mul((HALFI[0][idx,None],HALFI[1][idx,None]),absiv(dot(u,idx))),mul(WIDTHI,absiv(dot(n,idx))))
    gap=sub(sub(center,radius(PAIR_I)),radius(PAIR_J))
    margin=np.max(gap[0],axis=1)
    return bool(np.all(margin>0)),float(np.min(margin))

def certify_prefix(end=1.0,budget=512):
    cache={}
    def state(t):
        if t not in cache: cache[t]=enclosed_state(t)[3]
        return cache[t]
    pending=[(0.,float(end))]; safe=[]; attempted=0
    while pending:
        a,b=pending.pop(); attempted+=1
        ok,margin=safe_interval(a,b,state(a),state(b))
        if ok:safe.append({'start_s':a,'end_s':b,'minimum_gap_lower_bound_m':margin,'all_pairs':24531});continue
        if attempted>=budget or b-a<1e-7:
            return dict(status='UNKNOWN',safe_intervals=safe,first_unresolved_interval_s=[a,b],attempted=attempted)
        mid=(a+b)/2
        pending.append((mid,b));pending.append((a,mid))
    return dict(status='SAFE',safe_intervals=safe,attempted=attempted,scope_s=[0.,float(end)],method='outward_interval_fixed_axis_projection',handles_enclosed=224,pairs_per_interval=24531)

def geometry_fixtures():
    u=np.array([[1.,0.],[1.,0.]])
    n=np.array([[0.,1.],[0.,1.]])
    pairs=(np.array([0]),np.array([1])); half=np.ones(2)
    results={}
    for label,x,expected in [('separated',2.1,1),('contact',2.,0),('overlap',1.9,-1),('tiny_overlap',2.-1e-9,-1)]:
        g=float(sat_gap(np.array([[0.,0.],[x,0.]]),u,n,half,.15,pairs)[0])
        results[label]={'gap_m':g,'passed':bool(np.sign(g)==expected)}
    u[1]=[0,1]; n[1]=[-1,0]
    g=float(sat_gap(np.zeros((2,2)),u,n,half,.15,pairs)[0])
    results['crossed']={'gap_m':g,'passed':g<0}
    results['pair_policy']={'passed':len(PAIR_I)==24531 and bool(np.all(PAIR_J-PAIR_I>=2)),'pairs':int(len(PAIR_I))}
    return results

def main():
    out=Path('/work/output');times=np.array([0,1,60,120,180,240,299,300.])
    states=[solve(t) for t in times]
    q=np.stack([s[0] for s in states]);p=np.stack([s[1] for s in states]);v=np.stack([s[2] for s in states])
    gaps=[];records=[]
    for t,point in zip(times,p):
        c,u,n=rectangles(point);g=sat_gap(c,u,n);gaps.append(g);k=int(np.argmin(g))
        records.append(dict(time_s=float(t),minimum_sat_gap_m=float(g[k]),pair_zero_based=[int(PAIR_I[k]),int(PAIR_J[k])],sample_only=True))
    prefix=certify_prefix(1.,512)
    fixtures=geometry_fixtures()
    checks={'max_rod_error_m':float(np.max(abs(np.linalg.norm(np.diff(p,axis=1),axis=2)-ROD_L))),
        'max_head_speed_error_m_s':float(np.max(abs(np.linalg.norm(v[:,0],axis=1)-1))),
        'rigid_velocity_m2_s':float(np.max(abs(np.sum(np.diff(p,axis=1)*np.diff(v,axis=1),axis=2))))}
    guard_failed=False
    try: next_theta(0.,1.65,5e-14)
    except ValueError:guard_failed=True
    report=dict(scope='Q2_minimal_P1',contract_sha256=CONTRACT_SHA256,code_sha256=hashlib.sha256(Path('/work/job/solver.py').read_bytes()).hexdigest(),actual_solver_run=True,fixture=False,
        numerical_checks=checks,geometry_fixtures=fixtures,invalid_branch_rejected=guard_failed,samples=records,prefix_certificate=prefix,
        first_contact_answer_status='NOT_COMPUTED',full_contract_checks={key:'unknown' for key in CHECK_IDS},
        template_readback=read_template('/work/job/input/template.xlsx'),numerical_domain_s=[0,300],full_event_search_implemented=False,
        unresolved_tangency_policy='UNKNOWN; no subsequent interval may be promoted to first contact')
    passed=checks['max_rod_error_m']<1e-8 and checks['max_head_speed_error_m_s']<1e-9 and checks['rigid_velocity_m2_s']<1e-8 and all(x['passed'] for x in fixtures.values()) and guard_failed and prefix['status']=='SAFE'
    report['minimal_self_checks_passed']=bool(passed)
    (out/'checks.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
    if not passed:print(json.dumps(report));raise SystemExit(1)
    np.savez_compressed(out/'minimal.npz',time_s=times,theta_rad=q,position_m=p,velocity_m_s=v,speed_m_s=np.linalg.norm(v,axis=2),pair_i=PAIR_I,pair_j=PAIR_J)
    for k in range(2):np.savez_compressed(out/f'sat-gap-{k}.npz',sat_gap_m=np.stack(gaps)[4*k:4*k+4])
    print('Q2 minimal solver: eight states, 24531 pairs, continuous prefix [0,1]')
if __name__=='__main__':main()
