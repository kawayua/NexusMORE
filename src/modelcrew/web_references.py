"""Bounded public-web retrieval and immutable external-reference receipts.

DNS addresses are checked and the chosen address is pinned for the connection;
redirects are checked independently. No cookies, credentials or proxy inheritance.
"""
import hashlib
import http.client
import io
import ipaddress
import json
import os
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from pypdf import PdfReader
from .contracts import digest

MAX_BYTES = 5 * 1024 * 1024


class WebUnavailable(RuntimeError):
    pass


def public_target(url):
    try:
        parts = urlsplit(url)
        if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.port not in (None, 80, 443)
                or any(ord(c) < 33 for c in url)):
            raise ValueError('Only public HTTP(S) URLs without credentials on standard ports are supported')
        host = parts.hostname.encode('idna').decode('ascii')
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = sorted({item[4][0] for item in addresses})
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('Private, local and reserved destinations are prohibited')
        return parts, host, port, ips[0]
    except (OSError, UnicodeError) as exc:
        raise WebUnavailable('Public host resolution failed') from exc


class PublicWeb:
    def fetch(self, url):
        deadline = time.monotonic() + 45
        for _ in range(6):
            parts, host, port, ip = public_target(url)
            connection = http.client.HTTPConnection(host, port, timeout=min(15, max(1, deadline-time.monotonic())))
            raw = None
            try:
                raw = socket.create_connection((ip, port), timeout=connection.timeout)
                connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host) if parts.scheme == 'https' else raw
                path = urlunsplit(('', '', parts.path or '/', parts.query, ''))
                connection.request('GET', path, headers={'Host':host, 'User-Agent':'ModelCrew-Reference/0.2',
                    'Accept':'text/html,application/pdf,application/rss+xml,application/xml,text/plain', 'Accept-Encoding':'identity'})
                response = connection.getresponse()
                if response.status in (301,302,303,307,308):
                    location=response.getheader('Location')
                    if not location: raise WebUnavailable('Redirect has no location')
                    url=urljoin(url,location)
                    continue
                if response.status != 200:
                    raise WebUnavailable('Public source returned HTTP '+str(response.status))
                length=response.getheader('Content-Length')
                if length and int(length)>MAX_BYTES: raise WebUnavailable('Source exceeds 5 MiB limit')
                data=bytearray()
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0: raise WebUnavailable('Public source time limit exceeded')
                    if connection.sock is not None: connection.sock.settimeout(min(10,remaining))
                    block=response.read1(min(65536, MAX_BYTES+1-len(data)))
                    if not block: break
                    data.extend(block)
                    if len(data)>MAX_BYTES: raise WebUnavailable('Source exceeds 5 MiB limit')
                if response.getheader('Content-Encoding','identity') != 'identity':
                    raise WebUnavailable('Compressed transfer unsupported')
                return {'url':url, 'content':bytes(data), 'content_type':response.getheader('Content-Type',''),
                        'retrieved_at':datetime.now(timezone.utc).isoformat()}
            except (OSError, http.client.HTTPException, ValueError) as exc:
                raise WebUnavailable('Public source transfer failed') from exc
            finally:
                connection.close()
                if raw is not None: raw.close()
        raise WebUnavailable('Too many redirects')

    def search(self, query, limit, scope_url=None):
        terms=re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]+',query.lower())
        def matches(title,text):
            combined=(title+' '+text).lower()
            return bool(terms) and all(term in combined for term in terms)
        if scope_url:
            response=self.fetch(scope_url)
            if 'html' not in response['content_type'].lower():
                raise WebUnavailable('Directory search requires an HTML page')
            soup=BeautifulSoup(response['content'],'html.parser')
            rows=[];seen=set()
            for anchor in soup.select('a[href]'):
                title=anchor.get_text(' ',strip=True)
                target=urljoin(response['url'],anchor['href'])
                if urlsplit(target).scheme not in ('http','https') or target in seen or not matches(title,''):
                    continue
                seen.add(target)
                rows.append({'title':title,'url':target,'snippet':title})
                if len(rows)>=limit: break
            return response,rows
        # Public RSS endpoint; no API key. Fail explicitly on provider errors or non-RSS challenges.
        response=self.fetch('https://www.bing.com/search?'+urlencode({'q':query,'format':'rss'}))
        try:
            root=ET.fromstring(response['content'])
            if root.tag != 'rss': raise ValueError('Not RSS')
            items=root.findall('./channel/item')
            results=[]
            for item in items:
                url=item.findtext('link','')
                if urlsplit(url).scheme not in ('http','https'): continue
                title=item.findtext('title','')
                snippet=BeautifulSoup(item.findtext('description',''),'html.parser').get_text(' ',strip=True)
                if not matches(title,snippet): continue
                results.append({'title':title, 'url':url,'snippet':snippet})
                if len(results)>=limit: break
            return response, results
        except (ET.ParseError,ValueError) as exc:
            raise WebUnavailable('Search provider returned an unsupported response') from exc

    def read(self, url):
        response=self.fetch(url)
        data=response['content']; ctype=response['content_type'].lower()
        links=[]; images=[]; metadata={}; units=[]
        if data.startswith(b'%PDF-') or 'application/pdf' in ctype:
            reader=PdfReader(io.BytesIO(data))
            if reader.is_encrypted: raise WebUnavailable('Encrypted PDF unsupported')
            metadata={'title':str((reader.metadata or {}).get('/Title','')) or url,
                      'author':str((reader.metadata or {}).get('/Author','')) or None}
            for i,page in enumerate(reader.pages[:40],1):
                text=page.extract_text() or ''
                if text.strip(): units.append(({'page':i},text))
            parser='web-pdf-text-1'
            limited=len(reader.pages)>40
        elif 'html' in ctype:
            soup=BeautifulSoup(data,'html.parser')
            metadata={'title':soup.title.get_text(' ',strip=True) if soup.title else url}
            for name,key in [('author','author'),('citation_author','author'),('citation_title','title'),
                             ('citation_publication_date','publication_date'),('citation_doi','doi')]:
                tag=soup.find('meta',attrs={'name':name})
                if tag and tag.get('content'): metadata[key]=tag['content']
            main=soup.select_one('main') or soup.select_one('article') or soup.select_one('.detail-content') or soup.body or soup
            for node in main.select('script,style,nav,header,footer,noscript'): node.decompose()
            for image in main.select('img[src]')[:60]:
                target=urljoin(response['url'],image['src'])
                if urlsplit(target).scheme in ('http','https'):
                    images.append({'alt':image.get('alt','')[:300],'url':target})
            for anchor in main.select('a[href]'):
                target=urljoin(response['url'],anchor['href'])
                if urlsplit(target).scheme in ('http','https') and len(links)<60:
                    links.append({'title':anchor.get_text(' ',strip=True)[:300], 'url':target})
            units=[({'section':'body'},main.get_text('\n',strip=True))]
            parser='web-html-1'; limited=False
        elif ctype.startswith('text/plain'):
            metadata={'title':url};units=[({'section':'text'},data.decode('utf-8',errors='replace'))]
            parser='web-text-1';limited=False
        else:
            raise WebUnavailable('Unsupported content type; expected HTML, text or PDF')
        if not any(text.strip() for _,text in units):
            raise WebUnavailable('No readable text; scanned PDF may require OCR')
        hits=[]; remaining=24000
        for locator,text in units:
            if remaining<=0: limited=True;break
            value=text[:remaining]
            if len(value)<len(text):limited=True
            remaining-=len(value)
            hits.append(make_hit(response, value, metadata.get('title',url), parser,
                                 {**locator,'char_start':0,'char_end':len(value)}, metadata=metadata))
        return {'status':'ok','query':url,'include_same_problem':True,'hits':hits,
                'provider':'direct_public_web','links':links,'truncated':limited,'images':images,
                'content_warning':'Images are not transcribed; extracted HTML text is not proof of reading image-based paper content. OCR may be required.' if images else None}


