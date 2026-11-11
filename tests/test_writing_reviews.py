"""Separate figure-content consent from changed manuscript consent."""
import copy,json
from pathlib import Path
import pytest
from PIL import Image
from modelcrew.modeling_paper import policy,require_review_for_export,validate_draft
from modelcrew.writing_reviews import selection_record,manuscript_record,review_status,write_record_new

@pytest.fixture
def bundle(tmp_path):
    figures=[]
    for i in range(9):
        files={}
        for fmt in ['png','pdf','svg']:
            p=tmp_path/f'figure-{i}.{fmt}'
            if fmt=='png':Image.new('RGB',(4,4),(i*20,80,100)).save(p,dpi=(600,600))
            else:p.write_text(f'TEST_ONLY {i}',encoding='utf-8')
            from modelcrew.modeling_paper import sha
            files[fmt]={'path':p.name,'sha256':sha(p)}
        figures.append({'id':f'f{i}','category':['raw','process','result'][i//3],'question_ids':['q1'],
                        'formal':i<8,'number':i+1 if i<8 else None,'title':f'候选{i}',
                        'purpose':'用真实数据回答问题','source_kind':'TEST_ONLY','files':files})
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps({'question_ids':['q1'],'figures':figures}),encoding='utf-8')
    text='\n\n'.join('## '+section+'\n'+'根据问题条件分析模型与求解结果，并说明假设、单位与局限。'*2 for section in policy()['required_sections'])
    for f in figures[:8]:
        n=f['number'];text+=f'\n正文图{n}说明对应数据。\n\n![图{n} 数据说明]({f["files"]["png"]["path"]})\n\n图{n} 数据说明。\n'
    md=tmp_path/'draft.md';md.write_text(text,encoding='utf-8')
    kwargs={'decision':'approve','actor':'TEST_SIMULATED_USER','statement':'TEST_ONLY explicit approval','reason':'TEST_ONLY reviewed concrete content'}
    text_review=manuscript_record(md,catalog,**kwargs)
    selection=selection_record(catalog,[f['id'] for f in figures[:8]],**kwargs)
    return md,catalog,text_review,selection

def rewrite(catalog,mutate):
    c=json.loads(catalog.read_text(encoding='utf-8'));mutate(c);catalog.write_text(json.dumps(c),encoding='utf-8')

def test_both_separate_reviews_gate_export(bundle):
    md,c,t,f=bundle
    assert validate_draft(md,c)['status']=='passed'
    r={'review_version':'2.0.0','manuscript_review':t,'figure_selection_review':f}
    assert require_review_for_export(md,c,r)['separate_reviews']['can_export']

@pytest.mark.parametrize('missing',['text','figures'])
def test_one_approval_never_implies_other(bundle,missing):
    md,c,t,f=bundle
    r={'review_version':'2.0.0','manuscript_review':None if missing=='text' else t,'figure_selection_review':None if missing=='figures' else f}
    with pytest.raises(ValueError,match='Separate'):require_review_for_export(md,c,r)

def test_manuscript_edits_preserve_figure_choice_only(bundle):
    md,c,t,f=bundle;md.write_text(md.read_text(encoding='utf-8')+'\n补充图示说明需要审阅。',encoding='utf-8')
    status=review_status(md,c,t,f)
    assert status['manuscript']=='stale' and status['figure_selection']=='approved' and not status['can_export']

def test_unselected_candidate_addition_preserves_existing_approvals(bundle):
    md,c,t,f=bundle
    def add(cat):
        new=copy.deepcopy(cat['figures'][-1]);new['id']='new-unused';new['formal']=False;cat['figures'].append(new)
    rewrite(c,add);status=review_status(md,c,t,f)
    assert status['manuscript']=='approved' and status['figure_selection']=='approved'

def test_candidate_becomes_embedded_requires_both_current_scopes(bundle):
    md,c,t,f=bundle
    rewrite(c,lambda cat:cat['figures'][-1].update(formal=True,number=9))
    s=review_status(md,c,t,f)
    assert s['manuscript']=='stale' and s['figure_selection']=='stale'

@pytest.mark.parametrize('field',['title','purpose','geometry','limitation'])
def test_selected_semantics_change_invalidates_figure_choice(bundle,field):
    md,c,t,f=bundle
    rewrite(c,lambda cat:cat['figures'][0].update({field:{'width':.5} if field=='geometry' else 'different meaning'}))
    assert review_status(md,c,t,f)['figure_selection']=='stale'

