"""Content-addressed artifact snapshots; original run directories remain mutable.

Filesystem snapshots may outlive a rolled-back transaction. These harmless orphan
objects are never interpreted as registered/approved database artifacts.
"""
import hashlib,os,tempfile
from pathlib import Path
from .config import ROOT

def snapshot_artifacts(artifacts):
    result=[]
    for item in artifacts:
        source=Path(item['path'])
        if not source.is_absolute():source=ROOT/source
        data=source.read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual.lower()!=item['sha256'].lower():raise ValueError('Artifact changed before snapshot')
        destination=ROOT/'artifacts/sha256'/actual/'content'
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest()!=actual:raise ValueError('Artifact snapshot corrupted')
        else:
            # A unique temp file plus a hard-link publishes only a complete object.
            # The destination is never replaced, including on concurrent imports.
            fd,name=tempfile.mkstemp(prefix='snapshot-',dir=destination.parent)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
                try:os.link(name,destination)
                except FileExistsError:
                    if hashlib.sha256(destination.read_bytes()).hexdigest()!=actual:raise ValueError('Artifact snapshot corrupted')
            finally:Path(name).unlink(missing_ok=True)
        result.append({**item,'path':str(destination.relative_to(ROOT)),'origin_path':item.get('origin_path',item['path'])})
    return result

def same_artifacts(before,after):
    def normalized(items):return sorted((i.get('origin_path',i['path']),i['sha256'],i['role']) for i in items)
    try:return normalized(before)==normalized(after)
    except (KeyError,TypeError,AttributeError):return False
