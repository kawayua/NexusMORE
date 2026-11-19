"""Persistent review documents and exact native-chat user confirmations.

Private DSH parent pipes only. There is no model tool or HTTP decision API.
Documents do not expire; authorization is minted only when a fresh human reply
arrives and the exact displayed review is still current.
"""
from contextlib import redirect_stdout
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from psycopg.types.json import Jsonb

from . import trusted_decisions as trusted
from .business_adapter import scope_for
from .business_contract import BusinessContractError, request_digest
from .business_projection import check_binding, host_review_readiness
from .contracts import digest
from .review_documents import RENDERER_VERSION, render_model, proposal_sources
from .result_review_documents import RESULT_RENDERER_VERSION, render_result, result_sources, checked_bytes
from .dsh_decisions import _private_parent, _read, _write, validate_host, validate_scope, reject

PROTOCOL = 'nexusmore-dsh-chat/1'
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}')
# Deliberately whole-message matches: questions, quotations, negatives, conditions
# and "通过，但先修改…" must remain ordinary discussion, never authorization.
APPROVALS = {'同意', '确认', '通过', '审核通过', '确认通过', '确认审核', '确认当前版本', '确认当前版本，继续', '确认这个版本，继续', '通过，继续'}
LABELS = {'problem':'题目与目标','title':'题目','scope':'适用范围','objective':'目标','description':'说明',
 'assumptions':'模型假设','statement':'内容','parameters':'参数','variables':'变量','meaning':'含义',
 'value':'取值','unit':'单位','domain':'取值范围','constraints':'关系与约束','expression':'表达式',
 'method':'方法','steps':'步骤','checks':'检查计划','tolerance':'容差','initial_status':'初始状态',
 'evidence_required':'所需证据','outputs':'预期输出','risks':'风险与边界','alternatives':'其他方法',
 'conventions':'约定','mathematics':'数学论证','dossier':'论证材料','symbols':'符号','equations':'公式',
 'latex':'公式','derivations':'推导','theorems':'命题','premises':'前提','proof':'证明',
 'requires_new_confirmation':'需要重新确认的变更','allowed_equivalent_changes':'允许的等价调整'}


def native_message(message):
    if (not isinstance(message, dict) or set(message) != {'id','rpc_id','text'}
        or any(not isinstance(message.get(k), str) or not ID.fullmatch(message[k]) for k in ('id','rpc_id'))
        or not isinstance(message.get('text'), str) or not message['text'].strip()
        or len(message['text'].encode('utf-8')) > 65536):
        reject(message='Original native user RPC text required')
    return message


MODEL_APPROVAL = re.compile(
    r'(?:我?确认(?:你的|你|上述|以上|这)?(?:三个|三项|3个|3项)?口径[，,、；; ]*)?'
    r'我?(?:同意|通过|确认通过|审核通过)(?:当前|这份|本版)?(?:建模方案|模型方案)'
    r'(?:[，,、；; ]*(?:并|请|可以)?(?:进入|继续进入)(?:代码手|代码手阶段))?')


def is_approval(text, kind=None):
    if not isinstance(text, str): return False
    value=text.strip().rstrip('。！!')
    if value in APPROVALS: return True
    return (kind in (None, 'model') and '\n' not in value and '\r' not in value
            and MODEL_APPROVAL.fullmatch(value) is not None)


def _safe_folder(root, session):
    folder = Path(root).resolve()/'runs'/'reviews'/'dsh'/digest(session)
    for p in (folder, *folder.parents):
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()): reject(message='Linked review directory')
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _immutable(path, data):
    if path.is_symlink(): reject(message='Linked review document')
    try:
        with path.open('xb') as f: f.write(data)
    except FileExistsError:
        if path.read_bytes() != data: reject('artifact_changed', 'Review document changed')


