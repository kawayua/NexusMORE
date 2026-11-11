"""Python-only D4 candidate figures from frozen numerical arrays and verified inputs."""
import argparse,json,math,hashlib,platform
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon,Circle
from matplotlib.collections import PatchCollection
from matplotlib.text import Text
from PIL import Image
import fitz
from modelcrew.config import ROOT
from modelcrew.collaboration import sha_file
from modelcrew.full_numerics import load_arrays

BLUE='#406A8A';ORANGE='#BE803D';GRAY='#77818B';LIGHT='#E9EDF1'
PARAMS={'head_length_m':3.41,'body_length_m':2.2,'width_m':.3,'hole_offset_m':.275,'hole_diameter_m':.055}
SPECS=[
 ('raw-1','raw','板凳实体与孔位','题面长度、宽度和孔位如何构成2.86 m与1.65 m的中心距？','schematic-led composite','题面已核验尺寸；几何示意，不作碰撞证据'),
 ('raw-2','raw','任务采样与把手索引','301个时刻和224个把手如何对应题目要求的输出？','quantitative grid','契约时间轴与节点定义；不是观测样本'),
 ('raw-3','raw','初态与盘入方向','初始龙头位于第16圈正x轴，链条怎样沿螺线外侧排列？','quantitative grid','t=0真实求解位置与实体几何重建'),
 ('process-1','process','全时刻几何与弧长误差','301个时刻的杆长和弧长误差是否满足既定容差？','quantitative grid','每时刻最大杆长误差、独立积分误差与验收阈值'),
 ('process-2','process','速度差分步长核验','内部中心差分与端点单侧差分在不同步长下是否符合速度容差？','quantitative grid','三个实际步长误差；不要求严格单调下降'),
 ('process-3','process','求根括区与速度分母裕量','真实计算中首根括区和速度递推是否远离当前保护阈值？','quantitative grid','每时刻最小括区上端残差和最小分母；非全局安全证明'),
 ('result-1','result','代表时刻位置与实体轮廓','0至300 s的六个指定时刻呈现怎样的盘入演化？','quantitative grid','六时刻真实位置；同尺度总览；不是碰撞判定'),
 ('result-2','result','代表把手速率','沿链不同把手速率怎样随时间变化？','quantitative grid','指定把手真实速率；只有龙头被规定为1 m/s'),
 ('result-3','result','终态龙头局部与速度方向','t=300 s龙头附近的实体、孔位和速度方向怎样对应？','quantitative grid','局部实体几何和真实速度矢量；箭长=0.6 s乘速度')]


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):
    def native(value):
        if isinstance(value,np.generic):return value.item()
        raise TypeError('Unsupported JSON value')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=native),encoding='utf-8')


def bench_patches(pos):
    shapes=[]
    for i in range(len(pos)-1):
        a=pos[i];b=pos[i+1];u=(b-a)/np.linalg.norm(b-a);n=np.array([-u[1],u[0]])
        start=a-PARAMS['hole_offset_m']*u;end=b+PARAMS['hole_offset_m']*u
        shapes.append(Polygon(np.array([start-.15*n,end-.15*n,end+.15*n,start+.15*n]),closed=True))
    return shapes


def draw_geometry(ax,pos, *,holes=False,emphasize_head=True):
    patches=bench_patches(pos)
    ax.add_collection(PatchCollection(patches,facecolor=LIGHT,edgecolor=GRAY,linewidth=.35,zorder=2))
    if emphasize_head and patches:ax.add_patch(Polygon(patches[0].get_xy(),facecolor='#D7E2EC',edgecolor=BLUE,linewidth=.8,zorder=3))
    if holes:
        for p in pos:ax.add_patch(Circle(p,PARAMS['hole_diameter_m']/2,fill=False,edgecolor=BLUE,linewidth=.55,zorder=4))
    else:ax.plot(pos[:,0],pos[:,1],'.',color=BLUE,ms=1.2,zorder=4)
    ax.set_aspect('equal');ax.set_xlabel('x (m)');ax.set_ylabel('y (m)')


def source_geometry(folder,contract):
    source=next(i for i in contract['inputs'] if i['role']=='problem_statement')
    if sha_file(source['path'])!=source['sha256']:raise ValueError('Original statement changed')
    with fitz.open(source['path']) as document:text='\n'.join(p.get_text() for p in document)
    required=['341 cm','220 cm','30 cm','5.5 cm','27.5 cm']
    if any(x not in text for x in required):raise ValueError('Physical geometry source cannot be verified')
    first=text.find('341 cm')
    evidence={'source_sha256':source['sha256'],'physical_dimensions':PARAMS,'verified_required_text':required,'excerpt':text[max(0,first-90):first+230],
        'interpretation':'Hole center positions from solved handles; rectangles extend 0.275 m beyond end hole centers, width0.30 m. Adjacent shared handle holes represented as circles. Planar rendering is not collision validation.'}
    write(folder/'geometry-provenance.json',evidence)


