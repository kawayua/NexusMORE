"""Build a Chinese Markdown review draft and provisional figure-selection bundle.

Uses confirmed historical arrays only; no new solver, LLM, database or user approval.
"""
from modelcrew.project_assets import asset_path
import argparse
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from modelcrew.config import ROOT
from modelcrew.modeling_paper import sha, validate_draft, writing_context


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(folder, qa_tools):
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / 'writer-context.json', writing_context())
    figures_dir = folder / 'figures'
    figures_dir.mkdir()
    evidence = json.loads((asset_path(ROOT,'stage-a-plus/figure-evidence-plan.json')).read_text(encoding='utf-8'))['evidence']
    source = ROOT / evidence['path']
    if sha(source) != evidence['sha256']:
        raise ValueError('Historical data hash mismatch')
    with np.load(source, allow_pickle=False) as stored:
        t = stored['time_s'].copy()
        xy = stored['position_m'].copy()
        vel = stored['velocity_m_s'].copy()
        theta = stored['theta_rad'].copy()
    if t.shape != (301,) or xy.shape != (301, 224, 2) or vel.shape != xy.shape:
        raise ValueError('Unexpected historical data shape')
    if not all(np.isfinite(a).all() for a in (t, xy, vel, theta)):
        raise ValueError('Nonfinite data')
    contract_path = asset_path(ROOT,'stage-b-plus/examples/contract-v2-snapshot.json')
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    pars = {p['id']: p['value'] for p in contract['parameters']}
    pitch = float(pars['pitch']); b = pitch / (2 * np.pi)
    lengths = np.full(223, float(pars['body_gap'])); lengths[0] = float(pars['head_gap'])
    rods = np.diff(xy, axis=1)
    geometric = np.max(np.abs(np.linalg.norm(rods, axis=2) - lengths), axis=1)
    differential = np.max(np.abs(np.einsum('tij,tij->ti', rods, np.diff(vel, axis=1))), axis=1)
    speed = np.linalg.norm(vel, axis=2)
    tolerance = next(c['tolerance'] for c in contract['checks'] if c['id'] == 'rod_distance')
    if geometric.max() > float(tolerance):
        raise ValueError('Historical rod check failed')
    # All times and rods are retained; maxima are explicitly declared reductions.
    np.savetxt(folder / 'constraint-diagnostics.csv', np.column_stack((t, geometric, differential)), delimiter=',',
               header='time_s,max_rod_residual_m,max_velocity_constraint_m2_per_s', comments='')
    spec = importlib.util.spec_from_file_location('review_alignment', qa_tools / 'audit_panel_alignment.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
                         'font.size': 9, 'axes.labelsize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.linewidth': .7,
                         'lines.linewidth': 1.1, 'legend.frameon': False})
    audit = subprocess.run([sys.executable, str(qa_tools / 'validate_figure.py'), str(Path(__file__).resolve()), '--backend', 'python', '--json'], capture_output=True, text=True, encoding='utf-8', timeout=60)
    (folder / 'plot-source-audit.json').write_text(audit.stdout, encoding='utf-8')
    if audit.returncode:
        raise RuntimeError('Plot source preflight failed')
    write_json(folder / 'plot-warning-review.json', {'FINAL-WIDTH': '170 mm matches the existing modeling manuscript width; Nature column specifications are not the target.', 'EXPORT-RASTER': 'Markdown review uses PNG with editable PDF/SVG masters; TIFF submission export is not requested.'})
    entries = []
    review_notes = []
    blue, purple, gray = '#327998', '#735B88', '#777777'

    def chart(fid, category, title, purpose, draw, number=None, source_kind='historical_result'):
        width_mm = 170
        fig, ax = plt.subplots(figsize=(width_mm / 25.4, 112 / 25.4), layout='constrained')
        draw(fig, ax)
        fig.canvas.draw()
        module.require_matplotlib_panel_alignment(fig, json_out=figures_dir / (fid + '.alignment.json'), strict=True)
        files = {}
        paths = {'pdf': figures_dir / (fid + '.pdf'), 'svg': figures_dir / (fid + '.svg'), 'png': figures_dir / (fid + '.png')}
        for fmt, path in paths.items():
            fig.savefig(path, dpi=600)
            files[fmt] = {'path': path.relative_to(folder).as_posix(), 'sha256': sha(path)}
        plt.close(fig)
        for script, args in [('audit_pdf_text.py', ['--min-pt', '5', '--json']),
                             ('audit_figure_collisions.py', ['--json'])]:
            command = [sys.executable, str(qa_tools / script), str(figures_dir / (fid + '.pdf')), *args]
            done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=60)
            (figures_dir / (fid + '.' + script.replace('.py', '') + '.json')).write_text(done.stdout, encoding='utf-8')
            if done.returncode:
                raise RuntimeError('Figure QA failed: ' + fid + '/' + script)
        entries.append({'id': fid, 'category': category, 'question_ids': ['q1'], 'title': title,
                        'purpose': purpose, 'formal': number is not None, 'number': number,
                        'selection_status': 'proposed_not_user_approved', 'source_kind': source_kind,
                        'files': files, 'statistics': '确定性单次计算，不设统计误差条'})

    def spiral(fig, ax):
        u = np.linspace(0, 32 * np.pi, 3000)
        ax.plot(b * u * np.cos(u), b * u * np.sin(u), color=blue, lw=.8)
        ax.scatter([8.8], [0], s=24, color=purple, zorder=3)
        ax.set(xlabel='横坐标 x（m）', ylabel='纵坐标 y（m）', aspect='equal')
    chart('raw_q1_spiral', 'raw', '给定螺距下的盘入路径', '由题面螺距和初始圈数构造的路径示意，不是新增观测。', spiral, 1, 'input_parameters_schematic')

    def lengths_plot(fig, ax):
        ax.plot([0, 3.41], [1, 1], color=gray, lw=5, solid_capstyle='butt')
        ax.plot([0, 2.20], [0, 0], color=gray, lw=5, solid_capstyle='butt')
        ax.scatter([.275, 3.135], [1, 1], color=blue, s=32, zorder=3)
        ax.scatter([.275, 1.925], [0, 0], color=blue, s=32, zorder=3)
        ax.text(1.65, 1.25, '龙头板：全长 3.41 m；孔距 2.86 m', ha='center')
        ax.text(1.65, -.35, '龙身板：全长 2.20 m；孔距 1.65 m', ha='center')
        ax.set(xlabel='距板端距离（m）', xlim=(-.1, 3.5), ylim=(-.65, 1.65), yticks=[])
        ax.spines['left'].set_visible(False)
    chart('raw_q1_lengths', 'raw', '板长与把手孔距的区别', '解释杆长约束应使用孔距而非板凳全长；为尺寸示意。', lengths_plot, 2, 'input_parameters_schematic')

    def dimensions(fig, ax):
        ax.barh(['螺距', '孔中心距板端', '龙身孔距', '龙头孔距'], [.55, .275, 1.65, 2.86], color=[gray, gray, blue, purple])
        ax.set(xlabel='输入尺寸（m）')
    chart('raw_q1_dimensions', 'raw', '输入长度参数对照', '候选备用：概览输入尺寸；与尺寸示意有重叠，暂不入正文。', dimensions, source_kind='input_parameters')

    def branch(fig, ax):
        delta = np.linspace(0, np.pi, 600)
        r = b * float(theta[-1, 0]); ell = float(lengths[0])
        f = (b * delta) ** 2 + 4 * r * (r + b * delta) * np.sin(delta / 2) ** 2 - ell ** 2
        ax.plot(delta, f, color=blue)
        ax.set(xlabel='相邻极角差 δ（rad）', ylabel='平方弦长残差 F（m²）', xlim=(0, np.pi))
    chart('process_q1_branch', 'process', '末时刻首段杆的求根区间诊断', '显示实际半径对应约束函数及括区间形态，不是迭代轨迹。', branch, 3, 'derived_constraint_diagnostic')

    def rod(fig, ax):
        ax.plot(t, geometric, color=blue)
        ax.set(xlabel='时间 t（s）', ylabel='全杆最大长度残差（m）', xlim=(0, 300), ylim=(0, geometric.max() * 1.15))
        ax.ticklabel_format(axis='y', style='sci', scilimits=(0, 0), useMathText=False)
    chart('process_q1_rod', 'process', '定长杆几何约束残差', '使用全部 301 个时刻、223 根杆的逐时最大值检验离散几何一致性。', rod, 7)

    def derivative(fig, ax):
        ax.plot(t, differential, color=purple)
        ax.set(xlabel='时间 t（s）', ylabel='全杆最大速度约束残差（m²/s）', xlim=(0, 300), ylim=(0, differential.max() * 1.15))
        ax.ticklabel_format(axis='y', style='sci', scilimits=(0, 0), useMathText=False)
    chart('process_q1_velocity', 'process', '杆长导数约束残差', '检验速度递推与几何约束的一致性，不虚构该量纲下的容差。', derivative, 8)

    def snapshots(fig, ax):
        for k, color in zip([0, 150, 300], [gray, blue, purple]):
            ax.plot(xy[k, :, 0], xy[k, :, 1], color=color, lw=.9, label=f'{k} s')
        ax.set(xlabel='横坐标 x（m）', ylabel='纵坐标 y（m）', aspect='equal')
        ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.02), ncol=3, fontsize=8)
    chart('result_q1_configuration', 'result', '三个代表时刻的把手中心构型', '预先选取起点、中点和终点解释盘入形态；不是有限板宽碰撞证明。', snapshots, 4)

    def heat(fig, ax):
        image = ax.imshow(speed.T, origin='lower', aspect='auto', extent=[0, 300, -.5, 223.5], cmap='viridis', interpolation='nearest')
        ax.set(xlabel='时间 t（s）', ylabel='把手编号 i（0 为龙头前把手）')
        fig.colorbar(image, ax=ax, label='速率（m/s）', pad=.035)
    chart('result_q1_speedmap', 'result', '全时域把手速率分布', '全部 301×224 个速率值，检查时间与链位置的整体差异。', heat, 5)

    def selected(fig, ax):
        for i, color in zip([0, 51, 101, 151, 201, 223], ['#777777', '#327998', '#735B88', '#447A53', '#A46E40', '#8B5268']):
            ax.plot(t, speed[:, i], label=f'把手 {i}', color=color)
        ax.set(xlabel='时间 t（s）', ylabel='把手速率（m/s）', xlim=(0, 300))
        ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.02), ncol=3, fontsize=8)
    chart('result_q1_speeds', 'result', '指定把手速率的时间变化', '展示题目指定把手的精确趋势，辅助读出热图中的小幅变化；选择规则预先固定。', selected, 6)
    entries.sort(key=lambda item: item['number'] if item['formal'] else 999)
    catalog = {'policy_version': '1.0.0', 'question_ids': ['q1'], 'selection_status': 'awaiting_user_discussion',
               'figure_source_sha256': sha(source), 'contract_sha256': sha(contract_path),
               'evidence': evidence, 'figures': entries}
    write_json(folder / 'figure-catalog.json', catalog)
    rows = []
    for k in [0, 60, 120, 180, 240, 300]:
        rows.append(f'| {k} | {xy[k,0,0]:.6f} | {xy[k,0,1]:.6f} | {xy[k,223,0]:.6f} | {xy[k,223,1]:.6f} | {speed[k,223]:.6f} |')
    all_rows = []
    for k in [0, 60, 120, 180, 240, 300]:
        for i in [0, 1, 51, 101, 151, 201, 223]:
            all_rows.append([k, i, *xy[k, i], *vel[k, i], speed[k, i]])
    np.savetxt(folder / 'selected-results.csv', np.array(all_rows), delimiter=',', fmt=['%d','%d','%.12f','%.12f','%.12f','%.12f','%.12f'],
               header='time_s,handle_index,x_m,y_m,vx_m_s,vy_m_s,speed_m_s', comments='')
    argmax = np.unravel_index(np.argmax(speed), speed.shape)
    numbers = {'GEOM': f'{geometric.max():.6e}', 'DIFF': f'{differential.max():.6e}',
               'SPEEDMAX': f'{speed.max():.9f}', 'MAXTIME': str(int(t[argmax[0]])), 'MAXHANDLE': str(argmax[1]),
               'HEADR': f'{np.linalg.norm(xy[-1,0]):.6f}', 'HEADTHETA': f'{theta[-1,0]:.6f}',
               'RESULT_ROWS': '\n'.join(rows), 'SAMPLE_COUNT': str(t.size)}
    text = (asset_path(ROOT,'resources/paper/bench-dragon-review.md')).read_text(encoding='utf-8')
    for key, value in numbers.items():
        text = text.replace('@@' + key + '@@', value)
    for fig in entries:
        if fig['formal']:
            block = f"![图{fig['number']} {fig['title']}]({fig['files']['png']['path']})\n\n图{fig['number']} {fig['title']}。{fig['purpose']}"
            text = text.replace('@@FIG' + str(fig['number']) + '@@', block)
    (folder / '单题论文-中文审阅稿.md').write_text(text, encoding='utf-8')
    selection = ['# 配图候选与用户讨论清单', '', '状态：暂选，尚未获得用户确认。正文采用 8 幅；另有 1 幅备用。可以讨论保留、替换、合并或补图；正式排版前需确认最终图片清单。', '']
    for fig in entries:
        selection += [f"## {fig['id']}：{fig['title']}", f"类别：{fig['category']}；建议：" + ('暂选入文' if fig['formal'] else '备用，不入文'),
                      fig['purpose'], f"![{fig['title']}]({fig['files']['png']['path']})", '']
    (folder / '配图讨论清单.md').write_text('\n\n'.join(selection), encoding='utf-8')
    report = validate_draft(folder / '单题论文-中文审阅稿.md', folder / 'figure-catalog.json')
    write_json(folder / 'paper-check.json', report)
    write_json(folder / 'build-manifest.json', {'source': evidence, 'script_sha256': sha(Path(__file__)),
        'template_sha256': sha(asset_path(ROOT,'resources/paper/bench-dragon-review.md')),
        'new_solver_runs': 0, 'new_llm_calls': 0, 'user_review': 'pending', 'figure_selection': 'pending',
        'paper_exported': False, 'metrics': numbers, 'check': report})
    if report['status'] != 'passed':
        raise ValueError(str(report['findings']))
    print(json.dumps({'folder': str(folder), 'candidates': 9, 'formal_proposed': 8, 'status': report['status'], 'metrics': numbers}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qa-tools', type=Path, required=True)
    args = parser.parse_args()
    build(args.output, args.qa_tools)
