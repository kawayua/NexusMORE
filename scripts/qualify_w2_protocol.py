"""One-shot W2 protocol qualification, never a formal W2 admission or retry reset."""
import argparse
from pathlib import Path
from modelcrew import assembly_builds as builds
from modelcrew.collaboration import sha_file,workspace_path
from modelcrew.contracts import digest
from modelcrew.model_client import JsonModel
from modelcrew.modeling_paper import writing_context
from modelcrew.w2_protocol import prepare,compile_answer,VERSION
from modelcrew.workflow import Workflow,WorkflowError


def qualify(project,build_id,review_id,output,*,model=None):
    output=workspace_path(builds.ROOT,output)
    output.mkdir(parents=True,exist_ok=False)  # Never resend an existing qualification.
    with Workflow() as w:
        row=builds.load(w,project,build_id);inputs=builds.inputs.load(w,project,str(row['assembly_run_id']))
        with builds.locks_for(w,project,inputs):
            builds.guard(w,project,row)
            op=row['payload'].get('w2_reviews',{}).get(review_id)
            if not op:raise WorkflowError('Unknown original W2 review')
            path=workspace_path(builds.ROOT,op['folder'])/'packet.json'
            if sha_file(path)!=op['packet_sha256']:raise WorkflowError('Original packet changed')
            packet=builds.read(path)
            refs,view,images=prepare(packet)
            view['qualification_only']=True
            view['purpose']='Protocol qualification only, NOT another formal W2 or user acceptance. Independently inspect the data/pages and preserve all real defects. A valid FAIL/BLOCKED qualifies the protocol as well as a valid PASS. Never assume approval.'
            request={'kind':'W2_PROTOCOL_QUALIFICATION_ONLY','project':project,'build_id':build_id,'original_review':review_id,
                     'original_packet':builds.rel(path),'original_packet_sha256':sha_file(path),
                     'new_protocol':VERSION,'registry_sha256':digest(refs),'model_packet_sha256':digest(view),
                     'prior_recheck_exhausted':any(o.get('request',{}).get('recheck_of') and o.get('phase') in ['INVALID_RESPONSE','FAIL','BLOCKED'] for o in row['payload'].get('w2_reviews',{}).values()),'paper_W2_state_unchanged':True,
                     'formal_receipt_created':False,'provider_calls_allowed':1}
            builds.inputs.write_once(output/'input-binding.json',request)
            builds.inputs.write_once(output/'writer-context.json',writing_context())
            builds.inputs.write_once(output/'reference-registry.json',refs)
            builds.inputs.write_once(output/'model-packet.json',view)
            builds.inputs.write_once(output/'claim.json',{'phase':'DISPATCHING','request_sha256':digest(request)})
            native=[]
            for image in images:
                image_path=workspace_path(builds.ROOT,image['path'])
                if sha_file(image_path)!=image['sha256']:raise WorkflowError('Qualification image changed')
                native.append({**image,'path':str(image_path)})
    # No database state is changed, and no author conversation is sent.
    try:
        answer,meta=(model or JsonModel()).call(output,'W2',
            'You are an independent read-only reviewer in a protocol qualification. Return strict JSON matching the supplied schema. Select ONLY provided evidence_refs and page_ref codes; never write artifact names or JSON Pointers. Inspect all images and report EVERY page. Each check evidence_refs MUST contain at most THREE codes; independently choose the most decisive three, never an exhaustive list. Preserve genuine FAIL/BLOCKED and every real issue. You cannot approve the paper or change existing W2 records.',
            view,max_tokens=12000,image_inputs=native)
        builds.inputs.write_once(output/'answer.json',answer)
        compiled,proof=compile_answer(answer,packet,refs)
        builds.inputs.write_once(output/'compiled-answer.json',{'native_answer':compiled,'compilation':proof})
        result={'status':'PROTOCOL_QUALIFIED','protocol_version':VERSION,'reviewer_reported_status':compiled['status'],
                'checks':len(compiled['checks']),'pages':len(compiled['pages_reviewed']),
                'formal_W2_receipt_created':False,'paper_W2_state_unchanged':True,
                'request_sha256':digest(request),'provider_metadata':meta,'compilation':proof}
    except Exception as exc:
        result={'status':'QUALIFICATION_FAILED','error_type':type(exc).__name__,'message':str(exc)[:1000],
                'formal_W2_receipt_created':False,'paper_W2_state_unchanged':True}
        builds.inputs.write_once(output/'qualification-result.json',result)
        raise
    builds.inputs.write_once(output/'qualification-result.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True);parser.add_argument('--build',required=True)
    parser.add_argument('--review',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=qualify(args.project,args.build,args.review,args.output)
    print(result['status'],'reviewer verdict',result['reviewer_reported_status'],'pages',result['pages'],'formal W2 receipt',result['formal_W2_receipt_created'])
