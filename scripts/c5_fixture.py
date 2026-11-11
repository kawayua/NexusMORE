"""Fixed, non-contest engineering fixture; never modeler-generated or user-approved."""
from pathlib import Path
from modelcrew.contracts import validate
from modelcrew.inputs import file_hash


def contract_for(path):
    path=Path(path).resolve();sha=file_hash(path)
    value={'schema_version':'1.0.0',
        'problem':{'case_id':'TEST_C5_SUM_SQUARES','subproblem_id':'Q1','title':'TEST ONLY sum squares',
                   'scope':'Engineering integration of fixed [1,2,3] input','objective':{'kind':'analysis','description':'Compute sum of squares; no modeling-quality claim'}},
        'sources':[{'id':'dataset','kind':'user_guidance','locator':str(path),'sha256':sha}],
        'inputs':[{'id':'numbers','source_id':'dataset','path':str(path),'sha256':sha,'role':'dataset'}],
        'conventions':{'length_unit':'dimensionless','time_unit':'not_applicable','coordinate_system':'none',
                       'time_origin':'not_applicable','direction':'not_applicable','indexing':'zero_based'},
        'parameters':[{'id':'power','value':2,'unit':'dimensionless','source_id':'dataset','origin':'assumption','derivation':None}],
        'variables':[{'id':'total','meaning':'sum of input squares','unit':'dimensionless','domain':'nonnegative_integer'}],
        'assumptions':[{'id':'integer_input','statement':'Fixed fixture input integers','source_id':'dataset'}],
        'constraints':[{'id':'definition','expression':'total=sum(x*x for x in values)','meaning':'square and sum','check_id':'expected'}],
        'method':{'steps':['Read fixed input JSON','Compute sum of squares','Write result.json'],
                  'root_selection':'not_applicable','allowed_equivalent_changes':['Equivalent integer arithmetic'],
                  'requires_new_confirmation':['Any change to input, code or operation']},
        'outputs':[{'id':'result','path':'result.json','format':'json','fields':[{'name':'total','shape':[1],'unit':'dimensionless'}],'decimal_places':None}],
        'checks':[{'id':'expected','description':'fixed [1,2,3] has total 14','method':'independently read output and compare',
                   'tolerance':0,'unit':'dimensionless','evidence_required':'archived result.json','initial_status':'unknown'}],
        'risks':['Fixed engineering fixture is not independent modeling or a contest solve'],
        'alternatives':['Manual integer calculation as verification only']}
    validate(value);return value


CODE='''import json, os
from pathlib import Path
values=json.loads((Path(os.environ['MODELCREW_INPUT_DIR'])/'numbers.json').read_text())
(Path(os.environ['MODELCREW_OUTPUT_DIR'])/'result.json').write_text(json.dumps({'total':sum(x*x for x in values)}))
'''
