"""Versioned mathematical handoff. Structure checks are not a general proof engine."""
import copy
import hashlib
import json
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb
from .config import ROOT
from .contracts import digest
from .aplus import check_dossier
from .versions import differences

SCHEMA=json.loads((ROOT/'contracts/mathematical-package-1.0.0.schema.json').read_text(encoding='utf-8'))
class MathematicsError(ValueError):pass

def validate_package(package,contract):
    errors=list(Draft202012Validator(SCHEMA).iter_errors(package))
    if errors:raise MathematicsError('; '.join(f'{list(e.path)}: {e.message}' for e in errors))
    digest(package)
    d=package['dossier'];m=package['method_selection']
    findings=check_dossier(d)['findings']
    all_ids=[]
    for group in ['symbols','assumptions','equations','derivations','propositions']:all_ids.extend(i['id'] for i in d[group])
    if len(all_ids)!=len(set(all_ids)):findings.append('IDs must be unique across dossier groups')
    for items,label in [(m['candidates'],'candidate'),(package['validation_plan'],'validation'),(package['figures'],'figure')]:
        ids=[i['id'] for i in items]
        if len(ids)!=len(set(ids)):findings.append('duplicate '+label+' IDs')
    selected=[i for i in m['candidates'] if i['decision']=='selected']
    if len(selected)!=1 or selected[0]['id']!=m['selected_candidate_id']:findings.append('Exactly one matching selected candidate required')
    if selected and not selected[0]['premises']:findings.append('Selected method needs explicit premises')
    eqs={i['id'] for i in d['equations']}
    links=package['contract_links']
    if len(links)!=len(eqs) or {i['equation_id'] for i in links}!=eqs:findings.append('Each equation needs exactly one explicit contract link or explanatory scope')
    for link in links:
        if link['role']=='executable' and not link['targets']:findings.append('Executable equation needs a contract target')
        for target in link['targets']:
            if target['id'] not in {i['id'] for i in contract[target['group']]}:findings.append('Unknown contract target '+target['id'])
    if findings:raise MathematicsError('; '.join(findings))
    return package

def semantics(package):
    value=copy.deepcopy(package);value.pop('presentation',None);return value

def semantic_hash(task,version,contract_sha,package):
    return digest({'task_id':task,'version':version,'contract_sha256':contract_sha,'mathematics':semantics(package)})

def classify_change(old,new):
    """Only a closed set of layout knobs is exempt. Formula/name/text edits are semantic."""
    if old==new:return {'kind':'unchanged','changes':[],'requires_model_approval':False}
    changed=semantics(old)!=semantics(new)
    return {'kind':'mathematical' if changed else 'presentation','changes':differences(old,new),
            'requires_model_approval':changed,'invalidates_execution':changed,'invalidates_result_approval':changed,
            'requires_reexport':True}

def render(package):
    """Internal mathematical proposal, not a paper. Paper genre uses modeling_paper policy."""
    d=package['dossier'];m=package['method_selection']
    lines=['# 数学提案',d['problem_setting']['scope'],'数学正确性需审阅；结构通过不等于已证明。',
           '## 问题与方法',d['problem_setting']['inputs'],d['problem_setting']['requested_conclusion'],
           '模型：'+m['model'],'求解器：'+m['solver']]
    for c in m['candidates']:lines.append(f"- {c['id']} / {c['decision']}: {c['reason']}；前提："+'；'.join(c['premises']))
    lines+=['## 符号（先定义）']
    for x in d['symbols']:lines.append(f"- `{x['id']}` ${x['latex']}$：{x['meaning']}；单位 {x['unit']}；域 {x['domain']}；形状 {x['shape']}；范围 {x['scope']}")
    lines+=['## 假设']
    for x in d['assumptions']:lines.append(f"- `{x['id']}` {x['statement']}；来源 {x['source']}；影响 {x['impact']}")
    tex=['% Generated from the versioned mathematical package; compilation belongs to C+.','% Define symbols before referenced equations.']
    def escape(value):
        return ''.join({'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}'}.get(c,c) for c in value)
    tex+=['\\begin{description}']
    for x in d['symbols']:tex.append('\\item[$'+x['latex']+'$] '+escape(x['meaning']+'; unit: '+x['unit']+'; domain: '+x['domain']))
    tex+=['\\end{description}']
    for x in d['assumptions']:tex.append(escape(x['id']+': '+x['statement']))
    lines+=['## 公式与推导']
    space='\n\n' if package['presentation']['equation_spacing']=='relaxed' else '\n'
    for x in d['equations']:
        lines.append(f"`{x['id']}` — {x['meaning']}\n\n$${x['latex']}$$\n\n依赖符号：{', '.join(x['symbol_ids'])}；假设：{', '.join(x['assumption_ids'])}")
        tex.append('\\begin{equation}\n'+x['latex']+'\n\\label{'+x['id']+'}\n\\end{equation}'+space)
    for x in d['derivations']+d['propositions']:
        lines += [f"`{x['id']}` [{x['status']}]；条件："+'；'.join(x['conditions'])]+[f'{i}. {step}' for i,step in enumerate(x['steps'],1)]+['缺口：'+'；'.join(x['open_gaps'])]
        tex.append(escape(x['id']+'; status: '+x['status']+'; conditions: '+'; '.join(x['conditions'])+'; open gaps: '+'; '.join(x['open_gaps'])))
        tex.extend(escape(step) for step in x['steps'])
    lines+=['## 验证与局限']+[f"- {x['id']}: {x['description']}；阈值 {x['threshold']} {x['unit']}" for x in package['validation_plan']]+d['unproved_or_out_of_scope']
    lines+=['## 拟用图示']+[x['id']+': '+x['question']+'；'+x['specification'] for x in package['figures']]
    # Full canonical data prevents omitted source/condition fields in the readable handoff.
    lines+=['## 完整语义快照（供交接核对）','```json',json.dumps(semantics(package),ensure_ascii=False,indent=2,allow_nan=False,sort_keys=True),'```']
    return '\n\n'.join(lines)+'\n','\n'.join(tex)+'\n'

