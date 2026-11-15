"""D6: approved previous-question artifacts are references, never inherited approvals.

No complete-paper/export prerequisite. Source versions are pinned, stale current
sources block fresh consumption while the historical reference record is retained.
"""
from .project_assets import asset_path
from pathlib import Path
import json,re
from psycopg.types.json import Jsonb
from .config import ROOT
from .contracts import digest
from .collaboration import sha_file
from .mathematics import snapshot as math_snapshot, assert_gate_binding

SCOPES={'model','result','manuscript','figures'}

def artifact(path,expected=None):
    p=Path(path)
    if not p.is_absolute():p=asset_path(ROOT,p)
    p=p.resolve()
    if not p.is_relative_to(ROOT.resolve()):raise ValueError('Reference path outside workspace')
    actual=sha_file(p)
    if expected is not None and actual!=expected:raise ValueError('Confirmed reference file changed')
    return {'path':p.relative_to(ROOT.resolve()).as_posix(),'sha256':actual}

def verify_record(row):
    if row is None or digest(row['payload'])!=row['sha256']:raise ValueError('Reference record missing or changed')
    return row['payload']

def intake(w,*,target_id,revision,case_id,question_id,statement_path,statement_sha256,pages,excerpt_path):
    if not all(isinstance(x,str) and x.strip() for x in [target_id,case_id,question_id]):raise ValueError('Explicit target identity required')
    if revision<1 or not pages or any(type(i)!=int or i<1 for i in pages):raise ValueError('Invalid intake revision/pages')
    original=Path(statement_path).resolve()
    if sha_file(original)!=statement_sha256:raise ValueError('Original statement changed')
    excerpt=artifact(excerpt_path)
    value={'target_id':target_id,'revision':revision,'case_id':case_id,'question_id':question_id,'statement':{'path':str(original),'sha256':statement_sha256,'pages':pages},'excerpt':excerpt,'status':'INTAKE_ONLY','model_approved':False,'result_approved':False}
    with w.lock('question:'+target_id),w.db.transaction():
        old=w.db.execute('SELECT payload,sha256 FROM mc_question_intakes WHERE id=%s AND revision=%s',(target_id,revision)).fetchone()
        if old:
            if verify_record(old)!=value:raise ValueError('Intake revision already bound to different input')
        else:
            last=w.db.execute('SELECT max(revision) AS revision FROM mc_question_intakes WHERE id=%s',(target_id,)).fetchone()['revision'] or 0
            if revision!=last+1:raise ValueError('Intake revisions must be consecutive')
            w.db.execute('INSERT INTO mc_question_intakes(id,revision,case_id,question_id,payload,sha256) VALUES(%s,%s,%s,%s,%s,%s)',(target_id,revision,case_id,question_id,Jsonb(value),digest(value)))
    return value

def approved_event(w,t,gate):
    events=w.db.execute('SELECT id,actor,payload FROM mc_events WHERE task_id=%s AND kind=%s ORDER BY id DESC',(t['id'],gate+'_approve')).fetchall()
    for e in events:
        p=e['payload']
        if p.get('version')==t['current_version'] and p.get('decision')=='approve' and (gate!='result' or p.get('result_revision')==t['result_revision']):
            return {'event_id':e['id'],'actor':e['actor'],'payload_sha256':digest(p)}
    raise ValueError('Authoritative '+gate+' confirmation event missing')

def writing_approval(w,t,scope):
    rows=w.db.execute("SELECT id,body FROM mc_version_entries WHERE task_id=%s AND version=%s AND kind='feedback' AND actor='user' ORDER BY created_at DESC",(t['id'],t['current_version'])).fetchall()
    for row in rows:
        body=row['body'];metadata=body.get('metadata',{})
        if metadata.get('scope')!=scope or metadata.get('decision')!='approve':continue
        binding=metadata.get('binding',{})
        if binding.get('task_id')!=t['id'] or binding.get('contract_version')!=t['current_version'] or binding.get('execution_id')!=str(t['execution_id']) or binding.get('result_revision')!=t['result_revision']:continue
        proofs=body.get('artifacts',[])
        if len(proofs)!=1:raise ValueError('Ambiguous writing approval')
        source=artifact(proofs[0]['path'],proofs[0]['sha256']);data=json.loads((asset_path(ROOT,source['path'])).read_text(encoding='utf-8'))
        if data.get('actor')!='user' or data.get('decision')!='approve':raise ValueError('No explicit writing consent')
        return {'entry_id':str(row['id']),'record':source},data
    raise ValueError('Current '+scope+' confirmation missing')

