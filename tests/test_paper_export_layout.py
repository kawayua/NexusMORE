"""Pandoc table rounding must not overflow the selected template's text width."""
from decimal import Decimal
import re
from scripts.export_approved_paper import normalize_longtable_widths


def test_seven_equal_columns_remain_inside_linewidth_without_font_scaling():
    source=r'\begin{longtable}[]{'+' '.join([r'p{(\linewidth - 12\tabcolsep) * \real{0.1429}}']*7)+r'}\toprule NUMERIC_CONTENT'
    result=normalize_longtable_widths(source)
    weights=[Decimal(v) for v in re.findall(r'\\real\{([0-9.]+)\}',result)]
    assert Decimal('0.999999999')<sum(weights)<=1
    assert result.endswith('NUMERIC_CONTENT') and 'small' not in result


def test_exact_column_widths_and_non_table_math_unchanged():
    source=r'\begin{longtable}[]{p{\real{0.25}}p{\real{0.75}}}\toprule'+'\n'+r'\real{0.1429}'
    assert normalize_longtable_widths(source)==source

def test_small_labels_use_only_outer_whitespace_crop_and_keep_source_assets():
    from pathlib import Path
    import json
    from scripts.export_approved_paper import figure_embedding
    from modelcrew.modeling_paper import sha
    source=Path('stage-e/reviews/global-symbol-table-20261110-v3/source')
    catalog=json.loads((source/'figure-catalog.json').read_text(encoding='utf-8'))
    figure=next(f for f in catalog['figures'] if f['id']=='q1-process-1')
    before={fmt:sha(source/a['path']) for fmt,a in figure['files'].items()}
    result=figure_embedding(source,figure)
    assert result['crop'] and result['minimum_label_pt_before']<5<=result['minimum_label_pt_after']
    assert all(0<=v<15000 for v in result['png_crop_100000'].values())
    assert all(v>0 for v in result['pdf_trim_pt'])
    assert before=={fmt:sha(source/a['path']) for fmt,a in figure['files'].items()}

def test_global_symbol_column_widths_change_layout_only():
    from copy import deepcopy
    from scripts.export_approved_paper import set_symbol_table_widths
    header={'t':'Str','c':'符号含义单位适用范围'}
    table={'t':'Table','c':[[],[],[[{'t':'AlignDefault'},{'t':'ColWidthDefault'}] for _ in range(4)],header,'UNCHANGED_CELLS']}
    ast={'blocks':[table]};before=deepcopy(ast)
    set_symbol_table_widths(ast)
    assert [c[1]['c'] for c in table['c'][2]]==[.18,.52,.10,.20]
    assert table['c'][3:]==before['blocks'][0]['c'][3:]

def test_word_math_delimiters_are_equivalent_and_convert_to_omml():
    import subprocess,json,zipfile,io
    from scripts.export_approved_paper import word_math_compatible
    from pathlib import Path
    source=json.loads(Path('output/paper/global-symbols-20261110-v3/build/source-ast.json').read_text(encoding='utf-8'))
    expr=next(b['c'][0]['c'][1] for b in source['blocks'] if b['t']=='Para' and b['c'] and b['c'][0]['t']=='Math' and '\\tag{27}' in b['c'][0]['c'][1])
    transformed=word_math_compatible(expr)
    assert '\\tag' not in transformed and '\\left(' in transformed and '\\right)' in transformed
    ast={**source,'blocks':[{'t':'Para','c':[{'t':'Math','c':[{'t':'DisplayMath'},transformed]}]}]}
    result=subprocess.run(['stage-c-plus/tools/pandoc/pandoc.exe','-f','json','-t','docx','-o','-'],input=json.dumps(ast).encode(),capture_output=True,check=True)
    assert b'Could not convert' not in result.stderr
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as z:
        assert b'<m:oMath' in z.read('word/document.xml')
