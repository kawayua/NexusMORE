from modelcrew.project_assets import asset_path
from pathlib import Path
import json,hashlib,zipfile
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1]
base=asset_path(root,'stage-e/runs/q1-q2-20261109-v1')
out=root/'output/paper/q1-q2-20261109-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
review=json.loads((base/'W2-response.json').read_text(encoding='utf-8'))
print(json.dumps(review,ensure_ascii=False))
# This script is invoked only after independent W2 has passed its pinned final artifacts.
assert str(review.get('status','')).lower() in ('passed','pass','approved'), 'Independent W2 not passed'
qa=json.loads((out/'qa/content-layout-check.json').read_text(encoding='utf-8'))
assert qa['status']=='passed'
manifest=json.loads((out/'build-manifest.json').read_text(encoding='utf-8'))
for name,value in manifest['source_hashes'].items():assert sha(base/'source'/name)==value and sha(out/name)==value
files={name:sha(out/name) for name in ['paper.pdf','paper.docx','paper.tex']}
assert all(value in json.dumps(review) for value in files.values()), 'Independent W2 must bind all final artifact hashes'
record={'case_id':'q1-q2-20261109-v1','status':'case_export_and_independent_W2_passed','completed_at':datetime.now(timezone.utc).isoformat(),'user_authorization':'建议q1和q2一起汇编排版','source_manuscripts_previously_approved':True,'new_combined_manuscript_approval_inferred':False,'artifacts':files,'page_counts':{k:len(qa[k]['pages']) for k in ['latex','word']},'formal_figures':16,'scientific_tables':9,'numbered_equations':19,'word_native_math':qa['word_structure']['native_math'],'W2_response_sha256':sha(base/'W2-response.json'),'W2_report_sha256':sha(base/'W2-independent-review.md'),'visual_check_sha256':sha(out/'qa/content-layout-check.json'),'layout_fixes':['Long numeric paragraph wrapping without changing numerical values','Keep PDF table captions and short tables together','Keep Word repeated table headers with the first data row','Reduce table 9 cell padding to avoid a two-line final page'],'toolchain':{'docx_requested_renderer':'Actually executed render_docx.py; failed because LibreOffice/soffice absent; log retained','docx_actual_render':'Installed Word hidden COM native PDF export, all final pages visually reviewed','pdf':'Actual Tectonic compile, no missing glyph/overfull/undefined errors'},'scope_limit':'This is an actual Q1/Q2 assembly/export case with independent read-only W2, not acceptance of a general autonomous Writer/E-stage orchestration or project-provider API integration.'}
save(base/'completion.json',record)
manifest.update({'manual_review':'passed: actual independent W2 bound to final artifacts','final_artifacts':files,'page_counts':record['page_counts'],'case_completion':str((base/'completion.json').relative_to(root)),'layout_script_sha256':sha(root/'scripts/finalize_q1_q2_layout.py'),'word_spacing_script_sha256':sha(root/'scripts/tighten_q1_q2_word.py')})
save(out/'build-manifest.json',manifest)
approval=json.loads((out/'approval-check.json').read_text(encoding='utf-8'))
approval['W2']={'status':'passed','independent':True,'response_sha256':record['W2_response_sha256'],'artifact_hashes':files}
save(out/'approval-check.json',approval)
for name in ['W2-response.json','W2-independent-review.md','completion.json']:(out/name).write_bytes((base/name).read_bytes())
(out/'README.txt').write_text('Q1、Q2合编排版交付包\n\n正文与配图沿用已通过版本，共16幅图、9张表、19个编号公式。\npaper.pdf为正式编译PDF；paper.docx保留原生可编辑数学公式。\npaper.tex与fonts/、figures/构成LaTeX来源，可在本目录用Tectonic编译。\nresult1.xlsx、result2.xlsx及数值精度区间.json为数值附件。\nW2-independent-review.md、W2-response.json及completion.json保存独立审查与版本哈希。\n本次完成两题合编实例；未据此宣称通用自主导出框架已验收，未套用未经核验的官方最终投稿模板。\n',encoding='utf-8')
archive=out.parent/'q1-q2-20261109-v1-source.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(out.rglob('*')):
        if not p.is_file() or any(x in p.relative_to(out).parts for x in ('qa','build')) or p.suffix in ('.aux','.log','.out'):continue
        z.write(p,Path(out.name)/p.relative_to(out))
save(base.parent.parent/'current-assembly.json',{'case_id':record['case_id'],'status':record['status'],'run':str(base.relative_to(root)),'output':str(out.relative_to(root)),'completion_sha256':sha(base/'completion.json'),'archive':str(archive.relative_to(root)),'archive_sha256':sha(archive)})
print(json.dumps({'status':'completed','archive_bytes':archive.stat().st_size,'artifacts':files},ensure_ascii=False))
