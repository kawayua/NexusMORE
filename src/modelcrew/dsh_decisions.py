"""Private, parent-bound DSH native UI bridge. Never an MCP/HTTP approval API.

The OS account, trusted installed host/plugin and DB owner are the trust root.
This is not remote authentication or protection against same-account arbitrary
code/SQL. Pipe JSON alone is not accepted as independent capture evidence.
"""
from contextlib import redirect_stdout
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

from psycopg.types.json import Jsonb

from . import trusted_decisions as trusted
from .business_adapter import scope_for
from .business_contract import BusinessContractError, VERSION, request_digest
from .business_projection import check_binding
from .contracts import digest

PROTOCOL = 'nexusmore-dsh-decisions/1'
MAX_FRAME = 8 * 1024 * 1024
MAX_REVIEW = 2 * 1024 * 1024
SHA = re.compile(r'[a-f0-9]{64}')


def reject(code='untrusted_user_event', message='Invalid or cancelled native interaction'):
    raise BusinessContractError(code, message)


def adapter_sha256():
    return hashlib.sha256((Path(__file__).parent/'resources/harness/nexusmore-dsh-decisions.mjs').read_bytes()).hexdigest()


def validate_scope(scope):
    if (not isinstance(scope, dict) or set(scope) - {'project_id','task_id','run_id','build_id'}
            or not scope.get('project_id') or bool(scope.get('task_id')) == bool(scope.get('build_id'))
            or (scope.get('run_id') and not scope.get('task_id'))
            or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', v) for v in scope.values())):
        reject('invalid_request', 'Choose project + task[/run] or project + build')
    return dict(scope)


def validate_host(host):
    if (not isinstance(host, dict) or set(host) != {'instance_id','session_id','pid','adapter_sha256','engineering_only'}
            or host['pid'] != os.getppid() or isinstance(host['pid'], bool)
            or not isinstance(host['engineering_only'], bool)
            or host['adapter_sha256'] != adapter_sha256()
            or any(not isinstance(host[k], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', host[k]) for k in ('instance_id','session_id'))):
        reject(message='Host parent, session or installed adapter mismatch')
    return dict(host)


def _answer(frame, value):
    if not isinstance(value, dict) or set(value) != {'type','frame_id','result'} or value['type'] != 'answer' or value['frame_id'] != frame['frame_id']:
        reject()
    result = value['result']
    if not isinstance(result, dict) or set(result) != {'answers'} or not isinstance(result['answers'], list) or len(result['answers']) != len(frame['questions']):
        reject()
    answers = {}
    for question, answer in zip(frame['questions'], result['answers']):
        if (not isinstance(answer, dict) or set(answer) - {'id','selected','custom'}
                or answer.get('id') != question['id'] or not isinstance(answer.get('selected'), list)):
            reject()
        selected = answer['selected']; custom = answer.get('custom', '')
        if question.get('options'):
            if len(selected) != 1 or selected[0] not in [o['label'] for o in question['options']] or custom:
                reject()
            answers[question['id']] = selected[0]
        else:
            if selected or not isinstance(custom, str) or not custom.strip() or len(custom) > 2000:
                reject('user_input_required', 'Explicit bounded reason and statement required')
            answers[question['id']] = custom
    return answers


class NativeDecisionSession:
    """One private worker, one native conversation and at most one captured request."""
    def __init__(self, scope, host, service=None):
        self.scope = validate_scope(scope); self.host = validate_host(host)
        self.service = service or trusted.TrustedDecisions()
        self.principal = trusted.local_principal()
        self.deadline = time.monotonic() + 600
        self.transcript = []; self.frame = None; self.closed = False; self.request = None
        with self.service.adapter.workflow() as w:
            identity = w.db.execute('SELECT clock_timestamp() AS now,current_database() AS database').fetchone()
            now = identity['now']
            if self.host['engineering_only'] and not re.fullmatch(r'nexusmore_dsh_(?:decision|ui)_probe_[a-f0-9]{12,16}', identity['database']):
                reject(message='Engineering native decisions require an isolated probe database')
            if not w.db.execute('SELECT 1 FROM mc_migrations WHERE version=15').fetchone():
                reject('service_unavailable', 'Host capture migration required')
        self.expires_at = now + timedelta(minutes=10)

    def _question(self, stage, questions):
        frame_id = os.urandom(32).hex()
        for i, question in enumerate(questions):
            if self.host['engineering_only']:
                question['detail'] = 'TEST_ENGINEERING_ONLY：合成工程数据，不是真实业务批准。\n\n' + question.get('detail', '')
            question['id'] = frame_id + ':' + str(i)
            question['multiSelect'] = False
        self.frame = {'type':'questions','frame_id':frame_id,'stage':stage,'questions':questions}
        if len(json.dumps(self.frame, ensure_ascii=False).encode('utf-8')) > MAX_FRAME:
            reject('user_input_required', 'Review too large for native card; use trusted local terminal')
        return self.frame

    def begin(self):
        if self.frame or self.closed: reject()
        self.items = [p for p in self.service.pending(self.scope)
                      if all(p['binding'].get(k)==v for k,v in self.scope.items())]
        if not self.items: return {'type':'result','result':{'status':'no_pending','scope':self.scope}}
        if len(self.items) > 20: reject('user_input_required', 'Narrow the scope with run/build')
        return self._question('select', [{'header':'选择本次审阅对象','question':'请选择一个待确认项；正文与配图必须分别决定。',
            'detail':json.dumps({'scope':self.scope,'pending':self.items}, ensure_ascii=False, indent=2),
            'options':[{'label':p['pending_id'],'description':p['kind']+' / '+p['decision_operation']} for p in self.items]}])

    def answer(self, value):
        if self.closed or not self.frame or time.monotonic() >= self.deadline:
            self.closed = True; reject(message='Native interaction expired or closed')
        frame = self.frame; self.frame = None  # Consume even a malformed response.
        try:
            values = list(_answer(frame, value).values())
            self.transcript.append({'stage':frame['stage'],'frame_id':frame['frame_id'],
                'question_ids':[q['id'] for q in frame['questions']], 'questions_sha256':digest(frame['questions']),
                'result':value['result'],'result_sha256':digest(value['result'])})
            if frame['stage'] == 'select':
                self.item = next(p for p in self.items if p['pending_id'] == values[0])
                self.name = self.item['decision_operation']
                if self.name not in trusted.OPERATIONS: reject('unsupported_operation')
                self.args = {k:v for k,v in self.item['binding'].items() if k in ('project_id','task_id','run_id','build_id')}
                if self.name in ('task_decide','hand_decide'): self.args.pop('project_id', None)
                with self.service.adapter.workflow() as w:
                    self.bound_scope = scope_for(self.name, self.args, w)
                    with self.service._locks(w, self.bound_scope):
                        self.review = self.service._review(w, self.name, self.args, self.item['pending_id'])
                text = json.dumps(self.review, ensure_ascii=False, indent=2)
                if len(text.encode('utf-8')) > MAX_REVIEW:
                    reject('user_input_required', 'Full review exceeds native size limit; use trusted local terminal')
                self.review_text = text
                return self._question('decision', [{'header':'完整审阅与决定','question':'请实际审阅完整内容和对应文件，再选择本次决定。',
                    'detail':'正文和配图分别决定；此卡不替代实际审图及独立质检。\n审阅 SHA256：'+digest(self.review)+'\n\n'+text,
                    'options':[{'label':x,'description':'同意当前内容' if x=='approve' else '退回修改当前内容'} for x in self.item['allowed_decisions']]}])
            if frame['stage'] == 'decision':
                self.decision = values[0]
                return self._question('statement', [
                    {'header':'本次审阅理由','question':'请输入本次决定的理由；跳过即取消。'},
                    {'header':'真实用户决定陈述','question':'请输入你对本次内容的明确决定陈述；不能以模型建议代替。'}])
            if frame['stage'] == 'statement':
                self.reason, self.statement = values[0].strip(), values[1]
                if self.host['engineering_only'] and not self.statement.startswith('TEST_SIMULATED_USER:'):
                    reject(message='Engineering captures must be explicitly labelled')
                self.request = trusted.decision_request(self.item, self.review, self.decision, self.reason, self.statement, channel='trusted_host_ui')
                detail = json.dumps({'decision_request':self.request,'reason':self.reason,'statement':self.statement,
                                     'review_sha256':digest(self.review)}, ensure_ascii=False, indent=2)
                return self._question('confirm', [{'header':'最终确认本笔决定','question':'请核对对象、版本、决定和陈述，再确认这一笔；取消不会提交。',
                    'detail':detail+'\n\n完整审阅原文（同一快照）：\n'+self.review_text,
                    'options':[{'label':'确认本次决定','description':'仅提交上方绑定的这一笔决定；不自动执行求解。'}, {'label':'取消','description':'不捕获、不提交业务决定。'}]}])
            if frame['stage'] != 'confirm' or values != ['确认本次决定']: reject('user_input_required', 'Native confirmation cancelled')
            self.closed = True
            self._capture()
            return {'type':'captured','event_reference':self.request['user_event'],'request_id':self.request['request_id'],
                    'operation':self.name,'binding':self.request['expected_binding'],'request_sha256':request_digest(self.request)}
        except BaseException:
            self.closed = True
            raise

    def _capture(self):
        if trusted.local_principal() != self.principal or time.monotonic() >= self.deadline: reject()
        request = self.request; event_id = request['user_event']['event_id']
        capture = {'protocol':PROTOCOL,'source':'dsh_native_human_command','host':self.host,'scope':self.scope,
            'principal':self.principal,'event_id':event_id,'review_sha256':digest(self.review),
            'request_sha256':request_digest(request),'transcript':self.transcript}
        with self.service.adapter.workflow() as w:
            with self.service._locks(w, self.bound_scope):
                if self.service._review(w, self.name, self.args, self.item['pending_id']) != self.review:
                    reject('stale_binding', 'Review changed during native interaction')
                check_binding(w, self.args, {k:v for k,v in request['expected_binding'].items() if k!='artifact_sha256'})
                if w.db.execute('SELECT clock_timestamp() >= %s AS expired', (self.expires_at,)).fetchone()['expired']:
                    reject(message='Native interaction expired')
                with w.db.transaction():
                    w.db.execute('INSERT INTO mc_trusted_user_events(event_id,channel,principal,pending_id,review_sha256,review,statement,statement_sha256,request_sha256,request,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                        (event_id,'trusted_host_ui',Jsonb(self.principal),self.item['pending_id'],digest(self.review),Jsonb(self.review),self.statement,
                         trusted.statement_hash(self.statement),request_digest(request),Jsonb(request),self.expires_at))
                    w.db.execute('INSERT INTO mc_trusted_host_captures(event_id,capture,capture_sha256) VALUES(%s,%s,%s)',
                                 (event_id,Jsonb(capture),digest(capture)))

    def submit(self, value):
        if (not self.closed or not self.request or getattr(self, '_submitted', False)
                or value != {'type':'submit','request_sha256':request_digest(self.request)}): reject()
        self._submitted = True
        return {'type':'result','result':self.service.submit(self.request)}


def validate_capture(w, event):
    row = w.db.execute('SELECT capture,capture_sha256 FROM mc_trusted_host_captures WHERE event_id=%s', (event['event_id'],)).fetchone()
    if not row: reject(message='Missing independent native host capture')
    c = row['capture']
    if not isinstance(c, dict): reject()
    chat = c.get('source') == 'dsh_native_chat'
    if (digest(c) != row['capture_sha256'] or (not chat and (c.get('protocol') != PROTOCOL or c.get('source') != 'dsh_native_human_command'))
            or any(c.get(k) != event[k] for k in ('event_id','principal','review_sha256','request_sha256'))): reject()
    if chat:
        from .dsh_chat import validate_chat_capture
        validate_chat_capture(c,event)
    else:
        transcript = c.get('transcript', [])
        if (not isinstance(transcript, list) or any(not isinstance(r, dict) for r in transcript)
                or [r.get('stage') for r in transcript] != ['select','decision','statement','confirm']): reject()
        expected = [([event['pending_id']], None), ([event['request']['arguments']['body']['decision']], None),
                    (None, [event['request']['arguments']['body']['reason'], event['statement']]), (['确认本次决定'], None)]
        nonces = set()
        for step, (choices, texts) in zip(transcript, expected):
            nonce = step.get('frame_id', '')
            ids = step.get('question_ids'); count = 2 if texts else 1
            if (not isinstance(nonce, str) or not SHA.fullmatch(nonce) or nonce in nonces
                    or ids != [nonce+':'+str(i) for i in range(count)]
                    or not isinstance(step.get('questions_sha256'), str) or not SHA.fullmatch(step['questions_sha256'])
                    or digest(step.get('result')) != step.get('result_sha256')): reject()
            nonces.add(nonce)
            questions = [{'id':qid, **({'options':[{'label':choices[i]}]} if choices else {})} for i,qid in enumerate(ids)]
            values = list(_answer({'frame_id':nonce,'questions':questions}, {'type':'answer','frame_id':nonce,'result':step['result']}).values())
            if texts and [values[0].strip(), values[1]] != texts: reject()
    h = c.get('host')
    if (not isinstance(h, dict) or not isinstance(h.get('pid'), int) or isinstance(h.get('pid'), bool) or h['pid']<=0
            or not isinstance(h.get('engineering_only'), bool) or not isinstance(h.get('adapter_sha256'), str)
            or not SHA.fullmatch(h['adapter_sha256'])
            or any(not isinstance(h.get(k), str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',h[k]) for k in ('instance_id','session_id'))
            or (h['engineering_only'] and not chat and not event['statement'].startswith('TEST_SIMULATED_USER:'))): reject()
    if any(event['request']['expected_binding'].get(k)!=v for k,v in validate_scope(c.get('scope')).items()): reject()
    # Original host identity survives restart; never compare it to a new parent PID.


def capture_status(scope, service=None):
    scope = validate_scope(scope); service = service or trusted.TrustedDecisions(); principal = trusted.local_principal()
    with service.adapter.workflow() as w:
        rows = w.db.execute("SELECT e.event_id,e.request,e.captured_at,e.expires_at > clock_timestamp() AS valid_now,EXISTS(SELECT 1 FROM mc_trusted_user_event_claims c WHERE c.event_id=e.event_id) AS claimed FROM mc_trusted_user_events e JOIN mc_trusted_host_captures h USING(event_id) WHERE e.principal=%s AND e.request->'expected_binding' @> %s ORDER BY e.captured_at DESC,e.event_id DESC LIMIT 10", (Jsonb(principal),Jsonb(scope))).fetchall()
    result = []
    for row in rows:
        req = row['request']
        with service.adapter.workflow() as w: bound = scope_for(req['operation'], req['arguments'], w)
        state = service.adapter.invoke('operation_status', {'contract_version':VERSION,'operation':'operation_status',
            'arguments':{**bound,'operation_name':req['operation'],'request_id':req['request_id']}})
        result.append({'event_id':row['event_id'],'request_id':req['request_id'],'operation':req['operation'],
                       'confirmed_binding':req['expected_binding'],'authorization_state':'claimed' if row['claimed'] else 'captured_unclaimed',
                       'capture_valid_now':row['valid_now'],'operation_status':state})
    return {'status':'ok','captures':result,'dispatch_performed':False}


def _private_parent():
    if os.name != 'nt': reject(message='This DSH bridge baseline requires Windows')
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetFileType.argtypes=[wintypes.HANDLE]; kernel.GetFileType.restype=wintypes.DWORD
    if any(kernel.GetFileType(msvcrt.get_osfhandle(stream.fileno())) != 3 for stream in (sys.stdin,sys.stdout)):
        reject(message='Private anonymous pipes required')
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,os.getppid())
    if not handle: reject()
    try:
        buf=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buf))
        if not kernel.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size)) or Path(buf.value).name.casefold()!='deepseek harness.exe':
            reject(message='Trusted DSH parent process required')
    finally: kernel.CloseHandle(handle)
    if sys.version_info[:2] != (3,13): reject(message='Python 3.13 required')


