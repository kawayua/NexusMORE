"""Extend an approved Markdown bundle with unselected physical-board position figures.

Preserves the exact manuscript bytes; no solver/model call or figure approval.
"""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon, Circle
from PIL import Image, ImageDraw, ImageOps
from modelcrew.config import ROOT
from modelcrew.bench_visuals import bench_geometry
from modelcrew.modeling_paper import sha, validate_draft, writing_context


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(original, output, qa_tools):
    original = original.resolve(); output = output.resolve()
    if validate_draft(original / '单题论文-中文审阅稿.md', original / 'figure-catalog.json')['status'] != 'passed':
        raise ValueError('Original review bundle failed checks')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'figures').mkdir()
    for source_file in (original / 'figures').iterdir():
        if source_file.is_file():
            shutil.copyfile(source_file, output / 'figures' / source_file.name)
    for filename in ['单题论文-中文审阅稿.md', 'selected-results.csv', 'constraint-diagnostics.csv']:
        shutil.copyfile(original / filename, output / filename)
    save(output / 'writer-context.json', writing_context())
    catalog = json.loads((original / 'figure-catalog.json').read_text(encoding='utf-8'))
    evidence = catalog['evidence']
    data_file = ROOT / evidence['path']
    if sha(data_file) != evidence['sha256']:
        raise ValueError('Stored trajectory hash mismatch')
    with np.load(data_file, allow_pickle=False) as data:
        times = data['time_s'].copy(); all_positions = data['position_m'].copy()
    parameter_path = ROOT / 'stage-a/2024-A-problem-1/parameters.json'
    parameters = json.loads(parameter_path.read_text(encoding='utf-8'))
    width = parameters['bench_width_m']; offset = parameters['hole_offset_m']
    hole_radius = parameters['hole_diameter_m'] / 2
    report_times = parameters['report_times_s']
    shape = np.array([bench_geometry(points, width, offset) for points in all_positions])
    if shape.shape != (301, 223, 4, 2):
        raise ValueError('Unexpected board geometry')
    # Overview bounds are identical across all times; zoom uses only the declared first three boards.
    limit = float(np.max(np.abs(shape))) + .6
    spec = importlib.util.spec_from_file_location('position_alignment', qa_tools / 'audit_panel_alignment.py')
    alignment = importlib.util.module_from_spec(spec); spec.loader.exec_module(alignment)
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
                         'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5, 'ytick.labelsize': 7.5,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.linewidth': .6})
    source_check = subprocess.run([sys.executable, str(qa_tools / 'validate_figure.py'), str(Path(__file__).resolve()), '--backend', 'python', '--json'], capture_output=True, text=True, encoding='utf-8', timeout=60)
    (output / 'plot-source-audit.json').write_text(source_check.stdout, encoding='utf-8')
    if source_check.returncode:
        raise ValueError('Plot source audit failed')
    save(output / 'plot-warning-review.json', {'EXPORT-RASTER': 'PNG previews and editable PDF/SVG requested; TIFF is not a review deliverable.'})
    new_figures = []
    for time_value in report_times:
        matches = np.flatnonzero(times == time_value)
        if matches.size != 1:
            raise ValueError('Requested time not stored exactly')
        index = int(matches[0]); boards = shape[index]; positions = all_positions[index]
        fid = f'result_q1_boards_t{int(time_value):03d}'
        width_mm = 183
        fig, axes = plt.subplots(1, 2, figsize=(width_mm / 25.4, 104 / 25.4), layout='constrained')
        for panel, ax, count in zip(['a', 'b'], axes, [223, 3]):
            polygons = [Polygon(corners, closed=True) for corners in boards[:count]]
            colors = ['#735B88'] + ['#D6B88A' if i % 2 else '#BD9768' for i in range(1, count)]
            ax.add_collection(PatchCollection(polygons, facecolors=colors, edgecolors='#5E5244', linewidths=.3))
            holes = [Circle(tuple(center), radius=hole_radius) for center in positions[:count + 1]]
            ax.add_collection(PatchCollection(holes, facecolors='white', edgecolors='#327998', linewidths=.3))
            ax.set(xlabel='横坐标 x（m）', ylabel='纵坐标 y（m）')
            ax.set_box_aspect(1)
            if panel == 'a':
                ax.set(xlim=(-limit, limit), ylim=(-limit, limit))
            else:
                corners = boards[:3].reshape(-1, 2)
                center = (corners.max(axis=0) + corners.min(axis=0)) / 2
                half = float(np.ptp(corners, axis=0).max()) / 2 + .4
                ax.set(xlim=(center[0] - half, center[0] + half), ylim=(center[1] - half, center[1] + half))
            ax.set_aspect('equal', adjustable='datalim')
            ax.set_title('全部 223 节板凳' if panel == 'a' else '龙头与前两节龙身局部', fontsize=8, pad=14)
            ax.annotate(panel, xy=(0, 1), xycoords='axes fraction', xytext=(-17, 9), textcoords='offset points', fontsize=8, fontweight='bold')
        fig.canvas.draw()
        alignment.require_matplotlib_panel_alignment(fig, json_out=output / 'figures' / (fid + '.alignment.json'), require_panel_labels=True, strict=True)
        files = {}
        paths = {'png': output / 'figures' / (fid + '.png'), 'pdf': output / 'figures' / (fid + '.pdf'), 'svg': output / 'figures' / (fid + '.svg')}
        for fmt, path in paths.items():
            fig.savefig(path, dpi=600)
            files[fmt] = {'path': path.relative_to(output).as_posix(), 'sha256': sha(path)}
        plt.close(fig)
        for tool, arguments in [('audit_pdf_text.py', ['--min-pt', '5', '--json']), ('audit_figure_collisions.py', ['--json'])]:
            done = subprocess.run([sys.executable, str(qa_tools / tool), str(paths['pdf']), *arguments], capture_output=True, text=True, encoding='utf-8', timeout=60)
            (output / 'figures' / (fid + '.' + tool.replace('.py', '') + '.json')).write_text(done.stdout, encoding='utf-8')
            if done.returncode:
                raise ValueError('Figure audit failed: ' + fid + '/' + tool)
        record = {'id': fid, 'category': 'result', 'question_ids': ['q1'], 'title': f'{time_value} 秒板凳位置与局部细节',
                  'purpose': '显示该时刻全部板凳的平面轮廓与龙头局部结构；可讨论替换原中心线构型图或组成时间序列。',
                  'formal': False, 'number': None, 'selection_status': 'proposed_not_user_approved',
                  'time_s': time_value, 'source_kind': 'historical_centers_with_input_dimension_schematic',
                  'files': files, 'statistics': '确定性位置重建，不设统计误差条',
                  'geometry': {'width_m': width, 'hole_offset_m': offset, 'hole_diameter_m': hole_radius * 2,
                               'boards': 223, 'overview_limits_m': [-limit, limit], 'zoom_board_indices': [0, 1, 2]},
                  'limitation': '根据中心点与题面尺寸绘制的刚性平面示意，未进行碰撞检测或真实受力模拟。'}
        catalog['figures'].append(record); new_figures.append(record)
    catalog['selection_status'] = 'manuscript_approved_expanded_candidates_pending_user'
    save(output / 'figure-catalog.json', catalog)
    discussion = ['# 配图候选与用户讨论清单', '正文已通过；新增六个时刻的板凳实物轮廓图，最终选图尚未确认。原正文和八张入文图保持不变。',
                  '## 新增位置图的读法', '紫色为龙头板，棕色为龙身/龙尾板，白孔为把手孔。左图显示全部 223 节，且六个时刻使用相同坐标尺度；右图放大龙头及前两节龙身。板宽和孔位使用题面尺寸，中心位置使用已确认数值结果。所有轮廓是平面几何示意，不能当作已做碰撞检测。',
                  '建议先比较 0、150/180、300 秒作为主文时间序列，其余时刻保留为候选或附录。现有 150 秒图仍是中心线图，新增的中段轮廓图为题目指定的 120/180 秒；具体采用哪个时刻、是否替换原图4，由用户讨论确定。']
    ordered = new_figures + [fig for fig in catalog['figures'] if fig not in new_figures]
    for item in ordered:
        suggestion = '新增候选，待选择' if item in new_figures else ('原稿暂选入文' if item['formal'] else '原备用图')
        discussion += [f"## {item['title']}", f"类别：{item['category']}；建议：{suggestion}", item['purpose'],
                       f"![{item['title']}]({item['files']['png']['path']})"]
    (output / '配图讨论清单.md').write_text('\n\n'.join(discussion) + '\n', encoding='utf-8')
    sheet = Image.new('RGB', (2400, 2070), 'white')
    for i, item in enumerate(new_figures):
        with Image.open(output / item['files']['png']['path']) as original_image:
            thumb = ImageOps.contain(original_image.convert('RGB'), (1200, 650))
        left = (i % 2) * 1200; top = (i // 2) * 690
        sheet.paste(thumb, (left, top + 24))
        ImageDraw.Draw(sheet).text((left + 12, top + 5), f't = {item["time_s"]} s', fill='black')
    sheet.save(output / '新增位置图-总览.png')
    manuscript = output / '单题论文-中文审阅稿.md'
    assert manuscript.read_bytes() == (original / manuscript.name).read_bytes()
    save(output / 'user-review.json', {'date': '2026-11-07', 'source': 'actual_user_message', 'user_statement': '然后单体论文通过',
        'decision': 'approve', 'reason': '用户明确通过当前单题正文；同时要求扩充位置候选图并固化流程。',
        'scope': 'Approved existing Chinese manuscript bytes only; not a new figure-selection or paper-export approval.',
        'markdown_sha256': sha(manuscript), 'catalog_sha256': sha(output / 'figure-catalog.json'),
        'policy_sha256': sha(ROOT / 'resources/paper/chinese-modeling-policy.json'), 'figure_selection_decision': 'pending',
        'approved_original_bundle': original.relative_to(ROOT).as_posix()})
    report = validate_draft(manuscript, output / 'figure-catalog.json')
    save(output / 'paper-check.json', report)
    if report['status'] != 'passed':
        raise ValueError(str(report['findings']))
    save(output / 'build-manifest.json', {'original_manuscript_sha256': sha(original / manuscript.name),
        'manuscript_sha256': sha(manuscript), 'data': evidence, 'parameter_sha256': sha(parameter_path),
        'script_sha256': sha(Path(__file__)), 'geometry_source_sha256': sha(ROOT / 'modelcrew/bench_visuals.py'),
        'new_position_candidates': 6, 'all_candidates': len(catalog['figures']), 'formal_proposed_unchanged': 8,
        'new_solver_runs': 0, 'new_llm_calls': 0, 'manuscript_review': 'approved', 'figure_selection': 'pending',
        'paper_exported': False})
    print(json.dumps({'output': str(output), 'candidates': len(catalog['figures']), 'new_time_views': report_times, 'manuscript': 'approved_unchanged', 'figure_selection': 'pending'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qa-tools', type=Path, required=True)
    args = parser.parse_args()
    build(args.original, args.output, args.qa_tools)
