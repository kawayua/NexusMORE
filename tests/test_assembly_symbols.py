"""Semantic merge is explicit, complete, and preserves source units."""
from copy import deepcopy
import pytest
from modelcrew.assembly_symbols import build, source_table, atoms, markdown


def item(q,rows):
    return {'question_id':q,'sections':{'符号说明':'表2 局部符号\n\n| 符号 | 含义 | 单位 |\n|---|---|---|\n'+ '\n'.join('| '+' | '.join(r)+' |' for r in rows)}}


def row(symbol,meaning,unit,sources):
    return {'symbol':symbol,'meaning':meaning,'unit':unit,'sources':[{'question_id':q,'symbol':s} for q,s in sources],'reason':'Explicit author check against definitions'}


def test_exact_definition_merge_only():
    inputs=[item('q1',[('$x$','位置','m')]),item('q2',[('$x$','位置','m')])]
    r=build(inputs)
    assert len(r['rows'])==1 and r['rows'][0]['question_ids']==['q1','q2']
    assert r['source_rows']==2 and r['source_components']==2
    assert '问题一、问题二' in markdown(r,{'q1':'问题一','q2':'问题二'})


def test_different_definitions_require_explicit_map():
    inputs=[item('q1',[('$x$','位置','m')]),item('q2',[('$x$','同一位置的说明','m')])]
    with pytest.raises(ValueError,match='explicit'):build(inputs)
    r=build(inputs,[row('$x$','位置','m',[('q1','$x$'),('q2','$x$')])])
    assert r['coverage']=='complete' and r['mode']=='explicit_mapping'


def test_split_bundled_symbols_and_units():
    inputs=[item('q1',[(r'$r,\delta$','半径与角差','m, rad')])]
    rows=[row('$r$','半径','m',[('q1',r'$r,\delta$')]),row(r'$\delta$','角差','rad',[('q1',r'$r,\delta$')])]
    assert build(inputs,rows)['source_components']==2
    with pytest.raises(ValueError,match='every source symbol component'):build(inputs,rows[:1])
    rows[1]['unit']='m'
    with pytest.raises(ValueError,match='unit conflict'):build(inputs,rows)


def test_differing_units_cannot_be_silently_merged():
    inputs=[item('q1',[('$x$','位置','m')]),item('q2',[('$x$','位置','cm')])]
    with pytest.raises(ValueError,match='unit conflict'):
        build(inputs,[row('$x$','位置','m',[('q1','$x$'),('q2','$x$')])])


def test_symbol_atoms_preserve_function_arguments_and_definition_rhs():
    assert atoms(r'$F(\delta;r,\ell)$')==[r'F(\delta;r,\ell)']
    assert atoms(r'$b=p/(2\pi)$')==['b']
    assert atoms(r'$C_k,u_k,n_k$')==['C_k','u_k','n_k']


def test_escaped_norm_pipes_are_not_table_delimiters():
    r=build([item('q',[(r'$U_i$',r'速率，$U_i=\|\mathbf V_i\|$','m/s')])])
    assert r['source_rows']==1


def test_unknown_renamed_and_duplicate_rows_rejected():
    inputs=[item('q1',[('$x$','位置','m')])]
    with pytest.raises(ValueError,match='Unknown'):build(inputs,[row('$x$','位置','m',[('q2','$x$')])])
    with pytest.raises(ValueError,match='upstream patches'):build(inputs,[row('$y$','位置','m',[('q1','$x$')])])
    r=row('$x$','位置','m',[('q1','$x$')])
    with pytest.raises(ValueError,match='overlapping'):build(inputs,[r,deepcopy(r)])


def test_no_silent_loss_of_notes_or_extra_tables():
    i=item('q1',[('$x$','位置','m')])
    with pytest.raises(ValueError,match='notes'):source_table('q1',i['sections']['符号说明']+'\n\n不可丢弃的定义说明。')
    with pytest.raises(ValueError,match='one table'):source_table('q1',i['sections']['符号说明']+'\n\n'+i['sections']['符号说明'])

def test_global_structure_guard_rejects_question_subtables_and_missing_scope():
    from modelcrew.assembly_symbols import validate_global_table
    body='## 符号说明\n\n表1 全局符号说明\n\n| 符号 | 含义 | 单位 | 适用范围 |\n|---|---|---|---|\n| $x$ | 位置 | m | 问题一、问题二 |\n\n## 模型建立\n'
    assert validate_global_table(body)['rows']==1
    with pytest.raises(ValueError,match='subheadings'):validate_global_table(body.replace('表1','### 问题一\n\n表1'))
    with pytest.raises(ValueError,match='scope'):validate_global_table(body.replace(' | 适用范围',''))
    with pytest.raises(ValueError,match='one global logical symbol table'):
        validate_global_table(body.replace('## 模型建立','| 符号 | 含义 | 单位 | 适用范围 |\n|---|---|---|---|\n| $y$ | 位置 | m | 问题二 |\n\n## 模型建立'))


def test_applicable_scope_may_extend_to_other_verified_body_usage():
    inputs=[item('q1',[('$x$','位置','m')]),item('q2',[('$t$','时间','s')])]
    x=row('$x$','位置','m',[('q1','$x$')]);x['applicable_questions']=['q1','q2']
    t=row('$t$','时间','s',[('q2','$t$')])
    assert build(inputs,[x,t])['rows'][0]['question_ids']==['q1','q2']
    x['applicable_questions']=['q2']
    with pytest.raises(ValueError,match='scope'):build(inputs,[x,t])


def test_composer_identity_includes_symbol_adapter(tmp_path,monkeypatch):
    from modelcrew import assembly_compose as ac
    from modelcrew import assembly_symbols as sy
    before=ac.implementation_sha256()
    fake=tmp_path/'symbol_adapter.py';fake.write_text('Changed helper implementation',encoding='utf-8')
    monkeypatch.setattr(sy,'__file__',str(fake))
    assert ac.implementation_sha256()!=before
