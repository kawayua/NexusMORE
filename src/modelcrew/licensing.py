"""Offline legal notices; reading them never grants publication approval."""
import json
from .package_resources import resource


def information():
    return json.loads(resource('licensing/manifest.json').read_text(encoding='utf-8'))


def license_text(kind):
    entry = information()['license_files']
    if kind not in entry:
        raise ValueError('Unknown license text')
    return resource(entry[kind]).read_text(encoding='utf-8')
