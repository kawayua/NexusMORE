"""Trusted host MCP endpoints. API/tool arguments cannot change server commands."""
from .config import configured, settings_path, ENV_SETTINGS
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from .config import ROOT
from .execution_paths import execution_directory


class McpTransportError(RuntimeError):
    pass


def executor_root():
    return execution_directory(ROOT)


class McpClient:
    def __init__(self, *, database_url=None):
        self.database_url=database_url

    def call(self,service,tool,arguments):
        try:
            return anyio.run(self._call,service,tool,arguments)
        except Exception as exc:
            raise McpTransportError('MCP transport unavailable; inspect recorded operation before retry') from exc

    async def _call(self,service,tool,arguments):
        if service=='paper-search':
            args=['-m','modelcrew.paper_search_mcp']
            # A network-only tool needs no embedding runtime initialization.
            if tool != 'paper_search' and (tool != 'algorithm_search' or not configured('MODELCREW_ALGORITHM_CONFIG')):
                args+=['--web-only']
            if configured('MODELCREW_RETRIEVAL_CONFIG'):
                args+=['--config',configured('MODELCREW_RETRIEVAL_CONFIG')]
            from .paper_search_mcp import Envelope
        elif service=='code-executor':
            args=['-m','modelcrew.code_executor_mcp','--root',str(executor_root()),
                  '--image',configured('MODELCREW_EXECUTION_IMAGE','modelcrew-reference:py313')]
            from .code_executor_mcp import Envelope
        else:
            raise ValueError('Unknown trusted MCP service')
        names={'HF_HOME','LANG','LC_ALL','MODELCREW_DATABASE_URL','MODELCREW_DATABASE_CONFIG'} | {key for key in ENV_SETTINGS if not key.startswith(('MODELCREW_LLM_','MODELCREW_M1_','MODELCREW_W2_'))}
        env={key:os.environ[key] for key in names if key in os.environ}
        env.update(MODELCREW_WORKSPACE=str(ROOT))
        if 'MODELCREW_CONFIG' in os.environ: env['MODELCREW_CONFIG']=str(settings_path(ROOT).resolve())
        env.update(PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        if self.database_url:env['MODELCREW_DATABASE_URL']=self.database_url
        parameters=StdioServerParameters(command=sys.executable,args=args,cwd=str(ROOT),env=env)
        async with stdio_client(parameters) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=240)) as session:
                await session.initialize()
                response=await session.call_tool(tool,arguments)
                raw=response.structuredContent
                if not isinstance(raw,dict) or len(json.dumps(raw,ensure_ascii=False).encode())>8*1024*1024:
                    raise ValueError('Invalid or excessive MCP response')
                envelope=Envelope.model_validate(raw)
                if envelope.tool!=tool or (envelope.status=='error')!=response.isError:
                    raise ValueError('MCP envelope binding mismatch')
                if (envelope.status=='ok' and (envelope.data is None or envelope.error is not None)) or (envelope.status=='error' and (envelope.data is not None or envelope.error is None)):
                    raise ValueError('MCP success/error evidence mismatch')
                return envelope.model_dump(mode='json')
