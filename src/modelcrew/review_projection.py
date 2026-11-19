"""Explicit read-only context projection for lossless binary trace blobs.

Frozen artifacts remain byte-identical. Scientific checks, failures, units and
provenance are never shortened. Every omitted data pointer is disclosed.
"""
import copy


def project(evidence):
    omissions=[]
    def walk(value,path):
        if isinstance(value,list):return [walk(v,path+'/'+str(i)) for i,v in enumerate(value)]
        if not isinstance(value,dict):return value
        encoded=(value.get('encoding')=='zlib+base64; exact float64 columnar bytes'
                 and isinstance(value.get('data'),str) and len(value['data'])>1024
                 and isinstance(value.get('sha256_uncompressed'),str)
                 and len(value['sha256_uncompressed'])==64)
        result={}
        for key,item in value.items():
            escaped=str(key).replace('~','~0').replace('/','~1');pointer=path+'/'+escaped
            if key=='data' and encoded:
                omissions.append({'pointer':pointer,'encoded_characters':len(item),
                    'sha256_uncompressed':value['sha256_uncompressed'],
                    'reason':'Lossless raw binary trace remains in immutable source artifact; not decoded/read by reviewer model.'})
                continue
            result[key]=walk(item,pointer)
        return result
    return walk(evidence,''),omissions
