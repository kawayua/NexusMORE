"""Probe ONE installed optional group using synthetic engineering fixtures only.

Run with venv Python -I outside the repository. No model/service/native Office calls.
"""
import argparse
import copy
import hashlib
import importlib
import importlib.metadata as metadata
import importlib.util
import json
import os
from pathlib import Path
import site
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def write(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)

def reject(call, phrase):
    try:call()
    except ValueError as exc:
        if phrase.lower() not in str(exc).lower():raise
        return {'status':'rejected_as_required','error':str(exc)}
    raise AssertionError('Invalid probe was accepted: '+phrase)

def documents(out):
    import fitz
    from docx import Document
    from openpyxl import Workbook
    from modelcrew import document_tools as dt, office_tools as office
    from modelcrew.pdf_checks import inspect_pdf,verify_pdf_report,audit_pdf_tree
    doctor=office.doctor(out/'office-doctor');assert doctor['status']=='passed'
    assert all(not s['missing_dependencies'] for s in dt.available_tools().values())
    source=out/'synthetic.docx';doc=Document();doc.add_heading('Synthetic installation fixture',level=1);doc.add_paragraph('Engineering input, not a modeling paper.')
    # python-docx's default template omits a schema-required zoom percent.
    # Supply valid fixture input; do not weaken the validator or repair user files.
    from docx.oxml.ns import qn
    zoom=doc.settings.element.find(qn('w:zoom'))
    if zoom is not None:zoom.set(qn('w:percent'),'100')
    doc.save(source)
    original=dt.sha(source)
    profile=office.profile(out,source,out/'profile');assert profile['status']=='passed' and profile['formal_approval'] is False
    office.unpack(out,source,out/'docx-workspace');roundtrip=office.pack(out,out/'docx-workspace',out/'docx-roundtrip')
    assert roundtrip['member_bytes_preserved'] and office.parts(source)==office.parts(out/'docx-roundtrip/roundtrip.docx')
    structure=dt.run('docx_validate',source,out/'docx-validation');assert structure['status']=='passed',structure
    (out/'docx-workspace/word/document.xml').write_bytes(b'edited engineering negative fixture')
    edited=reject(lambda:office.pack(out,out/'docx-workspace',out/'edited-pack'),'edited')
    assert dt.sha(source)==original
    workbook=Workbook();sheet=workbook.active;sheet.title='observations';sheet.append(['index','value'])
    for i in range(1,36):sheet.append([i,i*i])
    xlsx=out/'synthetic.xlsx';workbook.save(xlsx);workbook.close()
    values=dt.read_spreadsheet(xlsx,expected_rows={'observations':36})
    assert values['complete'] and values['sheets'][0]['rows'][-1]==[35,1225] and values['formula_values_recalculated'] is False
    read=dt.run('xlsx_read',xlsx,out/'xlsx-read');assert read['status']=='passed'
    office.unpack(out,xlsx,out/'xlsx-workspace');xround=office.pack(out,out/'xlsx-workspace',out/'xlsx-roundtrip');assert xround['member_bytes_preserved']
    pdf=out/'synthetic-three-pages.pdf';font=fitz.Font('helv')
    with fitz.open() as document:
        for i in range(3):
            page=document.new_page(width=360,height=240);page.insert_font(fontname='FixtureFont',fontbuffer=font.buffer)
            page.insert_text((30,45),'Synthetic document page '+str(i+1)+' of 3',fontsize=12,fontname='FixtureFont')
            page.insert_text((30,75),'Engineering installation probe; no paper approval.',fontsize=10,fontname='FixtureFont')
            if i==0:
                widget=fitz.Widget();widget.field_name='probe_value';widget.field_type=fitz.PDF_WIDGET_TYPE_TEXT;widget.field_value='7';widget.rect=fitz.Rect(30,100,120,125);page.add_widget(widget)
        document.save(pdf)
    reports={}
    for tool in ['pdf_fields','pdf_structure']:
        reports[tool]=dt.run(tool,pdf,out/tool);assert reports[tool]['status']=='passed',reports[tool]
    fields=json.loads((out/'pdf_fields/fields.json').read_text(encoding='utf-8'));assert any(f['field_id']=='probe_value' for f in fields)
    pages=inspect_pdf(pdf,out/'pdf-pages');verify_pdf_report(pdf,out/'pdf-pages',pages);assert pages['page_count']==3
    omitted=copy.deepcopy(pages);omitted['pages'].pop()
    missing=reject(lambda:verify_pdf_report(pdf,out/'pdf-pages',omitted),'coverage')
    tree=audit_pdf_tree(out,out.parent/'documents-pdf-audit');assert tree['status']=='passed',tree
    return {'doctor':doctor,'docx_profile':'passed','docx_structural_validation':structure,'roundtrip_member_identity':True,'edited_workspace':edited,'xlsx_rows':36,'xlsx_complete':True,'formula_recalculation_registered':False,'pdf_field_count':len(fields),'pdf_tools':reports,'pdf_page_count':3,'omitted_last_page':missing,'all_generated_pdfs':tree,'native_word_render':'NOT_RUN','formal_approval':False}

