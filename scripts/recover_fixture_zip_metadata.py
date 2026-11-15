"""Recover exact historical XLSX bytes by constrained ZIP metadata reconstruction.

No cell XML or numerical data are changed. Candidates are accepted ONLY against
an independently recorded pre-existing SHA-256. Does not overwrite input files.
"""
from modelcrew.project_assets import asset_path
import hashlib,itertools,json,re,struct,time,zlib,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from modelcrew.config import ROOT

TARGET='d86a15905d3dc16658508adb5082bfc8d4688da64b7bda744165c94cf79168a4'
RUN=asset_path(ROOT,'stage-a/2024-A-problem-1/runs/bailian-20261101T150358548111Z')

def raw_deflate(data):
    compressor=zlib.compressobj(-1,zlib.DEFLATED,-15)
    return compressor.compress(data)+compressor.flush()

def build_base(raw,infos,start_dir,core):
    locals=[];centrals=[];patches=[];offset=0
    cursor=start_dir
    for info in infos:
        original=info.header_offset;flags=struct.unpack_from('<H',raw,original+6)[0]
        if flags&8:raise ValueError('Data descriptor archives need a different recovery implementation')
        name_length,extra_length=struct.unpack_from('<HH',raw,original+26)
        header=bytearray(raw[original:original+30+name_length+extra_length])
        data_start=original+len(header);compressed=raw[data_start:data_start+info.compress_size]
        central_lengths=struct.unpack_from('<HHH',raw,cursor+28)
        central_length=46+sum(central_lengths);central=bytearray(raw[cursor:cursor+central_length]);cursor+=central_length
        if info.filename=='docProps/core.xml':
            compressed=raw_deflate(core);crc=zlib.crc32(core)
            struct.pack_into('<III',header,14,crc,len(compressed),len(core))
            struct.pack_into('<III',central,16,crc,len(compressed),len(core))
        struct.pack_into('<I',central,42,offset)
        patches.append((offset+10,None));locals.append(bytes(header)+compressed);offset+=len(header);centrals.append(central)
    central_start=offset;central_bytes=bytearray();central_offsets=[]
    for index,central in enumerate(centrals):
        central_offsets.append(central_start+len(central_bytes)+12);central_bytes.extend(central)
    eocd_start=raw.rfind(b'PK\x05\x06');eocd=bytearray(raw[eocd_start:])
    struct.pack_into('<II',eocd,12,len(central_bytes),central_start)
    return bytearray(b''.join(locals)+central_bytes+eocd),[(p[0],q) for p,q in zip(patches,central_offsets)]

def dos(value):return ((value.hour<<11)|(value.minute<<5)|(value.second//2),((value.year-1980)<<9)|(value.month<<5)|value.day)

def main():
    folder=asset_path(ROOT,'stage-b/runs')/('fixture-metadata-recovery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));folder.mkdir(parents=True)
    source=RUN/'output/result1.xlsx';raw=source.read_bytes();source_hash=hashlib.sha256(raw).hexdigest()
    state=json.loads((RUN/'container-inspect.json').read_text(encoding='utf-8'))[0]['State']
    start=datetime.fromisoformat(state['StartedAt'].replace('Z','+00:00')).replace(microsecond=0)
    finish=datetime.fromisoformat(state['FinishedAt'].replace('Z','+00:00')).replace(microsecond=0)
    with zipfile.ZipFile(source) as archive:
        infos=archive.infolist();core=archive.read('docProps/core.xml');start_dir=archive.start_dir
        info=archive.getinfo('docProps/core.xml');name_len,extra_len=struct.unpack_from('<HH',raw,info.header_offset+26)
        compressed_start=info.header_offset+30+name_len+extra_len
        if raw_deflate(core)!=raw[compressed_start:compressed_start+info.compress_size]:raise ValueError('Host compressor differs; do not approximate original compression')
    # openpyxl emits app/core/theme, first sheet, then second sheet and tail.
    # Saved execution interval bounds metadata candidates, with 2s padding for DOS granularity.
    times=[start+timedelta(seconds=i) for i in range(-2,int((finish-start).total_seconds())+4)]
    zip_times=sorted({t.replace(second=t.second//2*2) for t in times})
    count=0;matched=None;t0=time.perf_counter()
    for modified in times:
        replacement=modified.strftime('%Y-%m-%dT%H:%M:%SZ').encode()
        new_core,n=re.subn(rb'(<dcterms:modified[^>]*>)[^<]+(</dcterms:modified>)',lambda m:m[1]+replacement+m[2],core)
        if n!=1:raise ValueError('Expected one core modified timestamp')
        base,offsets=build_base(raw,infos,start_dir,new_core)
        for first,sheet,tail in itertools.combinations_with_replacement(zip_times,3):
            if not (first<=modified<=first+timedelta(seconds=1)):continue
            schedule=[first]*3+[sheet]+[tail]*(len(infos)-4)
            for when,(local,central) in zip(schedule,offsets):
                stamp,date=dos(when);struct.pack_into('<HH',base,local,stamp,date);struct.pack_into('<HH',base,central,stamp,date)
            count+=1
            if hashlib.sha256(base).hexdigest()==TARGET:
                path=folder/'recovered-original-result1.xlsx';path.write_bytes(base)
                matched={'path':str(path.relative_to(ROOT)),'sha256':TARGET,'core_modified_utc':modified.isoformat(),'zip_initial_utc':first.isoformat(),'zip_sheet1_utc':sheet.isoformat(),'zip_sheet2_and_tail_utc':tail.isoformat()};break
        if matched:break
    assert source.read_bytes()==raw,'Source changed unexpectedly'
    if matched:
        with zipfile.ZipFile(ROOT/matched['path']) as recovered,zipfile.ZipFile(source) as current:
            differences=[i.filename for i in infos if current.read(i.filename)!=recovered.read(i.filename)]
        assert differences==['docProps/core.xml'],differences
    else:differences=[]
    result={'date':datetime.now().astimezone().isoformat(),'method':'Constrained ZIP timestamps and core modified timestamp reconstruction; exact pre-existing SHA-256 is the sole success criterion','target_sha256':TARGET,'source_path':str(source.relative_to(ROOT)),'source_sha256':source_hash,'original_container_time_bounds':state,'candidates_tested':count,'elapsed_seconds':time.perf_counter()-t0,'matched':matched,'changed_uncompressed_members':differences,'numerical_payload_modified':False,'source_overwritten':False,'real_solver_executed':False}
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(folder/'report.json'),'matched':matched,'candidates_tested':count,'elapsed_seconds':result['elapsed_seconds']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
