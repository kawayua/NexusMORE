"""C+ real historical-result figure and B+ package -> TeX/PDF export probe.

No solver execution or approval; raw model-generated TeX is not accepted here.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import fitz
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.text import Text
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.corpus import sha_file
from modelcrew.mathematics import validate_package
from modelcrew.aplus import check_dossier


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda item:item.item() if isinstance(item,np.generic) else str(item))+'\n',encoding='utf-8')
def esc(text):
    mapping={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_\allowbreak{}',
             '{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}',
             ':':r':\allowbreak{}','/':r'/\allowbreak{}','=':r'=\allowbreak{}'}
    return ''.join(mapping.get(ch,ch) for ch in str(text))


def safe_math(text):
    if re.search(r'\\(?:input|include|write|openout|openin|read|catcode|csname|usepackage|documentclass|def|newcommand|special|immediate|loop|shipout)(?![A-Za-z])',text):
        raise ValueError('Unsafe command in mathematical source')
    if re.search(r'\\(?:begin|end)\{(?:document|equation|figure|table)\}',text):raise ValueError('Unsafe math environment')
    return text


def plot(folder,package,contract,qa_tools=None):
    plan=json.loads((ROOT/'stage-a-plus/figure-evidence-plan.json').read_text(encoding='utf-8'))
    source=ROOT/plan['evidence']['path']
    if sha_file(source)!=plan['evidence']['sha256'] or package['figures'][0]['data_sha256']!=sha_file(source):
        raise ValueError('Historical result figure hash mismatch')
    with np.load(source,allow_pickle=False) as arrays:
        time=arrays['time_s'];position=arrays['position_m'];velocity=arrays['velocity_m_s']
    if time.shape!=(301,) or position.shape!=(301,224,2) or velocity.shape!=position.shape or not all(np.isfinite(a).all() for a in (time,position,velocity)):
        raise ValueError('Unexpected historical array structure')
    parameters={p['id']:p['value'] for p in contract['parameters']}
    lengths=np.full(223,parameters['body_gap']);lengths[0]=parameters['head_gap']
    rods=np.diff(position,axis=1);dv=np.diff(velocity,axis=1)
    geom=np.max(np.abs(np.linalg.norm(rods,axis=2)-lengths),axis=1)
    derivative=np.max(np.abs(np.einsum('tij,tij->ti',rods,dv)),axis=1)
    tolerance=next(c['tolerance'] for c in contract['checks'] if c['id']=='rod_distance')
    threshold=float(tolerance)
    contract_figure={'figure_id':'fig:kinematic-diagnostics','claim':'Stored handle-centre trajectories satisfy the declared rod-length tolerance at all 301 samples; differentiated-constraint residuals are reported separately.',
        'archetype':'quantitative grid','backend':'Python/matplotlib','size_mm':[170,105],
        'panels':{'a':'max absolute rod-length residual over all223 rods, m','b':'max absolute differentiated-rod residual over all223 rods, m^2/s; no approved threshold in this unit'},
        'samples':301,'rods':223,'aggregation':'maximum over all rods, every stored time; no exclusions','source':plan['evidence'],
        'statistics':'one deterministic run; no replicates or error bars; not a continuous-time or collision-clearance proof',
        'threshold_source':'approved historical contract check rod_distance; no threshold invented for panel b','exports':['PDF','SVG','PNG600dpi','TIFF600dpi']}
    save(folder/'figure-contract.json',contract_figure)
    with (folder/'figure-data.csv').open('w',newline='',encoding='utf-8') as stream:
        out=csv.writer(stream);out.writerow(['time_s','max_rod_residual_m','max_derivative_residual_m2_per_s']);out.writerows(zip(time,geom,derivative,strict=True))
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans','Arial','Helvetica'],'font.size':8,'axes.labelsize':8,'xtick.labelsize':7.5,'ytick.labelsize':7.5,
        'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,'lines.linewidth':.9})
    width_in,height_in=170/25.4,105/25.4
    fig,axes=plt.subplots(2,1,figsize=(width_in,height_in),sharex=True)
    fig.subplots_adjust(left=.17,right=.97,bottom=.13,top=.94,hspace=.38)
    zeros={}
    for ax,data,label,panel,color in zip(axes,[geom,derivative],['Rod-length residual\n(m)',r'Derivative residual'+'\n'+r'($\mathrm{m^2\,s^{-1}}$)'],['a','b'],['#327998','#735B88']):
        positive=data>0;floor=float(data[positive].min()/2) if positive.any() else 1e-16
        zeros[panel]={'count':int((~positive).sum()),'display_floor':floor}
        ax.plot(time,np.where(positive,data,np.nan),color=color)
        if not positive.all():ax.scatter(time[~positive],np.full((~positive).sum(),floor),marker='v',facecolors='none',edgecolors=color,s=9)
        ax.set_yscale('log');ax.set_ylabel(label,labelpad=8);ax.set_xlim(0,300)
        ax.text(-.14,1.02,panel,transform=ax.transAxes,fontsize=8,fontweight='bold',va='bottom')
        ax.tick_params(width=.6,length=3)
    axes[0].axhline(threshold,color='#777777',ls='--',lw=.8)
    axes[0].set_ylim(bottom=max(float(geom[geom>0].min())*.55,1e-17),top=threshold*8)
    axes[0].text(296,threshold*1.4,r'Contract tolerance: $10^{-8}$ m',ha='right',va='bottom',fontsize=7.5,color='#555555')
    axes[0].yaxis.set_major_locator(ticker.FixedLocator([1e-13,1e-12,1e-11,1e-10,1e-9,1e-8]))
    axes[1].yaxis.set_major_locator(ticker.FixedLocator([4e-16,6e-16,1e-15]))
    axes[1].set_ylim(3.5e-16,1.8e-15)
    for ax in axes:
        ax.yaxis.set_minor_locator(ticker.NullLocator())
    axes[1].set_xlabel('Time (s)');axes[1].set_xticks([0,60,120,180,240,300])
    fig.canvas.draw();renderer=fig.canvas.get_renderer();width,height=fig.canvas.get_width_height()
    bounds=[]
    for text in fig.findobj(Text):
        if not text.get_visible() or not text.get_text():continue
        bbox=text.get_window_extent(renderer)
        # Some hidden shared-axis tick texts have zero area; audit only rendered extents.
        if bbox.width and bbox.height:
            bounds.append({'text':text.get_text(),'fontsize_pt':text.get_fontsize(),'bbox':[bbox.x0,bbox.y0,bbox.x1,bbox.y1],
                           'inside':bbox.x0>=-1 and bbox.y0>=-1 and bbox.x1<=width+1 and bbox.y1<=height+1})
    positions=[ax.get_window_extent(renderer) for ax in axes]
    alignment=max(abs(positions[0].x0-positions[1].x0),abs(positions[0].x1-positions[1].x1))*72/fig.dpi
    if qa_tools:
        spec=importlib.util.spec_from_file_location('cplus_alignment',qa_tools/'audit_panel_alignment.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        require_matplotlib_panel_alignment=module.require_matplotlib_panel_alignment
        require_matplotlib_panel_alignment(fig,json_out=folder/'alignment-audit.json',require_panel_labels=True,strict=True)
    fig.savefig(folder/'kinematic-diagnostics.pdf')
    fig.savefig(folder/'kinematic-diagnostics.svg')
    fig.savefig(folder/'kinematic-diagnostics.png',dpi=600)
    fig.savefig(folder/'kinematic-diagnostics.tiff',dpi=600)
    plt.close(fig)
    pdf=fitz.open(folder/'kinematic-diagnostics.pdf');spans=[s for p in pdf for b in p.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
    min_font=min(s['size'] for s in spans if s['text'].strip())
    report={'data_source_sha256':sha_file(source),'data_hash':sha_file(folder/'figure-data.csv'),'rod_max_m':float(geom.max()),'derivative_max_m2_per_s':float(derivative.max()),
        'rod_contract_tolerance_m':threshold,'rod_check_passed':bool(np.all(geom<=threshold)),'derivative_check':'reported_no_contract_threshold_for_this_unit',
        'zeros':zeros,'axes_alignment_error_pt':alignment,'alignment_limit_pt':1.5,'rendered_pdf_min_span_font_pt':min_font,'minimum_font_pt':5,
        'text_bounds_passed':all(x['inside'] for x in bounds),'text_bounds':bounds,'pdf_has_raster_images':any(p.get_images() for p in pdf),
        'vector_size_pt':[pdf[0].rect.width,pdf[0].rect.height],'external_audit_scripts':'executed separately and archived' if qa_tools else 'not supplied; local checks only',
        'collision_coverage':'text bounds and alignment; no claim of exhaustive text-versus-curve intersection detection','manual_review':'pending'}
    pdf.close();save(folder/'figure-qa.json',report)
    if not report['rod_check_passed'] or not report['text_bounds_passed'] or min_font<5 or alignment>1.5:raise ValueError('Figure numerical or layout QA failed')
    return report


def tex_source(package,name,figure=False):
    citation='scipy-brentq' if name=='bench-dragon' else 'scipy-linprog'
    dossier=package['dossier'];parts=[r'\documentclass[11pt,a4paper]{article}',r'\usepackage[margin=20mm]{geometry}',
      r'\usepackage{amsmath,amssymb,booktabs,longtable,array,graphicx,hyperref}',r'\hypersetup{hidelinks}',r'\newsavebox{\equationbox}',
      r'\setlength{\parindent}{0pt}',r'\setlength{\tabcolsep}{4pt}',r'\emergencystretch=3em',r'\sloppy',r'\setlength{\parskip}{5pt}',r'\begin{document}',r'\title{C+ Mathematical Export Probe: '+esc(name)+'}',
      r'\author{ModelCrew engineering verification}',r'\date{6 November 2026}',r'\maketitle',
      'This is a mathematical handoff and export probe, not a full paper or a new solver run. Compilation does not establish mathematical truth.',
      r'\section{Problem and method}',esc(dossier['problem_setting']['scope']),esc(package['method_selection']['model']),esc(package['method_selection']['solver']),
      r'\section{Notation}',r'\small',r'\begin{longtable}{p{.16\linewidth}p{.36\linewidth}p{.28\linewidth}p{.1\linewidth}}',
      r'\toprule Symbol & Meaning & Domain & Unit \\ \midrule\endhead']
    for symbol in dossier['symbols']:
        parts.append('$'+safe_math(symbol['latex'])+'$ & '+esc(symbol['meaning'])+' & '+esc(symbol['domain'])+' & '+esc(symbol['unit'])+r' \\')
    parts += [r'\bottomrule\end{longtable}',r'\normalsize',r'\section{Assumptions}']
    for assumption in dossier['assumptions']:parts.append(r'\textbf{'+esc(assumption['id'])+'}: '+esc(assumption['statement'])+r'\par')
    parts += [r'\section{Equations and explicit references}']
    for equation in dossier['equations']:
        latex=safe_math(equation['latex'])
        parts += [r'\subsubsection*{'+esc(equation['meaning'])+'}',
            r'\begin{equation}\label{'+equation['id']+'}',
            r'\sbox{\equationbox}{$\displaystyle '+latex+r'$}',
            r'\ifdim\wd\equationbox>0.92\linewidth\resizebox{0.92\linewidth}{!}{\usebox{\equationbox}}\else\usebox{\equationbox}\fi',r'\end{equation}',
            'Equation~'+r'\eqref{'+equation['id']+'} uses symbols '+esc(', '.join(equation['symbol_ids']))+'. '+esc('Evidence type: '+equation['evidence_type'])+'.']
    parts += [r'\section{Derivation conditions and limits}']
    for step in dossier['derivations']+dossier['propositions']:
        parts += [r'\subsubsection*{'+esc(step['id'])+'}',esc('Status: '+step['status']+'. Conditions: '+'; '.join(step['conditions'])),r'\begin{enumerate}']
        parts += [r'\item '+esc(line) for line in step['steps']]
        parts += [r'\end{enumerate}',esc('Open gaps: '+'; '.join(step['open_gaps']) if step['open_gaps'] else 'No gaps declared in this reviewed finite baseline; not a general proof certificate.')]
    parts += [r'\section{Verification and scope}', 'The following claims remain unproved or outside this handoff scope:', r'\begin{itemize}']
    parts += [r'\item '+esc(item) for item in dossier['unproved_or_out_of_scope']] or [r'\item No additional unproved claims are declared in this package; review remains limited to its stated premises.']
    parts += [r'\end{itemize}']
    if figure:
        parts += [r'\clearpage\section{Historical result diagnostics}',
            r'\begin{figure}[ht]\centering\includegraphics[width=170mm]{kinematic-diagnostics.pdf}',
            r'\caption{Historical confirmed result v2/revision 2; all 301 stored times and 223 rods. Panel a shows the maximum rod-length residual and the original $10^{-8}$ m tolerance. Panel b reports the differentiated-constraint residual in $\mathrm{m^2\,s^{-1}}$ without inventing a tolerance in that unit. One deterministic run; no error bars. Zero residuals, if present, use hollow downward markers at the documented display floor. These are discrete numerical diagnostics, not a collision-clearance or continuous-time proof.}',
            r'\label{fig:kinematic-diagnostics}\end{figure}',r'Figure~\ref{fig:kinematic-diagnostics} is bound to the existing confirmed output, not a new mathematical-package result.']
    parts += [r'\section{Source references}',r'The relevant numerical interface is documented in reference~\cite{'+citation+'}. External references support method review; they do not replace this project execution evidence.',
       r'\begin{thebibliography}{9}',r'\bibitem{scipy-brentq} SciPy developers. SciPy 1.15.3, brentq reference. \url{https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.brentq.html}',
       r'\bibitem{scipy-linprog} SciPy developers. SciPy 1.15.3, linprog reference. \url{https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.optimize.linprog.html}',
       r'\end{thebibliography}',r'\end{document}']
    return '\n'.join(parts)+'\n'


def build(folder,compiler,qa_tools=None):
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=False)
    packages={name:json.loads((ROOT/f'stage-b-plus/examples/valid-{name}.json').read_text(encoding='utf-8')) for name in ('bench-dragon','resource')}
    contracts={name:json.loads((ROOT/('stage-b-plus/examples/contract-v2-snapshot.json' if name=='bench-dragon' else 'stage-b-plus/examples/resource-contract.json')).read_text(encoding='utf-8')) for name in packages}
    for name in packages:validate_package(packages[name],contracts[name])
    numerical=plot(folder,packages['bench-dragon'],contracts['bench-dragon'],qa_tools)
    results=[]
    for name,package in packages.items():
        source=folder/(name+'.tex');source.write_text(tex_source(package,name,figure=name=='bench-dragon'),encoding='utf-8')
        command=[str(compiler.resolve()),'--untrusted','--keep-logs','--keep-intermediates','--outdir',str(folder),str(source)]
        cache=ROOT/'stage-c-plus/tex-cache';cache.mkdir(exist_ok=True)
        env={**os.environ,'TECTONIC_CACHE_DIR':str(cache),'TEMP':str(cache),'TMP':str(cache)}
        process=subprocess.run(command,capture_output=True,timeout=600,env=env)
        (folder/(name+'-build.stdout.log')).write_bytes(process.stdout);(folder/(name+'-build.stderr.log')).write_bytes(process.stderr)
        if process.returncode:raise RuntimeError('Actual TeX compilation failed for '+name+'; inspect build logs')
        pdf_path=folder/(name+'.pdf');log=(folder/(name+'.log')).read_text(encoding='utf-8',errors='replace')
        bad=re.findall(r'(?:Undefined control sequence|Missing character:[^\n]*|Overfull \\hbox[^\n]*|LaTeX Warning: (?:Reference|Citation)[^\n]*undefined|There were undefined references)',log)
        aux=(folder/(name+'.aux')).read_text(encoding='utf-8',errors='replace')
        equations=package['dossier']['equations']
        refs=all(('\\newlabel{'+equation['id']+'}') in aux for equation in equations)
        doc=fitz.open(pdf_path);page_reports=[]
        for i,page in enumerate(doc,1):
            pix=page.get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False);pix.save(folder/(name+f'-page-{i:02}.png'))
            spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans'] if s['text'].strip()]
            page_reports.append({'page':i,'min_font_pt':min(s['size'] for s in spans),
                                 'text_in_page':all(s['bbox'][0]>=0 and s['bbox'][1]>=0 and s['bbox'][2]<=page.rect.width+1 and s['bbox'][3]<=page.rect.height+1 for s in spans)})
        results.append({'name':name,'command':command,'package_path':f'stage-b-plus/examples/valid-{name}.json','package_sha256':sha_file(ROOT/f'stage-b-plus/examples/valid-{name}.json'),
                        'contract_sha256':digest(contracts[name]),'dossier_sha256':digest(package['dossier']),
                        'structure_check':'passed','mathematical_review':check_dossier(package['dossier']),
                        'export_check':'passed' if not bad and refs and all(p['text_in_page'] and p['min_font_pt']>=5 for p in page_reports) else 'failed',
                        'log_failures':bad,'equations':len(equations),'symbols':len(package['dossier']['symbols']),'all_equation_labels_resolved':refs,
                        'pages':page_reports,'figure_embedded':name=='bench-dragon','manual_review':'pending'})
        doc.close()
    if qa_tools:
        for script,args in [('validate_figure.py',[str(Path(__file__).resolve()),'--backend','python','--json']),('audit_pdf_text.py',[str(folder/'kinematic-diagnostics.pdf'),'--min-pt','5','--json']),('audit_figure_collisions.py',[str(folder/'kinematic-diagnostics.pdf'),'--json'])]:
            audit=subprocess.run([sys.executable,str(qa_tools/script),*args],capture_output=True,text=True,encoding='utf-8',timeout=60)
            (folder/(script.replace('.py','')+'-report.json')).write_text(audit.stdout,encoding='utf-8')
            if audit.returncode:raise RuntimeError('External figure QA failed: '+script)
    compiler_version=subprocess.run([str(compiler.resolve()),'--version'],capture_output=True,text=True,check=True).stdout.strip()
    manifest={'scope':'C+ toolchain probe; historical confirmed result only; no new solver/LLM/user approval','compiler':compiler_version,'compiler_sha256':sha_file(compiler),
        'matplotlib_version':matplotlib.__version__,'pymupdf_version':fitz.VersionBind,'figure':numerical,'documents':results,
        'script_sha256':sha_file(Path(__file__)),'resources':{str(p.relative_to(folder)).replace('\\','/'):sha_file(p) for p in folder.iterdir() if p.is_file()},
        'new_llm_calls':0,'new_contest_solver_runs':0,'new_real_user_approvals':0,'manual_review':'pending'}
    save(folder/'build-manifest.json',manifest)
    if any(r['export_check']!='passed' for r in results):raise RuntimeError('PDF/log/label/font checks failed; inspect build-manifest')
    print(json.dumps({'folder':str(folder),'compiler':compiler_version,'documents':[{k:r[k] for k in ('name','export_check','equations','symbols','pages')} for r in results],'rod_max_m':numerical['rod_max_m'],'derivative_max':numerical['derivative_max_m2_per_s']},ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--compiler',type=Path,default=ROOT/'stage-c-plus/tools/tectonic.exe');p.add_argument('--qa-tools',type=Path);args=p.parse_args();build(args.output,args.compiler,args.qa_tools)