def figures(out):
    os.environ['MPLCONFIGDIR']=str(out/'matplotlib-cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    from modelcrew.figure_data import read_data,profile_numeric
    from modelcrew.figure_tools import export_figure
    from modelcrew.pdf_checks import sha,audit_pdf_tree
    csv=out/'synthetic.csv';csv.write_text(chr(10).join(['time,value','0,1','1,3','2,2'])+chr(10),encoding='utf-8')
    code=out/'probe-source.py';code.write_text('# Synthetic engineering fixture only',encoding='utf-8')
    data=read_data(csv,header=True,expected_rows=3);profile=profile_numeric(data,[0,1],units={0:'s',1:'m'})
    fig,ax=plt.subplots(figsize=(4,3),layout='constrained');ax.plot([float(r[0]) for r in data['rows']],[float(r[1]) for r in data['rows']],marker='o');ax.set(xlabel='Time (s)',ylabel='Value (m)',title='Synthetic engineering fixture')
    args={'figure_id':'synthetic-installation','binding':{'task_id':'engineering-probe','contract_version':1,'contract_sha256':'a'*64,'execution_id':'optional-group-probe','result_revision':1},'inputs':[{'path':str(csv),'sha256':sha(csv)}],'code':{'path':str(code),'sha256':sha(code)},'parameters':{'synthetic':True}}
    before=dict(matplotlib.rcParams)
    first=export_figure(fig,out/'export',**args);second=export_figure(fig,out/'repeat-export',**args)
    assert dict(matplotlib.rcParams)==before and first['status']=='passed' and first['visual_review']=='PENDING'
    for fmt in ['png','pdf','svg']:assert first['files'][fmt]['sha256']==second['files'][fmt]['sha256'],fmt
    with Image.open(out/'export/synthetic-installation.png') as image:assert image.size==(1200,900)
    with Image.open(out/'export/synthetic-installation-grayscale.png') as image:assert image.mode=='L'
    changed=copy.deepcopy(args);changed['inputs'][0]['sha256']='0'*64
    bad=reject(lambda:export_figure(fig,out/'bad-input',**changed),'changed')
    ax.title.set_fontsize(3)
    small=reject(lambda:export_figure(fig,out/'too-small',**args),'below 5')
    plt.close(fig)
    tree=audit_pdf_tree(out,out.parent/'figures-pdf-audit');assert tree['status']=='passed',tree
    return {'source_rows':data['row_count'],'numeric_profile':profile,'three_formats':'passed','deterministic_reexport':True,'png_dimensions':[1200,900],'png_dpi':300,'grayscale_separate':True,'global_plot_settings_restored':True,'changed_input':bad,'small_text':small,'all_generated_pdfs':tree,'visual_review':'PENDING','independent_review':'NOT_RUN','formal_approval':False}

def evidence(out):
    import numpy as np
    from scipy.integrate import quad
    from scipy.optimize import brentq
    from scipy.stats import ttest_1samp
    import sympy as sp
    import modelcrew.solver_validation
    import modelcrew.full_numerics
    from modelcrew.figure_data import profile_numeric
    x=sp.symbols('x',real=True);exact=sp.integrate(x*x,(x,0,1));assert exact==sp.Rational(1,3)
    integral,error=quad(lambda t:t*t,0,1,epsabs=1e-12,epsrel=1e-12);assert abs(integral-float(exact))<1e-12
    root=brentq(lambda t:t*t-2,1,2,xtol=1e-14);residual=abs(root*root-2);assert residual<1e-12
    A=np.array([[3.,1.],[1.,2.]]);b=np.array([9.,8.]);solution=np.linalg.solve(A,b);assert np.max(np.abs(A@solution-b))<1e-12 and np.allclose(solution,[2,3],rtol=0,atol=1e-12)
    test=ttest_1samp([1,2,3,4,5],popmean=3);assert abs(test.statistic)<1e-15 and abs(test.pvalue-1)<1e-15
    assert sp.simplify(sp.sqrt(2)**2-2)==0
    bad=reject(lambda:profile_numeric({'rows':[['nan']],'column_count':1,'row_count':1,'source_sha256':'synthetic'},[0],units={0:'dimensionless'}),'finite')
    return {'symbolic_integral':str(exact),'quadrature':{'value':integral,'reported_error':error,'absolute_error':abs(integral-float(exact))},'root':{'value':root,'residual':residual},'linear_solution':solution.tolist(),'linear_residual':float(np.max(np.abs(A@solution-b))),'one_sample_t_test':{'statistic':float(test.statistic),'pvalue':float(test.pvalue),'sample_count':5,'assumptions':'Synthetic library identity probe only; no inference on user data'},'nonfinite_input':bad,'historical_validator_module_import':'passed','historical_benchmark_execution':'NOT_RUN','automatic_proof_or_model_gate':'NOT_CLAIMED'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--group',choices=['documents','figures','evidence'],required=True);p.add_argument('--wheel',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    import modelcrew
    from modelcrew.package_resources import verify_resources
    assert sys.prefix!=sys.base_prefix and site.ENABLE_USER_SITE is False
    assert str(ROOT) not in sys.path and str(ROOT/'src') not in sys.path and not Path.cwd().is_relative_to(ROOT)
    package=Path(modelcrew.__file__).parent;assert package.is_relative_to(Path(sys.prefix))
    assert 'include-system-site-packages = false' in (Path(sys.prefix)/'pyvenv.cfg').read_text(encoding='utf-8')
    checked=0
    with zipfile.ZipFile(a.wheel) as z:
        for n in z.namelist():
            if n.startswith('modelcrew/'):
                assert z.read(n)==(package/n.removeprefix('modelcrew/')).read_bytes(),n
                checked+=1
    absent={'documents':['matplotlib','scipy','sympy'],'figures':['scipy','sympy','docx'],'evidence':['matplotlib','fitz','docx']}[a.group]
    for name in [*absent,'pytest']:assert importlib.util.find_spec(name) is None,name
    a.output.mkdir(parents=True,exist_ok=False)
    resources=verify_resources();assert resources['status']=='passed'
    result=globals()[a.group](a.output)
    checked_pip=subprocess.run([sys.executable,'-I','-m','pip','check'],capture_output=True,text=True,check=True)
    report={'status':'passed','group':a.group,'scope':'isolated installed dependency-group engineering probe; no paper, independent gate, user approval or native toolchain acceptance','python':sys.version,'executable':sys.executable,'cwd':str(Path.cwd()),'package_path':str(package),'system_site_packages':False,'user_site_enabled':False,'unrelated_dependencies_absent':absent+['pytest'],'candidate_files_compared':checked,'resources':resources,'checks':result,'pip_check':checked_pip.stdout.strip(),'distributions':sorted([{'name':d.metadata['Name'],'version':d.version} for d in metadata.distributions()],key=lambda d:d['name'].lower()),'visual_review':'PENDING' if a.group!='evidence' else 'NOT_APPLICABLE','independent_review':'NOT_RUN','formal_approval':False}
    write(a.output/'probe.json',report)
    print(json.dumps({'status':'passed','group':a.group,'report':str(a.output/'probe.json')}))

if __name__=='__main__':main()