def _tree(value, depth=0):
    """Readable lossless field values, without dumping machine JSON into chat."""
    lines = []
    if isinstance(value, dict):
        for k, v in value.items():
            label = LABELS.get(k, k)
            if isinstance(v, (dict, list)):
                lines.append('  '*depth+'- **'+label+'**'); lines.extend(_tree(v, depth+1))
            else: lines.append('  '*depth+'- '+label+'：'+str(v))
    elif isinstance(value, list):
        for v in value:
            if isinstance(v, (dict,list)):
                lines.append('  '*depth+'- 条目'); lines.extend(_tree(v,depth+1))
            else: lines.append('  '*depth+'- '+str(v))
    else: lines.append(str(value))
    return lines


def render_review(review, root):
    item=review['pending']; kind=item['kind']; bound=item['binding']; dossier=review['dossier']
    names={'model':'建模方案','result':'结果','manuscript':'论文正文','figures':'配图'}
    title=names.get(kind,kind)+'待审稿'
    lines=['# '+title, '', '版本：v'+str(bound.get('version',''))+'　状态：等待你的审核', '',
           '你可以在原生对话中提出修改意见。确认本稿时回复“通过”；仅确认当前对象和版本。', '']
    if kind=='model':
        title,markdown,_=render_model(review,root)
        return title,markdown
    elif kind=='result':
        title,markdown,_=render_result(review,root)
        return title,markdown
    for text in review.get('review_texts',[]):
        lines+=['## 待审内容', '', text['text'], '']
    if review.get('review_files'):
        lines+=['## 对应文件', '']
        for file in review['review_files']:
            # Exact local bytes remain traceable; no invented summaries.
            lines+=['- '+str(file.get('kind',file.get('artifact_id','文件')))+'：'+file['local_path']]
    lines+=['', '## 版本核对', '', '审阅快照 SHA256：'+digest(review),
            '此稿不代表已批准。正文与配图分别确认；用户确认不代替独立审查。', '']
    return title, '\n'.join(lines)


def prepare_review(scope, host, after_message, service=None, *, kind=None):
    scope=validate_scope(scope); host=validate_host(host)
    after=native_message(after_message) if after_message is not None else None
    service=service or trusted.TrustedDecisions()
    if kind not in (None,'model','result','manuscript','figures'):reject('invalid_request')
    from .paper_review_routing import review_target
    effective_scope,items=review_target(service,scope)
    items=[p for p in items if all(p['binding'].get(k)==v for k,v in effective_scope.items())]
    from .combined_paper_review import combined_pending
    combined=combined_pending(items)
    if combined and kind in (None,'manuscript','figures'):items=combined
    else:items=[p for p in items if kind is None or p['kind']==kind]
    if not items: return {'status':'no_pending'}
    # One combined writing scope is allowed; unrelated objects remain separate.
    if len(items)!=1: return {'status':'choose_required','items':[{'kind':p['kind'],'pending_id':p['pending_id']} for p in items]}
    item=items[0]; name=item['decision_operation']
    args={k:v for k,v in item['binding'].items() if k in ('project_id','task_id','run_id','build_id')}
    if name in ('task_decide','hand_decide'): args.pop('project_id',None)
    with service.adapter.workflow() as w:
        bound_scope=scope_for(name,args,w)
        if host['engineering_only']:
            database=w.db.execute('SELECT current_database() AS name').fetchone()['name']
            if not re.fullmatch(r'nexusmore_dsh_(?:decision|ui)_probe_[a-f0-9]{12,16}',database): reject()
        with service._locks(w,bound_scope):
            if item['kind']=='model' and not host_review_readiness(w,scope['task_id'])['model_ready']:
                return {'status':'not_ready'}
            review=service._review(w,name,args,item['pending_id'])
    return save_review_document(review,scope,host['session_id'],after,service.root)


def _preview_identity(session, review_sha256, presentation=None):
    value={'session':session,'review':review_sha256}
    if presentation is not None: value['presentation']=presentation
    return digest(value)


