"""Versioned input profiles. Inspection reports observations, never invents semantics."""
from .project_assets import asset_path,input_path
import copy,csv,hashlib,json,math
from pathlib import Path
from .contracts import ROOT,ContractError,validate

REGISTRY=json.loads((asset_path(ROOT,'contracts/input-templates-1.0.0.json')).read_text(encoding='utf-8'))
MAX_BYTES=20*1024*1024

def file_hash(path):
    h=hashlib.sha256()
    with input_path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def _type(value):
    if value is None:return 'null'
    if isinstance(value,bool):return 'boolean'
    if isinstance(value,int):return 'integer'
    if isinstance(value,float):return 'number'
    if isinstance(value,str):return 'string'
    if isinstance(value,list):return 'array'
    return 'object'

def _json_schema(value,depth=0):
    if depth>30:raise ContractError('JSON nesting exceeds inspection limit')
    kind=_type(value)
    if kind=='object':return {'type':'object','properties':{k:_json_schema(v,depth+1) for k,v in value.items()}}
    if kind=='array':
        variants=[]
        for v in value[:100]:
            schema=_json_schema(v,depth+1)
            if schema not in variants:variants.append(schema)
        return {'type':'array','items':variants[0] if len(variants)==1 else ({'anyOf':variants} if variants else {})}
    return {'type':kind}

def _safe(value):
    if value is None or isinstance(value,(bool,int,str)):return value
    if isinstance(value,float):return value if math.isfinite(value) else str(value)
    return str(value)

def inspect_file(path,role='dataset',kind=None):
    path=asset_path(ROOT,path).resolve()
    if not path.is_file():raise ContractError(f'Input file missing: {path.name}')
    if path.stat().st_size>MAX_BYTES:raise ContractError(f'Input exceeds {MAX_BYTES} byte inspection limit: {path.name}')
    before=file_hash(path);suffix=path.suffix.lower();fields=[];pending=[]
    def question(qid,text):pending.append({'id':qid,'question':text,'blocking':True,'status':'unresolved','resolution':None})
    def field(name,dtype,shape=()):
        fields.append({'path':name,'data_type':dtype,'shape':list(shape),'unit':None,'nullable':None,'meaning':None,'origin':'attachment','source_locator':str(path)+'#'+name})
    if suffix in ('.csv','.tsv','.xlsx'):
        tables=[]
        if suffix=='.xlsx':
            from openpyxl import load_workbook
            wb=load_workbook(path,read_only=True,data_only=False)
            try:
                for sheet in wb:
                    if sheet.max_row*sheet.max_column>1_000_000:raise ContractError('Workbook dimensions exceed inspection limit')
                    sample=[[_safe(v) for v in row] for row in sheet.iter_rows(min_row=1,max_row=min(sheet.max_row,6),values_only=True)]
                    tables.append({'name':sheet.title,'rows':sheet.max_row,'columns':sheet.max_column,'sample':sample})
            finally:wb.close()
        else:
            with path.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.reader(f,delimiter='\t' if suffix=='.tsv' else ',');sample=[];rows=0;columns=0
                for row in reader:
                    rows+=1;columns=max(columns,len(row))
                    if rows<=6:sample.append(row)
                    if rows*columns>1_000_000:raise ContractError('Table exceeds inspection limit')
            tables=[{'name':path.stem,'rows':rows,'columns':columns,'sample':sample}]
        detected='output_template' if role=='required_output_template' else 'table'
        if kind=='time_series':detected=kind
        observed={'format':suffix[1:],'tables':tables}
        for table in tables:
            field(table['name'],'table',[table['rows'],table['columns']])
            if detected!='output_template':
                for col in range(table['columns']):
                    values=[row[col] for row in table['sample'][1:] if len(row)>col]
                    types=sorted({_type(v) for v in values})
                    field(table['name']+'/column/'+str(col+1),'sample:'+('|'.join(types) or 'unknown'))
        question('layout','请确认表头/标签/数据区域、字段含义、单位和缺失值策略；sample仅为前六行，不能据此认定全表类型。' if detected!='output_template' else '请确认模板的表头、节点标签、填写区域和精度；空单元格不是缺失观测值。')
        if detected=='time_series':question('time','请确认时间列、格式、时区、采样间隔以及重复和间断处理。')
    elif suffix in ('.npy','.npz'):
        import numpy as np
        arrays=[]
        # Never enable pickle for object arrays from attachments.
        if suffix=='.npy':
            array=np.load(path,allow_pickle=False,mmap_mode='r');arrays=[{'name':path.stem,'shape':list(array.shape),'dtype':str(array.dtype)}]
        else:
            import zipfile
            with zipfile.ZipFile(path) as archive:
                if sum(x.file_size for x in archive.infolist())>MAX_BYTES:raise ContractError('Expanded NPZ exceeds inspection limit')
            with np.load(path,allow_pickle=False) as data:
                for key in data.files:
                    array=data[key];arrays.append({'name':key,'shape':list(array.shape),'dtype':str(array.dtype)})
        detected='array';observed={'format':suffix[1:],'arrays':arrays}
        for array in arrays:field(array['name'],array['dtype'],array['shape'])
        question('axes','请确认数组各轴含义、单位、非有限值及空数组处理。')
    elif suffix in ('.json','.geojson'):
        data=json.loads(path.read_text(encoding='utf-8-sig'),parse_constant=lambda x:(_ for _ in ()).throw(ContractError('Nonfinite JSON value')))
        if suffix=='.geojson' or (isinstance(data,dict) and data.get('type')=='FeatureCollection'):
            if not isinstance(data,dict) or data.get('type')!='FeatureCollection':raise ContractError('Only GeoJSON FeatureCollection is supported')
            features=data.get('features',[])
            if not isinstance(features,list):raise ContractError('GeoJSON features must be an array')
            detected='geospatial';observed={'format':'geojson','geometry_types':sorted({str((f.get('geometry') or {}).get('type','null')) for f in features}),'feature_count':len(features),'crs':None}
            question('crs','请依据来源确认坐标参考系、轴顺序、单位和空几何处理；格式名称不作为坐标语义的证据。')
        else:
            detected='parameters' if kind=='parameters' else 'nested';observed={'format':'json','data_schema':_json_schema(data)}
            field('$',_type(data))
            question('semantics','请确认字段语义、必需项、单位与空值策略；观测到的键不自动认定为必需字段。')
    elif suffix in ('.png','.jpg','.jpeg','.tif','.tiff','.bmp'):
        from PIL import Image
        with Image.open(path) as image:observed={'format':image.format or suffix[1:],'width':image.width,'height':image.height,'mode':image.mode}
        detected='image';field('pixels','image',[observed['height'],observed['width']])
        question('image_semantics','请确认图像用途、方向；用于物理测量时确认标定比例，非测量用途可说明无需标定。')
    elif suffix in ('.pdf','.txt','.md'):
        if suffix=='.pdf':
            from pypdf import PdfReader
            reader=PdfReader(path)
            if len(reader.pages)>100:raise ContractError('PDF exceeds 100 page inspection limit')
            pages=[{'page':i+1,'text':page.extract_text() or ''} for i,page in enumerate(reader.pages)]
        else:pages=[{'page':1,'text':path.read_text(encoding='utf-8-sig')}]
        detected='document';observed={'format':suffix[1:],'pages':pages}
        question('statement','请核对题目范围、文本提取遗漏及图示含义，确认关键假设与约束。')
    else:
        detected='unsupported';observed={'format':suffix[1:] or 'unknown'}
        question('unsupported','尚无此类型的解析器，请补充内部结构定义或转换为已支持格式。')
    if kind and detected!=kind:raise ContractError(f'{suffix} cannot be inspected using requested template {kind}')
    if before!=file_hash(path):raise ContractError('Input changed during inspection')
    structure={'template_id':detected,'template_version':'1.0.0','observed':observed,'fields':fields,'requirements':[],'pending':pending}
    return {'path':str(path),'sha256':before,'role':role,'structure':structure}

