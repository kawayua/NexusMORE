"""Public tests use temporary synthetic inputs; never initialize a business database."""
from pathlib import Path
import uuid


def pytest_configure(config):
    if config.option.basetemp is None:
        parent = config.rootpath/'tmp'
        parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(parent/('pytest-'+uuid.uuid4().hex))
