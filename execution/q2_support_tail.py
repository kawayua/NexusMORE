# Extra certificate generation composed with the frozen primary solver.
def supporting_corner_certificate(qi,spec):
    p,c,u,n=rect_iv(qi);bb=spec['base'];oo=spec['other']
    def at(x,k):return iv(x[0][k],x[1][k])
    axis=mul(iv(spec['normal_sign']),at(u if spec['axis_kind']==0 else n,bb))
    su=mul(iv(spec['corner_u_sign']),isum(mul(axis,at(u,oo)),0))
    sn=mul(iv(spec['corner_n_sign']),isum(mul(axis,at(n,oo)),0))
    if su[1]>=0 or sn[1]>=0:raise ValueError('corner does not remain unique supporting corner throughout event enclosure')
    return {'support_u_signed_dot_interval':[float(su[0]),float(su[1])],'support_n_signed_dot_interval':[float(sn[0]),float(sn[1])],'both_strictly_negative':True,'scope':'entire first_event_enclosure_s','proof':'chosen corner minimizes projection on base outward normal for both local axes over entire event enclosure'}

def certificate_main():
    a,b=EVENT_A,EVENT_B;lo,hi=EVENT_LO,EVENT_HI
    qa=enclosed_state(a)[3];qb=enclosed_state(b)[3];qi=iv(qb[0],qa[1])
    support=supporting_corner_certificate(qi,EVENT_SPEC)
    g,d,tc,eh,den=feature_interval(qi,EVENT_SPEC,True)
    support.update(feature_derivative_interval_m_s=[float(d[0]),float(d[1])],finite_edge_projection_interval_m=[float(tc[0]),float(tc[1])],edge_half_lower_m=float(eh[0]),denominator_lower_bound_m2=den,event_bracket_s=[lo,hi])
    if d[1]>=0 or max(abs(float(tc[0])),abs(float(tc[1])))>=eh[0]:raise ValueError('feature certificate failed')
    for key,t in [('lower',lo),('upper',hi)]:
        q,p,v,state=enclosed_state(t);g=feature_interval(state,EVENT_SPEC)[0];support[key+'_feature_gap_interval_m']=[float(g[0]),float(g[1])]
    if support['lower_feature_gap_interval_m'][0]<=0 or support['upper_feature_gap_interval_m'][1]>=0:raise ValueError('strict event endpoint signs absent')
    support['code_sha256']=hashlib.sha256(Path('/work/job/solver.py').read_bytes()).hexdigest();support['contract_sha256']=CONTRACT_SHA256
    Path('/work/output/support-certificate.json').write_text(json.dumps(support,allow_nan=False),encoding='utf-8')
    print('finite-edge support, sign and monotone crossing independently re-evaluated')
if __name__=='__main__':certificate_main()
