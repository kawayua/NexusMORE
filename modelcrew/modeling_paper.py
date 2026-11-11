"""Chinese modeling-paper boundary; mathematical handoff renderers are not paper writers."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from .config import ROOT

POLICY_PATH = ROOT / 'resources/paper/chinese-modeling-policy.json'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def policy():
    return json.loads(POLICY_PATH.read_text(encoding='utf-8'))

def writing_context():
    """Read project defaults on every invocation; do not rely on chat memory."""
    workflow_path = ROOT / 'resources/paper/workflow.json'
    workflow = json.loads(workflow_path.read_text(encoding='utf-8'))
    if workflow['default_language'] != 'zh-CN' or workflow['first_delivery'] != 'markdown':
        raise ValueError('Unsupported paper workflow language/delivery')
    documents = []
    for relative in workflow['must_load']:
        path = inside(ROOT, relative)
        documents.append({'path': relative, 'sha256': sha(path), 'text': path.read_text(encoding='utf-8')})
    return {'workflow': workflow, 'workflow_sha256': sha(workflow_path), 'documents': documents}

def inside(root, relative):
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Image path escapes draft bundle')
    return target

def scoped_figure_minimum(catalog_path,catalog,rules):
    """A documented user exception belongs to one bound catalog, never global defaults."""
    default=rules['figures']['minimum_formal'];record=catalog.get('policy_override')
    if not record:return default
    source=inside(Path(catalog_path).parent,record['path'])
    if sha(source)!=record['sha256']:raise ValueError('Changed user figure policy exception')
    value=json.loads(source.read_text(encoding='utf-8'))
    if value.get('actor')!='user' or not value.get('user_statement','').strip() or not value.get('reason','').strip() or value.get('base_policy_sha256')!=sha(POLICY_PATH):raise ValueError('Explicit current user figure exception required')
    if value.get('binding')!=catalog.get('evidence') or value.get('question_ids')!=catalog.get('question_ids'):raise ValueError('User figure exception belongs to another result')
    formal=sorted(f['id'] for f in catalog['figures'] if f['formal'])
    if value.get('selected_figure_ids')!=formal or not isinstance(value.get('minimum_formal'),int) or not 1<=value['minimum_formal']<=len(formal):raise ValueError('User figure exception selection differs')
    return value['minimum_formal']

def validate_draft(markdown_path, catalog_path):
    """Mechanical checks only; approval, scientific meaning and visual QA remain separate."""
    path = Path(markdown_path)
    text = path.read_text(encoding='utf-8')
    catalog = json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    rules = policy()
    findings = []
    headers = re.findall(r'^#{1,3} +(?:[一二三四五六七八九十0-9]+[、.． ]+)?(.+?)\s*$', text, re.M)
    for section in rules['required_sections']:
        if not any(section == header.strip() for header in headers):
            findings.append('Missing Chinese section: ' + section)
    if any(term in text for term in rules['internal_terms_forbidden']):
        findings.append('Internal engineering material leaked into paper')
    if re.search(r'待补充|待插图|TODO|PLACEHOLDER', text, re.I):
        findings.append('Unresolved content placeholder')
    prose = re.sub(r'\$\$[\s\S]*?\$\$|\$[^$\n]*\$|!\[[^]]*\]\([^)]+\)|https?://[^\s)]+', '', text)
    chinese = len(re.findall(r'[\u4e00-\u9fff]', prose))
    latin = len(re.findall(r'[A-Za-z]', prose))
    ratio = chinese / max(chinese + latin, 1)
    if ratio < rules['minimum_chinese_ratio']:
        findings.append('Main prose must be Chinese')
    if re.search(r'^#{1,3} +(?:Theorem|Proof|Proposition|Equations|Derivation)', text, re.M | re.I):
        findings.append('Proof-paper outline is not a modeling-paper outline')
    figures = catalog['figures']
    ids = [fig['id'] for fig in figures]
    if len(ids) != len(set(ids)):
        findings.append('Duplicate logical figure ID')
    counts = Counter(fig['category'] for fig in figures)
    qids = catalog['question_ids']
    if len(qids)>1 and rules.get('symbol_table',{}).get('scope')=='whole_paper':
        from .assembly_symbols import validate_global_table
        try:validate_global_table(text)
        except ValueError as exc:findings.append('Global symbol table: '+str(exc))
    if not qids or len(qids) != len(set(qids)):
        findings.append('Question scope must be nonempty and unique')
    if len(figures) < rules['figures']['minimum_candidates']:
        findings.append('Fewer than 9 logical candidate figures')
    for category in rules['figures']['categories']:
        if counts[category] < rules['figures']['minimum_per_category']:
            findings.append('Candidate category deficit: ' + category)
        for qid in qids:
            if not any(fig['category'] == category and qid in fig['question_ids'] for fig in figures):
                findings.append('Missing question/category coverage: ' + qid + '/' + category)
    formal = [fig for fig in figures if fig['formal']]
    minimum_formal=scoped_figure_minimum(catalog_path,catalog,rules)
    if len(formal) < minimum_formal:
        findings.append('Fewer than '+str(minimum_formal)+' formal figures')
    for qid in qids:
        if not any(qid in fig['question_ids'] for fig in formal):
            findings.append('No formal figure for question: ' + qid)
    image_links = re.findall(r'!\[([^]]*)\]\(([^)]+)\)', text)
    if len(image_links) != len(formal):
        findings.append('Embedded image count differs from formal catalog')
    image_paths = [link for _, link in image_links]
    if len(image_paths) != len(set(image_paths)):
        findings.append('Same image embedded repeatedly')
    if [fig.get('number') for fig in formal] != list(range(1, len(formal) + 1)):
        findings.append('Formal figure numbers must be continuous')
    hashes = []
    for fig in figures:
        if fig['category'] not in rules['figures']['categories'] or not set(fig['question_ids']).issubset(qids):
            findings.append('Invalid figure scope/category: ' + fig['id'])
        for fmt in rules['figures']['required_formats']:
            try:
                asset = inside(path.parent, fig['files'][fmt]['path'])
                if sha(asset) != fig['files'][fmt]['sha256']:
                    findings.append('Changed figure bytes: ' + fig['id'] + '/' + fmt)
                if fmt == 'png':
                    hashes.append(sha(asset))
                    from PIL import Image
                    with Image.open(asset) as image:
                        if min(image.info.get('dpi', (0, 0))) < rules['figures']['minimum_png_dpi'] - 1:
                            findings.append('PNG resolution below 300 dpi: ' + fig['id'])
            except (KeyError, OSError, ValueError):
                findings.append('Missing or unsafe figure file: ' + fig['id'] + '/' + fmt)
        if fig['formal']:
            number = fig['number']
            png = fig['files']['png']['path']
            if not any(alt.startswith(f'图{number} ') and link == png for alt, link in image_links):
                findings.append('Missing image/Chinese alt number: ' + fig['id'])
            if not re.search(r'^图' + str(number) + r' +\S+', text, re.M):
                findings.append('Missing Chinese figure caption: ' + fig['id'])
            body = re.sub(r'^图[0-9]+ .*$', '', text, flags=re.M)
            body = re.sub(r'!\[[^]]*\]\([^)]+\)', '', body)
            if not re.search(r'图' + str(number) + r'(?![0-9])', body):
                findings.append('Figure not referenced in body: ' + fig['id'])
    if len(hashes) != len(set(hashes)):
        findings.append('Duplicate PNG content is not a new logical figure')
    return {'status': 'passed' if not findings else 'failed', 'findings': findings,
            'policy_version': rules['policy_version'], 'policy_sha256': sha(POLICY_PATH),
            'markdown_sha256': sha(path), 'catalog_sha256': sha(catalog_path),
            'language_ratio': ratio, 'candidate_figures': len(figures), 'categories': dict(counts),
            'formal_figures': len(formal), 'minimum_formal_effective': minimum_formal, 'policy_override': catalog.get('policy_override'), 'user_review': 'pending',
            'scope': 'Mechanical genre/Chinese/image checks, not scientific or visual approval'}

def require_review_for_export(markdown_path, catalog_path, review):
    report = validate_draft(markdown_path, catalog_path)
    if report['status'] != 'passed':
        raise ValueError('Paper checks failed')
    if review.get('review_version') == '2.0.0':
        from .writing_reviews import review_status
        state=review_status(markdown_path,catalog_path,review.get('manuscript_review'),review.get('figure_selection_review'))
        if not state['can_export']:
            raise ValueError('Separate current manuscript and figure selection approvals required: '+str({k:state[k] for k in ['manuscript','figure_selection']}))
        return {**report,'separate_reviews':state}
    if review.get('decision') != 'approve' or not review.get('reason', '').strip() or review.get('figure_selection_decision') != 'approve':
        raise ValueError('Explicit user review of Markdown and figure selection required before paper export')
    for field in ('markdown_sha256', 'catalog_sha256', 'policy_sha256'):
        if review.get(field) != report[field]:
            raise ValueError('Stale paper review: ' + field)
    return report