def latest(w,task,version):
    return w.db.execute('SELECT * FROM mc_math_packages WHERE task_id=%s AND version=%s ORDER BY revision DESC LIMIT 1',(task,version)).fetchone()

def store(w,task,version,package,actor,reason,kind):
    contract=w.db.execute('SELECT content,sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
    validate_package(package,contract['content']);old=latest(w,task,version);revision=1 if old is None else old['revision']+1
    markdown,tex=render(package);sha=semantic_hash(task,version,contract['sha256'],package)
    w.db.execute('INSERT INTO mc_math_packages(task_id,version,revision,content,sha256,semantic_sha256,proposal_markdown,proposal_sha256,latex_source,actor,reason,change_kind) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(task,version,revision,Jsonb(package),digest(package),sha,markdown,hashlib.sha256(markdown.encode()).hexdigest(),tex,actor,reason,kind))
    return snapshot(w,task,version)

def snapshot(w,task,version):
    row=latest(w,task,version)
    if row is None:return None
    contract=w.db.execute('SELECT sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(task,version)).fetchone()
    md,tex=render(row['content'])
    if digest(row['content'])!=row['sha256'] or semantic_hash(task,version,contract['sha256'],row['content'])!=row['semantic_sha256'] or md!=row['proposal_markdown'] or tex!=row['latex_source'] or hashlib.sha256(md.encode()).hexdigest()!=row['proposal_sha256']:raise MathematicsError('Mathematical package integrity failure')
    return {'task_id':task,'version':version,'revision':row['revision'],'contract_sha256':contract['sha256'],'package_sha256':row['sha256'],'semantic_sha256':row['semantic_sha256'],'proposal_sha256':row['proposal_sha256'],'content':row['content'],'proposal_markdown':md,'latex_source':tex,'change_kind':row['change_kind'],'review_scope':'Structure/declared dimensions checked; user mathematical review required; no PDF compilation.'}

def approval_snapshot(w,t,expected,reason):
    current=snapshot(w,t['id'],t['current_version'])
    if current is None:
        if expected is not None:raise MathematicsError('No mathematical package for this version')
        return None
    if expected!=current['semantic_sha256']:raise MathematicsError('Missing or stale mathematical semantic hash')
    if not reason.strip():raise MathematicsError('Explicit mathematical review reason required')
    result={k:current[k] for k in ['task_id','version','revision','contract_sha256','package_sha256','semantic_sha256','proposal_sha256']}
    result['review_reason']=reason
    return result


def assert_gate_binding(w,t,gate):
    current=snapshot(w,t['id'],t['current_version'])
    if current is None:return
    events=w.db.execute('SELECT payload FROM mc_events WHERE task_id=%s AND kind=%s ORDER BY id DESC',(t['id'],gate+'_approve')).fetchall()
    events=[e['payload'] for e in events if e['payload'].get('version')==t['current_version'] and (gate!='result' or e['payload'].get('result_revision')==t['result_revision'])]
    bound=events[0].get('math_snapshot') if events else None
    if not bound or any(bound.get(k)!=current[k] for k in ['task_id','version','contract_sha256','semantic_sha256']):raise MathematicsError('Durable mathematical approval binding missing or stale')
    if gate=='result':
        result=w.db.execute('SELECT review FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(t['id'],t['current_version'],t['result_revision'])).fetchone()
        if bound.get('execution_id')!=str(t['execution_id']) or bound.get('result_review_sha256')!=digest(result['review']):raise MathematicsError('Mathematical result snapshot changed')
