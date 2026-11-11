"""Q2-specific admission of an actual continuous-collision result and independent P2."""
from pathlib import Path
import json,uuid
import numpy as np
from openpyxl import load_workbook
from .config import ROOT
from .contracts import digest
from .collaboration import CollaborationStore,Receipt,Snapshot,Ticket,sha_file
from .modeling_hand import assert_m1
from .mathematics import assert_gate_binding

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def verify_q2_frozen_files(folder):
    folder=Path(folder).resolve()
    if folder.parent!=(ROOT/'stage-d/runs/full').resolve() or folder.is_symlink():raise ValueError('Q2 full run outside workspace')
    manifest=read(folder/'frozen-artifacts.json');paths=[];seen=set()
    for item in manifest['artifacts']:
        relative=item['path'];p=(ROOT/relative)
        if relative in seen or p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(folder) or not p.is_file():raise ValueError('invalid Q2 frozen file')
        seen.add(relative)
        if p.stat().st_size!=item['size_bytes'] or sha_file(p)!=item['sha256']:raise ValueError('Q2 frozen artifact changed: '+relative)
        paths.append(p)
    must={'full-base.py','contract.json','inputs.json','code-evidence.json','execution-evidence.json','result-evidence.json','validation.json','reproduction.json','support-certificate.json','figures.json','results/terminal-state.npz','results/result2.xlsx','results/continuous-certificate.npz','results/selected-handles.json','collision-event.json'}
    if not must<={p.relative_to(folder).as_posix() for p in paths}:raise ValueError('Q2 frozen package incomplete')
    return manifest,paths

def verify_q2_precision(folder,event,velocity,speed):
    """Bind supplemental precision evidence to real controlled output and frozen functions."""
    from scripts.validate_q2_full import artifacts
    folder=Path(folder);sub=folder/'precision-supplement'
    report=read(folder/'precision-supplement.json');raw=artifacts(folder,'precision-supplement')
    if set(raw)!={'support-certificate.json'}:raise ValueError('Q2 precision outputs differ')
    c=read(raw['support-certificate.json']);receipt=read(sub/'execution.json')
    primary=folder/'part-10g-final-bound/generated_solver.py'
    prefix=primary.read_text(encoding='utf-8').split("if __name__=='__main__':full_main()")[0]
    source=(sub/'generated_solver.py').read_text(encoding='utf-8')
    if not source.startswith(prefix+'\nEVENT_TIME=') or c['source_primary_sha256']!=sha_file(primary) or c['code_sha256']!=receipt['code_sha256']:raise ValueError('Q2 precision source differs')
    if report['certificate']!=c or report['execution']!=receipt or report['status']!='PASS' or c['contract_sha256']!=event['contract_sha256'] or c['time_interval_s']!=event['time_interval_s']:raise ValueError('Q2 precision binding differs')
    vl=np.array(c['velocity_lower_m_s']);vu=np.array(c['velocity_upper_m_s']);sl=np.array(c['speed_lower_m_s']);su=np.array(c['speed_upper_m_s'])
    if vl.shape!=(224,2) or vu.shape!=(224,2) or sl.shape!=(224,) or su.shape!=(224,) or not all(np.isfinite(a).all() for a in [vl,vu,sl,su]):raise ValueError('Q2 precision arrays invalid')
    if not np.array_equal(np.array(c['nominal_velocity_m_s']),velocity) or not np.array_equal(np.array(c['nominal_speed_m_s']),speed) or not np.all((vl<=velocity)&(velocity<=vu)) or not np.all((sl<=speed)&(speed<=su)):raise ValueError('Q2 precision does not enclose terminal state')
    expected=np.flatnonzero(np.round(sl,6)!=np.round(su,6)).tolist()
    actual=report['rounding_disclosure']['ambiguous_speed_coordinates']
    if c['six_decimal_speed_rounding_ambiguous_handles']!=expected or [r['handle_index_zero_based'] for r in actual]!=expected:raise ValueError('Q2 speed rounding disclosure incomplete')
    for item in actual:
        i=item['handle_index_zero_based']
        if item['interval_m_s']!=[float(sl[i]),float(su[i])] or item['xlsx_cell']!='D'+str(i+2):raise ValueError('Q2 speed rounding disclosure differs')
    error=float(np.max(np.maximum(speed-sl,su-speed)))
    if error!=c['max_speed_enclosure_error_m_s'] or report['rounding_disclosure']['max_displayed_error_bound_m_s']!=5e-7+error:raise ValueError('Q2 speed uncertainty differs')
    files=[folder/'precision-supplement.json']+list(raw.values())
    files += [p for p in sub.glob('*.json')]+[sub/'generated_solver.py']
    return sorted(set(files))

