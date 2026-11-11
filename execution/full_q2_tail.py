# Full Q2 extension: bounded interval search. Never execute on the host.
_sin_poly=siniv
def siniv(a):
    # Evaluate only endpoints through the audited Taylor polynomial; then add
    # any enclosed sine extrema. This avoids polynomial interval dependency.
    k=np.rint((a[0]+a[1])/(4*math.pi));r=sub(a,mul(iv(k),mul(iv(2),PI)))
    lo,hi=r
    if np.any(np.maximum(abs(lo),abs(hi))>4):return np.full_like(lo,-1.),np.full_like(hi,1.)
    left=_sin_poly(iv(lo));right=_sin_poly(iv(hi))
    lower=np.minimum(left[0],right[0]);upper=np.maximum(left[1],right[1])
    hp=div(PI,iv(2))
    upper=np.where((lo<=hp[1])&(hi>=hp[0]),1.,upper)
    lower=np.where((lo<=-hp[0])&(hi>=-hp[1]),-1.,lower)
    return np.maximum(lower,-1.),np.minimum(upper,1.)

def rect_iv(qi):
    p=positions_iv(qi)
    c=div(add((p[0][:-1],p[1][:-1]),(p[0][1:],p[1][1:])),iv(2))
    u=div(sub((p[0][1:],p[1][1:]),(p[0][:-1],p[1][:-1])),ELLI)
    n=(np.stack((-u[1][:,1],u[0][:,0]),axis=1),np.stack((-u[0][:,1],u[1][:,0]),axis=1))
    return p,c,u,n

def pair_margins(qi,point,pairs=None,variable_axes=False):
    p,c,u,n=rect_iv(qi);i,j=(PAIR_I,PAIR_J) if pairs is None else pairs
    # Conservative AABB separation, including full board extensions.
    radius=add(mul((HALFI[0][:,None],HALFI[1][:,None]),absiv(u)),mul(WIDTHI,absiv(n)))
    boxlo=sub(c,radius)[0];boxhi=add(c,radius)[1]
    aabb=np.maximum(down(boxlo[j]-boxhi[i]),down(boxlo[i]-boxhi[j]))
    broad=np.max(aabb,axis=1)
    if variable_axes:remaining=np.ones(len(i),dtype=bool)
    else:remaining=broad<=0
    low=broad.copy();high=np.full_like(low,np.inf)
    if not np.any(remaining):return low,high
    ri=i[remaining];rj=j[remaining]
    if variable_axes:
        axes=(np.stack((u[0][ri],n[0][ri],u[0][rj],n[0][rj]),axis=1),np.stack((u[1][ri],n[1][ri],u[1][rj],n[1][rj]),axis=1))
    else:
        _,um,nm=rectangles(point);axes=iv(np.stack((um[ri],nm[ri],um[rj],nm[rj]),axis=1))
    def dot(x,idx):return isum(mul((x[0][idx,None,:],x[1][idx,None,:]),axes),2)
    d=sub((c[0][rj],c[1][rj]),(c[0][ri],c[1][ri]))
    center=absiv(isum(mul((d[0][:,None,:],d[1][:,None,:]),axes),2))
    def radius_at(idx):return add(mul((HALFI[0][idx,None],HALFI[1][idx,None]),absiv(dot(u,idx))),mul(WIDTHI,absiv(dot(n,idx))))
    gap=sub(sub(center,radius_at(ri)),radius_at(rj))
    low[remaining]=np.max(gap[0],axis=1);high[remaining]=np.max(gap[1],axis=1)
    return low,high

