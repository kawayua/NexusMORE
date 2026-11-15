import hashlib
from scripts.check_repository_layout import check_layout


def policy():
    return {'allowed_roots':['docs','src','modelcrew','requirements-old.txt'],
            'transitional_roots':{'modelcrew':'pending'},
            'legacy_stage_path_sha256':[hashlib.sha256(b'stage-e/approved.json').hexdigest()]}


def test_guard_accepts_only_existing_stage_files():
    assert check_layout(['stage-e/approved.json','docs/guide.md'],policy())['status'] == 'passed'
    assert check_layout(['stage-e/new.json'],policy())['status'] == 'failed'
    assert check_layout(['stage-f/README.md'],policy())['status'] == 'failed'


def test_final_rejects_legacy_and_transitional_roots():
    for name in ['stage-e/approved.json','modelcrew/a.py','requirements-old.txt']:
        result=check_layout([name],policy(),final=True)
        assert result['status'] == 'failed'
        assert not result['final_f0_accepted']
    assert check_layout(['src/modelcrew/a.py'],policy(),final=True)['final_layout_accepted']
    assert not check_layout(['src/modelcrew/a.py'],policy(),final=True)['final_f0_accepted']


def test_root_outputs_rejected():
    assert check_layout(['random.png'],policy())['status'] == 'failed'