def validate_q2_full_run(w,task,version,folder):
    from scripts.validate_q2_full import artifacts,gaps,PARAMETERS
    from scripts.reference_2024_a_q1 import solve
    folder=Path(folder).resolve();manifest,paths=verify_q2_frozen_files(folder);meta=read(folder/'run.json');current=w.task(task)
    if meta['task_id']!=task or meta['contract_version']!=version or current['current_version']!=version or not current['model_approved']:raise ValueError('Q2 task/model mismatch')
    durable=str(uuid.UUID(meta['durable_execution_id']))
    if manifest['durable_execution_id']!=durable or current['result_revision'] not in [meta['result_revision']-1,meta['result_revision']]:raise ValueError('Q2 stale revision')
    if current['result_revision']==meta['result_revision'] and str(current['execution_id'])!=durable:raise ValueError('Q2 another execution is current')
    contract=w.db.execute('SELECT content,sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
    if contract['sha256']!=meta['contract_sha256'] or digest(read(folder/'contract.json'))!=contract['sha256']:raise ValueError('Q2 contract mismatch')
    assert_m1(w,current);assert_gate_binding(w,current,'model')
    for item in contract['content']['inputs']:
        if sha_file(item['path'])!=item['sha256']:raise ValueError('approved Q2 input changed')
    admission=read(folder/'P2-admission.json');store=CollaborationStore(folder/'records');receipt=store.load(Receipt,admission['receipt_sha256']);snapshot=store.load(Snapshot,admission['snapshot_sha256']);ticket=store.load(Ticket,receipt.ticket_sha256)
    if ticket.gate!='P2' or receipt.status!='PASS' or store.accept_review(receipt,admission['snapshot_sha256'])!=admission['receipt_sha256']:raise ValueError('Q2 independent P2 PASS required')
    binding=snapshot.binding
    if binding.task_id!=task or binding.contract_version!=version or binding.contract_sha256!=contract['sha256'] or binding.execution_id!=folder.name or binding.result_revision!=meta['result_revision']:raise ValueError('Q2 P2 binding mismatch')
    if manifest['binding']!=binding.model_dump(mode='json'):raise ValueError('Q2 frozen binding differs')
    frozen=next((a for a in snapshot.artifacts if a.artifact_id=='frozen_files'),None)
    if frozen is None or frozen.sha256!=sha_file(folder/'frozen-artifacts.json'):raise ValueError('P2 did not review this frozen Q2 package')
    v=read(folder/'validation.json');event=read(folder/'collision-event.json');support=read(folder/'support-certificate.json');reproduction=read(folder/'reproduction.json');figures=read(folder/'figures.json')
    if not v['passed'] or any(not c['passed'] for c in v['checks'].values()) or event['status']!='FIRST_CONTACT' or event['time_interval_s'][1]-event['time_interval_s'][0]>1e-6 or event['coordinate_error_bound_m']>5e-7:raise ValueError('Q2 numerical/event validation missing')
    if support['feature_derivative_interval_m_s'][1]>=0 or not support['both_strictly_negative'] or support['lower_feature_gap_interval_m'][0]<=0 or support['upper_feature_gap_interval_m'][1]>=0:raise ValueError('Q2 finite feature not certified')
    if reproduction['status']!='PASS' or not reproduction['full_primary_prefix_and_event_replayed']:raise ValueError('Q2 full reproduction missing')
    cursor=0.
    for record in v['partition_evidence']:
        key=record['key'];files=artifacts(folder,key);r=read(files['partition-result.json'])
        if r['partition_s'][0]!=cursor:raise ValueError('Q2 partition gap')
        with np.load(files['safe-segments.npz'],allow_pickle=False) as z:segs=z['segments']
        for a,b,margin in segs:
            if a!=cursor or b<=a or margin<=0:raise ValueError('Q2 certificate gap or nonpositive margin')
            cursor=float(b)
        if r['safe_prefix_end_s']!=cursor:raise ValueError('Q2 incorrect safe end')
        if r['status']=='FIRST_CONTACT':
            if r!=event:raise ValueError('Q2 event changed')
        elif r['status']!='SAFE' or cursor!=r['partition_s'][1]:raise ValueError('Q2 unresolved earlier interval')
    if cursor!=event['first_event_enclosure_s'][0]:raise ValueError('Q2 event prefix incomplete')
    for record in reproduction['partitions']:
        one=artifacts(folder,record['primary']);two=artifacts(folder,record['reproduction'])
        if set(one)!=set(two) or any(sha_file(one[n])!=sha_file(two[n]) for n in one):raise ValueError('Q2 reproduced bytes differ')
    with np.load(folder/'results/terminal-state.npz',allow_pickle=False) as z:p=z['position_m'];vel=z['velocity_m_s'];speed=z['speed_m_s']
    _,rp,rv=solve(event['time_estimate_s'],PARAMETERS)
    if p.shape!=(224,2) or vel.shape!=(224,2) or speed.shape!=(224,) or not all(np.isfinite(a).all() for a in [p,vel,speed]) or np.max(abs(rp-p))>1e-8 or np.max(abs(rv-vel))>1e-8:raise ValueError('Q2 current reference mismatch')
    precision_artifact=next((a for a in snapshot.artifacts if a.artifact_id=='speed_precision'),None)
    if precision_artifact is None or precision_artifact.sha256!=sha_file(folder/'precision-supplement.json'):raise ValueError('P2 did not review terminal speed intervals')
    paths+=verify_q2_precision(folder,event,vel,speed)
    workbook=load_workbook(folder/'results/result2.xlsx',data_only=True);sheet=workbook[workbook.sheetnames[0]];values=np.array([[sheet.cell(k+2,c).value for c in [2,3,4]] for k in range(224)]);workbook.close()
    if np.max(abs(values-np.column_stack((p,speed))))>1e-12:raise ValueError('Q2 workbook differs')
    if figures['counts']!={'raw':3,'process':3,'result':3} or figures['candidate_count']!=9:raise ValueError('Q2 figure coverage')
    for figure in figures['figures']:
        if figure['visual_inspection']!='PASS':raise ValueError('Q2 figure QA incomplete')
        for item in figure['files']:
            if sha_file(folder/item['path'])!=item['sha256']:raise ValueError('Q2 figure changed')
    result={'passed':True,'review_kind':'d4_P2_review','execution_id':durable,'logical_execution_id':folder.name,'result_revision':meta['result_revision'],'source_run':folder.relative_to(ROOT).as_posix(),'P2_receipt_sha256':admission['receipt_sha256'],'P2_snapshot_sha256':admission['snapshot_sha256'],'frozen_manifest_sha256':sha_file(folder/'frozen-artifacts.json'),'full_contract_checks':len(contract['content']['checks']),'independent_numeric_checks':v['checks'],'figure_counts':figures['counts'],'user_confirmation':'pending','figure_selection':'pending','collision_validation':True,'time_interval_s':event['time_interval_s']}
    paths += [folder/'frozen-artifacts.json',folder/'P2-admission.json',folder/'P2-response.json',folder/'P2-dispatch.json',folder/'P2-provider-call.json']
    paths += [ROOT/a.path for a in snapshot.artifacts]
    paths+=list((folder/'review-final').rglob('*.json'))
    paths+=list((folder/'review-final').rglob('*.md'))
    paths+=list((folder/'records').rglob('*.json'))
    registered=[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha_file(p),'role':'Q2_frozen_full_result_evidence'} for p in sorted(set(paths))]
    return result,registered
