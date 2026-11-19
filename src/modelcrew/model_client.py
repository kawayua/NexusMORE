"""One-shot configured model calls. No secrets, tool execution or implicit retries."""
import json
import base64
import hashlib
import time
import uuid
from pathlib import Path

import httpx

from .drafts import model_config


class ModelCallError(RuntimeError):
    def __init__(self, message, *, domain='infrastructure'):
        super().__init__(message)
        self.domain = domain


def decode_content(content, stage, data):
    """Decode the declared author protocol, never repair or normalize model text."""
    if stage == 'Writer' and data.get('output_protocol') == 'raw_markdown_v1':
        if not isinstance(content, str) or not content.strip():
            raise ModelCallError('Writer must return nonempty Markdown', domain='model_output')
        return {'markdown': content}
    answer = json.loads(content)
    if not isinstance(answer, dict):
        raise ModelCallError('Model must return one JSON object', domain='model_output')
    return answer


class JsonModel:
    def __init__(self, *, client=None, config=None):
        self.config = config or model_config()
        self.client = client
        for key in ['MODELCREW_LLM_API_KEY', 'MODELCREW_LLM_MODEL', 'MODELCREW_LLM_BASE_URL']:
            if not self.config.get(key):
                raise ModelCallError('Configured model service is incomplete')

    def call(self, folder, stage, system, data, *, max_tokens=10000, image_inputs=None):
        folder = Path(folder)
        identifier = str(uuid.uuid4())
        model = (self.config.get('MODELCREW_VISION_MODEL') if stage=='P2' and image_inputs else self.config.get('MODELCREW_M1_MODEL') if stage == 'M1' else self.config.get('MODELCREW_W2_MODEL') if stage == 'W2' else None) or self.config['MODELCREW_LLM_MODEL']
        # New stateless request each time; M1 receives evidence, not author chat history.
        request = {'model': model, 'max_tokens': max_tokens,
                   'enable_thinking': False, 'thinking': {'type': 'disabled'},
                   'messages': [{'role': 'system', 'content': system},
                                {'role': 'user', 'content': json.dumps(data, ensure_ascii=False, allow_nan=False)}]}
        # Structured stages request native JSON at the provider, not fenced prose.
        # JSON mode is not server-side schema validation; local strict checks remain.
        if not (stage == 'Writer' and data.get('output_protocol') == 'raw_markdown_v1'):
            request['response_format'] = {'type': 'json_object'}
        if stage=='W2' and data.get('output_protocol') in ('w2_evidence_refs_v2','w2_evidence_refs_v3'):
            mode=self.config.get('MODELCREW_W2_RESPONSE_FORMAT','json_object')
            if mode not in ['json_object','json_schema']:
                raise ModelCallError('Unsupported W2 response format configuration',domain='not_sent')
            request['response_format']={'type':mode}
            if mode=='json_schema':
                request['response_format']['json_schema']={
                    'name':data['output_protocol'],'strict':True,'schema':data['schema']}
        image_manifest=[]
        if image_inputs:
            if len(image_inputs)>100:raise ModelCallError('Too many review images')
            parts=[{'type':'text','text':request['messages'][1]['content']}]
            for image in image_inputs:
                raw=Path(image['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=image['sha256']:
                    raise ModelCallError('Review image changed before dispatch')
                if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ModelCallError('Review images must be PNG')
                image_manifest.append({'image_id':image.get('image_id'), 'sha256':image['sha256'],
                    'size_bytes':len(raw),'label':image['label']})
                parts.append({'type':'text','text':image['label']})
                parts.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(raw).decode('ascii'),'detail':'high'}})
            request['messages'][1]['content']=parts
        prefix = folder / (stage + '-' + identifier)
        def write(suffix, value):
            text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
            Path(str(prefix) + suffix).write_text(text.replace(self.config['MODELCREW_LLM_API_KEY'], '[REDACTED]'), encoding='utf-8')
        write('-request.json', request)
        meta = {'call_id': identifier, 'context_id': str(uuid.uuid4()), 'stage': stage,
                'configured_model': model, 'status': 'started', 'independent_stateless_request': True, 'image_count':len(image_inputs or []),
                'image_manifest':image_manifest,'image_bytes_total':sum(i['size_bytes'] for i in image_manifest),
                'request_record_sha256':hashlib.sha256(Path(str(prefix)+'-request.json').read_bytes()).hexdigest(),
                'output_protocol': data.get('output_protocol', 'json_object') if stage in ['Writer','W2'] else 'json_object',
                'response_format_type':request.get('response_format',{}).get('type','none'),
                'server_schema_requested':request.get('response_format',{}).get('type')=='json_schema',
                'server_schema_enforced':None if request.get('response_format',{}).get('type')=='json_schema' else False}
        write('-metadata.json', meta)
        start = time.perf_counter()
        try:
            post = self.client.post if self.client is not None else httpx.post
            response = post(self.config['MODELCREW_LLM_BASE_URL'].rstrip('/') + '/chat/completions',
                            headers={'Authorization': 'Bearer ' + self.config['MODELCREW_LLM_API_KEY']},
                            json=request, timeout=httpx.Timeout(600, connect=30))
            meta.update(http_status=response.status_code, elapsed_seconds=time.perf_counter() - start)
            if response.status_code >= 400:
                meta['status'] = 'http_error'
                # Never persist request headers or unsanitized transport exceptions.
                try:
                    error = response.json().get('error', {}).get('message', '')
                except Exception:
                    error = ''
                meta['error_message'] = str(error)[:1000]
                raise ModelCallError('Model HTTP ' + str(response.status_code))
            raw = response.json()
            write('-response.json', raw)
            meta['response_sha256']=hashlib.sha256(Path(str(prefix)+'-response.json').read_bytes()).hexdigest()
            choice = raw['choices'][0]
            meta.update(usage=raw.get('usage'), returned_model=raw.get('model'), finish_reason=choice.get('finish_reason'))
            if choice.get('finish_reason') != 'stop':
                raise ModelCallError('Incomplete model response; preserved without retry', domain='model_output')
            answer = decode_content(choice['message']['content'], stage, data)
            meta['status'] = 'completed'
            return answer, meta
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            meta.update(status='not_sent' if stage=='W2' else 'unknown', error_type=type(exc).__name__)
            raise ModelCallError('Model connection failed before HTTP delivery; no automatic resend',
                                 domain='not_sent' if stage=='W2' else 'infrastructure') from None
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            meta.update(status='unknown', error_type=type(exc).__name__)
            raise ModelCallError('Model transport outcome unknown; no automatic resend') from None
        except Exception:
            if meta['status'] == 'started':
                meta['status'] = 'invalid_response'
            raise
        finally:
            meta['elapsed_seconds'] = time.perf_counter() - start
            write('-metadata.json', meta)
