"""Shared NexusMORE capability and supported-version registry; no host duplication."""
import importlib
import json
from .package_resources import resource,verify_resources


def load_capabilities():
    checked=verify_resources()
    value=json.loads(resource('capabilities/registry.json').read_text(encoding='utf-8'))
    if value['schema_version']!='1.0.0' or value['backend']!='python':raise ValueError('Unknown capability registry')
    results=[]
    for entry in value['capabilities']:
        current=dict(entry)
        try:
            module=importlib.import_module(entry['module'])
            if not all(callable(getattr(module,name,None)) for name in entry['functions']):raise ValueError('Missing capability entry')
            current['entry_available']=True
        except ImportError:
            current['entry_available']=False
        # Import availability is not a renderer, supplier, host or end-to-end acceptance.
        results.append(current)
    value['capabilities']=results;value['resource_check']=checked
    value['scope']='Installed project entry/resources only; actual environment, execution, scientific and independent reviews remain separate'
    return value


def main():print(json.dumps(load_capabilities(),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
