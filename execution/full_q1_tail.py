# D4 wrapper; concatenated after the unchanged, P1-reviewed Q1 numerical core.

def main():
    out = Path('/work/output')
    code_hash = hashlib.sha256(Path('/work/job/solver.py').read_bytes()).hexdigest()
    times = np.arange(301, dtype=float)
    solved = [solve(float(t)) for t in times]
    theta = np.stack([s[0] for s in solved])
    pos = np.stack([s[1] for s in solved])
    vel = np.stack([s[2] for s in solved])
    speed = np.linalg.norm(vel, axis=2)
    arrays = dict(time_s=times, theta_rad=theta, position_m=pos,
                  velocity_m_s=vel, speed_m_s=speed)
    if not all(np.all(np.isfinite(a)) for a in arrays.values()):
        raise ValueError('Nonfinite full result')
    rods = np.diff(pos, axis=1)
    denominators = np.sum(rods*tau(theta)[:, 1:], axis=2)
    delta = np.diff(theta, axis=1)
    radius = B*theta[:, :-1]
    residual = (B*delta)**2+4*radius*(radius+B*delta)*np.sin(delta/2)**2-ROD_L**2
    measures = {
        'max_rod_distance_error_m': float(np.max(np.abs(np.linalg.norm(rods, axis=2)-ROD_L))),
        'max_chord_squared_error_m2': float(np.max(np.abs(residual))),
        'max_head_speed_error_m_s': float(np.max(np.abs(speed[:, 0]-1))),
        'max_rigid_velocity_error_m2_s': float(np.max(np.abs(np.sum(rods*np.diff(vel,axis=1),axis=2)))),
        'minimum_abs_denominator_m2': float(np.min(np.abs(denominators))),
        'minimum_denominator_index': [int(i) for i in np.unravel_index(np.argmin(np.abs(denominators)),denominators.shape)],
        'theta_chain_increasing': bool(np.all(delta>0)),
        'theta_time_decreasing': bool(np.all(np.diff(theta,axis=0)<0)),
    }
    fd = {}
    for h in [.01, .001, .0001]:
        interior = []; endpoints = []
        for t in [1,60,120,180,240,299]:
            derivative = (solve(t+h)[1]-solve(t-h)[1])/(2*h)
            interior.append(float(np.max(np.linalg.norm(derivative-vel[t],axis=1))))
        for t,d in [(0,1),(300,-1)]:
            derivative = d*(-3*pos[t]+4*solve(t+d*h)[1]-solve(t+2*d*h)[1])/(2*h)
            endpoints.append(float(np.max(np.linalg.norm(derivative-vel[t],axis=1))))
        fd[str(h)] = dict(interior_max_m_s=max(interior),endpoint_max_m_s=max(endpoints))
    refined = []
    for t in [0,60,120,180,240,300]:
        q,p,v = solve(t,xtol=5e-15)
        refined.append(dict(time_s=t,xtol=5e-15,
            max_position_difference_m=float(np.max(np.linalg.norm(p-pos[t],axis=1))),
            max_theta_difference_rad=float(np.max(np.abs(q-theta[t]))),
            max_velocity_difference_m_s=float(np.max(np.abs(v-vel[t])))))
    integration = []
    for t in range(301):
        val,err = quad(lambda u:B*math.hypot(u,1),theta[t,0],THETA_INIT,epsabs=1e-10,epsrel=1e-12)
        integration.append(dict(time_s=t,abs_error_m=float(abs(val-t)),estimated_error_m=float(err)))
    report = dict(scope='D4_full_numerical_run',contract_sha256=CONTRACT_SHA256,code_sha256=code_hash,
        actual_solver_run=True,fixture=False,time_samples=301,handles=224,
        measures=measures,finite_difference=fd,root_refinement=refined,
        head_arc_quadrature=dict(epsabs=1e-10,epsrel=1e-12,records=integration),
        spreadsheet_export_status='pending_trusted_host_export',
        full_contract_checks={key:'unknown' for key in CHECK_IDS})
    limits = [measures['max_rod_distance_error_m']<=1e-8,
        measures['max_chord_squared_error_m2']<=1e-10,
        measures['max_head_speed_error_m_s']<=1e-9,
        measures['max_rigid_velocity_error_m2_s']<=1e-8,
        measures['minimum_abs_denominator_m2']>DENOM_GUARD,
        measures['theta_chain_increasing'],measures['theta_time_decreasing'],
        max(fd['0.001'].values())<=1e-5,
        max(r['max_position_difference_m'] for r in refined)<=1e-10,
        max(r['abs_error_m'] for r in integration)<=1e-8]
    report['numerical_self_checks_passed'] = bool(all(limits))
    (out/'numeric-checks.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
    if not all(limits):
        print(json.dumps(report,allow_nan=False));raise SystemExit(1)
    for i,(start,end) in enumerate([(0,100),(100,200),(200,301)]):
        np.savez_compressed(out/f'trajectory-{i}.npz',**{name:a[start:end] for name,a in arrays.items()})
    print('full Q1 numerical run completed: 301 times x 224 handles')


if __name__ == '__main__':
    main()
