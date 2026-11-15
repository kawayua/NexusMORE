"""Explicitly migrate reviewed A+ material to B+ samples; no user approval or model call."""
from modelcrew.project_assets import asset_path
import copy,json
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.contracts import digest,validate
from modelcrew.inputs import file_hash
from modelcrew.mathematics import validate_package,render
from modelcrew.workflow import Workflow

def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def write(p,v):
    p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def build(contract,name='bench-dragon'):
    source=f'stage-a-plus/math/{name}-dossier.json';raw=read(source);method=read(f'stage-a-plus/cases/{name}-method-selection.json')
    d={k:copy.deepcopy(raw.get(k,[])) for k in ['id','structure','symbols','assumptions','equations','derivations','propositions','unproved_or_out_of_scope','statistical_inference']}
    d['statistical_inference']=raw.get('statistical_inference','Not applicable: deterministic synthetic LP; no statistical inference.')
    d['schema_version']='1.0.0';d['problem_setting']={'scope':raw.get('scope','Synthetic continuous resource allocation; not contest data'),'inputs':raw.get('inputs','Fixed synthetic coefficients and capacities from A+ resource-allocation.json'),'requested_conclusion':method['fingerprint'].get('requested_conclusion',method['fingerprint'].get('objective','Specified calculation'))}
    for symbol in d['symbols']:symbol['scope']='this subproblem'
    candidates=[]
    for c in method['candidates']:
        candidates.append({'id':c['id'],'decision':c['decision'],'premises':c.get('premises',[]),'data':c.get('data','Known coefficients and continuous domain'),'sources':c.get('sources',method.get('sources',[])),'reason':c['reason'],'complexity':c.get('complexity','Not selected; complexity not estimated.'),'risks':c.get('risks',[]),'validation':c.get('validation',method.get('validation',[])),'fallback':c.get('fallback',method.get('fallback','Review premises before changing method.'))})
    m={'schema_version':'1.0.0','id':'method:'+name,'fingerprint':method['fingerprint'],'model':method.get('model',method.get('model_vs_solver',{}).get('model')),'solver':method.get('solver',method.get('model_vs_solver',{}).get('selected_solver')),'selected_candidate_id':next(c['id'] for c in candidates if c['decision']=='selected'),'candidates':candidates,'coverage_gap':method.get('coverage_gap','Synthetic sample only, not a general LP modelling classifier.'),'conditions_evidence':method.get('conditions_evidence','Explicit primal-dual argument in A+ source; prerequisites require review.')}
    links=[]
    for e in d['equations']:
        # These are cross-references requiring human comparison, not algebraic-equivalence proofs.
        targets=[]
        if name=='bench-dragon':
            ids={'eq:head':['head_arc'],'eq:rod':['chord'],'eq:stable-chord':['chord'],'eq:velocity':['velocity_relation']}.get(e['id'],[])
            targets=[{'group':'constraints','id':x['id']} for x in contract['constraints'] if x['id'] in ids]
        if name=='resource' and e['id']=='eq:lp-primal':targets=[{'group':'constraints','id':'resources'}]
        links.append({'equation_id':e['id'],'role':'executable' if targets else 'explanatory','targets':targets,'reason':'Executable constraint cross-reference; mathematical equivalence still requires user review.' if targets else 'Explanatory definition, derivation or branch certificate; no claim of automatic equivalence to executable code.'})
    vp=[]
    if name=='bench-dragon':
        checks=[('check:rod','Rod length residual, all stored samples',1e-8,'m'),('check:head-speed','Head speed error',1e-9,'m/s'),('check:denominator','Minimum sampled positive velocity denominator',1e-10,'m^2'),('check:fd','Independent velocity finite difference at h=0.001s',1e-5,'m/s')]
    else:checks=[('check:lp-gap','Explicit primal feasibility, dual feasibility and zero objective gap',0,'currency')]
    for key,desc,threshold,unit in checks:vp.append({'id':key,'description':desc,'threshold':threshold,'unit':unit,'evidence_kind':'numerical'})
    vp.append({'id':'check:math-review','description':'Review assumptions, domains, derivation steps, scope and executable cross-references before approval','threshold':None,'unit':'1','evidence_kind':'human_review'})
    figures=[]
    if name=='bench-dragon':
        fp=read('stage-a-plus/figure-evidence-plan.json')
        for f in fp['figures']:figures.append({'id':f['figure_id'],'question':f['question'],'data_origin':'historical confirmed dragon-q1 v2/revision2 NPZ; reference only, never treated as this new version execution','data_sha256':fp['evidence']['sha256'],'contract_version':2,'result_revision':2,'specification':json.dumps(f,ensure_ascii=False),'status':'planned'})
    paths=[source,f'stage-a-plus/cases/{name}-method-selection.json','stage-a-plus/sources/read-log.json','stage-a-plus/mathematical-review.json']
    package={'schema_version':'1.0.0','method_selection':m,'dossier':d,'contract_links':links,'validation_plan':vp,'figures':figures,'provenance':[{'path':p,'sha256':file_hash(ROOT/p),'role':'A+ reviewed source; historical confirmations are not imported as B+ approvals'} for p in paths],'presentation':{'equation_spacing':'normal'}}
    validate_package(package,contract);return package

