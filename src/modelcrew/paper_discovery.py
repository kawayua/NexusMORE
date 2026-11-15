"""Project-owned candidate discovery over existing audited search tools.

DOI groups preserve all original records. Matching is never source verification.
No optional external API, model, approval or retrieval defaults are invented.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote, urlsplit


def normalized_doi(value):
    if not isinstance(value,str):return None
    value=value.strip()
    if value.lower().startswith(('http://doi.org/','https://doi.org/','https://dx.doi.org/','http://dx.doi.org/')):
        value=unquote(urlsplit(value).path.lstrip('/'))
    value=re.sub(r'^doi:\s*','',value,flags=re.I).lower()
    return value if re.fullmatch(r'10\.\d{4,9}/[^\s<>"\\]+',value) else None


def candidates(records, *, year_from=None, year_to=None):
    """Conservative DOI groups; no title collapse, missing-year filter passes or proof."""
    for year in [year_from,year_to]:
        if year is not None and (type(year) is not int or not 1800<=year<=2200):raise ValueError('Invalid year filter')
    if year_from is not None and year_to is not None and year_from>year_to:raise ValueError('Reversed year filter')
    groups={};excluded=[];seen=set()
    if len(records)>200:raise ValueError('Too many candidate records')
    for position,record in enumerate(records):
        if not isinstance(record,dict) or not isinstance(record.get('source'),str):raise ValueError('Candidate source required')
        raw=json.dumps(record,ensure_ascii=False,sort_keys=True,allow_nan=False)
        if len(raw.encode('utf-8'))>200_000:raise ValueError('Oversized candidate record')
        key=hashlib.sha256(raw.encode('utf-8')).hexdigest()
        if key in seen:continue
        seen.add(key)
        year=record.get('year')
        if type(year) is not int:year=None
        if year_from is not None or year_to is not None:
            if year is None or year_from is not None and year<year_from or year_to is not None and year>year_to:
                excluded.append({'record_sha256':key,'source':record['source'],'reason':'year_missing_or_outside_requested_range'});continue
        doi=normalized_doi(record.get('doi')) or normalized_doi(record.get('url'))
        group_key='doi:'+doi if doi else 'record:'+key
        group=groups.setdefault(group_key,{'id':group_key,'doi':doi,'records':[], 'sources':[],
                         'verification':'UNVERIFIED_CANDIDATE','match_method':'exact_normalized_doi' if doi else 'unmerged_record'})
        group['records'].append({'record_sha256':key,'original':record})
        if record['source'] not in group['sources']:group['sources'].append(record['source'])
    items=list(groups.values())
    for group in items:
        group['conflicts']={}
        for field in ['title','year','authors']:
            values={json.dumps(r['original'][field],ensure_ascii=False,sort_keys=True) for r in group['records'] if r['original'].get(field) is not None}
            if len(values)>1:group['conflicts'][field]=[json.loads(v) for v in sorted(values)]
    # Suggestions only: known equal authors/year, different sources, no conflicting DOI.
    suggestions=[];used=set()
    for i,left in enumerate(items):
        if i in used:continue
        a=left['records'][0]['original']
        if not a.get('authors') or type(a.get('year')) is not int:continue
        for j in range(i+1,len(items)):
            if j in used:continue
            right=items[j];b=right['records'][0]['original']
            if set(left['sources'])&set(right['sources']) or left['doi'] and right['doi']:continue
            if a.get('authors')!=b.get('authors') or a['year']!=b.get('year'):continue
            normalize=lambda text:re.sub(r'[^\w]+','',str(text).casefold())
            title_a,title_b=normalize(a.get('title','')),normalize(b.get('title',''))
            if title_a and title_b and SequenceMatcher(None,title_a,title_b).ratio()>=0.95:
                suggestions.append({'left':left['id'],'right':right['id'],'status':'REVIEW_REQUIRED','merge_performed':False})
                used.update([i,j]);break
    return {'candidates':items,'excluded':excluded,'possible_matches':suggestions,
            'verification':'UNVERIFIED_CANDIDATE','user_approval':False}


def discover(query, output, *, sources=None, limit=5, year_from=None, year_to=None, adapter=None):
    """Persist tool envelopes and candidate identities in a new attempt directory."""
    from .package_resources import resource
    registry_raw=resource('capabilities/registry.json').read_bytes()
    policy=json.loads(registry_raw)['paper_discovery']
    sources=policy['default_sources'] if sources is None else sources
    if (not isinstance(query,str) or not query.strip() or len(query)>400 or type(limit) is not int or not 1<=limit<=10
            or not isinstance(sources,list) or not sources or any(not isinstance(source,str) for source in sources) or len(set(sources))!=len(sources)
            or any(source not in policy['allowed_sources'] for source in sources)):
        raise ValueError('Invalid query, limit or configured source; dedicated academic APIs are not registered')
    candidates([],year_from=year_from,year_to=year_to)
    folder=Path(output).resolve();folder.mkdir(parents=True,exist_ok=False)
    own=adapter is None
    if own:
        from .paper_search_mcp import SearchTool
        adapter=SearchTool(log_path=folder/'search-audit.jsonl',references=folder/'references')
    records=[];states=[]
    try:
        for source in sources:
            try:
                reply=adapter.invoke(source,{'query':query,'limit':limit})
                packet=reply.structuredContent
                if not isinstance(packet,dict):raise ValueError('Missing structured tool result')
                raw=json.dumps(packet,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
                if len(raw)>5_000_000:raise ValueError('Tool envelope exceeds resource limit')
                with (folder/(source+'.json')).open('xb') as stream:stream.write(raw)
                if packet.get('status')!='ok':
                    states.append({'source':source,'status':'error','code':(packet.get('error') or {}).get('code','invalid_tool_result')});continue
                hits=packet['data']['hits']
                if not isinstance(hits,list) or len(hits)>20:raise ValueError('Invalid search hits')
                pending=[]
                for hit in hits:
                    citation=hit.get('citation') or {}
                    pending.append({'source':source,'call_id':packet['call_id'],'title':citation.get('title') or hit.get('title'),
                        'authors':hit.get('authors'),'year':hit.get('year'),'doi':hit.get('doi'),
                        'url':hit.get('source_url'),'reference_id':citation.get('reference_id'),
                        'source_sha256':hit['source_sha256'],'content_sha256':citation.get('content_sha256'),
                        'original_hit':hit})
                records.extend(pending)
                states.append({'source':source,'status':'ok' if hits else 'empty','envelope_sha256':hashlib.sha256(raw).hexdigest(),'hits':len(hits)})
            except Exception:
                # Provider-specific details may contain secrets; only stable errors escape.
                states.append({'source':source,'status':'error','code':'invalid_or_failed_tool_response'})
        success=sum(x['status']!='error' for x in states)
        result=candidates(records,year_from=year_from,year_to=year_to)
        status='failed' if not success else 'partial' if success<len(states) else 'ok' if result['candidates'] else 'empty'
        result.update(schema_version='1.0.0',status=status,query=query,sources=states,
                      created_at=datetime.now(timezone.utc).isoformat(),policy_sha256=hashlib.sha256(registry_raw).hexdigest(),
                      scope='Discovery only; DOI grouping is not verification or model approval')
        with (folder/'discovery.json').open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
        return result
    finally:
        if own:adapter.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--query',required=True);p.add_argument('--output',required=True)
    p.add_argument('--source',action='append',dest='sources');p.add_argument('--limit',type=int,default=5)
    p.add_argument('--year-from',type=int);p.add_argument('--year-to',type=int)
    result=discover(**vars(p.parse_args()));print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['status'] in {'failed','partial'} else 0

if __name__=='__main__':raise SystemExit(main())
