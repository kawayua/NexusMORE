"""Trusted D5 deliverable checks; manuscript self-check, not W2 independent review."""
import argparse,json,re
from pathlib import Path
import numpy as np
from modelcrew.config import ROOT
from modelcrew import writing_hand as wh
from modelcrew.full_numerics import load_arrays
from modelcrew.modeling_paper import validate_draft
from scripts.run_d4_full import workflow

def check(folder):
    with workflow() as w:state=wh.status(folder,w)
    folder=Path(folder);text=(folder/'单题论文-中文审阅稿.md').read_text(encoding='utf-8')
    arrays=load_arrays(ROOT/wh.read(folder/'run.json')['source_run']/'output/trajectories.npz')
    times=[0,60,120,180,240,300];indices=[0,1,51,101,151,201,223]
    labels=['龙头','第1节龙身','第51节龙身','第101节龙身','第151节龙身','第201节龙身','龙尾（后）']
    lines=text.splitlines();count=0;max_error={'position_m':0.,'speed_m_s':0.}
    for i,label in zip(indices,labels):
        for axis,axis_id in [('x',0),('y',1)]:
            prefix='| '+label+' '+axis+' |';matches=[x for x in lines if x.startswith(prefix)];assert len(matches)==1
            values=[float(x.strip()) for x in matches[0].strip('|').split('|')[1:]];assert len(values)==6
            err=float(np.max(np.abs(np.array(values)-arrays['position_m'][times,i,axis_id])))
            assert err<=5.00001e-7;max_error['position_m']=max(max_error['position_m'],err);count+=6
        prefix='| '+label+' |';matches=[x for x in lines if x.startswith(prefix)];assert len(matches)==1
        values=[float(x.strip()) for x in matches[0].strip('|').split('|')[1:]];assert len(values)==6
        err=float(np.max(np.abs(np.array(values)-arrays['speed_m_s'][times,i])))
        assert err<=5.00001e-7;max_error['speed_m_s']=max(max_error['speed_m_s'],err);count+=6
    assert count==126
    images=re.findall(r'!\[图(\d+) ',text);assert list(map(int,images))==list(range(1,10))
    assert r'\cos\theta,\ \sin\theta' in text and r'\\sin' not in text
    assert re.findall(r'\\tag\{(\d+)\}',text)==[str(i) for i in range(1,10)]
    assert text.count('{')==text.count('}') and all(line.count('$')%2==0 for line in lines)
    mechanics=validate_draft(folder/'单题论文-中文审阅稿.md',folder/'figure-catalog.json');assert mechanics['status']=='passed'
    assert state['state']['reviews']['manuscript']=='pending' and state['state']['reviews']['figure_selection']=='approved'
    return {'status':'passed','scope':'Trusted author-side value, source and Markdown checks; not independent W2 or formal rendering','markdown_sha256':wh.sha(folder/'单题论文-中文审阅稿.md'),'numeric_cells_checked':count,'table_max_rounding_error':max_error,'ordered_figures':9,'equation_numbers':9,'tables':5,'chinese_characters':len(re.findall(r'[\u4e00-\u9fff]',text)),'separate_reviews':state['state']['reviews'],'mechanical_report':mechanics}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=check(a.run);wh.new(a.output,r);print(json.dumps({k:v for k,v in r.items() if k not in ['separate_reviews','mechanical_report']},ensure_ascii=False,indent=2))