def test_figure_bytes_changed_without_rehash_are_rejected(bundle):
    md,c,t,f=bundle;(c.parent/'figure-0.pdf').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Changed figure'):review_status(md,c,t,f)

def test_figure_bytes_changed_with_rehash_invalidate_choice(bundle):
    from modelcrew.modeling_paper import sha
    md,c,t,f=bundle;p=c.parent/'figure-0.pdf';p.write_bytes(b'changed')
    rewrite(c,lambda cat:cat['figures'][0]['files']['pdf'].update(sha256=sha(p)))
    assert review_status(md,c,t,f)['figure_selection']=='stale'

@pytest.mark.parametrize('ids',[[],['unknown'],['f0','f0']])
def test_unknown_duplicate_empty_selection_rejected(bundle,ids):
    md,c,t,f=bundle
    with pytest.raises(ValueError):selection_record(c,ids,decision='approve',actor='TEST',statement='TEST',reason='TEST')

def test_records_do_not_overwrite_prior_user_actions(bundle):
    md,c,t,f=bundle;p=c.parent/'decision.json';write_record_new(p,f)
    with pytest.raises(FileExistsError):write_record_new(p,t)
    assert json.loads(p.read_text(encoding='utf-8'))==f

def test_reject_and_no_explicit_statement_never_approve(bundle):
    md,c,t,f=bundle;f['decision']='reject'
    assert review_status(md,c,t,f)['figure_selection']=='rejected'
    with pytest.raises(ValueError):selection_record(c,['f0'],decision='approve',actor='TEST',statement='',reason='TEST')

def test_all_15_actual_selection_has_no_manuscript_approval():
    from modelcrew.config import ROOT
    p=ROOT/'output/md/modeling-q1-all-figures-v5'
    c=p/'figure-catalog.json';md=p/'单题论文-中文审阅稿.md';r=json.loads((p/'user-review.json').read_text(encoding='utf-8'))
    report=validate_draft(md,c);assert report['status']=='passed' and report['formal_figures']==15
    status=review_status(md,c,r['manuscript_review'],r['figure_selection_review'])
    assert status['manuscript']=='pending' and status['figure_selection']=='stale' and not status['can_export']
    from modelcrew.writing_reviews import selection_snapshot
    actual=selection_snapshot(c,[f['id'] for f in json.loads(c.read_text(encoding='utf-8'))['figures'] if f['formal']])
    assert actual['sha256']==r['figure_selection_review']['snapshot']['sha256']
    assert actual['policy_sha256']!=r['figure_selection_review']['snapshot']['policy_sha256']
    with pytest.raises(ValueError):require_review_for_export(md,c,r)


def test_source_evidence_binding_change_invalidates_choice(bundle):
    md,c,t,f=bundle
    rewrite(c,lambda cat:cat.update(evidence={'execution_id':'different-source','result_revision':99}))
    assert review_status(md,c,t,f)['figure_selection']=='stale'

def test_historical_cplus_approvals_are_preserved_but_stale_after_policy_update():
    from modelcrew.config import ROOT
    from modelcrew.modeling_paper import sha
    folder=ROOT/'output/md/modeling-q1-cplus-recheck-20261107'
    md=folder/'单题论文-中文审阅稿.md';catalog=folder/'figure-catalog.json'
    review=json.loads((folder/'user-review-confirmed.json').read_text(encoding='utf-8'))
    assert review['manuscript_review']['user_statement']=='补图后的新版正文也通过'
    assert sha(md)==sha(ROOT/'output/md/modeling-q1-all-figures-v5/单题论文-中文审阅稿.md')
    status=review_status(md,catalog,review['manuscript_review'],review['figure_selection_review'])
    assert status['manuscript']==status['figure_selection']=='stale' and not status['can_export']
    recorded=review['manuscript_review']['snapshot'];actual=status['current_manuscript_snapshot']
    assert actual['markdown_sha256']==recorded['markdown_sha256']
    assert actual['embedded_figures_sha256']==recorded['embedded_figures_sha256']
    assert actual['policy_sha256']!=recorded['policy_sha256']
    with pytest.raises(ValueError,match='Separate'):require_review_for_export(md,catalog,review)
    previous=json.loads((folder/'user-review.json').read_text(encoding='utf-8'))
    assert previous['manuscript_review'] is None
    with pytest.raises(ValueError,match='Separate'):require_review_for_export(md,catalog,previous)