def resource_contract():
    source='stage-a-plus/cases/resource-allocation.json';h=file_hash(ROOT/source)
    c={'schema_version':'1.0.0','problem':{'case_id':'resource-toy','subproblem_id':'Q1','title':'Synthetic continuous resource allocation','scope':'Known deterministic continuous LP, not contest data','objective':{'kind':'optimization','description':'maximize 3*x1+2*x2 with linear resource capacities'}},'sources':[{'id':'synthetic','kind':'user_guidance','locator':source,'sha256':h}],'inputs':[{'id':'data','path':str(ROOT/source),'role':'synthetic_parameters','source_id':'synthetic','sha256':h}],
    'parameters':[{'id':'capacity1','value':4,'unit':'h','source_id':'synthetic','origin':'given','derivation':None},{'id':'capacity2','value':6,'unit':'h','source_id':'synthetic','origin':'given','derivation':None}],
    'variables':[{'id':'x','meaning':'two divisible product masses','unit':'kg','domain':'R^2 nonnegative'}],
    'assumptions':[{'id':'linear','statement':'Known fixed linear rates, divisible masses; no fixed costs','source_id':'synthetic'}],
    'constraints':[{'id':'resources','expression':'x1+x2<=4 and 2*x1+x2<=6; x1,x2>=0','meaning':'resource capacities and nonnegative mass','check_id':'feasibility'}],
    'checks':[{'id':'feasibility','unit':'h','method':'evaluate both capacity residuals and nonnegativity','tolerance':1e-9,'description':'primal feasibility','initial_status':'unknown','evidence_required':'mass vector and slacks'},{'id':'duality','unit':'currency','method':'primal and explicit dual objective gap','tolerance':1e-9,'description':'optimality certificate','initial_status':'unknown','evidence_required':'primal and dual feasible candidates'}],
    'method':{'steps':['Construct continuous LP','Solve with scipy.optimize.linprog(method=highs)','Independently check primal and dual certificate'],'root_selection':'Not applicable to LP','requires_new_confirmation':['Any coefficient, variable domain, objective or validation change'],'allowed_equivalent_changes':['Equivalent continuous LP solver with the same checked constraints']},
    'outputs':[{'id':'solution','path':'solution.json','fields':[{'name':'x','shape':[2],'unit':'kg'},{'name':'objective','shape':[1],'unit':'currency'}],'format':'json','decimal_places':6}],
    'conventions':{'coordinate_system':'two decision quantities; no geometric coordinates','direction':'maximize revenue','time_origin':'not applicable','time_unit':'h','length_unit':'not applicable','indexing':'products1,2'},'risks':['Synthetic finite sample only; structural validation is not proof'],'alternatives':['Use an integer formulation if masses are indivisible']}
    validate(c);return c

def main():
    with Workflow() as w:
        with w.lock('dragon-q1'),w.db.transaction():
            w.db.execute('SET TRANSACTION READ ONLY')
            c=w.db.execute('SELECT content,sha256 FROM mc_contracts WHERE task_id=%s AND version=2',('dragon-q1',)).fetchone()
    assert digest(c['content'])==c['sha256']
    write('stage-b-plus/examples/contract-v2-snapshot.json',c['content'])
    for name in ['bench-dragon','resource']:
        target=c['content'] if name=='bench-dragon' else resource_contract()
        if name=='resource':write('stage-b-plus/examples/resource-contract.json',target)
        p=build(target,name);write(f'stage-b-plus/examples/valid-{name}.json',p)
        md,tex=render(p);out=asset_path(ROOT,'stage-b-plus/proposals');out.mkdir(exist_ok=True)
        (out/f'{name}.md').write_text(md,encoding='utf-8');(out/f'{name}-fragments.tex').write_text(tex,encoding='utf-8')
    bad=build(c['content']);bad['dossier']['equations'][0]['symbol_ids'].append('sym:undefined');write('stage-b-plus/examples/invalid-symbol.json',bad)
    bad=build(c['content']);bad['dossier']['equations'][0]['rhs_dimension']='s';write('stage-b-plus/examples/invalid-dimension.json',bad)
    bad=build(c['content']);bad['dossier']['propositions'][0]['conditions']=[];write('stage-b-plus/examples/invalid-proof-premise.json',bad)
    bad=build(c['content']);bad['contract_links'][0]['targets']=[{'group':'constraints','id':'not-in-contract'}];write('stage-b-plus/examples/invalid-contract-link.json',bad)
    print('B+ two valid and four invalid samples generated; production read only; no approvals imported.')
if __name__=='__main__':main()
