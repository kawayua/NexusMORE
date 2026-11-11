"""Prepare a finite reviewed card catalog, preserving complete related source sections."""
import json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.contracts import digest
from modelcrew.corpus import sha_file


def prepare():
    # The authoritative index is intentionally the first algorithm resource read.
    index=ROOT/'resources/algorithms/index.md';index_text=index.read_text(encoding='utf-8')
    log=json.loads((ROOT/'stage-a-plus/sources/read-log.json').read_text(encoding='utf-8'))
    sources=[]
    for item in log['sources']:
        if item['id']=='index':continue
        path=ROOT/item['project_path'];text='\n'.join(path.read_text(encoding='utf-8-sig').splitlines()[item['line_start']-1:item['line_end']])+'\n'
        # Retain the entire already-reviewed section, including definitions, formulas and caveats.
        sources.append({'id':item['id'],'path':item['project_path'],'sha256':sha_file(path),'line_start':item['line_start'],'line_end':item['line_end'],
                        'section_sha256':digest(text),'text':text,'version':'math-modeling 1.3.0' if '/reference/' in item['project_path'] else 'ModelCrew 1.0.0',
                        'verification':'excerpt_manually_reviewed_not_all_examples_executed'})
    cards=[]
    def add(id,title,category,layer,text,facts,source_ids,model,algorithm,api,maximum=None):
        cards.append({'id':id,'title':title,'category':category,'layer':layer,'retrieval_text':text,
            'required_facts':facts,'forbidden_conditions':['negation of required premise '+key for key in facts],
            'source_ids':source_ids,'model':model,'numerical_algorithm':algorithm,'api':api,'source_url':None,
            'dependencies':['scipy'] if api else [],'max_variables':maximum,
            'scale_note':'Review budget only, not a universal solver size bound' if maximum else 'No general scale guarantee',
            'verification':'reviewed_numeric_baseline' if id in ['bracketed-root','continuous-lp','geometry-model'] else 'reviewed_excerpt_not_executed',
            'not_adoption':'Actual adoption reason belongs to task-bound MethodSelection; this card is only a reference.'})
    add('geometry-model','曲线弧长与固定弦长几何模型','geometry','model','连续几何运动 曲线弧长反演 固定直线弦长 速度约束 区分模型和数值求解器',{'known_mechanism':True,'continuous_geometry':True},['geometry','notes'],'given kinematic geometry','branch-certified scalar solves',None)
    add('bracketed-root','连续异号括区间标量求根','geometry','numerical_algorithm','Brent 二分 标量方程连续 异号括区间 介值定理 不保证唯一 单调性与分支核验',{'scalar_equation':True,'continuous_on_bracket':True,'opposite_endpoint_signs':True},['geometry'],'scalar equation f(x)=0','Brent safeguarded interpolation/bisection','scipy.optimize.brentq',1)
    add('continuous-lp','连续变量线性规划','optimization','model','连续变量 线性目标 线性约束 资源分配 线性规划 LP 对偶界 可行性 求解状态',{'linear_objective_constraints':True,'continuous_variables':True},['lp','notes'],'continuous linear program','HiGHS LP solver; verify primal/dual residuals','scipy.optimize.linprog',10000)
    add('integer-lp','整数约束线性规划','optimization','model','整数 0-1变量 分支定界 混合整数规划 MILP 不能对连续松弛解四舍五入 最优间隙',{'linear_objective_constraints':True,'integer_variables':True},['integer','notes'],'integer or mixed-integer linear program','branch-and-bound/cut; inspect incumbent and gap','scipy.optimize.milp',1000)
    add('ivp-integrator','常微分方程初值问题数值积分','simulation','numerical_algorithm','常微分方程 初值问题 ODE 积分 步长 误差控制 事件检测 输出采样不是积分步长',{'known_rhs':True,'initial_state_available':True},['ode','geometry'],'ODE initial value model','adaptive integration; stiffness and event review','scipy.integrate.solve_ivp',10000)
    add('brentq-api','SciPy brentq接口使用','geometry','api','SciPy optimize brentq API xtol rtol 收敛返回状态 调用前核对连续与异号前提',{'scalar_equation':True,'continuous_on_bracket':True,'opposite_endpoint_signs':True},['geometry'],'not a model; API reference','Brent','scipy.optimize.brentq',1)
    catalog={'schema_version':'1.0.0','index':{'path':str(index.relative_to(ROOT)).replace('\\','/'),'sha256':sha_file(index),'version':'1.1.1','read_first':True},
             'sources':sources,'cards':cards,'scope':'Six finite authored reference cards; not a universal classifier or proof engine'}
    catalog['catalog_sha256']=digest(catalog)
    target=ROOT/'stage-c-plus/algorithm-catalog.json';target.parent.mkdir(exist_ok=True)
    with target.open('x',encoding='utf-8') as f:json.dump(catalog,f,ensure_ascii=False,indent=2)
    print(json.dumps({'cards':len(cards),'sources':len(sources),'catalog':str(target.relative_to(ROOT))}))

if __name__=='__main__':prepare()