def velocity_iv(qi):
    si=siniv(qi);co=cosiv(qi)
    tx=mul(BI,sub(co,mul(qi,si)));ty=mul(BI,add(si,mul(qi,co)))
    tangent=(np.stack((tx[0],ty[0]),axis=1),np.stack((tx[1],ty[1]),axis=1))
    p=positions_iv(qi);rod=sub((p[0][1:],p[1][1:]),(p[0][:-1],p[1][:-1]))
    D=isum(mul(rod,(tangent[0][1:],tangent[1][1:])),1)
    numerator=isum(mul(rod,(tangent[0][:-1],tangent[1][:-1])),1)
    if np.any(D[0]<=1e-10):raise ValueError('velocity denominator not interval-certified')
    omega=[neg(div(iv(1),mul(BI,sqrtiv(add(iv(1),sqr(iv(qi[0][0],qi[1][0])))))))]
    for k in range(223):omega.append(mul(omega[-1],div(iv(numerator[0][k],numerator[1][k]),iv(D[0][k],D[1][k]))))
    om=(np.array([o[0] for o in omega]),np.array([o[1] for o in omega]))
    return mul(tangent,(om[0][:,None],om[1][:,None])),float(np.min(D[0]))

def feature_spec(t,pair):
    _,p,_=solve(t);c,u,n=rectangles(p);i,j=pair
    axes=np.array([u[i],n[i],u[j],n[j]])
    d=c[j]-c[i]
    g=abs(axes@d)-HALF[i]*abs(axes@u[i])-.15*abs(axes@n[i])-HALF[j]*abs(axes@u[j])-.15*abs(axes@n[j])
    k=int(np.argmax(g));base=i if k<2 else j;other=j if k<2 else i;kind=k%2
    ax=(u if kind==0 else n)[base];sgn=1 if np.dot(c[other]-c[base],ax)>0 else -1
    direction=sgn*ax
    su=-1 if np.dot(u[other],direction)>0 else 1
    sn=-1 if np.dot(n[other],direction)>0 else 1
    return dict(base=int(base),other=int(other),axis_kind=kind,normal_sign=sgn,corner_u_sign=su,corner_n_sign=sn,axis_index=k)

def feature_interval(qi,spec,derivative=False):
    p,c,u,n=rect_iv(qi);b=spec['base'];o=spec['other'];kind=spec['axis_kind'];sgn=spec['normal_sign'];su=spec['corner_u_sign'];sn=spec['corner_n_sign']
    def at(x,k):return iv(x[0][k],x[1][k])
    axis=mul(iv(sgn),at(u if kind==0 else n,b))
    corner=add(at(c,o),add(mul(iv(su),mul(iv(HALFI[0][o],HALFI[1][o]),at(u,o))),mul(iv(sn),mul(WIDTHI,at(n,o)))))
    diff=sub(corner,at(c,b));radius=iv(HALFI[0][b],HALFI[1][b]) if kind==0 else WIDTHI
    gap=sub(isum(mul(axis,diff),0),radius)
    if not derivative:return gap,corner,axis
    v,mind=velocity_iv(qi)
    cv=div(add((v[0][:-1],v[1][:-1]),(v[0][1:],v[1][1:])),iv(2))
    uv=div(sub((v[0][1:],v[1][1:]),(v[0][:-1],v[1][:-1])),ELLI)
    nv=(np.stack((-uv[1][:,1],uv[0][:,0]),axis=1),np.stack((-uv[0][:,1],uv[1][:,0]),axis=1))
    av=mul(iv(sgn),at(uv if kind==0 else nv,b))
    corner_v=add(at(cv,o),add(mul(iv(su),mul(iv(HALFI[0][o],HALFI[1][o]),at(uv,o))),mul(iv(sn),mul(WIDTHI,at(nv,o)))))
    derivative=add(isum(mul(av,diff),0),isum(mul(axis,sub(corner_v,at(cv,b))),0))
    # Finite-edge witness, rather than only intersection with its infinite line.
    tangent=at(n if kind==0 else u,b)
    tangent_coord=isum(mul(tangent,diff),0)
    edge_half=WIDTHI if kind==0 else iv(HALFI[0][b],HALFI[1][b])
    return gap,derivative,tangent_coord,edge_half,mind

