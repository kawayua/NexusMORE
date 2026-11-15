"""Render/check final paper layouts; scientific and user approval remain separate."""
import argparse,hashlib,json,re,zipfile
from pathlib import Path
import fitz
from PIL import Image,ImageDraw
from docx import Document


def check(folder):
    qa=folder/'qa';qa.mkdir(exist_ok=True);ast=json.loads((folder/'build/source-ast.json').read_text(encoding='utf-8'))
    def text(n):
        if isinstance(n,dict):
            if n.get('t')=='Str':return n['c']
            if n.get('t') in ['Math','Image']:return ''
            return ''.join(text(v) for v in n.values())
        return ''.join(map(text,n)) if isinstance(n,list) else ''
    def cn(s):return ''.join(re.findall('[\u4e00-\u9fff]',s))
    blocks=[cn(text(b)) for b in ast['blocks'] if b['t'] in ['Para','Header'] and len(cn(text(b)))>3]
    result={}
    for kind,path in [('latex',folder/'paper.pdf'),('word',qa/'word-render.pdf')]:
        doc=fitz.open(path);pages=[];body=''
        for i,page in enumerate(doc,1):
            page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(qa/f'{kind}-{i:02}.png')
            body+=page.get_text(clip=fitz.Rect(0,50,page.rect.width,page.rect.height-45))
            spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans'] if s['text'].strip()]
            outside=[s['text'] for s in spans if s['bbox'][0]<-1 or s['bbox'][1]<-1 or s['bbox'][2]>page.rect.width+1 or s['bbox'][3]>page.rect.height+1]
            pages.append({'page':i,'characters':len(page.get_text()),'min_font_pt':min(s['size'] for s in spans),'outside':outside})
        result[kind]={'pages':pages,'missing_chinese_source_paragraphs':[value for value in blocks if value not in cn(body)],'source_paragraphs_checked':len(blocks),'all_15_figures_referenced':all('图'+str(i) in body.replace(' ','') for i in range(1,16))}
        for i in range(0,len(pages),2):
            images=[Image.open(qa/f'{kind}-{j+1:02}.png').convert('RGB') for j in range(i,min(i+2,len(pages)))];sheet=Image.new('RGB',(sum(im.width for im in images),max(im.height for im in images)+25),'#dddddd');draw=ImageDraw.Draw(sheet);x=0
            for j,im in enumerate(images):draw.text((x+10,5),f'{kind} page {i+j+1}',fill='black');sheet.paste(im,(x,25));x+=im.width
            sheet.save(qa/f'{kind}-sheet-{i//2+1:02}.png')
            for im in images:im.close()
        doc.close()
    log=(folder/'paper.log').read_text(encoding='utf-8',errors='replace');result['latex_log_failures']=[line for line in log.splitlines() if any(x in line for x in ['Missing character','Overfull','undefined','Undefined control'])]
    w=Document(folder/'paper.docx');result['word_structure']={'images':len(w.inline_shapes),'scientific_tables':len(w.tables),'native_math':len(w.element.xpath('//m:oMath'))}
    catalog=json.loads((folder/'figure-catalog.json').read_text(encoding='utf-8'));expected={f['files']['png']['sha256'] for f in catalog['figures'] if f['formal']}
    with zipfile.ZipFile(folder/'paper.docx') as z:actual={hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('word/media/')}
    result['word_original_image_hashes_match']=expected==actual
    result['status']='passed' if not result['latex_log_failures'] and expected==actual and all(not p['outside'] and p['min_font_pt']>=5 for k in ['latex','word'] for p in result[k]['pages']) and all(not result[k]['missing_chinese_source_paragraphs'] and result[k]['all_15_figures_referenced'] for k in ['latex','word']) else 'failed'
    (qa/'content-layout-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'pages':{k:len(result[k]['pages']) for k in ['latex','word']},'minimum_font':{k:min(p['min_font_pt'] for p in result[k]['pages']) for k in ['latex','word']},'missing_source_paragraphs':{k:len(result[k]['missing_chinese_source_paragraphs']) for k in ['latex','word']},'word_structure':result['word_structure']}))
    if result['status']!='passed':raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);check(p.parse_args().folder)
