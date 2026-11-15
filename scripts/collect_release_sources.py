"""Collect fixed runtime license/source evidence without running upstream build code."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from email.parser import BytesParser
import hashlib,json,re,urllib.request,zipfile
from pathlib import Path

def normalize(name):return re.sub(r'[-_.]+','-',name).lower()
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def fetch(url,maximum):
    request=urllib.request.Request(url,headers={'User-Agent':'NexusMORE-source-review/0.1'})
    with urllib.request.urlopen(request,timeout=120) as response:
        data=response.read(maximum+1)
    if len(data)>maximum:raise ValueError('Upstream file exceeds collection bound')
    return data

def collect(inventory,wheelhouse,output):
    inv=json.loads(Path(inventory).read_text(encoding='utf-8'));out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    for folder in ['metadata','sources','licenses']:(out/folder).mkdir()
    wheel_map={}
    for wheel in Path(wheelhouse).glob('*.whl'):
        with zipfile.ZipFile(wheel) as archive:
            md=BytesParser().parsebytes(archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))))
            wheel_map[(normalize(md['Name']),md['Version'])]=wheel
    rows=[]
    def one(row):
        name=normalize(row['name']);version=row['version'];key=name+'-'+version
        result={'name':row['name'],'version':version,'status':'review_required','source_downloaded':False}
        try:
            data=fetch('https://pypi.org/pypi/'+name+'/'+version+'/json',8*1024*1024)
            metadata=json.loads(data);assert normalize(metadata['info']['name'])==name and metadata['info']['version']==version
            (out/'metadata'/(key+'.json')).write_bytes(data)
            result.update(metadata_sha256=hashlib.sha256(data).hexdigest(),declared_expression=metadata['info'].get('license_expression'),declared_license=(metadata['info'].get('license') or '')[:1000],project_urls=metadata['info'].get('project_urls'))
            wheel=wheel_map.get((name,version))
            if wheel:
                asset=next((a for a in metadata['urls'] if a['filename']==wheel.name),None)
                result['wheel']={'filename':wheel.name,'sha256':sha(wheel),'official_PyPI_digest_matches':bool(asset and sha(wheel)==asset['digests']['sha256'])}
                if asset and not result['wheel']['official_PyPI_digest_matches']:raise ValueError('Local wheel differs from official PyPI digest')
            else:result['wheel_inventory_note']='No matching wheel in this wheelhouse; installer runtime or separately obtained artifact needs mapping'
            source=next((a for a in metadata['urls'] if a['packagetype']=='sdist'),None)
            if source:
                if source['size']>200*1024*1024:raise ValueError('Source exceeds 200 MiB per-file review bound')
                if not source['url'].startswith('https://files.pythonhosted.org/'):raise ValueError('Unexpected source host')
                content=fetch(source['url'],200*1024*1024)
                digest=hashlib.sha256(content).hexdigest()
                if digest!=source['digests']['sha256'] or len(content)!=source['size']:raise ValueError('Source digest/size mismatch')
                (out/'sources'/source['filename']).write_bytes(content)
                result.update(source_downloaded=True,source={'filename':source['filename'],'sha256':digest,'bytes':len(content),'url':source['url']})
            else:result['source_gap']='No sdist published for this version; obtain fixed official source and bundled submodule/build sources separately'
            result['status']='evidence_collected_not_license_clearance'
        except Exception as error:result.update(status='collection_failed',error=str(error))
        return result
    site=Path(inv['source_runtime_site_packages'])
    # Preserve complete installed notices, including nested BUILD_LICENSES component texts.
    for row in inv['dependencies']:
        dest=out/'licenses'/(normalize(row['name'])+'-'+row['version']);dest.mkdir()
        for item in row['license_files']:
            rel=Path(item['path']);source=(site/rel).resolve()
            if not source.is_relative_to(site.resolve()) or sha(source)!=item['sha256']:raise ValueError('Installed license identity/boundary mismatch')
            target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(one,row) for row in inv['dependencies']]
        for future in as_completed(futures):
            row=future.result();rows.append(row)
            (out/'progress.json').write_text(json.dumps({'completed':len(rows),'total':len(futures),'sources':sum(r['source_downloaded'] for r in rows),'failed':[r['name'] for r in rows if r['status']=='collection_failed']},indent=2),encoding='utf-8')
            if len(rows)%10==0:print('Collected '+str(len(rows))+'/'+str(len(futures)),flush=True)
    rows.sort(key=lambda r:normalize(r['name']))
    result={'schema_version':'1.0.0','status':'evidence_collection_finished_not_legal_clearance','packages':rows,'package_count':len(rows),'downloaded_sources':sum(r['source_downloaded'] for r in rows),'collection_failures':[r['name'] for r in rows if r['status']=='collection_failed'],'source_gaps':[r['name'] for r in rows if not r['source_downloaded']],'public_release_cleared':False}
    (out/'collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='packages'}),flush=True)
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['inventory','wheelhouse','output']:parser.add_argument('--'+key,type=Path,required=True)
    a=parser.parse_args();collect(a.inventory,a.wheelhouse,a.output)
