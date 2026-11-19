"""Verified bounded JSON sources for model revisions; never an approval channel."""
import json
from .business_artifacts import read_verified
from .business_contract import BusinessContractError

LIMIT=2*1024*1024


def resolve(root,refs):
    values={}
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('Duplicate JSON key')
            obj[key]=value
        return obj
    def reject(value):raise ValueError('Nonfinite JSON constant')
    for name in ('contract','math_package'):
        data,size=read_verified(root,refs[name+'_path'],refs[name+'_sha256'],limit=LIMIT)
        if not 0<size<=LIMIT:raise BusinessContractError('invalid_request','Revision JSON file exceeds 2 MiB')
        try:
            value=json.loads(data.decode('utf-8-sig'),object_pairs_hook=unique,parse_constant=reject)
            if not isinstance(value,dict):raise ValueError('Expected JSON object')
        except (ValueError,UnicodeError,RecursionError) as exc:
            raise BusinessContractError('invalid_request','Invalid revision JSON source') from exc
        values[name]=value
    return values
