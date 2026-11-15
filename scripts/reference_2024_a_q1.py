"""Deterministic, human-authored reference for CUMCM 2024 A, problem 1.

No network, subprocesses, or generated code execution. Reads a fixed case and
Excel template, writes only to stage-a/2024-A-problem-1/runs/<run_id>.
"""
from __future__ import annotations
from modelcrew.project_assets import asset_path
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
import time
import traceback
import numpy as np
from scipy.optimize import brentq
from scipy.integrate import quad
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
CASE = asset_path(ROOT,'stage-a') / '2024-A-problem-1'


def arc(theta: float, b: float) -> float:
    return b / 2 * (theta * math.hypot(theta, 1) + math.asinh(theta))


def solve(t: float, p: dict, xtol: float = 5e-14):
    b = p['pitch_m'] / (2 * math.pi)
    initial = p['initial_turns'] * 2 * math.pi
    remaining = arc(initial, b) - t * p['head_speed_m_s']
    if remaining <= 0:
        raise ValueError('Requested time reaches the spiral origin')
    theta = np.empty(p['handle_count'])
    theta[0] = brentq(lambda q: arc(q, b) - remaining, 0, initial + 1, xtol=xtol)
    distances = np.full(len(theta) - 1, p['other_handle_distance_m'])
    distances[0] = p['head_handle_distance_m']
    for i, distance in enumerate(distances, 1):
        previous = theta[i-1]
        r = b * previous
        # Stable squared chord: (r2-r1)^2 + 4*r1*r2*sin(delta/2)^2.
        def residual(delta):
            return (b*delta)**2 + 4*r*(r+b*delta)*math.sin(delta/2)**2 - distance**2
        # Strictly increasing chord on delta in (0, pi) for positive radii.
        # Thus this bracket certifies the first outward root, with no jump turn.
        if residual(math.pi) <= 0:
            raise ValueError('First-root bracket cannot be certified')
        delta = brentq(residual, 0, math.pi, xtol=xtol)
        theta[i] = previous + delta
    c, s = np.cos(theta), np.sin(theta)
    xy = b * theta[:, None] * np.column_stack((c, s))
    tangent = b * np.column_stack((c-theta*s, s+theta*c))
    omega = np.empty(len(theta))
    omega[0] = -p['head_speed_m_s'] / np.linalg.norm(tangent[0])
    for i in range(1, len(theta)):
        rod = xy[i] - xy[i-1]
        denominator = rod @ tangent[i]
        if abs(denominator) < 1e-10:
            raise ArithmeticError('Near-singular velocity constraint')
        omega[i] = (rod @ tangent[i-1]) / denominator * omega[i-1]
    velocity = tangent * omega[:, None]
    return theta, xy, velocity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', type=Path, default=Path(r'D:\big-third-up\A题\附件\result1.xlsx'))
    args = parser.parse_args()
    p = json.loads((CASE/'parameters.json').read_text(encoding='utf-8'))
    manifest = json.loads((CASE/'input-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        if item['used_in_stage_a']:
            actual = hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
            if actual.lower() != item['sha256'].lower():
                raise ValueError(f"Input changed: {item['path']}")
    expected_template = next(x for x in manifest['files'] if x['role']=='required_output_template')
    if hashlib.sha256(args.template.read_bytes()).hexdigest().lower() != expected_template['sha256'].lower():
        raise ValueError('Template does not match frozen manifest')
    run_id = datetime.now(timezone.utc).strftime('reference-%Y%m%dT%H%M%S%fZ')
    out = CASE/'runs'/run_id
    out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    metadata = {'run_id': run_id, 'run_type': 'human_authored_reference', 'llm_calls': 0,
                'execution': 'reviewed deterministic local program; not a sandbox isolation test',
                'python': platform.python_version(), 'dependencies': {k:importlib.metadata.version(k) for k in ['numpy','scipy','openpyxl']},
                'command': [sys.executable, str(Path(__file__).resolve()), '--template', str(args.template)],
                'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'status':'running'}
    for name in ['parameters.json','input-manifest.json','scope.md','acceptance-checklist.md']:
        (out/name).write_bytes((CASE/name).read_bytes())
    (out/'reference_solver.py').write_bytes(Path(__file__).read_bytes())
    try:
        times = np.arange(p['time_start_s'],p['time_end_s']+1,p['time_step_s'])
        solutions = [solve(float(t),p) for t in times]
        angles = np.stack([x[0] for x in solutions])
        pos = np.stack([x[1] for x in solutions])
        vel = np.stack([x[2] for x in solutions])
        speed = np.linalg.norm(vel,axis=2)
        b = p['pitch_m']/(2*math.pi)
        rod = np.diff(pos,axis=1)
        target = np.full(223,p['other_handle_distance_m']); target[0]=p['head_handle_distance_m']
        checks = {}
        def check(name,value,limit):
            checks[name]={'value':float(value),'limit':limit,'passed':bool(value<=limit)}
        check('initial_head_position_error_m',np.linalg.norm(pos[0,0]-[8.8,0]),1e-9)
        check('spiral_radial_residual_m',np.max(np.abs(np.linalg.norm(pos,axis=2)-b*angles)),1e-8)
        check('rod_distance_residual_m',np.max(np.abs(np.linalg.norm(rod,axis=2)-target)),1e-8)
        check('head_speed_error_m_s',np.max(np.abs(speed[:,0]-1)),1e-9)
        check('rod_velocity_dot_residual_m2_s',np.max(np.abs(np.sum(rod*np.diff(vel,axis=1),axis=2))),1e-8)
        # Independent numerical quadrature, rather than reusing the arc formula.
        initial = p['initial_turns']*2*math.pi
        arc_errors = [abs(quad(lambda q:b*math.hypot(q,1),angles[i,0],initial,epsabs=1e-10)[0]-float(t)) for i,t in enumerate(times)]
        check('head_arc_quadrature_error_m',max(arc_errors),1e-8)
        checks['physical_order']={'passed':bool(np.all(np.diff(angles,axis=1)>0) and np.all(np.diff(angles,axis=0)<0) and np.all(vel[0,0]<[1e-9,0]))}
        checks['finite_values']={'passed':bool(np.all(np.isfinite(pos)) and np.all(np.isfinite(vel)))}
        # Independently differentiate solved Cartesian positions, all handles at 5 times.
        fd_errors = {}
        for h in [1e-2,1e-3,1e-4]:
            errors=[]
            for t in [1,60,120,240,299]:
                approx=(solve(t+h,p)[1]-solve(t-h,p)[1])/(2*h)
                errors.append(float(np.max(np.linalg.norm(approx-vel[t],axis=1))))
            fd_errors[str(h)]=max(errors)
        check('central_difference_velocity_error_m_s',fd_errors['0.001'],1e-5)
        # Second-order one-sided derivative at output endpoints.
        errors=[]; h=1e-3
        for t,direction in [(0,1),(300,-1)]:
            p0=pos[t]; p1=solve(t+direction*h,p)[1]; p2=solve(t+direction*2*h,p)[1]
            derivative=direction*(-3*p0+4*p1-p2)/(2*h)
            errors.append(np.max(np.linalg.norm(derivative-vel[t],axis=1)))
        check('endpoint_velocity_difference_error_m_s',max(errors),1e-5)
        refined_pos=[]; refined_vel=[]
        for t in [0,60,120,180,240,300]:
            refined=solve(t,p,xtol=5e-15)
            refined_pos.append(np.max(np.linalg.norm(refined[1]-pos[t],axis=1)))
            refined_vel.append(np.max(np.linalg.norm(refined[2]-vel[t],axis=1)))
        check('refined_root_position_difference_m',max(refined_pos),1e-8)
        check('refined_root_velocity_difference_m_s',max(refined_vel),1e-8)
        if not all(c['passed'] for c in checks.values()):
            raise AssertionError(json.dumps(checks,ensure_ascii=False))
        workbook=load_workbook(args.template)
        position_sheet=workbook['位置']; speed_sheet=workbook['速度']
        assert (position_sheet.max_row,position_sheet.max_column)==(449,302)
        assert (speed_sheet.max_row,speed_sheet.max_column)==(225,302)
        for ti,t in enumerate(times):
            assert position_sheet.cell(1,ti+2).value==f'{t} s'
            assert speed_sheet.cell(1,ti+2).value==f'{t} s'
            for i in range(224):
                for axis in range(2):
                    cell=position_sheet.cell(2+2*i+axis,ti+2,float(round(pos[ti,i,axis],6)))
                    cell.number_format='0.000000'
                cell=speed_sheet.cell(i+2,ti+2,float(round(speed[ti,i],6)))
                cell.number_format='0.000000'
        workbook.save(out/'result1.xlsx')
        # Reopen exported file and check every data cell against the unrounded arrays.
        exported=load_workbook(out/'result1.xlsx',read_only=True,data_only=True)
        for sheet_name,expected in [('位置',pos.transpose(1,2,0).reshape(448,301)),('速度',speed.T)]:
            ws=exported[sheet_name]
            actual=np.array(list(ws.iter_rows(min_row=2,min_col=2,max_row=expected.shape[0]+1,max_col=302,values_only=True)),dtype=float)
            check(f'xlsx_{sheet_name}_rounding_error',np.max(np.abs(actual-expected)),5.00001e-7)
        exported.close()
        if not all(c['passed'] for c in checks.values()): raise AssertionError('Export verification failed')
        np.savez_compressed(out/'trajectories.npz',time_s=times,theta_rad=angles,position_m=pos,velocity_m_s=vel,speed_m_s=speed)
        labels=['龙头','第1节龙身','第51节龙身','第101节龙身','第151节龙身','第201节龙身','龙尾（后）']
        indices=p['report_handle_indices_zero_based']; selected=p['report_times_s']
        lines=['# 问题 1 人工参考计算报告','',f'run_id: `{run_id}`','',
               '本次是人工编写并审阅的确定性参考程序，未调用MiMo，不计入LLM生成代码可运行率。未检测碰撞，未处理问题2～5。',
               '', '螺线：r=bθ，b=0.55/(2π)，初始θ₀=32π。弧长原函数为b/2·[θ√(1+θ²)+asinhθ]；由S(θ₀)−S(θ)=t确定龙头。',
               '', '其余把手以直线孔距约束逐点求解。δ∈(0,π)时弦长平方严格递增，故该区间内的根为外侧第一个根。本次全部节点均通过该括区验证。',
               '', '速度用(Xᵢ−Xᵢ₋₁)·(Vᵢ−Vᵢ₋₁)=0递推，并用位置的独立时间差分复核。所有内部计算使用双精度，导出时舍入至6位小数。','',
               '## 关键时刻位置（m）','', '| 把手/分量 | '+' | '.join(f'{t} s' for t in selected)+' |', '|---|'+'---:|'*6]
        for label,i in zip(labels,indices):
            for a,axis in enumerate(['x','y']): lines.append(f'| {label} {axis} | '+' | '.join(f'{pos[t,i,a]:.6f}' for t in selected)+' |')
        lines += ['', '## 关键时刻速率（m/s）','', '| 把手 | '+' | '.join(f'{t} s' for t in selected)+' |','|---|'+'---:|'*6]
        for label,i in zip(labels,indices): lines.append(f'| {label} | '+' | '.join(f'{speed[t,i]:.6f}' for t in selected)+' |')
        lines += ['', '## 核验','', '| 检查 | 实际误差/结果 | 阈值 | 通过 |','|---|---:|---:|---|']
        for name,c in checks.items(): lines.append(f"| {name} | {c.get('value', '布尔检查')} | {c.get('limit', '—')} | {c['passed']} |")
        lines += ['', '中心差分最大向量误差（h秒 → m/s）：'+json.dumps(fd_errors), '',
                  '误差限为本项目核验口径，并非官方参考答案。固定杆长、螺线轨迹、弧长积分和速度差分构成独立检查；尚无官方答案对照。',
                  '', '执行方式：经审阅的本地固定程序，不代表Docker隔离已验证。源文件哈希已核对，原模板没有修改。完整内部精度数据见trajectories.npz，结构化检查见validation.json。']
        (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        (out/'validation.json').write_text(json.dumps({'checks':checks,'finite_difference_errors':fd_errors},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        metadata.update(status='passed',exit_code=0,elapsed_seconds=time.perf_counter()-start,artifacts=['result1.xlsx','trajectories.npz','report.md','validation.json'])
        (out/'stdout.txt').write_text(f'All {len(checks)} checks passed.\n',encoding='utf-8')
        (out/'stderr.txt').write_text('',encoding='utf-8')
        print(json.dumps({'run_id':run_id,'status':'passed','output':str(out),'checks':checks,'head_position_300_s':pos[300,0].tolist(),'elapsed_seconds':metadata['elapsed_seconds']},ensure_ascii=False,indent=2))
    except Exception:
        metadata.update(status='failed',exit_code=1,elapsed_seconds=time.perf_counter()-start)
        (out/'stderr.txt').write_text(traceback.format_exc(),encoding='utf-8')
        (out/'stdout.txt').write_text('Run failed; see stderr.txt.\n',encoding='utf-8')
        raise
    finally:
        (out/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    main()
