"""Readable modeling proposals and evidence-bound M1 audits, opt-in per snapshot."""
from __future__ import annotations

import copy
import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .collaboration import Record, Text, Evidence, Issue

VERSION = '1.0.0'
Paragraph = Annotated[str, Field(min_length=40, max_length=14000)]
Detail = Annotated[str, Field(min_length=10, max_length=2000)]
INTERNAL = re.compile(r'\bbaseline\b|\bedits\s*=|contract_sha256|\bchk_[a-z0-9_]+\b|\b(?:M1|P1|P2)\b|\b(?:eq|der|vp):', re.I)


class ProposalProseError(ValueError):
    """Locate rejected author prose without editing it or echoing full inputs."""
    def __init__(self, diagnostics):
        self.diagnostics=copy.deepcopy(diagnostics)
        super().__init__('Internal workflow IDs/logs belong in trace metadata, not proposal prose; '
            'see validation_errors for the exact field, token and character offset')

    def errors(self, **kwargs):
        return copy.deepcopy(self.diagnostics)


def prose_diagnostics(document, limit=30):
    """Group exact token positions by authored field; source IDs are metadata."""
    findings=[]
    def walk(value, loc):
        if len(findings)>=limit:return
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='source_id':continue
                walk(item,loc+[key])
        elif isinstance(value,list):
            for index,item in enumerate(value):walk(item,loc+[index])
        elif isinstance(value,str):
            matches=[];tokens=[];count=0
            for match in INTERNAL.finditer(value):
                end=match.end()
                if match.group().endswith(':'):
                    end+=len(re.match(r'[A-Za-z0-9_.:-]*',value[end:]).group())
                token=value[match.start():end];count+=1
                if token not in tokens and len(tokens)<60:tokens.append(token)
                if len(matches)<30:
                    matches.append({'matched_text':token,'char_start':match.start(),'char_end':end,
                        'line':value.count('\n',0,match.start())+1})
            if matches:
                findings.append({'type':'internal_reference_in_prose','loc':loc.copy(),
                    'msg':'Replace all internal references in this field with scientific names or actual LaTeX equations; preserve scientific content and retain IDs only in trace/source metadata.',
                    **matches[0], 'matched_tokens':tokens, 'matches':matches,
                    'occurrence_count':count,'matches_truncated':count>len(matches)})
    walk(document.model_dump(mode='json'),['review_document'])
    return findings


class Assumption(Record):
    statement: Detail
    # A concise factual basis is valid; evidence quality belongs to independent M1.
    basis: Annotated[str, Field(min_length=1, max_length=2000, pattern=r'\S')]
    impact: Detail


class Symbol(Record):
    symbol: Text
    meaning: Text
    unit: Text
    scope: Text


class SourceUse(Record):
    source_id: Text
    use: Detail


class Applicability(Record):
    status: Literal['applies', 'not_applicable']
    reason: Detail


class ReviewDocument(Record):
    problem_analysis: Paragraph
    assumptions: list[Assumption] = Field(min_length=1, max_length=30)
    symbols: list[Symbol] = Field(min_length=1, max_length=60)
    model_derivation: Paragraph
    solution_plan: Paragraph
    verification_plan: Paragraph
    limitations: Paragraph
    sources: list[SourceUse] = Field(min_length=1, max_length=30)
    applicability: dict[Literal['discretization','nonlinear_solver','stability','convergence','boundary_conditions'], Applicability]

    @field_validator('applicability')
    @classmethod
    def complete_applicability(cls, value):
        required={'discretization','nonlinear_solver','stability','convergence','boundary_conditions'}
        if set(value)!=required:
            raise ValueError('Every numerical applicability item needs an explicit status and reason')
        return value


class AuditFinding(Record):
    criterion: Text
    status: Literal['PASS', 'FAIL', 'BLOCKED']
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
    explanation: Text


# ID -> (existing M1 check, proposal section, compare against baseline evidence)
CRITERIA = {
    'problem_reasoning': ('model','problem_analysis',True),
    'assumption_basis': ('assumptions','assumptions',True),
    'symbols_units': ('units','symbols',True),
    'physical_quantity_basis': ('units','model_derivation',True),
    'derivation': ('model','model_derivation',True),
    'initial_boundary_conditions': ('constraints','model_derivation',True),
    'discretization': ('algorithm_premises','solution_plan',True),
    'nonlinear_solver': ('algorithm_premises','solution_plan',True),
    'stability_reasoning': ('algorithm_premises','solution_plan',True),
    'verification_definitions': ('validation_plan','verification_plan',True),
    'convergence_reasoning': ('validation_plan','verification_plan',True),
    'limitations_sources': ('assumptions','limitations',True),
    'reader_presentation': ('model','problem_analysis',False),
}


def proposal_selectors(criterion):
    """Accept relevant alternate sections, but not arbitrary document roots."""
    primary='/review_document/'+CRITERIA[criterion][1]
    alternate={
        'nonlinear_solver':['/review_document/model_derivation','/review_document/applicability/nonlinear_solver'],
        'stability_reasoning':['/review_document/model_derivation','/review_document/applicability/stability'],
        'convergence_reasoning':['/review_document/applicability/convergence'],
        'reader_presentation':['/review_document','/text'],
    }
    return [primary]+alternate.get(criterion,[])