def _read():
    data=sys.stdin.buffer.readline(MAX_FRAME+1)
    if not data: raise EOFError
    if len(data)>MAX_FRAME or not data.endswith(b'\n'): reject('invalid_request')
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d: reject('invalid_request')
            d[k]=v
        return d
    return json.loads(data.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda _:reject('invalid_request'))


def _write(value):
    data=json.dumps(value,ensure_ascii=False,allow_nan=False,default=str).encode('utf-8')+b'\n'
    if len(data)>MAX_FRAME: reject('service_unavailable', 'Native frame too large; query original operation status')
    sys.stdout.buffer.write(data);sys.stdout.buffer.flush()


def main():
    try:
        if sys.argv[1:] != ['--private-stdio']: reject('invalid_request')
        _private_parent();init=_read()
        if not isinstance(init,dict) or set(init)!={'protocol','mode','scope','host'} or init['protocol']!=PROTOCOL: reject()
        validate_host(init['host']);validate_scope(init['scope'])
        if init['mode']=='status':
            with redirect_stdout(sys.stderr): result=capture_status(init['scope'])
            _write({'type':'result','result':result});return
        if init['mode']!='review': reject('invalid_request')
        with redirect_stdout(sys.stderr):
            session=NativeDecisionSession(init['scope'],init['host']);frame=session.begin()
        while True:
            _write(frame)
            if frame['type']=='result':return
            value=_read()
            with redirect_stdout(sys.stderr):
                frame=session.submit(value) if frame['type']=='captured' else session.answer(value)
    except (EOFError,KeyboardInterrupt,BrokenPipeError):return
    except Exception as exc:
        try:_write({'type':'error','code':exc.code if isinstance(exc,BusinessContractError) else 'service_unavailable','recovery':'Query /nexusmore-review-status with the original scope; never automatically redispatch'})
        except (OSError,ValueError):pass
        raise SystemExit(1) from None


if __name__=='__main__':main()