def source_package(w,source_task,scopes):
    if not scopes or len(scopes)!=len(set(scopes)) or not set(scopes)<=SCOPES:raise ValueError('Unknown/duplicate/empty reference scopes')
    t=w.task(source_task)
    if not t['model_approved']:raise ValueError('Source model is unconfirmed')
    assert_gate_binding(w,t,'model')
    c=w.db.execute('SELECT content,sha256 FROM mc_contracts WHERE task_id=%s AND version=%s',(source_task,t['current_version'])).fetchone()
    if digest(c['content'])!=c['sha256']:raise ValueError('Source contract changed')
    math=math_snapshot(w,source_task,t['current_version'])
    for item in c['content']['inputs']:
        if sha_file(item['path'])!=item['sha256']:raise ValueError('Confirmed source input changed')
    model={'contract':c['content'],'mathematics':math,'approval':approved_event(w,t,'model')}
    values={};files=[];receipts={'model':model['approval']}
    if 'model' in scopes:values['model']=model
    needs_result=bool(set(scopes)-{'model'})
    binding={'task_id':source_task,'contract_version':t['current_version'],'contract_sha256':c['sha256']}
    if needs_result:
        if not t['result_approved']:raise ValueError('Source result is unconfirmed')
        assert_gate_binding(w,t,'result');receipts['result']=approved_event(w,t,'result')
        binding.update(execution_id=str(t['execution_id']),result_revision=t['result_revision'])
        r=w.db.execute('SELECT review,interpretation FROM mc_results WHERE task_id=%s AND version=%s AND revision=%s',(source_task,t['current_version'],t['result_revision'])).fetchone()
        if r['review'].get('status')!='passed':raise ValueError('Source result review has not passed')
        if r['review'].get('kind')=='d4_P2_review':
            from .full_result import validate_full_run
            validate_full_run(w,source_task,t['current_version'],asset_path(ROOT,r['review']['source_run']))
        execution=w.db.execute('SELECT artifacts FROM mc_executions WHERE id=%s',(t['execution_id'],)).fetchone()
        if 'result' in scopes:
            result_files=[artifact(a['path'],a['sha256']) for a in execution['artifacts'] if Path(a.get('origin_path',a['path'])).name in ['trajectories.npz','result1.xlsx','independent-numerics.json','sample-results.json']]
            if not result_files:raise ValueError('No registered readable numerical result artifacts')
            files+=result_files;values['result']={'interpretation':r['interpretation'],'review':r['review'],'artifacts':result_files}
        if set(scopes)&{'manuscript','figures'}:
            from .writing_reviews import manuscript_snapshot,selection_snapshot
            # Obtain the current catalog from the user-confirmed D5 figure decision,
            # not a mutable current-writing pointer or arbitrary caller file path.
            proof,decision=writing_approval(w,t,'D5_current_nine_figures')
            catalog_path=asset_path(ROOT,decision['catalog_path']);catalog=artifact(catalog_path)
            ids=decision['snapshot']['selected_ids'];actual=selection_snapshot(catalog_path,ids)
            if actual!=decision['snapshot']:raise ValueError('Selected figures changed since approval')
            if 'figures' in scopes:
                receipts['figures']=proof;values['figures']={'catalog':catalog,'selection':actual}
                files.append(catalog)
                cat=json.loads(catalog_path.read_text(encoding='utf-8'))
                for f in cat['figures']:
                    if f['id'] in ids:
                        files += [artifact(catalog_path.parent/a['path'],a['sha256']) for a in f['files'].values()]
            if 'manuscript' in scopes:
                proof,decision=writing_approval(w,t,'D5_current_manuscript')
                md=catalog_path.parent/'单题论文-中文审阅稿.md'
                if manuscript_snapshot(md,catalog_path)!=decision['snapshot']:raise ValueError('Approved manuscript changed')
                receipts['manuscript']=proof;values['manuscript']={'document':artifact(md),'snapshot':decision['snapshot']};files.append(artifact(md))
    return {'source_binding':binding,'case_id':c['content']['problem']['case_id'],'question_id':c['content']['problem']['subproblem_id'],'scopes':sorted(scopes),'values':values,'files':sorted({x['path']:x for x in files}.values(),key=lambda x:x['path']),'confirmation_receipts':receipts,'use':'reference_only_not_downstream_approval','limitations':['Q1 kinematics do not establish collision-free motion','0..300 s arrays do not establish later-time states','paper completion/export is not a prerequisite for approved model/result access']}

