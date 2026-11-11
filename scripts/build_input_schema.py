import copy,json
from pathlib import Path
root=Path.cwd()
def obj(props,required=None):return {'type':'object','properties':props,'required':required if required is not None else list(props),'additionalProperties':False}
s={'type':'string','minLength':1}; ns={'type':['string','null']}; integer={'type':'integer','minimum':0}
field=obj({'path':s,'data_type':s,'shape':{'type':'array','items':{'type':['integer','null'],'minimum':0}},'unit':ns,'nullable':{'type':['boolean','null']},'meaning':ns,'origin':{'enum':['attachment','statement','user','system_suggestion']},'source_locator':s})
question=obj({'id':s,'question':s,'blocking':{'type':'boolean'},'status':{'enum':['unresolved','resolved']},'resolution':ns})
rule=obj({'path':s,'rule':s,'origin':{'enum':['statement','user','system_suggestion']},'source_locator':s})
base={'template_id':s,'template_version':{'const':'1.0.0'},'observed':{'type':'object'},'fields':{'type':'array','items':field},'requirements':{'type':'array','items':rule},'pending':{'type':'array','items':question}}
# Observations are typed per template; facts and proposed requirements stay distinct.
observations={
 'table':obj({'format':s,'tables':{'type':'array','items':obj({'name':s,'rows':integer,'columns':integer,'sample':{'type':'array','maxItems':6,'items':{'type':'array','items':{}}}})}}),
 'time_series':obj({'format':s,'tables':{'type':'array','items':obj({'name':s,'rows':integer,'columns':integer,'sample':{'type':'array','maxItems':6,'items':{'type':'array','items':{}}}})}}),
 'array':obj({'format':s,'arrays':{'type':'array','items':obj({'name':s,'shape':{'type':'array','items':integer},'dtype':s})}}),
 'nested':obj({'format':s,'data_schema':{'type':'object'}}),
 'image':obj({'format':s,'width':integer,'height':integer,'mode':s}),
 'geospatial':obj({'format':s,'geometry_types':{'type':'array','items':s},'feature_count':integer,'crs':ns}),
 'document':obj({'format':s,'pages':{'type':'array','items':obj({'page':{'type':'integer','minimum':1},'text':{'type':'string'}})}}),
 'output_template':obj({'format':s,'tables':{'type':'array','items':obj({'name':s,'rows':integer,'columns':integer,'sample':{'type':'array','maxItems':6,'items':{'type':'array','items':{}}}})}}),
 'parameters':obj({'format':s,'data_schema':{'type':'object'}}),
 'unsupported':obj({'format':s})}
registry={'registry_version':'1.0.0','templates':{}}
variants=[]
for kind,obs in observations.items():
 props=copy.deepcopy(base);props['template_id']={'const':kind};props['observed']=obs
 entry=obj(props);variants.append(entry);registry['templates'][kind]={'version':'1.0.0','schema':entry}
(root/'contracts/input-templates-1.0.0.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
schema=json.loads((root/'contracts/model-contract-1.0.0.schema.json').read_text())
schema['properties']['schema_version']={'const':'1.1.0'};schema['$id']='https://modelcrew.local/schemas/model-contract/1.1.0';schema['title']='Model Contract v1.1.0'
schema['properties']['inputs']['items']['properties']['structure']={'oneOf':variants};schema['properties']['inputs']['items']['required'].append('structure')
(root/'contracts/model-contract-1.1.0.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
