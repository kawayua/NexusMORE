"""One bounded, source-preserving engineering repair of the current D3 code.

The revision is explicitly Codex-authored, not misreported as fresh model output.
Independent P1 still runs in a new stateless model context after real execution.
"""
from modelcrew.project_assets import asset_path
import argparse
import uuid
from pathlib import Path
from scripts.run_d3_minimal import read,write,static_check,approved
from modelcrew.config import ROOT
from modelcrew.collaboration import Call,CollaborationStore,sha_file
from modelcrew.workflow import Workflow


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args()
    source=args.source.resolve()
    if source.parent!=(asset_path(ROOT,'stage-d/runs/coding')).resolve() or source.is_symlink():raise ValueError('Invalid source')
    previous=read(source/'run.json')
    if previous.get('attempt',1)>=3:raise ValueError('Repair budget exhausted')
    code=(source/'generated_solver.py').read_text(encoding='utf-8')
    changes=[]
    def replace(old,new,label):
        nonlocal code
        if code.count(old)!=1:raise ValueError('Unexpected source for '+label)
        code=code.replace(old,new,1);changes.append(label)
    start=code.index('def read_template(path):');end=code.index('\ndef norm_float',start)
    original=code[start:end]
    replacement='''def read_template(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    out = {}
    try:
        for name in wb.sheetnames:
            sh = wb[name]
            rows = sh.iter_rows(values_only=True)
            first_row = list(next(rows))
            first_col = [first_row[0]] + [row[0] for row in rows]
            out[name] = {"dimensions": sh.calculate_dimension(),
                         "rows": int(sh.max_row), "cols": int(sh.max_column),
                         "first_row": first_row, "first_col": first_col}
    finally:
        wb.close()
    return out

'''
    replace(original,replacement,'Use supported read-only worksheet API and bounded sequential row traversal')
    replace('def velocity(th):','def velocity(th, t):','Include actual time in denominator failure diagnostics')
    replace('node={i} t_unknown D={Di}','node={i} t={t} D={Di}','Record actual denominator failure time')
    replace('vel, _, _ = velocity(th)','vel, _, _ = velocity(th, t)','Pass actual solver time to velocity guard')
    replace('    if not (math.isfinite(t)):\n        raise ValueError("non-finite t")','    if not (math.isfinite(t) and 0.0 <= t <= T_END):\n        raise ValueError("t outside approved interval")','Reject times outside approved interval')
    replace('    fa = (arc(a) - arc(THETA_INIT)) + target  # arc(THETA_INIT)-arc(a) - target\n','', 'Remove overwritten dead bracket expression')
    start=code.index('    # arc integration\n');end=code.index('    # velocity finite difference',start)
    replace(code[start:end],'''    # Independent adaptive quadrature: actual tolerances/error estimates.
    arc_max = 0.0; arc_idx = None; arc_records = []
    for k, t in enumerate(times):
        val, error_estimate = quad(lambda u: B * math.hypot(1.0, u),
            float(theta_arr[k, 0]), THETA_INIT,
            epsabs=1e-10, epsrel=1e-12, limit=200)
        err = abs(val - V0 * t)
        if err > arc_max:
            arc_max = err; arc_idx = int(k)
        arc_records.append({"time_index": int(k), "quad_arc_m": float(val),
            "target_m": float(V0*t), "abs_err_m": float(err),
            "epsabs": 1e-10, "epsrel": 1e-12,
            "estimated_error_m": float(error_estimate),
            "method": "adaptive_quad_no_fixed_step"})

''','Remove unused fixed-step hints and record true quadrature tolerances/error estimates')
    replace('    if exit_code != 0:\n        raise SystemExit(1)','    if exit_code != 0:\n        print(json.dumps(report, ensure_ascii=True, allow_nan=False))\n        raise SystemExit(1)','Expose bounded failure diagnostics in durable executor stdout')
    replace('        print("MINIMAL P1 CHECK FAILURES: " + ", ".join(fails))','        print(json.dumps({"failed_checks": fails, "report": report}, ensure_ascii=True, allow_nan=False))','Preserve numerical failure reasons in durable executor stdout')
    static_check(code)
    with Workflow() as w,w.lock(previous['task_id']):
        approved(w,previous['task_id'],previous['contract_version'],previous['contract_sha256'])
        folder=asset_path(ROOT,'stage-d/runs/coding')/('minimal-'+uuid.uuid4().hex);folder.mkdir(parents=True)
        store=CollaborationStore(folder/'records');priorstore=CollaborationStore(source/'records')
        # Copy immutable records by their schema, preserving all author identities.
        import shutil
        shutil.copytree(source/'records',folder/'records',dirs_exist_ok=True)
        prior=priorstore.call(previous['author']['call_id'])
        editor=Call(call_id=str(uuid.uuid4()),context_id='codex-primary-engineering-'+uuid.uuid4().hex,role='coding',binding=prior.binding)
        store.register_call(editor)
        for name in ['contract.json','mathematics.json','inputs.json','handoff.json','handoff-inputs.json']:
            if (source/name).exists():shutil.copyfile(source/name,folder/name)
        (folder/'generated_solver.py').write_text(code,encoding='utf-8')
        notes={'source_run':previous['folder'],'source_code_sha256':sha_file(source/'generated_solver.py'),
               'revised_code_sha256':sha_file(folder/'generated_solver.py'),'changes':changes,
               'author':'Codex engineering revision in coding-hand role','new_model_generation_calls':0,
               'source_llm_authorship_retained':True,'not_independent_P1':True}
        write(folder/'repair.json',notes)
        meta={**previous,'folder':folder.relative_to(ROOT).as_posix(),'previous_run':previous['folder'],
              'attempt':previous.get('attempt',1)+1,'author':editor.model_dump(mode='json'),
              'prior_author_ids':previous.get('prior_author_ids',[])+[prior.call_id],
              'status':'generated','code_sha256':sha_file(folder/'generated_solver.py'),
              'implementation_revision':notes,'new_generation_call':False}
        for key in ['model_call','mcp_trace_id','job_sha256']:meta.pop(key,None)
        write(folder/'run.json',meta)
        write(folder/'code-evidence.json',{'code':code,'code_sha256':meta['code_sha256'],'preflight':static_check(code),'implementation_notes':notes})
        write(folder/'preflight.json',static_check(code))
        w.record_entry(meta['task_id'],version=meta['contract_version'],kind='code',actor='coding-hand-codex-engineer',request_id=folder.name+'-repair',text='保留失败代码与回执；修复只读模板API和诊断，模型与契约未变。',artifacts=[{'path':meta['folder']+'/generated_solver.py','sha256':meta['code_sha256'],'role':'minimal_solver_code'}],metadata=notes)
        print(str(folder))


if __name__=='__main__':main()