def render(document, contract, references):
    """Only author-provided scientific prose enters the readable view."""
    doc=document.model_dump(mode='json')
    labels={s['id']:s.get('locator',s['id']) for s in contract['sources']}
    labels.update({s['citation_id']:s.get('title',s['citation_id']) for s in references['cards']})
    def cell(text):return text.replace('|',r'\|').replace('\n',' ')
    lines=['# 建模方案（待确认）','', '## 问题分析与建模思路','',doc['problem_analysis'],'', '## 模型假设及依据','']
    for i,item in enumerate(doc['assumptions'],1):
        lines.extend([f"### 假设 {i}",'',item['statement'],'','依据：'+item['basis'],'','影响与适用边界：'+item['impact'],''])
    lines.extend(['## 符号说明','','| 符号 | 含义 | 单位 | 适用范围 |','| --- | --- | --- | --- |'])
    lines.extend('| '+' | '.join(cell(s[k]) for k in ('symbol','meaning','unit','scope'))+' |' for s in doc['symbols'])
    for heading,key in [('模型建立与推导','model_derivation'),('离散与求解流程','solution_plan'),('检验方法与判据','verification_plan'),('局限性与适用范围','limitations')]:
        lines.extend(['','## '+heading,'',doc[key]])
    lines.extend(['','## 方法适用性说明',''])
    names={'discretization':'离散方法','nonlinear_solver':'非线性求解','stability':'稳定性','convergence':'收敛性','boundary_conditions':'初边值条件'}
    for key in names:
        item=doc['applicability'][key]
        lines.append(names[key]+('：适用。' if item['status']=='applies' else '：不适用。')+item['reason'])
        lines.append('')
    lines.extend(['## 资料依据',''])
    lines.extend('- '+labels[s['source_id']]+'：'+s['use'] for s in doc['sources'])
    return '\n'.join(lines).rstrip()+'\n'


def validate_document(document, contract, references):
    if document is None:
        raise ValueError('Readable review_document required; an internal summary is insufficient')
    known={s['id'] for s in contract['sources']} | {s['citation_id'] for s in references['cards']}
    source_ids=[s.source_id for s in document.sources]
    if len(source_ids)!=len(set(source_ids)) or not set(source_ids)<=known:
        raise ValueError('Proposal source references must be unique, actually supplied source IDs')
    symbols=[s.symbol for s in document.symbols]
    if len(symbols)!=len(set(symbols)):
        raise ValueError('Use one unambiguous definition per symbol')
    if not re.search(r'\$\$?[^$]+\$\$?|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)',document.model_derivation):
        raise ValueError('Model derivation requires readable LaTeX math delimiters, not raw operator text')
    text=render(document,contract,references)
    chinese=sum('\u4e00'<=c<='\u9fff' for c in text)
    latin=sum(c.isascii() and c.isalpha() for c in text)
    if chinese<80 or chinese/max(chinese+latin,1)<0.4:
        raise ValueError('User-facing modeling proposal requires substantive Chinese explanations')
    diagnostics=prose_diagnostics(document)
    if diagnostics:raise ProposalProseError(diagnostics)
    return {'policy_version':VERSION,'status':'PASS','scope':'structure_and_source_ids_only',
            'semantic_correctness_verified':False,'independent_audit_required':True}


def enforce_audit(checks, issues, findings, evidence, resolve):
    """Missing evidence blocks admission; semantic findings can only downgrade checks."""
    checks=copy.deepcopy(checks);issues=copy.deepcopy(issues)
    indexed={}
    for finding in findings or []:
        indexed.setdefault(finding.criterion,[]).append(finding)
    decisions=[]
    for criterion,(check_id,section,compare) in CRITERIA.items():
        matches=indexed.get(criterion,[])
        finding=matches[0] if len(matches)==1 else None
        status='BLOCKED';reason='缺少唯一的逐项审查记录';proof=[]
        if finding is not None:
            reason=finding.explanation;proof=finding.evidence
            roots=proposal_selectors(criterion)
            has_section=any(e.artifact_id=='proposal' and any(e.selector==root or
                (root!='/review_document' and e.selector.startswith(root+'/')) for root in roots) for e in proof)
            has_baseline=not compare or any(e.artifact_id in ('contract','mathematics','original','sources') for e in proof)
            valid=True
            for e in proof:
                try:
                    if e.artifact_id not in evidence:raise ValueError('Unknown evidence')
                    resolve(evidence[e.artifact_id],e.selector)
                except (ValueError,KeyError,IndexError,TypeError):valid=False
            if has_section and has_baseline and valid:
                status=finding.status
            else:
                reason='审查未引用相应方案段落及可解析的原始依据：'+criterion
                proof=[]
        target=next((c for c in checks if c.check_id==check_id),None)
        if target is None:raise ValueError('Required M1 check missing: '+check_id)
        if status!='PASS':
            if target.status!='FAIL':target=target.model_copy(update={'status':status})
            issues.append(Issue(check_id=check_id,severity='blocking',domain='model',target='modeling',
                reason=(criterion+'：'+reason)[:300],recheck='修正方案或补齐独立逐项证据后重新审查'))
        for e in proof:
            if e not in target.evidence:target.evidence.append(e)
        checks[next(i for i,c in enumerate(checks) if c.check_id==check_id)]=target
        decisions.append({'criterion':criterion,'status':status,'explanation':reason,
            'reported_status':finding.status if finding else None,
            'evidence':[e.model_dump(mode='json') for e in proof]})
    extra=set(indexed)-set(CRITERIA)
    if extra:
        raise ValueError('Unknown proposal audit criteria')
    return checks,issues,decisions