def draft_inputs(contract):
    """Upgrade a COPY; reuse matching profiles, never rewrite stored contracts."""
    validate(contract);result=copy.deepcopy(contract);result['schema_version']='1.1.0'
    for item in result['inputs']:
        if file_hash(item['path']).lower()!=item['sha256'].lower():raise ContractError(f'Input snapshot changed: {item["id"]}; create a deliberate input revision')
        if 'structure' not in item:item['structure']=inspect_file(item['path'],item['role'])['structure']
    validate(result)
    return result

def pending_questions(contract):
    return [{'input_id':i['id'],**q} for i in contract['inputs'] for q in i.get('structure',{}).get('pending',[]) if q['status']=='unresolved']

def assert_ready(contract,verify_files=True):
    validate(contract)
    blockers=[q for q in pending_questions(contract) if q['blocking']]
    if blockers:raise ContractError('Unresolved input questions: '+', '.join(q['input_id']+'/'+q['id'] for q in blockers))
    if verify_files:
        for item in contract['inputs']:
            if not Path(item['path']).is_file() or file_hash(item['path']).lower()!=item['sha256'].lower():raise ContractError(f'Input snapshot missing or changed: {item["id"]}')
            structure=item.get('structure')
            if structure:
                actual=inspect_file(item['path'],item['role'],structure['template_id'])['structure']['observed']
                if actual!=structure['observed']:raise ContractError(f'Input observed structure does not match file: {item["id"]}')

def resolve_question(contract,input_id,question_id,resolution):
    if not resolution.strip():raise ContractError('Resolution must be nonempty')
    result=copy.deepcopy(contract)
    matches=[q for i in result['inputs'] if i['id']==input_id for q in i.get('structure',{}).get('pending',[]) if q['id']==question_id]
    if len(matches)!=1:raise ContractError('Unknown or duplicate input question')
    matches[0].update(status='resolved',resolution=resolution)
    validate(result);return result
