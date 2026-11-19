"""Private native text intake, without arbitrary file access or approval authority."""
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import re
import sys

from .business_contract import BusinessContractError
from .contracts import digest
from .dsh_decisions import _private_parent, _read, _write, validate_host
from .hand_guidance import freeze_guidance

PROTOCOL='nexusmore-dsh-input/1'
ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}')


def validate_input(value):
    if not isinstance(value,dict) or set(value)!={'protocol','host','project_id','message'} or value['protocol']!=PROTOCOL:
        raise BusinessContractError('invalid_request','Invalid native input frame')
    validate_host(value['host'])
    message=value['message']
    if (not ID.fullmatch(value.get('project_id','')) or not isinstance(message,dict)
            or set(message)!={'id','rpc_id','text'} or not all(isinstance(message.get(k),str) and ID.fullmatch(message[k]) for k in ('id','rpc_id'))
            or not isinstance(message.get('text'),str) or not message['text'].strip() or len(message['text'].encode('utf-8'))>65536):
        raise BusinessContractError('invalid_request','Native text input is missing or too large')
    return value


def prepare(value, workflow, root):
    value=validate_input(value);root=Path(root).resolve();session=value['host']['session_id'];message=value['message']
    key=digest({'session':session});task='native-'+key[:32]
    folder=root/'runs'/'inputs'/'dsh'/key
    for part in (folder,*folder.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise BusinessContractError('artifact_access_denied','Linked input directory')
    folder.mkdir(parents=True,exist_ok=True)
    identity={'schema_version':'1.0.0','session_id':session,'project_id':value['project_id'],'message_id':message['id'],'rpc_id':message['rpc_id'],'text_sha256':hashlib.sha256(message['text'].encode('utf-8')).hexdigest(),'channel':'dsh_native_user_prompt','scope':'text_only_not_approval'}
    def immutable(path,data):
        try:
            with path.open('xb') as stream:stream.write(data)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes()!=data:
                raise BusinessContractError('idempotency_conflict','Original native input changed')
    immutable(folder/'question.txt',message['text'].encode('utf-8'))
    from .hand_guidance import frozen_bundle
    guidance=folder/'collaboration-guidance.json'
    if guidance.exists():frozen_bundle(folder,hashlib.sha256(guidance.read_bytes()).hexdigest())
    else:freeze_guidance(folder)
    identity['guidance_sha256']=hashlib.sha256(guidance.read_bytes()).hexdigest()
    immutable(folder/'provenance.json',json.dumps(identity,ensure_ascii=False,sort_keys=True).encode('utf-8'))
    from .business_artifacts import register_input
    with workflow() as w:
        # Never overwrite a task created outside this intake or attach to another question.
        owner={'project_id':value['project_id'],'task_id':task,'version':1}
        existing=w.db.execute('SELECT project_id FROM mc_tasks WHERE id=%s',(task,)).fetchone()
        if existing and existing['project_id']!=owner['project_id']:
            raise BusinessContractError('artifact_access_denied','Native task belongs elsewhere')
        receipt=register_input(w,root,owner,folder/'question.txt')
    from .inputs import inspect_file
    from .business_artifacts import ArtifactRegistry
    with workflow() as w:
        path,_=ArtifactRegistry(w,root).resolve_input('artifact:'+receipt['artifact_id'],owner)
    observed=inspect_file(path,'input','document')['structure']['observed']
    return {'status':'prepared','owner':owner,'input':receipt,'input_observation':{'template_id':'document','template_version':'1.0.0','observed':observed},'source':{'id':'native_statement','kind':'problem_statement','locator':'DSH native message '+message['id'],'sha256':receipt['sha256']},'provenance_sha256':hashlib.sha256((folder/'provenance.json').read_bytes()).hexdigest(),'user_approval_created':False}


def main():
    try:
        if sys.argv[1:]!=['--private-stdio']:raise BusinessContractError('invalid_request','Private bridge only')
        _private_parent();value=_read()
        from .workflow import Workflow
        from .config import ROOT
        with redirect_stdout(sys.stderr):result=prepare(value,Workflow,ROOT)
        _write({'type':'result','result':result})
    except Exception as exc:
        _write({'type':'error','code':exc.code if isinstance(exc,BusinessContractError) else 'service_unavailable'})
        raise SystemExit(1) from None


if __name__=='__main__':main()
