"""Python-only evidence figures for the Q2 frozen full result."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib import font_manager
from scripts.run_q2_full import active
from scripts.run_d3_minimal import read,write
from scripts.validate_q2_full import corners
from modelcrew.collaboration import sha_file

def main():
    folder=active();v=read(folder/'validation.json')
    if not v['passed']:raise ValueError('validated data required')
    out=folder/'figures-v2';out.mkdir(exist_ok=False)
    with np.load(folder/'results/representative-states.npz',allow_pickle=False) as z:r={k:z[k].copy() for k in z.files}
    with np.load(folder/'results/terminal-state.npz',allow_pickle=False) as z:term={k:z[k].copy() for k in z.files}
    with np.load(folder/'results/continuous-certificate.npz',allow_pickle=False) as z:cert=z['segments'].copy()
    with np.load(folder/'results/contact-profile.npz',allow_pickle=False) as z:profile={k:z[k].copy() for k in z.files}
    e=v['first_contact_event'];pair=e['active_board_pairs'][0]
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42,'axes.unicode_minus':False,'savefig.facecolor':'white'})
    specs=[('raw-01','raw','板凳尺寸与孔位（示意）','题目尺寸定义完整矩形与孔中心距；孔位只作尺寸示意，碰撞体不扣孔。','representative-states.npz'),('raw-02','raw','初始实体外包络','初态几何由题目约束和已验证状态重建，不是实测或连续安全证明。','representative-states.npz'),('raw-03','raw','非相邻板对范围（规则示意）','已确认规则只检查上三角非相邻24531对，整对豁免相邻与自身。','representative-states.npz'),('process-01','process','连续证书时间分辨率','认证分段随局部几何难度自适应细化。','continuous-certificate.npz'),('process-02','process','全程分离证据下界','每个已认证时间段全部板对存在严格正投影分离下界。','continuous-certificate.npz'),('process-03','process','接触特征附近的间隙','活动板对的运动学延拓从分离进入重叠；首碰后的曲线只作数学诊断，不模拟冲击后真实运动，也不替代首事件证明。','contact-profile.npz'),('result-01','result','终止时刻整体位置','终止形态来自同一已验证运动学状态。','terminal-state.npz'),('result-02','result','首次接触局部几何','活动板对在有限边与角点发生接触。','terminal-state.npz'),('result-03','result','终止速率分布','各把手速率由约束微分递推，不能统一设为1。','terminal-state.npz')]
    contracts=[]
    for ident,cat,title,claim,source in specs:
        contracts.append({'figure_id':ident,'category':cat,'title':title,'claim':claim,'backend':'Python/matplotlib','archetype':'quantitative grid' if 'process' in ident or ident=='result-03' else 'image plate + quant','final_size_inches':[12,4.6] if ident=='result-01' else [7.2,6.2] if ident.startswith('raw') or ident in ['result-01','result-02'] else [7.2,4.4],'source_data':source,'source_sha256':sha_file(folder/'results'/source),'execution_id':folder.name,'result_revision':1,'contract_sha256':read(folder/'run.json')['contract_sha256'],'statistics':'deterministic computation; no confidence intervals','risk':'do not infer continuous safety from a drawing or sampled curve; coordinate enclosure is numerical, not statistical','candidate_selection':'pending_user'})
    write(out/'figure-contracts.json',{'backend':'Python','figures':contracts,'figure_count':9,'minimum_font_size_pt':9,'candidate_only':True})
    records=[]
    def export(fig,ax,contract):
        fig.tight_layout();fig.canvas.draw()
        if contract['figure_id']=='result-01':
            boxes=[a.get_window_extent().transformed(fig.dpi_scale_trans.inverted()) for a in fig.axes]
            if (max(b.y0 for b in boxes)-min(b.y0 for b in boxes))*72>1.5 or (max(b.y1 for b in boxes)-min(b.y1 for b in boxes))*72>1.5:raise ValueError('geometry panels misaligned')
        texts=[x for x in fig.findobj(matplotlib.text.Text) if x.get_visible() and x.get_text()]
        minimum=min(x.get_fontsize() for x in texts)
        if minimum<5:raise ValueError('font below minimum')
        for ext in ['png','pdf','svg']:fig.savefig(out/(contract['figure_id']+'.'+ext),dpi=300)
        records.append({**contract,'files':[{'path':out.name+'/'+contract['figure_id']+'.'+ext,'sha256':sha_file(out/(contract['figure_id']+'.'+ext))} for ext in ['png','pdf','svg']],'minimum_font_size_pt':minimum,'visual_inspection':'pending','panel_alignment':('same-scale three-panel geometry; checked axes edges within 1.5pt' if contract['figure_id']=='result-01' else 'not applicable: single panel'),'rendered':True})
        plt.close(fig)
    def geometry(ax,point,limit=True,highlight=None):
        verts,*_=corners(point);ax.add_collection(PolyCollection(verts,facecolors='#cad5df',edgecolors='#667788',linewidths=.35))
        if highlight is not None:
            ax.add_collection(PolyCollection(verts[highlight],facecolors=['#e9c88b','#86b5c6'],edgecolors='#333333',linewidths=1.1))
        ax.plot(point[:,0],point[:,1],'.',ms=1.2,color='#3d5263');ax.plot(point[0,0],point[0,1],'o',ms=4,color='#a36635')
        ax.set_aspect('equal');ax.set_xlabel('x / m');ax.set_ylabel('y / m')
        if limit:ax.set_xlim(-12.8,12.8);ax.set_ylim(-12.8,12.8)
    for spec in contracts:
        ident=spec['figure_id'];fig,ax=plt.subplots(figsize=spec['final_size_inches'])
        if ident=='raw-01':
            from matplotlib.patches import Rectangle
            for center,length,ell,label in [(0,3.41,2.86,'龙头'),(-1.1,2.2,1.65,'龙身 / 龙尾')]:
                ax.add_patch(Rectangle((-length/2,center-.15),length,.3,facecolor='#cad5df',edgecolor='#3d5263',lw=1))
                ax.plot([-ell/2,ell/2],[center,center],'o',ms=5,color='#a36635')
                ax.annotate('',(-length/2,center+.35),(length/2,center+.35),arrowprops={'arrowstyle':'<->','lw':.8})
                ax.text(0,center+.4,f'{label}：全长 {length:g} m',ha='center',va='bottom')
                ax.text(0,center-.4,f'孔距 {ell:g} m；端部外伸 0.275 m',ha='center',va='top',fontsize=9)
            ax.text(1.85,-.55,'宽度\n0.30 m',ha='center',fontsize=10);ax.set_xlim(-2.3,2.3);ax.set_ylim(-1.8,.9);ax.set_aspect('equal');ax.axis('off');ax.set_title(spec['title'])
        elif ident=='raw-02':
            geometry(ax,r['position_m'][0]);ax.set_title(spec['title']+'  t = 0 s')
        elif ident=='raw-03':
            ii,jj=np.indices((223,223));matrix=np.zeros((223,223));matrix[(jj==ii)|(jj==ii+1)]=1;matrix[jj>=ii+2]=2
            from matplotlib.colors import ListedColormap
            ax.imshow(matrix,origin='lower',cmap=ListedColormap(['white','#d4d4d4','#47758c']),interpolation='nearest',vmin=0,vmax=2)
            ax.set_xlabel('板凳 j（从0编号）');ax.set_ylabel('板凳 i（从0编号）');ax.set_title(spec['title']);ax.text(.02,.97,'蓝色：检查 24,531 对\n灰色：自身 / 相邻整对豁免',transform=ax.transAxes,ha='left',va='top',fontsize=9,bbox={'facecolor':'white','alpha':.9,'edgecolor':'none'})
        elif ident=='process-01':
            ax.plot(cert[:,0],cert[:,1]-cert[:,0],lw=.6,color='#3d6a85');ax.set_yscale('log');ax.set_xlabel('时间 / s');ax.set_ylabel('已认证区间宽度 / s');ax.set_title(spec['title']);ax.grid(axis='y',alpha=.18)
        elif ident=='process-02':
            ax.plot(cert[:,0],cert[:,2],lw=.6,color='#3d6a85');ax.set_yscale('log');ax.set_xlabel('时间 / s');ax.set_ylabel('严格投影分离下界 / m');ax.set_title(spec['title']);ax.grid(axis='y',alpha=.18)
        elif ident=='process-03':
            ax.plot(profile['time_s']-e['time_estimate_s'],profile['gap_m']*1000,lw=1.3,color='#3d6a85');ax.axhline(0,color='#888888',lw=.7);ax.axvline(0,color='#a36635',lw=.8,ls='--');ax.set_xlabel('相对终止时刻 / s');ax.set_ylabel('活动板对 SAT 间隙 / mm');ax.set_title(spec['title']+'（运动学延拓诊断）')
        elif ident=='result-01':
            plt.close(fig);fig,axs=plt.subplots(1,3,figsize=spec['final_size_inches'])
            for kk,(axis,tval,point) in enumerate(zip(axs,[0.,200.,e['time_estimate_s']],[r['position_m'][0],r['position_m'][2],term['position_m']])):
                geometry(axis,point,highlight=pair if kk==2 else None);axis.set_title(f"{chr(97+kk)}  t = {tval:.6f} s" if kk==2 else f"{chr(97+kk)}  t = {tval:g} s",fontsize=10)
            ax=axs[0]
        elif ident=='result-02':
            point=term['position_m'];geometry(ax,point,False,pair);verts,*_=corners(point);allpts=verts[pair].reshape(-1,2);mid=allpts.mean(0);span=np.max(np.ptp(allpts,axis=0))*.65;ax.set_xlim(mid[0]-span,mid[0]+span);ax.set_ylim(mid[1]-span,mid[1]+span)
            cp=np.mean(e['contact_point_interval_m'],axis=0);ax.plot(*cp,'x',ms=8,mew=1.5,color='#333333');ax.annotate('角点—有限边接触',cp,xytext=(18,48),textcoords='offset points',arrowprops={'arrowstyle':'-','lw':.7},fontsize=9)
            for kk,k in enumerate(pair):ax.annotate(f'板凳 {k+1}',verts[k].mean(0),xytext=((-20,-28) if kk==0 else (42,-25)),textcoords='offset points',fontsize=10,ha='center',arrowprops={'arrowstyle':'-','lw':.6},bbox={'facecolor':'white','alpha':.95,'edgecolor':'none','pad':1.5})
            ax.set_title(spec['title']+'（板凳从1编号）')
        else:
            ax.plot(np.arange(224),term['speed_m_s'],color='#3d6a85',lw=1.1);ax.axhline(1,ls='--',lw=.7,color='#888888');ax.set_xlabel('把手索引（从0编号）');ax.set_ylabel('速率 / (m/s)');ax.set_title(spec['title'])
        export(fig,ax,spec)
    # Python-rendered contact sheet is for independent visual inspection only.
    sheet,axes=plt.subplots(3,3,figsize=(15,13))
    for ax,record in zip(axes.flat,records):
        ax.imshow(plt.imread(out/(record['figure_id']+'.png')));ax.axis('off');ax.set_title(record['figure_id'],fontsize=12)
    sheet.tight_layout();sheet.savefig(out/'contact-sheet.png',dpi=120);plt.close(sheet)
    write(folder/'figures.json',{'figures':records,'counts':{'raw':3,'process':3,'result':3},'candidate_count':9,'formal_selection':'pending_user','generated_from_validated_data':True,'backend':'Python/matplotlib','contact_sheet':out.name+'/contact-sheet.png'})
    print('9 Python figures exported with PNG/PDF/SVG; awaiting visual QA',flush=True)
if __name__=='__main__':main()
