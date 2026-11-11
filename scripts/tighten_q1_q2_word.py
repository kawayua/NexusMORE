from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
p=Path(__file__).resolve().parents[1]/'output/paper/q1-q2-20261109-v1/paper.docx'
doc=Document(p)
for row in doc.tables[8].rows:
    for cell in row.cells:
        for side in ('top','bottom'):
            for node in cell._tc.xpath('./w:tcPr/w:tcMar/w:'+side):node.set(qn('w:w'),'30')
doc.save(p)