def attempt_event(a,b,state):
    qa,pa,va,ia=state(a);qb,pb,vb,ib=state(b)
    c,u,n=rectangles(pb);g=sat_gap(c,u,n);k=int(np.argmin(g));pair=(int(PAIR_I[k]),int(PAIR_J[k]))
    tiny=(np.array([pair[0]]),np.array([pair[1]]))
    _,upper=pair_margins(ib,pb,tiny,True)
    if upper[0]>=0:return None
    qi=iv(ib[0],ia[1]);mid=(a+b)/2;_,pm,_=solve(mid)
    lower,_=pair_margins(qi,pm)
    others=np.arange(24531)!=k
    if np.any(lower[others]<=0):return None
    spec=feature_spec(mid,pair)
    fa=feature_interval(ia,spec)[0];fb=feature_interval(ib,spec)[0]
    if fa[0]<=0 or fb[1]>=0:return None
    fg,df,tc,eh,mind=feature_interval(qi,spec,True)
    if df[1]>=0 or max(abs(float(tc[0])),abs(float(tc[1])))>=eh[0]:return None
    # Enclosure refinement is feature-specific, with all earlier time certified.
    left,right=a,b
    for unused in range(40):
        if right-left<2e-9:break
        m=(left+right)/2;value=feature_interval(state(m)[3],spec)[0]
        if value[0]>0:left=m
        elif value[1]<0:right=m
        else:break
    def feature_float(t):
        _,p,_=solve(t);c,u,n=rectangles(p);bb=spec['base'];oo=spec['other'];ax=spec['normal_sign']*(u if spec['axis_kind']==0 else n)[bb]
        corner=c[oo]+spec['corner_u_sign']*HALF[oo]*u[oo]+spec['corner_n_sign']*.15*n[oo]
        return float(np.dot(ax,corner-c[bb])-(HALF[bb] if spec['axis_kind']==0 else .15))
    tau=float(brentq(feature_float,left,right,xtol=5e-14,rtol=4*np.finfo(float).eps))
    qi=iv(state(right)[3][0],state(left)[3][1]);piv=positions_iv(qi);q,p,v=solve(tau)
    error=float(np.max(np.maximum(abs(p-piv[0]),abs(piv[1]-p))))
    if right-left>1e-6 or error>5e-7:return None
    gap,corner,normal=feature_interval(qi,spec)
    _,denom=velocity_iv(qi)
    if max(abs(float(gap[0])),abs(float(gap[1])))>1e-8:return None
    return dict(status='FIRST_CONTACT',time_interval_s=[left,right],time_estimate_s=tau,active_board_pairs=[list(pair)],index_base=0,
        first_event_enclosure_s=[a,b],unique_contact_feature=spec,feature_derivative_m_s=[float(df[0]),float(df[1])],feature_gap_interval_m=[float(gap[0]),float(gap[1])],
        contact_point_interval_m=[corner[0].tolist(),corner[1].tolist()],normal_interval=[normal[0].tolist(),normal[1].tolist()],
        all_other_pairs_separated_over_event_enclosure=True,other_pairs_min_gap_lower_bound_m=float(np.min(lower[others])),
        coordinate_error_bound_m=error,minimum_velocity_denominator_lower_bound_m2=denom,
        left_limit_velocity=True,adjacent_pair_policy='whole adjacent pair exempt',hole_policy='filled full rectangle',isolated_tangency_policy='all earlier intervals certified; unresolved cases UNKNOWN',
        local_safe_extension_s=[a,left],terminal_rounding='six decimal formatting; enclosure bound retained')

