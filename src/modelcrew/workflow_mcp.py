"""NexusMORE full-workflow MCP adapter; stdio only, no approval tools."""
import argparse
from contextlib import redirect_stdout
import copy
from io import TextIOWrapper
import json
import logging
import os
from pathlib import Path
import sys

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from .business_adapter import BusinessAdapter, IMPLEMENTED, CATALOG
from .business_contract import BusinessContractError, request_schema, response_schema


def input_schema(name):
    schema=request_schema();branch=copy.deepcopy(schema['$defs']['request_'+name]);needed={}
    def visit(value):
        if isinstance(value,dict):
            if '$ref' in value:
                key=value['$ref'].removeprefix('#/$defs/')
                if key not in needed:
                    needed[key]=copy.deepcopy(schema['$defs'][key]);visit(needed[key])
            for key,child in value.items():
                if key!='$ref':visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(branch)
    if needed:branch['$defs']=needed
    branch['$schema']=schema['$schema']
    return branch


def definitions():
    return [types.Tool(name=name,description=CATALOG[name]['description']+('。可用arguments.proposal_files={path,sha256}提交工作区内完整提案JSON：含binding(task_id/version/contract_sha256/math_package_sha256)、plan、proposal、authorship(kind=prepared_file,statement)。核验后原结构正文直接进入新快照和独立M1，不经模型重写；edits必须为空，失败不自动重写，不授予批准。' if name=='modeling_start' else '')+('。已授权修复的GENERATE阶段可传arguments.code_revision提交现成代码；已批准模型的新代码手运行在未领取的首次最小阶段也可用同一入口，previous_code_sha256必须为64个0，不改变批准或跳过执行/P1；已有有效P1且尚无全量源码/作业的GENERATE_FULL也可直接提交stage=full，previous_code_sha256须为通过P1的minimal源码哈希，无需先耗尽重试：stage、code_path、code_sha256、previous_code_sha256、rationale；保留代码手来源，提交后另用hand_advance在Docker执行和独立审查。' if name=='hand_advance' else '')+('。已有数学包的版本修订必须同时提供 math_package；可内联，或在arguments.revision_files提供工作区内contract_path/contract_sha256及math_package_path/math_package_sha256，两对象同一新版本写入。文件方式body不带contract/math_package，仅含actor/request_id/version/kind/reason等。提交不批准模型。' if name=='task_revise' else '。每条运行最多一次独立复核，跨 attempt 共用额度；不得换请求键再次申请或新建运行重置预算。' if name=='hand_recheck' else '')+'。真实用户确认经可信本地入口；未知结果先查询原请求，禁止自动重发。',
                       inputSchema=input_schema(name),outputSchema=response_schema(),
                       annotations=types.ToolAnnotations(readOnlyHint=not CATALOG[name]['mutating'],
                           destructiveHint=False,idempotentHint=True,openWorldHint=name in ('modeling_start','modeling_recheck','hand_advance','hand_recheck','references_retrieve','assembly_review_w2')))
            for name in sorted(IMPLEMENTED)]


def create_server(adapter):
    server=Server('nexusmore-workflow',version='1.0.0',
        instructions='完整业务工具复用枢模 Workflow 与 PostgreSQL。模型无用户批准权限。needs_user_input 时展示独立待办，用户经可信本地入口确认。outcome_unknown 仅查询 operation_status，禁止换键重发。')
    @server.list_tools()
    async def list_tools():
        return definitions()
    @server.call_tool(validate_input=False)
    async def call_tool(name,arguments):
        try:
            result=await anyio.to_thread.run_sync(adapter.invoke,name,arguments)
        except BusinessContractError:
            return types.CallToolResult(isError=True,content=[types.TextContent(type='text',text='unsupported_operation: operation is not registered')])
        return types.CallToolResult(isError=result['status'] in ('error','outcome_unknown','blocked'),
            structuredContent=result,content=[types.TextContent(type='text',text=json.dumps(result,ensure_ascii=False,allow_nan=False))])
    return server


async def serve(adapter):
    server=create_server(adapter)
    # Pin the real protocol stream before redirecting prints from existing core
    # services. Only the stdio writer can use the captured stdout handle.
    output_fd=sys.stdout.fileno()
    protocol_fd=os.dup(output_fd)
    os.set_inheritable(protocol_fd,False)
    protocol_stdout=anyio.wrap_file(TextIOWrapper(os.fdopen(protocol_fd,'wb'),encoding='utf-8'))
    # Redirect fd 1 too: native extensions and os.write must not bypass the
    # Python-level print redirect and corrupt JSON-RPC framing.
    os.dup2(sys.stderr.fileno(),output_fd)
    try:
        with redirect_stdout(sys.stderr):
            async with stdio_server(stdout=protocol_stdout) as (read,write):
                await server.run(read,write,server.create_initialization_options())
    finally:
        os.dup2(protocol_fd,output_fd)
        await protocol_stdout.aclose()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command')
    sub.add_parser('serve',help='Run standard MCP stdio server (default)')
    sub.add_parser('describe',help='Offline list of implemented and unavailable operations')
    sub.add_parser('migrate',help='Apply additive core/database migrations through Workflow.setup')
    c=sub.add_parser('register-input',help='Trusted local input registration; not an MCP tool')
    c.add_argument('--project',required=True);c.add_argument('--task',required=True)
    c.add_argument('--version',type=int,required=True);c.add_argument('--file',type=Path,required=True)
    c.add_argument('--role',default='input')
    args=parser.parse_args()
    logging.basicConfig(stream=sys.stderr,level=logging.WARNING,format='%(name)s: %(message)s')
    if args.command=='describe':
        print(json.dumps(BusinessAdapter().capabilities(),ensure_ascii=False,indent=2));return
    if args.command in ('migrate','register-input'):
        from .workflow import Workflow
        from .config import ROOT
        try:
            with Workflow() as w:
                if args.command=='migrate':
                    w.setup();version=w.db.execute('SELECT max(version) AS version FROM mc_migrations').fetchone()['version']
                    value={'status':'passed','migration':version,'user_approval_created':False}
                else:
                    from .business_artifacts import register_input
                    owner={'project_id':args.project,'task_id':args.task,'version':args.version}
                    value=register_input(w,ROOT,owner,args.file,args.role)
            print(json.dumps(value,ensure_ascii=False));return
        except Exception as exc:
            print(json.dumps({'error':'local_command_failed','type':type(exc).__name__}),file=sys.stderr)
            raise SystemExit(1) from None
    # Windows scientific DLL initialization must complete on the startup thread.
    # A first NumPy import inside a dispatched AnyIO worker stalled in the
    # real DSH subprocess before the business response could be saved.
    if sys.platform == 'win32':
        with redirect_stdout(sys.stderr):
            __import__('numpy')
    anyio.run(serve,BusinessAdapter())


if __name__=='__main__':main()
