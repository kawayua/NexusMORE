"""Preserve approved Markdown while separating exact explicit image captions."""
from copy import deepcopy
from modelcrew.paper_export import separate_image_captions


def sample(caption):
    image={'t':'Image','c':[['',[],[]],[{'t':'Str','c':'alt'}],['figures/f01.png','']]}
    catalog={'figures':[{'formal':True,'number':1,'title':'Input','files':{'png':{'path':'figures/f01.png'}}}]}
    ast={'blocks':[{'t':'Para','c':[image,{'t':'SoftBreak'},{'t':'Str','c':caption}]}]}
    return ast,catalog


def test_exact_caption_is_split_without_mutating_input():
    ast,catalog=sample('\u56fe1 Input');before=deepcopy(ast)
    result,changes=separate_image_captions(ast,catalog)
    assert ast==before
    assert len(result['blocks'])==2 and len(changes)==1
    assert result['blocks'][0]['c']==[before['blocks'][0]['c'][0]]
    assert result['blocks'][1]['c']==before['blocks'][0]['c'][2:]


def test_following_narrative_is_not_a_caption():
    ast,catalog=sample('\u56fe1 Input describes the given parameters.')
    result,changes=separate_image_captions(ast,catalog)
    assert result==ast and changes==[]


def test_already_separate_caption_is_unchanged():
    ast,catalog=sample('\u56fe1 Input')
    inline=ast['blocks'][0]['c'];ast['blocks']=[{'t':'Para','c':inline[:1]},{'t':'Para','c':inline[2:]}]
    result,changes=separate_image_captions(ast,catalog)
    assert result==ast and changes==[]


def test_five_column_symbol_widths_preserve_cells():
    from modelcrew.paper_export import set_symbol_table_widths
    table={'t':'Table','c':[[],[],[[{'t':'AlignDefault'},{'t':'ColWidthDefault'}] for _ in range(5)],{'t':'Str','c':'\u9002\u7528\u8303\u56f4'},'CELLS']}
    original=deepcopy(table)
    set_symbol_table_widths({'blocks':[table]})
    assert sum(x[1]['c'] for x in table['c'][2])==1
    assert table['c'][3:]==original['c'][3:]


def test_latex_break_opportunities_preserve_all_math_and_code_characters():
    from modelcrew.paper_export import latex_line_breaks
    src=r'\begin{longtable} \(a=b,c\approx2.22\times10^{-16}\) \end{longtable} \texttt{scipy.optimize.linprog(method=x)}'
    converted=latex_line_breaks(src)
    assert converted!=src
    assert converted.replace(r'\allowbreak ','')==src
    assert latex_line_breaks(r'Outside \(a=b\)')==r'Outside \(a=b\)'
