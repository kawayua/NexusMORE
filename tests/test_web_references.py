"""Provenance, public-network boundaries and same-problem reference contracts."""
import hashlib
import json
from unittest.mock import patch

import pytest

from modelcrew.paper_search_mcp import SearchTool
from modelcrew.web_references import PublicWeb, ReferenceStore, WebUnavailable, public_target


PAGE='https://example.org/paper'


def response(content=b'<html><title>Reference</title><main>Method text</main></html>',ctype='text/html'):
    return {'url':PAGE,'content':content,'content_type':ctype,'retrieved_at':'2026-11-06T00:00:00Z'}


class FixedWeb(PublicWeb):
    def fetch(self,url): return response()


@pytest.mark.parametrize('url',[
    'file:///etc/passwd','http://user:secret@example.org/', 'http://example.org:56333/',
    'http://127.0.0.1/', 'http://[::1]/', 'http://169.254.169.254/latest/',
    'http://10.0.0.1/', 'http://example.org/\r\nInjected:yes',
])
def test_private_or_credentialed_urls_are_rejected(url):
    with pytest.raises(ValueError): public_target(url)


def test_all_dns_addresses_checked_and_public_ip_returned():
    with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]):
        assert public_target(PAGE)[-1]=='8.8.8.8'
    with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('127.0.0.1',443))]):
        with pytest.raises(ValueError):public_target(PAGE)


def test_search_filters_provider_noise_and_scoped_links():
    class Web(PublicWeb):
        def fetch(self,url):
            if 'bing.com' in url:
                return response(b'<rss><channel><item><title>unrelated furniture</title><link>https://example.org/no</link><description>noise</description></item><item><title>A163 paper</title><link>https://example.org/yes</link><description>reference</description></item></channel></rss>','application/rss+xml')
            return response(b'<a href="/a">A163 paper</a><a href="/a">A163 duplicate</a><a href="/b">Other</a>')
    assert [row['url'] for row in Web().search('A163',5)[1]]==['https://example.org/yes']
    assert [row['url'] for row in Web().search('A163',5,PAGE)[1]]==['https://example.org/a']


def test_search_challenge_is_error_not_empty_success():
    with pytest.raises(WebUnavailable):FixedWeb().search('A163',5)


def test_read_limits_text_and_labels_images_without_inventing_ocr():
    class Web(PublicWeb):
        def fetch(self,url):return response(b'<title>Paper</title><main><script>hidden</script>'+b'x'*25000+b'<img src="/page01.jpg" alt="page1"></main>')
    value=Web().read(PAGE)
    assert value['truncated'] and len(value['hits'][0]['text'])==24000
    assert value['images'][0]['url']=='https://example.org/page01.jpg'
    assert 'not transcribed' in value['content_warning']
    assert value['hits'][0]['source_sha256']==hashlib.sha256(Web().fetch(PAGE)['content']).hexdigest()


def test_reference_binding_survives_restart_and_detects_tampering(tmp_path):
    hit=FixedWeb().read(PAGE)['hits'][0]
    bound=ReferenceStore(tmp_path).bind(hit,'call-123')
    citation=bound['citation'];ref=citation['reference_id']
    record=ReferenceStore(tmp_path).get(ref)
    assert record['text']=='Method text' and record['citation']==citation
    assert record['modeler_generated'] is False and record['untrusted_content'] is True
    path=tmp_path/(ref+'.json')
    altered=json.loads(path.read_text(encoding='utf-8'));altered['text']='altered'
    path.write_text(json.dumps(altered),encoding='utf-8')
    with pytest.raises(WebUnavailable):ReferenceStore(tmp_path).get(ref)
    with pytest.raises(ValueError):ReferenceStore(tmp_path).get('../escape')


def test_mcp_web_and_reference_lookup_do_not_load_bge(tmp_path):
    def forbidden(): raise AssertionError('Web request loaded local embedding model')
    tool=SearchTool(forbidden,log_path=tmp_path/'calls.jsonl',web=FixedWeb(),references=tmp_path/'refs')
    result=tool.invoke('web_read',{'url':PAGE})
    assert not result.isError
    hit=result.structuredContent['data']['hits'][0];citation=hit['citation']
    assert citation['bound_call_id']==result.structuredContent['call_id']
    assert citation['source_url']==PAGE and citation['modeler_generated'] is False
    lookup=SearchTool(forbidden,log_path=tmp_path/'calls.jsonl',references=tmp_path/'refs').invoke('reference_get',{'reference_id':citation['reference_id']})
    assert not lookup.isError
    assert lookup.structuredContent['data']['hits'][0]['citation']==citation
    logs=[json.loads(line) for line in (tmp_path/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all(log['reference_ids']==[citation['reference_id']] for log in logs)


def test_missing_reference_and_web_failure_are_explicit(tmp_path):
    tool=SearchTool(log_path=tmp_path/'calls.jsonl')
    assert tool.invoke('reference_get',{'reference_id':'ref_'+'0'*64}).structuredContent['error']['code']=='reference_unavailable'
    assert tool.invoke('web_read',{'url':'http://127.0.0.1/'}).structuredContent['error']['code']=='invalid_request'


def test_same_problem_local_evidence_has_external_citation(tmp_path):
    hit={**FixedWeb().read(PAGE)['hits'][0],'same_problem_reference':True}
    class Local:
        def search(self,query,**kwargs):
            return {'status':'ok','query':query,'include_same_problem':kwargs['include_same_problem'],
                    'collection':'TEST','corpus_sha256':'TEST','embedding_signature':'TEST','hits':[hit]}
    tool=SearchTool(Local,log_path=tmp_path/'calls.jsonl')
    result=tool.invoke('paper_search',{'query':'same problem'})
    assert not result.isError
    assert result.structuredContent['data']['hits'][0]['same_problem_reference'] is True
    assert result.structuredContent['data']['hits'][0]['citation']['origin']=='external_reference'
    blocked=tool.invoke('paper_search',{'query':'same problem','include_same_problem':False})
    assert blocked.isError and blocked.structuredContent['error']['code']=='retrieval_unavailable'


def test_redirect_to_private_host_blocked_before_second_connection():
    from unittest.mock import MagicMock
    connection=MagicMock()
    redirect=connection.getresponse.return_value
    redirect.status=302
    redirect.getheader.return_value='http://127.0.0.1/private'
    original=public_target
    def resolve(url):
        if url==PAGE:return (__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(PAGE),'example.org',80,'8.8.8.8')
        return original(url)
    with patch('modelcrew.web_references.public_target',side_effect=resolve), patch('http.client.HTTPConnection',return_value=connection), patch('socket.create_connection') as connect, patch('ssl.create_default_context'):
        with pytest.raises(ValueError):PublicWeb().fetch(PAGE)
        assert connect.call_count==1


def test_pdf_page_locator_and_empty_pdf_failure():
    import io
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=200,height=200)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 100 Td (Reference method) Tj ET')
    page[NameObject('/Contents')]=stream
    output=io.BytesIO();writer.write(output)
    class Web(PublicWeb):
        def fetch(self,url):return response(output.getvalue(),'application/pdf')
    value=Web().read(PAGE)
    assert value['hits'][0]['locator']['page']==1
    assert 'Reference method' in value['hits'][0]['text']
    empty=PdfWriter();empty.add_blank_page(width=200,height=200);output=io.BytesIO();empty.write(output)
    with pytest.raises(WebUnavailable,match='OCR'):Web().read(PAGE)
