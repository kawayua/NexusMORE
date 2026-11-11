"""D4 frozen-result admission. Independent P2 and exact file bytes are mandatory."""
from pathlib import Path
import json,uuid
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.collaboration import CollaborationStore,Receipt,Snapshot,Ticket,sha_file
from modelcrew.full_numerics import load_arrays,numeric_checks,workbook_checks
from modelcrew.modeling_hand import assert_m1
from modelcrew.mathematics import assert_gate_binding


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_frozen_files(folder):
    folder=Path(folder).resolve()
    if folder.parent!=(ROOT/'stage-d/runs/full').resolve() or folder.is_symlink():raise ValueError('Full run outside intended workspace')
    manifest=read(folder/'frozen-artifacts.json')
    paths=[];seen=set()
    for item in manifest['artifacts']:
        relative=item['path'];p=ROOT/relative
        if relative in seen or p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(folder) or not p.is_file():raise ValueError('Invalid frozen artifact')
        seen.add(relative)
        if p.stat().st_size!=item['size_bytes'] or sha_file(p)!=item['sha256']:raise ValueError('Frozen full-result artifact changed: '+relative)
        paths.append(p)
    must={'contract.json','generated_solver.py','numerical-core.py','output/trajectories.npz','output/result1.xlsx','output/checks.json','independent-numerics.json','figure-manifest.json','figure-qa.json','visual-review.json','reproduction.json','fault-probes.json'}
    if not must<={p.relative_to(folder).as_posix() for p in paths}:raise ValueError('Frozen full-result package incomplete')
    return manifest,paths


