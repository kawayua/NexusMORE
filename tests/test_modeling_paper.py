"""Exercise Chinese genre, figure integrity and explicit draft/selection review boundaries."""
import copy
import json
from pathlib import Path
import pytest
from PIL import Image
from modelcrew.modeling_paper import policy, sha, validate_draft, require_review_for_export

@pytest.fixture
def bundle(tmp_path):
    figures = []
    for i in range(9):
        paths = {}
        for fmt in ('png', 'pdf', 'svg'):
            asset = tmp_path / f'candidate-{i}.{fmt}'
            if fmt == 'png':
                Image.new('RGB', (4, 4), (i * 20, 80, 100)).save(asset, dpi=(600, 600))
            else:
                asset.write_text(f'fixture-{i}-{fmt}', encoding='utf-8')
            paths[fmt] = {'path': asset.name, 'sha256': sha(asset)}
        figures.append({'id': f'figure-{i}', 'category': ['raw', 'process', 'result'][i // 3],
                        'question_ids': ['q1'], 'formal': i < 8, 'number': i + 1 if i < 8 else None, 'files': paths})
    catalog = tmp_path / 'figures.json'
    catalog.write_text(json.dumps({'question_ids': ['q1'], 'figures': figures}), encoding='utf-8')
    text = '\n\n'.join('## ' + section + '\n' + '根据问题实际条件分析模型与求解结果，并说明假设和适用范围。' * 2 for section in policy()['required_sections'])
    for fig in figures[:8]:
        n = fig['number']
        text += f"\n正文通过图{n}说明对应结果和数据含义。\n\n![图{n} 数据说明]({fig['files']['png']['path']})\n\n图{n} 数据说明。\n"
    md = tmp_path / 'review.md'; md.write_text(text, encoding='utf-8')
    return md, catalog

def test_valid_draft_is_still_pending_user_review(bundle):
    report = validate_draft(*bundle)
    assert report['status'] == 'passed'
    assert report['user_review'] == 'pending'

@pytest.mark.parametrize('defect', ['missing_category', 'lost_image', 'duplicate_content', 'escape_path', 'missing_caption', 'english'])
def test_defects_cannot_be_released(bundle, defect):
    md, catalog = bundle
    data = json.loads(catalog.read_text(encoding='utf-8'))
    if defect == 'missing_category':
        data['figures'][-1]['category'] = 'raw'
    elif defect == 'lost_image':
        (md.parent / data['figures'][0]['files']['png']['path']).unlink()
    elif defect == 'duplicate_content':
        data['figures'][1]['files']['png'] = copy.deepcopy(data['figures'][0]['files']['png'])
    elif defect == 'escape_path':
        data['figures'][0]['files']['svg']['path'] = '../outside.svg'
    elif defect == 'missing_caption':
        md.write_text(md.read_text(encoding='utf-8').replace('\n图1 数据说明。', ''), encoding='utf-8')
    else:
        md.write_text(md.read_text(encoding='utf-8') + ' This is a theorem proof article.' * 1000, encoding='utf-8')
    catalog.write_text(json.dumps(data), encoding='utf-8')
    assert validate_draft(md, catalog)['status'] == 'failed'

def test_requires_both_text_and_figure_approval_and_detects_stale_review(bundle):
    md, catalog = bundle
    report = validate_draft(md, catalog)
    review = {k: report[k] for k in ['markdown_sha256', 'catalog_sha256', 'policy_sha256']}
    review.update(decision='approve', reason='TEST_SIMULATED_USER reviewed draft')
    with pytest.raises(ValueError, match='figure selection'):
        require_review_for_export(md, catalog, review)
    review['figure_selection_decision'] = 'approve'
    assert require_review_for_export(md, catalog, review)['status'] == 'passed'
    md.write_text(md.read_text(encoding='utf-8') + '\n新增解释需要重新审阅。', encoding='utf-8')
    with pytest.raises(ValueError, match='Stale'):
        require_review_for_export(md, catalog, review)


def test_writing_context_reads_current_instructions_every_time(tmp_path, monkeypatch):
    import modelcrew.modeling_paper as paper
    (tmp_path / 'resources/paper').mkdir(parents=True)
    (tmp_path / 'instructions.md').write_text('第一版中文流程', encoding='utf-8')
    config = {'default_language': 'zh-CN', 'first_delivery': 'markdown', 'must_load': ['instructions.md']}
    (tmp_path / 'resources/paper/workflow.json').write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr(paper, 'ROOT', tmp_path)
    old = paper.writing_context()
    (tmp_path / 'instructions.md').write_text('更新后的中文流程', encoding='utf-8')
    new = paper.writing_context()
    assert old['documents'][0]['sha256'] != new['documents'][0]['sha256']
    assert new['documents'][0]['text'] == '更新后的中文流程'


def test_adding_unselected_candidates_keeps_manuscript_but_requires_new_selection(bundle):
    md, catalog = bundle
    old = validate_draft(md, catalog)
    record = {k: old[k] for k in ['markdown_sha256', 'catalog_sha256', 'policy_sha256']}
    record.update(decision='approve', reason='TEST_SIMULATED_USER approves manuscript only', figure_selection_decision='pending')
    with pytest.raises(ValueError, match='figure selection'):
        require_review_for_export(md, catalog, record)
    data = json.loads(catalog.read_text(encoding='utf-8'))
    data['selection_status'] = 'more_candidates_pending'
    catalog.write_text(json.dumps(data), encoding='utf-8')
    new = validate_draft(md, catalog)
    assert old['markdown_sha256'] == new['markdown_sha256']
    assert old['catalog_sha256'] != new['catalog_sha256']
    record['figure_selection_decision'] = 'approve'
    with pytest.raises(ValueError, match='Stale'):
        require_review_for_export(md, catalog, record)
