"""Repeat every primary partition with independently dispatched identical code."""
from modelcrew.project_assets import asset_path
import shutil,json
from scripts.run_q2_full import active,job
from scripts.run_d3_minimal import read,write
from modelcrew.collaboration import sha_file
from modelcrew.config import ROOT

def main():
    folder=active();records=[]
    plan=read(folder/'primary-plan.json')['partitions']
    for k,part in enumerate(plan):
        primary=folder/part['key'];r=read(primary/'partition-result.json');a,b=r['partition_s']
        key=f'repro-{k:02d}';target=folder/key;target.mkdir(exist_ok=True)
        source=primary/'generated_solver.py';dest=target/'generated_solver.py'
        if not dest.exists():shutil.copyfile(source,dest)
        if sha_file(source)!=sha_file(dest):raise ValueError('reproduction source differs')
        reproduced=job(folder,key,a,b)
        one=read(primary/'output-manifest.json');two=read(target/'output-manifest.json')
        equal=set(one)==set(two) and all(one[n]['sha256']==two[n]['sha256'] for n in one)
        if not equal:raise ValueError('reproduction artifacts differ')
        records.append({'primary':primary.name,'reproduction':key,'identical_code':True,'all_output_sha256_equal':True,'primary_execution_sha256':sha_file(primary/'execution.json'),'reproduction_execution_sha256':sha_file(target/'execution.json')})
        write(folder/'reproduction.json',{'status':'in_progress','partitions':records,'coverage':'prefix replay in order, no inferred full coverage'})
        if r['status']=='FIRST_CONTACT':break
    write(folder/'reproduction.json',{'status':'PASS','partitions':records,'all_output_sha256_equal':True,'full_primary_prefix_and_event_replayed':True,'independent_Docker_dispatches':True})
    event=read(folder/'collision-event.json');sub=folder/'support';sub.mkdir(exist_ok=True)
    base=(primary/'generated_solver.py').read_text(encoding='utf-8').split("if __name__=='__main__':full_main()")[0]
    values={'EVENT_A':event['first_event_enclosure_s'][0],'EVENT_B':event['first_event_enclosure_s'][1],'EVENT_LO':event['time_interval_s'][0],'EVENT_HI':event['time_interval_s'][1],'EVENT_SPEC':event['unique_contact_feature']}
    code='\n'.join(k+'='+repr(v) for k,v in values.items())+'\n'+base+'\n'+(asset_path(ROOT,'execution/q2_support_tail.py')).read_text(encoding='utf-8-sig')
    p=sub/'generated_solver.py'
    if not p.exists():p.write_text(code,encoding='utf-8')
    elif p.read_text(encoding='utf-8')!=code:raise ValueError('support source changed')
    certificate=job(folder,'support',event['time_interval_s'][0],event['time_interval_s'][1]);write(folder/'support-certificate.json',certificate)
    print('all partitions reproduced exactly and extra finite-edge support certificate verified',flush=True)
if __name__=='__main__':main()