def target(w,target_id,revision):
    value=verify_record(w.db.execute('SELECT payload,sha256 FROM mc_question_intakes WHERE id=%s AND revision=%s',(target_id,revision)).fetchone())
    latest=w.db.execute('SELECT max(revision) AS revision FROM mc_question_intakes WHERE id=%s',(target_id,)).fetchone()['revision']
    if latest!=revision:raise ValueError('Target intake revision is stale')
    if sha_file(value['statement']['path'])!=value['statement']['sha256']:raise ValueError('Target statement changed')
    artifact(value['excerpt']['path'],value['excerpt']['sha256'])
    return value

def attach(w,*,target_id,target_revision,source_task,scopes,purpose):
    if not purpose.strip():raise ValueError('Reference purpose required')
    if source_task==target_id:raise ValueError('Self reference forbidden')
    with w.lock('question:'+target_id),w.lock(source_task),w.db.transaction():
        destination=target(w,target_id,target_revision);package=source_package(w,source_task,scopes)
        if destination['case_id']!=package['case_id'] or destination['question_id']==package['question_id']:raise ValueError('Question/case reference mismatch')
        before=re.fullmatch(r'Q([1-9][0-9]*)',package['question_id']);after=re.fullmatch(r'Q([1-9][0-9]*)',destination['question_id'])
        if not before or not after or int(before[1])>=int(after[1]):raise ValueError('Only earlier questions may supply references; explicit Qn order required')
        value={'target_id':target_id,'target_revision':target_revision,'target_sha256':digest(destination),'source':package,'purpose':purpose,'downstream_model_approved':False,'downstream_result_approved':False}
        key=digest(value)
        w.db.execute('INSERT INTO mc_question_references(id,target_id,target_revision,source_task,payload,sha256) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(key,target_id,target_revision,source_task,Jsonb(value),key))
        actual=verify_record(w.db.execute('SELECT payload,sha256 FROM mc_question_references WHERE id=%s',(key,)).fetchone())
        if actual!=value:raise ValueError('Reference key conflict')
    return {'reference_id':key,'reference':value}

def consume(w,*,target_id,target_revision,reference_ids):
    if len(reference_ids)!=len(set(reference_ids)):raise ValueError('Duplicate reference IDs')
    destination=target(w,target_id,target_revision);packages=[]
    for key in reference_ids:
        row=w.db.execute('SELECT payload,sha256 FROM mc_question_references WHERE id=%s',(key,)).fetchone();value=verify_record(row)
        if key!=digest(value) or value['target_id']!=target_id or value['target_revision']!=target_revision or value['target_sha256']!=digest(destination):raise ValueError('Reference belongs to another question/version')
        old=value['source']
        from .reference_lineage import conserved
        fresh=old if conserved(w,target_id,key,old) else source_package(w,old['source_binding']['task_id'],old['scopes'])
        if fresh!=old:raise ValueError('Source confirmation/version changed; old reference retained, create a new reference explicitly')
        packages.append({'reference_id':key,**value})
    return {'question':destination,'references':packages,'reference_use_only':True,'model_approved':False,'result_approved':False,'next_gate':'Q2 independent model/M1 and explicit user model confirmation before solving'}


def revalidate_context(w,context,*,expected_target):
    q=context['question']
    if q['target_id']!=expected_target:raise ValueError('Question reference target mismatch')
    fresh=consume(w,target_id=q['target_id'],target_revision=q['revision'],reference_ids=[r['reference_id'] for r in context['references']])
    if fresh!=context:raise ValueError('Bound previous-question context changed')
    return fresh
