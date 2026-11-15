"""TEST ONLY MCP process faults; never installed as a production server endpoint."""
import argparse
import os
from pathlib import Path
import anyio
from modelcrew.code_executor_mcp import ExecutionTools,serve
from modelcrew.docker_executor import DockerExecutor,ExecutorError,atomic


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--mode',choices=['exit_running','cleanup_fail','exit_before_dispatch'],required=True)
    parser.add_argument('--marker',type=Path,required=True);args=parser.parse_args()
    class FaultExecutor(DockerExecutor):
        def execute(self,job_id):
            if args.mode=='exit_before_dispatch':
                atomic(args.marker,{'mode':args.mode,'pid':os.getpid(),'job_id':job_id})
                os._exit(92)
            return super().execute(job_id)
        def inspect(self,name,job):
            value=super().inspect(name,job)
            if args.mode=='exit_running' and value and value['State']['Running']:
                atomic(args.marker,{'mode':args.mode,'pid':os.getpid(),'container':name,'job_sha256':job['job_sha256']})
                os._exit(91)
            return value
        def docker(self,*items,**kwargs):
            if args.mode=='cleanup_fail' and items and items[0]=='rm' and not args.marker.exists():
                atomic(args.marker,{'mode':args.mode,'pid':os.getpid(),'container':items[-1]})
                raise ExecutorError('infrastructure_error','TEST_C6 injected cleanup transport failure')
            return super().docker(*items,**kwargs)
    anyio.run(serve,ExecutionTools(FaultExecutor(args.root),log_path=args.marker.with_suffix('.jsonl')))


if __name__=='__main__':main()
