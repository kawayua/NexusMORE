from pathlib import Path
import re,json,hashlib,subprocess,os
from docx import Document
root=Path(__file__).resolve().parents[1]
out=root/'output/paper/q1-q2-20261109-v1'
tex=out/'paper.tex'
s=tex.read_text(encoding='utf-8')
# Preserve numbers and wording; use a ragged paragraph for the long exact bracket.
pat=r'(计算得到首次接触时间为412\.473838.*?)(?=\n\n)'
s,n=re.subn(pat,lambda m:r'{\raggedright\parindent=2em '+m[1]+r'\par}',s,flags=re.S)
assert n==1
# These nine modest tables fit on a page. Keep each caption and complete table together.
pat=r'(表\d+[^\n]*\n\n)(\\begingroup\\small\s*\\begin\{longtable\}.*?\\end\{longtable\}\s*\\endgroup)'
def atomic(m):
    block=m[2].replace(r'\begin{longtable}',r'\begin{tabular}').replace(r'\end{longtable}',r'\bottomrule\end{tabular}')
    block=re.sub(r'\\endhead\s*\\bottomrule\\noalign\{\}\s*\\endlastfoot','',block)
    return r'\par\medskip\noindent\begin{minipage}{\linewidth}'+ '\n'+m[1]+block+'\n'+r'\end{minipage}\par\medskip'
s,count=re.subn(pat,atomic,s,flags=re.S)
print('atomic_tables',count)
assert count==8 # table2 has an intervening explanatory paragraph; handled below
# Table2 title + its short explanation remain with the table.
pat=r'(表2 问题二主要符号与单位\n\n.*?)(\\begingroup\\small\s*\\begin\{longtable\}.*?\\end\{longtable\}\s*\\endgroup)'
s,n=re.subn(pat,atomic,s,flags=re.S);assert n==1
tex.write_text(s,encoding='utf-8')
doc=Document(out/'paper.docx')
for table in doc.tables:
    for cell in table.rows[0].cells:
        for p in cell.paragraphs:p.paragraph_format.keep_with_next=True
    # Keep the first data row intact; subsequent rows may break between pages.
    for cell in table.rows[1].cells:
        for p in cell.paragraphs:p.paragraph_format.keep_together=True
doc.save(out/'paper.docx')
cache=root/'stage-c-plus/tex-cache'
cmd=[str(root/'stage-c-plus/tools/tectonic.exe'),'--untrusted','--keep-logs','--keep-intermediates','--outdir',str(out),str(tex)]
r=subprocess.run(cmd,capture_output=True,timeout=600,cwd=out,env={**os.environ,'TECTONIC_CACHE_DIR':str(cache),'TEMP':str(cache),'TMP':str(cache)})
(out/'build/latex-layout-final.log').write_bytes(r.stdout+b'\n'+r.stderr)
print('compile_returncode',r.returncode)
raise SystemExit(r.returncode)
