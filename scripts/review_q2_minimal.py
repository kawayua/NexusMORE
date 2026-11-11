"""Freeze and admit an independently authored P1 receipt; never fabricate one."""
import argparse,json,uuid
from pathlib import Path
from modelcrew.config import ROOT
from modelcrew.collaboration import Artifact,Binding,Call,CollaborationStore,Snapshot,Receipt,sha_file,require_tool
from scripts.run_d3_minimal import read,write,approved
from modelcrew.modeling_hand import pointer
from scripts.run_d4_full import workflow
from scripts.run_q2_minimal import validate,TASK

def prepare(folder):
    validate(folder);m=read(folder/'run.json');store=CollaborationStore(folder/'records')
    origin_dir=ROOT/'stage-d/runs/modeling/q2-collision-20261109-v2'
    origin=CollaborationStore(origin_dir/'records');old=origin.load(Snapshot,read(origin_dir/'run.json')['snapshot_sha256'])
    for cid in old.lineage_call_ids:store.register_call(origin.call(cid))
    source=old.model_copy(update={'artifacts':old.artifacts+[Artifact(artifact_id='frozen_inputs',kind='input',path=(folder/'inputs.json').relative_to(ROOT).as_posix(),sha256=sha_file(folder/'inputs.json'),author_call_ids=old.lineage_call_ids)]})
    sk=store.freeze(source);hk=store.handoff(sk,'coding',[a.artifact_id for a in source.artifacts]);coder=Call.model_validate(m['author']);write(folder/'formal-handoff.json',store.context(hk,coder.call_id))
    previous=ROOT/'stage-d/runs/coding/q2-minimal-f27903ee91f64d4f85102ad0587f6738'
    previous_meta=read(previous/'run.json');prior=Call.model_validate(previous_meta['author']);store.register_call(prior)
    write(folder/'repair-lineage.json',{'previous_run':previous_meta['folder'],'previous_status':previous_meta['status'],'previous_execution_sha256':sha_file(previous/'execution.json'),'repair':'split SAT outputs to respect existing 1MiB per-file limit; batch interval root certification using nonexpansiveness; no model change','author_context':'same Codex author; review uses fresh context','attempt':2})
    bind=Binding(task_id=TASK,contract_version=2,contract_sha256=m['contract_sha256'],execution_id=folder.name,result_revision=1)
    specs=[('code','code','code-evidence.json'),('inputs','input','inputs.json'),('execution','execution','execution.json'),('result','result','validation.json'),('handoff','input','formal-handoff.json'),('repair','reproduction','repair-lineage.json')]
    artifacts=[Artifact(artifact_id=a,kind=k,path=(folder/p).relative_to(ROOT).as_posix(),sha256=sha_file(folder/p),author_call_ids=[coder.call_id]) for a,k,p in specs]
    snap=Snapshot(binding=bind,hand='coding',artifacts=artifacts,lineage_call_ids=[prior.call_id,coder.call_id]);key=store.freeze(snap)
    reviewer=Call(call_id='independent-P1-'+uuid.uuid4().hex,context_id='fresh-P1-'+uuid.uuid4().hex,role='quality',binding=bind)
    store.register_call(reviewer);tk=store.dispatch_review(key,'P1',reviewer.call_id)
    out={'ticket_sha256':tk,'snapshot_sha256':key,'reviewer_call_id':reviewer.call_id,'required_checks':['execution','input_output','constraints','numerics','units'],'scope':'P1 minimal [0,300] eight states and continuous [0,1] prefix only; full first-event search not implemented; no final answer or user confirmation','artifact_ids':[a.artifact_id for a in artifacts]}
    write(folder/'P1-dispatch.json',out);print(json.dumps(out,ensure_ascii=False))

def admit(folder):
    m=read(folder/'run.json');d=read(folder/'P1-dispatch.json');store=CollaborationStore(folder/'records');receipt=Receipt.model_validate(read(folder/'P1-response.json'))
    if receipt.ticket_sha256!=d['ticket_sha256'] or receipt.reviewer_call_id!=d['reviewer_call_id']:raise ValueError('review identity mismatch')
    snapshot=store.load(Snapshot,d['snapshot_sha256'])
    evidence={a.artifact_id:read(ROOT/a.path) for a in snapshot.artifacts}
    for check in receipt.checks:
        for proof in check.evidence:pointer(evidence[proof.artifact_id],proof.selector)
    require_tool(store.call(d['reviewer_call_id']),'submit_review')
    key=store.accept_review(receipt,d['snapshot_sha256'])
    result={'status':receipt.status,'receipt_sha256':key,'snapshot_sha256':d['snapshot_sha256'],'reviewer_call_id':d['reviewer_call_id'],'read_only_independent_context':True,'scope':d['scope'],'not_user_approval':True}
    write(folder/'P1-admission.json',result);m.update(status='P1_'+receipt.status.lower(),receipt_sha256=key,snapshot_sha256=d['snapshot_sha256']);write(folder/'run.json',m)
    with workflow() as w,w.lock(TASK):
        approved(w,TASK,2,m['contract_sha256'])
        w.record_entry(TASK,version=2,kind='experiment',text='Q2最小运行独立P1：'+receipt.status+'；尚无完整首碰答案，用户结果确认仍待定。',actor='coding-hand',request_id=folder.name+'-P1',artifacts=[{'path':(folder/'P1-admission.json').relative_to(ROOT).as_posix(),'sha256':sha_file(folder/'P1-admission.json'),'role':'independent_P1'}])
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','admit']);p.add_argument('--run',type=Path,required=True);a=p.parse_args();folder=a.run.resolve()
    if folder.parent!=(ROOT/'stage-d/runs/coding').resolve():raise ValueError('invalid folder')
    (prepare if a.stage=='prepare' else admit)(folder)
