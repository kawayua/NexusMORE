# Algebraically equivalent, tighter interval angular-rate recurrence.
def velocity_iv(qi):
    si=siniv(qi);co=cosiv(qi)
    tx=mul(BI,sub(co,mul(qi,si)));ty=mul(BI,add(si,mul(qi,co)))
    tangent=(np.stack((tx[0],ty[0]),axis=1),np.stack((tx[1],ty[1]),axis=1))
    prev=iv(qi[0][:-1],qi[1][:-1]);nxt=iv(qi[0][1:],qi[1][1:]);delta=sub(nxt,prev)
    if np.any(delta[0]<=0) or np.any(delta[1]>=float(PI[0]/2)):raise ValueError('interval branch lost')
    r=mul(BI,prev);bd=mul(BI,delta);one_minus_cos=sub(iv(1),cosiv(delta))
    D=add(add(mul(sqr(BI),delta),mul(mul(BI,r),one_minus_cos)),mul(mul(r,add(r,bd)),siniv(delta)))
    difference=mul(one_minus_cos,add(mul(sqr(BI),delta),mul(iv(2),mul(BI,r))))
    ratio=sub(iv(1),div(difference,D))
    # Intersect with the independently established open-unit implicit map bound.
    ratio=(np.maximum(ratio[0],0),np.minimum(ratio[1],1))
    if np.any(D[0]<=1e-10) or np.any(ratio[0]>ratio[1]):raise ValueError('analytic rate interval failed')
    head=neg(div(iv(1),mul(BI,sqrtiv(add(iv(1),sqr(iv(qi[0][0],qi[1][0])))))))
    omega=[head]
    for k in range(223):omega.append(mul(omega[-1],iv(ratio[0][k],ratio[1][k])))
    om=(np.array([o[0] for o in omega]),np.array([o[1] for o in omega]))
    return mul(tangent,(om[0][:,None],om[1][:,None])),float(np.min(D[0]))