def save_review_document(review, scope, session, after, root):
    """Write a new immutable presentation; this never captures a user decision."""
    from urllib.parse import quote
    item=review['pending'];base=_safe_folder(root,session)
    renderer='legacy'
    if item['kind']=='model':
        renderer=RENDERER_VERSION
        folder=base/'readable-model-v1'
        if folder.is_symlink() or (hasattr(folder,'is_junction') and folder.is_junction()): reject()
        folder.mkdir(exist_ok=True)
        title,markdown,sources=render_model(review,root)
        evidence={'renderer_version':RENDERER_VERSION,'review':review,'proposal_sources':sources}
        evidence_bytes=(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        evidence_sha=hashlib.sha256(evidence_bytes).hexdigest()
        evidence_name='evidence-'+evidence_sha+'.json'
        evidence_path=folder/evidence_name
        uri='dsh-resource://file/session/'+quote(session,safe='')+'/'+quote(str(evidence_path).replace('\\','/'),safe='/:')
        markdown+='\n[完整证据附件]('+uri+')\n'
        presentation={'renderer_version':RENDERER_VERSION,
                      'markdown_sha256':hashlib.sha256(markdown.encode('utf-8')).hexdigest(),
                      'evidence_sha256':evidence_sha}
        _immutable(evidence_path,evidence_bytes)
    elif item.get('confirmation_scope')=='manuscript_and_figures':
        from .paper_review_documents import RENDERER_VERSION as PAPER_RENDERER,sources as paper_sources,render as render_paper
        renderer=PAPER_RENDERER;folder=base/'readable-paper-bundle-v1'
        if folder.is_symlink() or (hasattr(folder,'is_junction') and folder.is_junction()):reject()
        folder.mkdir(exist_ok=True);sources=paper_sources(review,root);urls={}
        for source in sources:
            asset=folder/'assets'/digest(sources)/source['name']
            if not asset.resolve().is_relative_to(folder.resolve()):reject('artifact_access_denied')
            for part in (asset,*asset.parents):
                if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):reject('artifact_access_denied')
            asset.parent.mkdir(parents=True,exist_ok=True);_immutable(asset,checked_bytes(root,source))
            urls[source['name']]='dsh-resource://file/session/'+quote(session,safe='')+'/'+quote(str(asset).replace('\\','/'),safe='/:')
        title,markdown=render_paper(review,root,sources,urls)
        evidence={'renderer_version':renderer,'review':review,'paper_sources':sources}
        evidence_bytes=(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n').encode('utf-8');evidence_sha=hashlib.sha256(evidence_bytes).hexdigest()
        evidence_name='evidence-'+evidence_sha+'.json';evidence_path=folder/evidence_name
        uri='dsh-resource://file/session/'+quote(session,safe='')+'/'+quote(str(evidence_path).replace('\\','/'),safe='/:')
        markdown+='\n[完整审阅证据附件]('+uri+')\n'
        presentation={'renderer_version':renderer,'markdown_sha256':hashlib.sha256(markdown.encode('utf-8')).hexdigest(),'evidence_sha256':evidence_sha}
        _immutable(evidence_path,evidence_bytes)
    elif item['kind']=='result':
        renderer=RESULT_RENDERER_VERSION
        folder=base/'readable-result-v1'
        if folder.is_symlink() or (hasattr(folder,'is_junction') and folder.is_junction()):reject()
        folder.mkdir(exist_ok=True)
        sources=result_sources(review,root);urls={}
        for source in sources:
            asset=folder/'assets'/digest(sources)/source['name']
            if not asset.resolve().is_relative_to(folder.resolve()):reject('artifact_access_denied')
            for part in (asset,*asset.parents):
                if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):reject('artifact_access_denied')
            asset.parent.mkdir(parents=True,exist_ok=True)
            _immutable(asset,checked_bytes(root,source))
            urls[source['name']]='dsh-resource://file/session/'+quote(session,safe='')+'/'+quote(str(asset).replace('\\','/'),safe='/:')
        title,markdown,_=render_result(review,root,sources,urls)
        evidence={'renderer_version':renderer,'review':review,'result_sources':sources}
        evidence_bytes=(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        evidence_sha=hashlib.sha256(evidence_bytes).hexdigest();evidence_name='evidence-'+evidence_sha+'.json';evidence_path=folder/evidence_name
        uri='dsh-resource://file/session/'+quote(session,safe='')+'/'+quote(str(evidence_path).replace('\\','/'),safe='/:')
        markdown+='\n[完整数据来源与审查证据附件]('+uri+')\n'
        presentation={'renderer_version':renderer,'markdown_sha256':hashlib.sha256(markdown.encode('utf-8')).hexdigest(),'evidence_sha256':evidence_sha}
        _immutable(evidence_path,evidence_bytes)
    else:
        folder=base;title,markdown=render_review(review,root);presentation=None
    key=_preview_identity(session,digest(review),presentation)
    record_path=folder/(key+'.json')
    if record_path.is_symlink(): reject()
    if record_path.exists():
        record=json.loads(record_path.read_text(encoding='utf-8'))
        if record['review']!=review or record['host_session']!=session: reject('artifact_changed')
    else:
        record={'schema':2 if presentation else 1,'host_session':session,'scope':scope,'pending':item,'review':review,
                'review_sha256':digest(review),'after_message':after,'title':title,'markdown':markdown,
                'markdown_sha256':hashlib.sha256(markdown.encode('utf-8')).hexdigest()}
        if presentation: record.update(presentation=presentation,evidence_file=evidence_name)
        _immutable(record_path,(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        _immutable(folder/(key+'.md'),markdown.encode('utf-8'))
    _verify_document(record,folder,key,root)
    return {'status':'waiting_for_user','preview_id':key,'binding':item['binding'],'kind':item['kind'],
            'title':record['title'],'markdown':record['markdown'],'review_sha256':record['review_sha256'],
            'renderer_version':renderer,
            **({'confirmation_scope':item['confirmation_scope']} if item.get('confirmation_scope') else {}),
            'local_path':str(folder/(key+'.md'))}


def _verify_document(record, folder, key, root):
    presentation=record.get('presentation')
    if not presentation: return
    is_bundle=record['pending'].get('confirmation_scope')=='manuscript_and_figures'
    from .paper_review_documents import RENDERER_VERSION as PAPER_RENDERER,sources as paper_sources
    expected_renderer=PAPER_RENDERER if is_bundle else RESULT_RENDERER_VERSION if record['pending']['kind']=='result' else RENDERER_VERSION
    if (record.get('schema')!=2 or presentation.get('renderer_version')!=expected_renderer
            or presentation.get('markdown_sha256')!=record['markdown_sha256']
            or hashlib.sha256(record['markdown'].encode('utf-8')).hexdigest()!=record['markdown_sha256']
            or record.get('evidence_file')!='evidence-'+presentation.get('evidence_sha256','')+'.json'):
        reject('artifact_changed')
    path=folder/record['evidence_file']
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=presentation['evidence_sha256']:
        reject('artifact_changed','Review evidence changed')
    evidence=json.loads(path.read_text(encoding='utf-8'))
    if record['pending']['kind']=='result' or is_bundle:
        sources=paper_sources(record['review'],root) if is_bundle else result_sources(record['review'],root)
        expected={'renderer_version':expected_renderer,'review':record['review'],('paper_sources' if is_bundle else 'result_sources'):sources}
        for source in sources:
            asset=folder/'assets'/digest(sources)/source['name']
            if not asset.resolve().is_relative_to(folder.resolve()):reject('artifact_changed','Displayed result asset escaped review folder')
            for part in (asset,*asset.parents):
                if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):reject('artifact_changed','Linked displayed result asset')
            if hashlib.sha256(asset.read_bytes()).hexdigest()!=source['sha256']:
                reject('artifact_changed','Displayed result asset changed')
    else:expected={'renderer_version':RENDERER_VERSION,'review':record['review'],'proposal_sources':proposal_sources(record['review'],root)}
    if evidence!=expected:
        reject('artifact_changed','Review source or evidence changed')
    if key!=_preview_identity(record['host_session'],record['review_sha256'],presentation):
        reject('artifact_changed')
    if (folder/(key+'.md')).read_bytes()!=record['markdown'].encode('utf-8'):
        reject('artifact_changed','Displayed document changed')


def confirm_review(scope,host,preview_id,message,service=None):
    scope=validate_scope(scope);host=validate_host(host);message=native_message(message)
    service=service or trusted.TrustedDecisions()
    if not re.fullmatch('[a-f0-9]{64}',preview_id or '') or not is_approval(message['text']): reject('user_input_required')
    folder=_safe_folder(service.root,host['session_id'])
    readable=folder/'readable-model-v1'
    if readable.is_symlink() or (hasattr(readable,'is_junction') and readable.is_junction()): reject()
    if (readable/(preview_id+'.json')).exists(): folder=readable
    result_readable=_safe_folder(service.root,host['session_id'])/'readable-result-v1'
    if result_readable.is_symlink() or (hasattr(result_readable,'is_junction') and result_readable.is_junction()):reject()
    if (result_readable/(preview_id+'.json')).exists():folder=result_readable
    paper_folder=_safe_folder(service.root,host['session_id'])/'readable-paper-bundle-v1'
    if paper_folder.is_symlink() or (hasattr(paper_folder,'is_junction') and paper_folder.is_junction()):reject()
    if (paper_folder/(preview_id+'.json')).exists():folder=paper_folder
    record_path=folder/(preview_id+'.json')
    if record_path.is_symlink():reject()
    if not record_path.exists():reject('stale_binding','No review published in this session')
    record=json.loads(record_path.read_text(encoding='utf-8'))
    _verify_document(record,folder,preview_id,service.root)
    review=record['review']; item=record['pending']
    if not is_approval(message['text'],item['kind']): reject('user_input_required')
    if (record['host_session']!=host['session_id'] or record['scope']!=scope or item!=review['pending']
        or digest(review)!=record['review_sha256'] or preview_id!=_preview_identity(host['session_id'],digest(review),record.get('presentation'))
        or hashlib.sha256(record['markdown'].encode('utf-8')).hexdigest()!=record['markdown_sha256']
        or (folder/(preview_id+'.md')).read_bytes()!=record['markdown'].encode('utf-8')
        or (record['after_message'] and (message['id']==record['after_message']['id'] or message['rpc_id']==record['after_message']['rpc_id']))):
        reject('stale_binding','Displayed review or user message does not match')
    name=item['decision_operation'];args={k:v for k,v in item['binding'].items() if k in ('project_id','task_id','run_id','build_id')}
    if name in ('task_decide','hand_decide'):args.pop('project_id',None)
    event_id='chat-event-'+digest({'session':host['session_id'],'message':message['id'],'rpc':message['rpc_id']})
    principal=trusted.local_principal()
    with service.adapter.workflow() as w:
        bound_scope=scope_for(name,args,w)
        if host['engineering_only']:
            database=w.db.execute('SELECT current_database() AS name').fetchone()['name']
            if not re.fullmatch(r'nexusmore_dsh_(?:decision|ui)_probe_[a-f0-9]{12,16}',database): reject()
        with service._locks(w,bound_scope):
            existing=w.db.execute('SELECT request FROM mc_trusted_user_events WHERE event_id=%s',(event_id,)).fetchone()
            if existing:
                # Never resubmit on a repeated pre-step / uncertain outcome.
                return {'status':'already_received','request_id':existing['request']['request_id'],'dispatch_performed':False}
            if scope.get('task_id') and name=='assembly_decide':
                from .paper_review_routing import contains_task
                if not contains_task(w,scope['project_id'],args['build_id'],scope['task_id'],scope.get('run_id')):reject('stale_binding','Assembly is no longer linked to this chat task')
            if service._review(w,name,args,item['pending_id'])!=review: reject('stale_binding','Review changed; show the new document before confirming')
            if item['kind']=='model' and not host_review_readiness(w,scope['task_id'])['model_ready']: reject('stale_binding')
            check_binding(w,args,{k:v for k,v in item['binding'].items() if k!='artifact_sha256'})
            request=trusted.decision_request(item,review,'approve',message['text'],message['text'],channel='trusted_host_ui')
            request['user_event']['event_id']=event_id
            # One source message owns exactly one durable authorization.
            capture={'protocol':PROTOCOL,'source':'dsh_native_chat','host':host,'scope':validate_scope({k:v for k,v in bound_scope.items() if k in ('project_id','task_id','run_id','build_id')}),'principal':principal,
                     'event_id':event_id,'review_sha256':digest(review),'request_sha256':request_digest(request),
                     'preview_id':preview_id,'markdown_sha256':record['markdown_sha256'],
                     'after_message':record['after_message'],'message':message}
            if record.get('presentation'): capture['presentation']=record['presentation']
            if host['engineering_only'] and not principal['kind'].startswith('test_simulated'):
                reject(message='Synthetic chat captures require synthetic principal')
            expires=w.db.execute('SELECT clock_timestamp() AS now').fetchone()['now']+timedelta(minutes=10)
            with w.db.transaction():
                w.db.execute('INSERT INTO mc_trusted_user_events(event_id,channel,principal,pending_id,review_sha256,review,statement,statement_sha256,request_sha256,request,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (event_id,'trusted_host_ui',Jsonb(principal),item['pending_id'],digest(review),Jsonb(review),message['text'],trusted.statement_hash(message['text']),request_digest(request),Jsonb(request),expires))
                w.db.execute('INSERT INTO mc_trusted_host_captures(event_id,capture,capture_sha256) VALUES(%s,%s,%s)',(event_id,Jsonb(capture),digest(capture)))
    return service.submit(request)


def validate_chat_capture(c,event):
    message=native_message(c.get('message'))
    if (c.get('protocol')!=PROTOCOL or c.get('source')!='dsh_native_chat' or not is_approval(message['text'],event['review']['pending']['kind'])
        or message['text']!=event['statement'] or message['text']!=event['request']['arguments']['body']['reason']
        or event['request']['arguments']['body']['decision']!='approve'
        or c.get('preview_id')!=_preview_identity(c['host']['session_id'],event['review_sha256'],c.get('presentation'))
        or not re.fullmatch('[a-f0-9]{64}',c.get('markdown_sha256',''))
        or c['event_id']!='chat-event-'+digest({'session':c['host']['session_id'],'message':message['id'],'rpc':message['rpc_id']})):
        reject()
    if c.get('presentation') and c['presentation'].get('markdown_sha256')!=c.get('markdown_sha256'): reject()
    after=c.get('after_message')
    if after:
        native_message(after)
        if after['id']==message['id'] or after['rpc_id']==message['rpc_id']:reject()
    if c['host']['engineering_only'] and not event['principal']['kind'].startswith('test_simulated'):reject()


def main():
    try:
        if sys.argv[1:]!=['--private-stdio']:reject()
        _private_parent();v=_read()
        if (not isinstance(v,dict) or set(v)!={'protocol','mode','scope','host','payload'} or v['protocol']!=PROTOCOL):reject()
        validate_host(v['host']);validate_scope(v['scope'])
        with redirect_stdout(sys.stderr):
            if v['mode']=='preview' and set(v['payload'])=={'after_message','kind'}:
                result=prepare_review(v['scope'],v['host'],v['payload']['after_message'],kind=v['payload']['kind'])
            elif v['mode']=='confirm' and set(v['payload'])=={'preview_id','message'}:
                result=confirm_review(v['scope'],v['host'],v['payload']['preview_id'],v['payload']['message'])
            else:reject()
        _write({'type':'result','result':result})
    except Exception as exc:
        try:_write({'type':'error','code':exc.code if isinstance(exc,BusinessContractError) else 'service_unavailable'})
        except (OSError,ValueError):pass
        raise SystemExit(1) from None


if __name__=='__main__':main()