def validate_full_run(w,task,version,folder):
    candidate=Path(folder).resolve()
    if candidate.parent==(ROOT/'stage-d/runs/full').resolve() and (candidate/'contract.json').is_file():
        problem=read(candidate/'contract.json').get('problem',{})
        if problem.get('case_id')=='CUMCM2024A' and problem.get('subproblem_id')=='Q2':
            from .q2_full_result import validate_q2_full_run
            return validate_q2_full_run(w,task,version,candidate)
    from scripts.run_d4_full import merge_arrays,read_execution
    folder=Path(folder).resolve();manifest,paths=verify_frozen_files(folder)
    meta=read(folder/'run.json');current=w.task(task)
    if (meta['task_id']!=task or meta['contract_version']!=version or current['current_version']!=version or not current['model_approved']):raise ValueError('Full result task/version/current model approval mismatch')
    uuid.UUID(meta['execution_id'])
    if current['result_revision'] not in [meta['result_revision']-1,meta['result_revision']]:raise ValueError('Full result revision is stale')
    if current['result_revision']==meta['result_revision'] and str(current['execution_id'])!=meta['execution_id']:raise ValueError('Full result belongs to another execution')
    contract=w.db.execute('SELECT content,sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
    if meta['contract_sha256']!=contract['sha256'] or digest(read(folder/'contract.json'))!=contract['sha256']:raise ValueError('Full result contract binding mismatch')
    if manifest['binding']!={'task_id':task,'contract_version':version,'contract_sha256':contract['sha256'],'execution_id':meta['execution_id'],'result_revision':meta['result_revision']}:raise ValueError('Frozen manifest binding mismatch')
    assert_m1(w,current);assert_gate_binding(w,current,'model')
    for item in contract['content']['inputs']:
        if sha_file(item['path'])!=item['sha256']:raise ValueError('Approved input changed')
    source=ROOT/meta['parent_run'];parent=read(source/'run.json');admission=read(source/'P1-admission.json')
    origin=CollaborationStore(source/'records');old=origin.load(Receipt,admission['receipt_sha256'])
    if old.status!='PASS' or origin.accept_review(old,admission['snapshot_sha256'])!=meta['parent_P1_receipt_sha256']:raise ValueError('Parent independent P1 no longer valid')
    core=(source/'generated_solver.py').read_text(encoding='utf-8').split('def run_checks():',1)[0]
    if (folder/'numerical-core.py').read_text(encoding='utf-8')!=core or sha_file(folder/'numerical-core.py')!=meta['core_sha256'] or not (folder/'generated_solver.py').read_text(encoding='utf-8').startswith(core):raise ValueError('P1 numerical core changed')
    primary,report=merge_arrays(folder,'primary');replica,_=merge_arrays(folder,'reproduction');stored=load_arrays(folder/'output/trajectories.npz')
    import numpy as np
    if any(not np.array_equal(primary[k],replica[k]) or not np.array_equal(primary[k],stored[k]) for k in primary):raise ValueError('Full reproduction/merged data differ')
    for key in ['guard-probe','bracket-probe']:read_execution(folder,key)
    numeric=numeric_checks(stored,contract['content'],report)
    template=next(i for i in contract['content']['inputs'] if i['role']=='required_output_template')
    workbook=workbook_checks(folder/'output/result1.xlsx',stored,template)
    if not numeric['passed'] or not workbook['passed']:raise ValueError('Current full numerical/workbook recomputation failed')
    aggregate=read(folder/'output/checks.json')
    if aggregate.get('contract_sha256')!=contract['sha256'] or aggregate.get('code_sha256')!=meta['code_sha256'] or sha_file(folder/'generated_solver.py')!=meta['code_sha256']:raise ValueError('Full check/code binding mismatch')
    if set(aggregate['checks'])!={c['id'] for c in contract['content']['checks']} or any(v.get('status')!='passed' or not v.get('evidence') for v in aggregate['checks'].values()):raise ValueError('Full contract check coverage incomplete')
    figures=read(folder/'figure-manifest.json');policy=read(folder/'sources/2-chinese-modeling-policy.json')
    if figures['logical_count']<policy['figures']['minimum_candidates'] or any(figures['counts'].get(c,0)<policy['figures']['minimum_per_category'] for c in policy['figures']['categories']):raise ValueError('Candidate figure policy not met')
    for figure in figures['figures']:
        for fmt,path in figure['files'].items():
            if path not in {p.relative_to(ROOT).as_posix() for p in paths} or sha_file(ROOT/path)!=figure['file_hashes'][fmt]:raise ValueError('Figure file changed or not frozen')
    if not read(folder/'figure-qa.json')['passed'] or not read(folder/'visual-review.json')['passed']:raise ValueError('Figure QA incomplete')
    admission=read(folder/'P2-admission.json');store=CollaborationStore(folder/'records');receipt=store.load(Receipt,admission['receipt_sha256'])
    snapshot=store.load(Snapshot,admission['snapshot_sha256']);ticket=store.load(Ticket,receipt.ticket_sha256)
    if ticket.gate!='P2' or receipt.status!='PASS' or store.accept_review(receipt,admission['snapshot_sha256'])!=admission['receipt_sha256']:raise ValueError('Independent P2 PASS required')
    binding=snapshot.binding
    if binding.task_id!=task or binding.contract_version!=version or binding.contract_sha256!=contract['sha256'] or binding.execution_id!=meta['execution_id'] or binding.result_revision!=meta['result_revision']:raise ValueError('P2 binding mismatch')
    frozen=next((a for a in snapshot.artifacts if a.artifact_id=='frozen_files'),None)
    if frozen is None or frozen.sha256!=sha_file(folder/'frozen-artifacts.json'):raise ValueError('P2 did not review this frozen package')
    result={'passed':True,'review_kind':'d4_P2_review','execution_id':meta['execution_id'],'result_revision':meta['result_revision'],
        'source_run':folder.relative_to(ROOT).as_posix(),'P2_receipt_sha256':admission['receipt_sha256'],'P2_snapshot_sha256':admission['snapshot_sha256'],
        'frozen_manifest_sha256':sha_file(folder/'frozen-artifacts.json'),'full_contract_checks':len(aggregate['checks']),
        'independent_numeric_checks':numeric['checks'],'workbook':workbook,'figure_counts':figures['counts'],
        'user_confirmation':'pending','figure_selection':'pending','not_collision_validation':True}
    paths += [folder/'frozen-artifacts.json',folder/'P2-admission.json',folder/'P2-dispatch.json',folder/'P2-response.json']
    paths += list((folder/'records').rglob('*.json'))
    artifacts=[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha_file(p),'role':'D4_frozen_full_result_evidence'} for p in sorted(set(paths))]
    return result,artifacts