def render(folder, only=None):
    meta=read(folder/'run.json');contract=read(folder/'contract.json');arrays=load_arrays(folder/'output/trajectories.npz')
    numeric=read(folder/'independent-numerics.json')
    if not numeric['passed']:raise ValueError('Validated full data required before plotting')
    directory=folder/'figures-v5';directory.mkdir(exist_ok=False)
    previous=read(folder/'figure-manifest.json') if only else None
    previous_qa=read(folder/'figure-qa.json') if only else None
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Microsoft YaHei','DejaVu Sans'],
        'font.size':8,'axes.titlesize':8,'axes.labelsize':8,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':7,
        'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,
        'axes.linewidth':.7,'lines.linewidth':1.1,'savefig.facecolor':'white','figure.facecolor':'white','axes.unicode_minus':False})
    source_geometry(folder,contract)
    contracts=[]
    for key,category,title,question,archetype,evidence in SPECS:
        contracts.append({'figure_id':key,'category':category,'title':title,'question':question,'claim_status':'validated_data_ready_for_independent_P2',
            'archetype':archetype,'backend':'Python/matplotlib','formats':['png','pdf','svg'],'dpi':300,'width_mm':183,
            'source_arrays_sha256':sha_file(folder/'output/trajectories.npz'),'source_contract_sha256':meta['contract_sha256'],
            'execution_id':meta['execution_id'],'result_revision':meta['result_revision'],'evidence':evidence,
            'statistics':'Deterministic 301 times x224 handles; no replicates, no CI/error bars; indicated maxima are exact aggregates.',
            'review_risks':['Not collision or force/structural verification','Initial reconstructed states are not raw measurements'],
            'selection_status':'candidate_pending_user_selection'})
    write(folder/'figure-contracts.json',{'figures':contracts,'configuration_sha256':sha_file(folder/'configuration.json')})
    p=arrays['position_m'];v=arrays['velocity_m_s'];times=arrays['time_s'];series=numeric['series'];results=[];qa=[]
    for spec in contracts:
        key=spec['figure_id']
        if only and key!=only:
            old=next(item for item in previous['figures'] if item['figure_id']==key)
            old.setdefault('renderer_code_sha256',previous['source_script_sha256'])
            results.append(old);qa.append(next(item for item in previous_qa['checks'] if item['figure_id']==key));continue
        height=110 if key=='result-1' else 85
        fig=plt.figure(figsize=(183/25.4,height/25.4))
        fig.subplots_adjust(left=.105,right=.975,bottom=.16,top=.88,wspace=.38,hspace=.52)
        comparison_groups=[]
        if key=='raw-1':
            ax=fig.add_subplot(111)
            for y,length,gap,label in [(1,3.41,2.86,'龙头'),(0,2.2,1.65,'龙身 / 龙尾')]:
                ax.add_patch(Polygon([[0,y-.15],[length,y-.15],[length,y+.15],[0,y+.15]],fc=LIGHT,ec=BLUE,lw=.8))
                for x in [.275,length-.275]:ax.add_patch(Circle([x,y],.055/2,fill=False,ec=BLUE,lw=.8))
                ax.text(length+.15,y,label,va='center')
                ax.annotate('',(.275,y+.25),(length-.275,y+.25),arrowprops={'arrowstyle':'<->','color':GRAY,'lw':.7})
                ax.text(length/2,y+.29,f'孔中心距 {gap:.2f} m',ha='center',va='bottom')
                ax.text(length/2,y-.29,f'全长 {length:.2f} m',ha='center',va='top')
            ax.text(4.25,.5,'宽度 0.30 m\n孔直径 0.055 m\n孔心至板端 0.275 m',ha='center',va='center',linespacing=1.7)
            ax.set(xlim=(-.18,5.0),ylim=(-.65,1.65));ax.set_aspect('equal');ax.axis('off')
            fig.text(.105,.92,'按题面尺寸重建的平面示意',fontsize=8)
        elif key=='raw-2':
            axes=fig.subplots(2,1);comparison_groups=[axes.tolist()]
            for ax,count,label,selected in [(axes[0],301,'时间 t (s)',[0,60,120,180,240,300]),(axes[1],224,'把手编号（1为龙头，224为龙尾后把手）',[0,1,51,101,151,201,223])]:
                grid=np.arange(count);ax.vlines(grid,0,.15,color=GRAY,lw=.45);ax.scatter(selected,np.full(len(selected),.22),s=14,color=ORANGE,zorder=3)
                ax.set(ylim=(-.1,.5),xlim=(-3,count+2),yticks=[],xlabel=label);ax.spines['left'].set_visible(False)
                if count==224:ax.set_xticks([0,51,101,151,201,223],['1','52','102','152','202','224'])
                ax.text(.01,.76,f'{count} 个输出点',transform=ax.transAxes)
        elif key=='raw-3':
            ax=fig.add_subplot(111);draw_geometry(ax,p[0])
            ax.plot([0,8.8],[0,0],color=ORANGE,lw=.8);ax.text(4.4,.35,'初始半径 8.8 m',ha='center')
            ax.scatter([8.8],[0],s=18,c=ORANGE,zorder=5)
            ax.text(-2,4,'龙头：顺时针盘入',ha='center')
            ax.annotate('',(8.2*math.cos(-.6),8.2*math.sin(-.6)),(8.2*math.cos(-.15),8.2*math.sin(-.15)),arrowprops={'arrowstyle':'->','color':BLUE,'connectionstyle':'arc3,rad=-0.2'})
            ax.set(xlim=(-13.5,13.5),ylim=(-13.5,13.5));ax.set_xticks([-10,0,10]);ax.set_yticks([-10,0,10])
        elif key=='process-1':
            axes=fig.subplots(2,1,sharex=True);comparison_groups=[axes.tolist()]
            for ax,data,threshold,label in [(axes[0],series['rod_distance_error_m'],1e-8,'最大杆长误差 (m)'),(axes[1],series['head_arc_error_m'],1e-8,'龙头弧长误差 (m)')]:
                ax.semilogy(times,np.maximum(data,1e-16),color=BLUE);ax.axhline(threshold,c=ORANGE,ls='--',lw=.8,label='验收阈值')
                ax.set(ylabel=label,ylim=(3e-17,3e-8));ax.legend(loc='upper right')
            axes[-1].set_xlabel('时间 t (s)');spec['display_transform']='Exact zeros shown at1e-16 m floor on logarithmic axes; original values retained.'
        elif key=='process-2':
            ax=fig.add_subplot(111);hs=np.array([.01,.001,.0001]);fd=numeric['finite_difference']
            ax.loglog(hs,[fd[str(h)]['interior_max_m_s'] for h in hs],'-o',c=BLUE,ms=4,label='内部：中心差分')
            ax.loglog(hs,[fd[str(h)]['endpoint_max_m_s'] for h in hs],'--s',c=ORANGE,ms=4,label='端点：二阶单侧差分')
            ax.axhline(1e-5,c=GRAY,ls=':',label='h=0.001 s 的验收阈值');ax.invert_xaxis()
            ax.set(xlabel='差分步长 h (s)',ylabel='最大速度向量误差 (m/s)');ax.legend(loc='upper right')
        elif key=='process-3':
            axes=fig.subplots(2,1,sharex=True);comparison_groups=[axes.tolist()]
            axes[0].plot(times,series['min_denominator_m2'],color=BLUE);axes[0].set_ylabel('最小 |D| (m²)')
            axes[0].text(.02,.13,'中止阈值：1e-10 m²（低于图示范围）',transform=axes[0].transAxes,fontsize=7)
            axes[1].plot(times,series['min_bracket_upper_m2'],color=ORANGE);axes[1].set(ylabel='最小 F(π) (m²)',xlabel='时间 t (s)')
        elif key=='result-1':
            axes=fig.subplots(2,3);comparison_groups=[list(axes.ravel())]
            for ax,t in zip(axes.ravel(),[0,60,120,180,240,300]):
                draw_geometry(ax,p[t]);ax.set(xlim=(-13.5,13.5),ylim=(-13.5,13.5),xticks=[-10,0,10],yticks=[-10,0,10]);ax.set_title(f't = {t} s',pad=4)
                ax.tick_params(labelsize=6)
            fig.subplots_adjust(left=.075,right=.985,bottom=.1,top=.91,wspace=.38,hspace=.55)
        elif key=='result-2':
            ax=fig.add_subplot(111)
            styles=['-','--','-.',':','-','--','-.'];colors=[BLUE,ORANGE,GRAY,'#866B91','#526C61','#A46B74','#5A7785']
            for node,style,color in zip([0,1,51,101,151,201,223],styles,colors):
                ax.plot(times,arrays['speed_m_s'][:,node],ls=style,c=color,lw=1,label='龙头' if node==0 else ('龙尾后把手' if node==223 else f'把手 {node+1}'))
            ax.set(xlabel='时间 t (s)',ylabel='速率 (m/s)');ax.legend(loc='lower left',ncol=2)
            fig.text(.105,.93,'速率差异较小；纵轴局部放大，非零起点',fontsize=8)
        else:
            ax=fig.add_subplot(111);local=p[300,:4];draw_geometry(ax,local,holes=True)
            ax.quiver(local[:,0],local[:,1],.6*v[300,:4,0],.6*v[300,:4,1],angles='xy',scale_units='xy',scale=1,color=ORANGE,width=.004,zorder=5)
            for i,point in enumerate(local):ax.annotate(str(i+1),point,xytext=(4,4),textcoords='offset points',fontsize=7)
            ax.set(xlim=(local[:,0].min()-.8,local[:,0].max()+.8),ylim=(local[:,1].min()-.8,local[:,1].max()+.8))
            fig.text(.105,.93,'t = 300 s；箭长为速度乘 0.6 s',fontsize=8)
        fig.canvas.draw();renderer=fig.canvas.get_renderer();width,heightpx=fig.canvas.get_width_height()
        text_sizes=[t.get_fontsize() for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
        outside=[]
        for text in fig.findobj(Text):
            if not text.get_visible() or not text.get_text():continue
            box=text.get_window_extent(renderer)
            if box.x0 < -1 or box.y0 < -1 or box.x1 > width+1 or box.y1 > heightpx+1:outside.append(text.get_text())
        alignments=[]
        for group in comparison_groups:
            boxes=[ax.get_window_extent(renderer) for ax in group]
            widths=[b.width*72/fig.dpi for b in boxes];heights=[b.height*72/fig.dpi for b in boxes]
            alignments.append({'max_width_difference_pt':max(widths)-min(widths),'max_height_difference_pt':max(heights)-min(heights),'passed':max(widths)-min(widths)<=1.5 and max(heights)-min(heights)<=1.5})
        paths={}
        for fmt in ['png','pdf','svg']:
            target=directory/(key+'.'+fmt);fig.savefig(target,dpi=300);paths[fmt]=target.relative_to(ROOT).as_posix()
        pdf=fitz.open(directory/(key+'.pdf'));spans=[s for page in pdf for block in page.get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for s in line['spans'] if s['text'].strip()]
        minpdf=min(s['size'] for s in spans)
        # The exported PDF contains only actually drawn glyphs; Matplotlib's
        # object tree also retains ticks outside the view that were never drawn.
        bounds=pdf[0].rect
        outside=[span['text'] for span in spans if span['bbox'][0]<-.5 or span['bbox'][1]<-.5 or span['bbox'][2]>bounds.width+.5 or span['bbox'][3]>bounds.height+.5]
        pdf.close()
        qa.append({'figure_id':key,'min_declared_text_pt':min(text_sizes),'min_pdf_span_text_pt':minpdf,'text_outside_canvas':outside,'alignment':alignments,
            'editable_svg_text':'<text' in (directory/(key+'.svg')).read_text(encoding='utf-8'),'passed':not outside and minpdf>=5 and all(a['passed'] for a in alignments),
            'collision_audit':'manual visual review still required; no automatic line/text collision proof'})
        spec.update({'files':paths,'height_mm':fig.get_size_inches()[1]*25.4,'caption':spec['title']+'。'+spec['evidence']+'；确定性结果，不设置信区间。',
            'file_hashes':{fmt:sha_file(ROOT/path) for fmt,path in paths.items()},'renderer_code_sha256':sha_file(Path(__file__)),'recommended_for_draft':key!='raw-2'})
        results.append(spec);plt.close(fig)
    # Same-backend overview is a QA convenience, not a tenth candidate figure.
    contact,axes=plt.subplots(3,3,figsize=(13.5,10))
    for ax,item in zip(axes.ravel(),results):
        image=Image.open(ROOT/item['files']['png']);ax.imshow(image);ax.set_title(item['figure_id']+' '+item['title'],fontsize=10);ax.axis('off')
    contact.tight_layout(pad=1);contact.savefig(directory/'contact-sheet.png',dpi=150);plt.close(contact)
    write(folder/'figure-manifest.json',{'figures':results,'counts':{c:sum(i['category']==c for i in results) for c in ['raw','process','result']},
        'logical_count':len(results),'recommended_draft_count':sum(i['recommended_for_draft'] for i in results),'user_selection':'pending',
        'backend':'Python/matplotlib','source_script_sha256':sha_file(Path(__file__)),'source_arrays_sha256':sha_file(folder/'output/trajectories.npz')})
    write(folder/'figure-qa.json',{'passed':all(q['passed'] for q in qa),'checks':qa,'png_dpi':300,'python_backend_exclusive':True,
        'manual_visual_review':'pending','unimplemented_audits':['General text-line collision detector','Full manuscript placement W2']})
    write(folder/'figure-contracts.json',{'figures':results,'configuration_sha256':sha_file(folder/'configuration.json')})
    print(json.dumps({'figures':len(results),'mechanical_qa_passed':all(q['passed'] for q in qa)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--only',choices=[item[0] for item in SPECS]);args=parser.parse_args()
    folder=args.run.resolve()
    if folder.parent!=(ROOT/'stage-d/runs/full').resolve():raise ValueError('Unexpected full run path')
    render(folder,args.only)