def solve_partition(start,end):
    proof=branch_domain_certificate();cache={};safe=[];attempts=0
    def state(t):
        if t not in cache:cache[t]=enclosed_state(t)
        return cache[t]
    initial=state(start);initial_low,_=pair_margins(initial[3],initial[1])
    if np.min(initial_low)<=0:
        return dict(status='UNKNOWN',reason='partition start not certified separated',first_unresolved_interval_s=[start,start],proof=proof),safe,cache
    stack=[(start,end)]
    while stack:
        a,b=stack.pop();attempts+=1
        if attempts>20000:return dict(status='UNKNOWN',reason='partition budget exhausted',first_unresolved_interval_s=[a,b],proof=proof),safe,cache
        sa=state(a);sb=state(b);qi=iv(sb[3][0],sa[3][1])
        if b-a>1.:
            stack.extend(left_children(a,b));continue
        lower,_=pair_margins(qi,solve((a+b)/2)[1])
        if np.all(lower>0):safe.append((a,b,float(np.min(lower))));continue
        if b-a<2e-7:
            probe=min(end,a+4e-7)
            event=attempt_event(a,probe,state)
            if event is not None:
                event.update(proof=proof,attempted_intervals=attempts,partition_s=[start,end],safe_prefix_end_s=a)
                return event,safe,cache
            if b-a<2e-10:return dict(status='UNKNOWN',reason='earliest interval unresolved; tangency/precision',first_unresolved_interval_s=[a,b],proof=proof),safe,cache
        stack.extend(left_children(a,b))
    return dict(status='SAFE',partition_s=[start,end],proof=proof,attempted_intervals=attempts,safe_prefix_end_s=end),safe,cache

def full_main():
    out=Path('/work/output');report,segments,cache=solve_partition(PART_START,PART_END)
    report.update(contract_sha256=CONTRACT_SHA256,code_sha256=hashlib.sha256(Path('/work/job/solver.py').read_bytes()).hexdigest(),actual_solver_run=True,fixture=False,eligible_pairs=24531,handles=224)
    np.savez_compressed(out/'safe-segments.npz',segments=np.asarray(segments,dtype=float).reshape(-1,3))
    if report['status']=='FIRST_CONTACT':
        t=report['time_estimate_s'];q,p,v=solve(t);qi=iv(enclosed_state(report['time_interval_s'][1])[3][0],enclosed_state(report['time_interval_s'][0])[3][1]);pp=positions_iv(qi)
        np.savez_compressed(out/'terminal-state.npz',theta_rad=q,position_m=p,velocity_m_s=v,speed_m_s=np.linalg.norm(v,axis=1),position_lower_m=pp[0],position_upper_m=pp[1])
        points=[0.,100.,200.,300.,400.,t];states=[solve(x) for x in points]
        np.savez_compressed(out/'representative-states.npz',time_s=points,theta_rad=np.stack([s[0] for s in states]),position_m=np.stack([s[1] for s in states]),velocity_m_s=np.stack([s[2] for s in states]))
        near_t=np.linspace(t-.01,t+.01,41);pair=report['active_board_pairs'][0];vals=[]
        for x in near_t:
            c,u,n=rectangles(solve(x)[1]);vals.append(sat_gap(c,u,n,pairs=(np.array([pair[0]]),np.array([pair[1]])))[0])
        np.savez_compressed(out/'contact-profile.npz',time_s=near_t,gap_m=vals)
        report['terminal_checks']={'rod_distance_error_m':float(np.max(abs(np.linalg.norm(np.diff(p,axis=0),axis=1)-ROD_L))),'head_speed_error_m_s':float(abs(np.linalg.norm(v[0])-1)),'rigid_velocity_error_m2_s':float(np.max(abs(np.sum(np.diff(p,axis=0)*np.diff(v,axis=0),axis=1))))}
        report['full_contract_checks']={key:'unknown' for key in CHECK_IDS}
    (out/'partition-result.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
    print(json.dumps({'status':report['status'],'partition_s':[PART_START,PART_END],'safe_segments':len(segments),'attempted':report.get('attempted_intervals'),'time_interval_s':report.get('time_interval_s')},allow_nan=False),flush=True)
if __name__=='__main__':full_main()
