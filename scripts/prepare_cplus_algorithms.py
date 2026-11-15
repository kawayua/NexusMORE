"""Historical preparation compatibility; new tasks use prepare_algorithm_catalog."""
from modelcrew.project_assets import asset_path
from modelcrew.config import ROOT
if __package__:
    from .prepare_algorithm_catalog import prepare as _prepare
else:
    from prepare_algorithm_catalog import prepare as _prepare

def prepare():
    return _prepare(asset_path(ROOT,'stage-a-plus/sources/read-log.json'))

if __name__ == '__main__':
    prepare()