def make_hit(response,text,title,parser,locator,*,url=None,metadata=None):
    source_url=url or response['url']
    sha=hashlib.sha256(response['content']).hexdigest()
    return {'doc_id':digest(source_url),'chunk_id':digest({'url':source_url,'sha':sha,'text':text,'locator':locator}),
            'text':text,'title':title,'source_url':source_url,'source_sha256':sha,'parser':parser,
            'locator':locator,'score':0.0,'score_kind':'not_ranked','same_problem_reference':None,
            'classification':'unreviewed','retrieved_at':response['retrieved_at'],
            'metadata':metadata or {},'evidence_kind':'search_snippet' if parser in ('bing-rss-1','directory-link-1') else 'source_text',
            'discovery_url':response['url'] if parser in ('bing-rss-1','directory-link-1') else None,
            'hash_scope':'search_response' if parser in ('bing-rss-1','directory-link-1') else 'source_response'}


class ReferenceStore:
    def __init__(self, root):
        from .retrieval_paths import reference_directory
        self.root=reference_directory(explicit=root)

    def bind(self, hit, call_id):
        record={**hit, 'origin':'builtin_project_reference' if hit.get('reference_kind')=='builtin_project_reference' else 'external_reference','modeler_generated':False,
                'usage':'idea_reference_requires_user_model_approval', 'untrusted_content':True,
                'content_sha256':digest(hit['text']), 'bound_call_id':call_id,
                'recorded_at':datetime.now(timezone.utc).isoformat()}
        ref_id='ref_'+digest(record)
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/(ref_id+'.json')).open('x',encoding='utf-8') as stream:
            json.dump(record,stream,ensure_ascii=False,allow_nan=False,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        citation=self.citation(record, ref_id)
        return {**hit,'citation':citation}

    @staticmethod
    def citation(record, ref_id):
        hit=record
        return {'reference_id':ref_id,'source_url':hit.get('source_url'),'title':hit.get('title'),
                  'locator':hit['locator'],'source_sha256':hit['source_sha256'],
                  'content_sha256':record['content_sha256'],'origin':record.get('origin','external_reference'),
                  'modeler_generated':False,'bound_call_id':record['bound_call_id'],
                  'label':'枢模内置算法资料，仅供参考，非本次建模手生成' if record.get('origin')=='builtin_project_reference' else '外部资料，仅供思路参考，非 modeler 原创'}

    def get(self, ref_id):
        if not re.fullmatch(r'ref_[0-9a-f]{64}',ref_id): raise ValueError('Invalid reference ID')
        record=json.loads((self.root/(ref_id+'.json')).read_text(encoding='utf-8'))
        if 'ref_'+digest(record)!=ref_id: raise WebUnavailable('Reference receipt integrity check failed')
        return {**record,'citation':self.citation(record,ref_id)}
