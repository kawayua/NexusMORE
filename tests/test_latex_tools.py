"""Own LaTeX tools: genuine cached compiler probes, no formal paper approvals."""
from pathlib import Path
import json
import subprocess
import sys

import pytest

from modelcrew import latex_tools as tools
from modelcrew.pdf_checks import sha


def custom_project(tmp_path, text=None):
    template=tmp_path/'template';template.mkdir()
    (template/'main.tex').write_text(text or r'''\documentclass[12pt]{article}
\begin{document}
Engineering toolchain probe. Data and formula below are synthetic.
\[x^2+1=2\]
\newpage
Second physical page: all pages must be previewed and checked.
\end{document}
''',encoding='utf-8')
    tools.initialize(tmp_path,'project',template='template',template_source='project-authored-test',template_version='fixture-1')
    return tmp_path/'project'


def test_default_skeleton_chinese_global_symbols_and_optional_english(tmp_path):
    result=tools.initialize(tmp_path,'zh')
    assert result['purpose']=='engineering_probe' and not result['user_approval']
    text=(tmp_path/'zh/main.tex').read_text(encoding='utf-8-sig')
    assert text.count(r'\section{符号说明}')==1 and text.count(r'\begin{longtable}')==1
    assert text.index(r'\clearpage')<text.index(r'\section{问题重述}')
    assert tools.preflight(tmp_path,'zh')['status']=='failed'
    with pytest.raises(FileExistsError):tools.initialize(tmp_path,'zh')
    tools.initialize(tmp_path,'english',profile='en')
    assert 'Team ' not in (tmp_path/'english/main.tex').read_text(encoding='utf-8-sig')


def test_custom_template_metadata_and_main_required(tmp_path):
    (tmp_path/'template').mkdir()
    (tmp_path/'template/paper.tex').write_text('test',encoding='utf-8')
    with pytest.raises(ValueError,match='source and version'):
        tools.initialize(tmp_path,'project',template='template')
    with pytest.raises(ValueError,match='existing template main'):
        tools.initialize(tmp_path,'project',template='template',template_source='test',template_version='1')
    assert not (tmp_path/'project').exists()


def test_path_escape_and_build_in_source_rejected(tmp_path):
    tools.initialize(tmp_path,'project')
    with pytest.raises(ValueError,match='workspace'):tools.initialize(tmp_path,'../outside')
    with pytest.raises(ValueError,match='separate'):tools.build(tmp_path,'project','project/build')
    with pytest.raises(ValueError,match='workspace'):tools.bind(tmp_path,'project','../outside','copy.csv')


def test_resource_binding_is_real_and_detects_drift(tmp_path):
    custom_project(tmp_path)
    original=tmp_path/'data.csv';original.write_text('x,y\n1,2\n',encoding='utf-8')
    bound=tools.bind(tmp_path,'project','data.csv','assets/data.csv')
    assert bound['sha256']==sha(original)
    assert tools.preflight(tmp_path,'project')['status']=='passed'
    original.write_text('x,y\n1,3\n',encoding='utf-8')
    assert 'Changed or missing resource' in str(tools.preflight(tmp_path,'project')['issues'])
    with pytest.raises(ValueError,match='differs'):tools.bind(tmp_path,'project','data.csv','assets/data.csv')


@pytest.mark.parametrize('name',['extra.csv','extra.py','extra.json'])
def test_unbound_input_in_arbitrary_directory_fails(tmp_path,name):
    project=custom_project(tmp_path);(project/'unusual').mkdir();(project/'unusual'/name).write_text('input',encoding='utf-8')
    report=tools.preflight(tmp_path,'project')
    assert report['status']=='failed' and 'Unbound' in str(report['issues'])


def test_missing_include_cycle_citation_and_duplicate_label(tmp_path):
    project=custom_project(tmp_path,r'\documentclass{article}\begin{document}\input{child}\cite{missing}\label{a}\label{a}\end{document}')
    (project/'child.tex').write_text(r'\input{main}',encoding='utf-8')
    report=tools.preflight(tmp_path,'project')
    assert 'Cyclic TeX includes' in report['issues']
    assert 'Duplicate TeX labels' in report['issues']
    assert 'Citation key has no inline bibliography item' in report['issues']


def test_external_bibliography_and_prohibited_commands_blocked(tmp_path):
    custom_project(tmp_path,r'\documentclass{article}\begin{document}\openout1=other\bibliography{data}\end{document}')
    report=tools.preflight(tmp_path,'project')
    assert any('bibliography requires' in item for item in report['issues'])
    assert 'Prohibited TeX execution/file command' in report['issues']
    report=tools.build(tmp_path,'project','blocked')
    assert report['status']=='failed' and not report['formal_approval']
    assert not (tmp_path/'blocked/artifacts').exists()
    assert (tmp_path/'blocked/build-check.json').is_file()


def test_logged_timeout_and_spawn_failure_keep_stdout_stderr(tmp_path,monkeypatch):
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args[0],1,output=b'before timeout',stderr=b'diagnostic')
    monkeypatch.setattr(tools.subprocess,'run',timeout)
    with pytest.raises(RuntimeError,match='timeout'):
        tools.run_logged(['fixture'],tmp_path,'timed',timeout=1)
    assert (tmp_path/'timed-stdout.log').read_bytes()==b'before timeout'
    assert json.loads((tmp_path/'timed-result.json').read_text())['status']=='timeout'
    def missing(*args,**kwargs):raise FileNotFoundError('missing test tool')
    monkeypatch.setattr(tools.subprocess,'run',missing)
    with pytest.raises(RuntimeError,match='missing test tool'):
        tools.run_logged(['fixture'],tmp_path,'missing',timeout=1)
    assert (tmp_path/'missing-command.json').is_file() and (tmp_path/'missing-stderr.log').is_file()


def test_doctor_missing_engine_blocks_without_installing(tmp_path):
    report=tools.doctor(tmp_path/'diagnostics',compiler=tmp_path/'missing.exe')
    assert report['status']=='blocked' and not report['downloaded']
    assert report['issues'] and (tmp_path/'diagnostics/doctor.json').is_file()


def test_actual_cached_compilation_and_all_page_validation(tmp_path):
    custom_project(tmp_path)
    before=tools.inventory(tmp_path/'project')
    result=tools.build(tmp_path,'project','attempt')
    assert result['status']=='passed',result
    assert result['page_count']==2 and not result['formal_approval']
    assert tools.inventory(tmp_path/'project')==before
    assert (tmp_path/'attempt/pdf-check/page-0002.png').is_file()
    assert tools.validate(tmp_path,'project','attempt')['status']=='passed'
    with pytest.raises(FileExistsError):tools.build(tmp_path,'project','attempt')
    (tmp_path/'attempt/pdf-check/page-0002.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='artifacts or logs'):
        tools.validate(tmp_path,'project','attempt')


def test_real_compile_failure_retains_complete_logs(tmp_path):
    custom_project(tmp_path,r'\documentclass{article}\begin{document}\UndefinedProbeCommand\end{document}')
    report=tools.build(tmp_path,'project','failed-attempt')
    assert report['status']=='failed'
    assert (tmp_path/'failed-attempt/compile-1-command.json').is_file()
    assert (tmp_path/'failed-attempt/compile-1-stdout.log').is_file()
    assert (tmp_path/'failed-attempt/compile-1-stderr.log').is_file()
    assert (tmp_path/'failed-attempt/source/main.tex').is_file()
    assert not report['formal_approval']


def test_no_arbitrary_source_formal_export_option():
    result=subprocess.run([sys.executable,'-m','modelcrew.latex_tools','export','--source','fake'],capture_output=True,text=True)
    assert result.returncode!=0
    assert '--build-id' in result.stderr and '--project-id' in result.stderr

def test_actual_compiler_warning_cannot_be_allowed_by_reason(tmp_path):
    custom_project(tmp_path,r'\documentclass{article}\begin{document}\hbox to 1pt{This intentionally overflows its box}\end{document}')
    result=tools.build(tmp_path,'project','warnings')
    assert result['status']=='failed' and not result['formal_approval']
    check=json.loads((tmp_path/'warnings/compiler-check.json').read_text(encoding='utf-8'))
    assert any('Overfull' in line for line in check['findings'])
    assert check['warning_exceptions']==[]
    with pytest.raises(ValueError,match='successful probe'):
        tools.validate(tmp_path,'project','warnings')


def test_initialized_guidance_is_frozen_and_tamper_blocks(tmp_path):
    tools.initialize(tmp_path,'project')
    frozen=tmp_path/'project/collaboration-guidance.json'
    assert frozen.is_file()
    with frozen.open('ab') as stream:stream.write(b'tamper')
    with pytest.raises(ValueError,match='Frozen'):
        tools.preflight(tmp_path,'project')


def test_existing_export_adapter_preserves_command_failure_logs(tmp_path,monkeypatch):
    from scripts import export_approved_paper as export
    def fail(source,output,pandoc,compiler,attempt_id):
        output.mkdir()
        export.save(output/'build-attempt.json',{'attempt_id':attempt_id})
        (output/'build').mkdir()
        tools.run_logged([sys.executable,'-c','import sys; print("failure evidence"); sys.exit(7)'],output/'build','compiler')
    monkeypatch.setattr(export,'_build',fail)
    with pytest.raises(RuntimeError):export.build(tmp_path,tmp_path/'output')
    assert (tmp_path/'output/build/compiler-stdout.log').read_bytes().strip()==b'failure evidence'
    assert json.loads((tmp_path/'output/build-error.json').read_text(encoding='utf-8'))['status']=='failed'
    original=sha(tmp_path/'output/build-error.json')
    with pytest.raises(FileExistsError):export.build(tmp_path,tmp_path/'output')
    assert sha(tmp_path/'output/build-error.json')==original


def test_registered_export_uses_existing_workflow_gates(monkeypatch):
    from modelcrew import workflow
    calls=[]
    class Workflow:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def export_assembly(self,project,build_id,**kwargs):
            calls.append((project,build_id,kwargs))
            raise ValueError('Existing assembly approvals missing')
    monkeypatch.setattr(workflow,'Workflow',Workflow)
    with pytest.raises(ValueError,match='approvals missing'):
        tools.export_registered('registered-project','registered-build','export-request','test-operator')
    assert calls==[('registered-project','registered-build',{'request_id':'export-request','actor':'test-operator'})]


def test_chinese_font_is_local_snapshot_with_explicit_file_mapping(tmp_path):
    font=tmp_path/'local-font.ttf';font.write_bytes(b'font identity fixture; not compiled')
    result=tools.initialize(tmp_path,'zh',cjk_font=font)
    assert result['template']['local_font']['sha256']==sha(font)
    assert (tmp_path/'zh/fonts/cjk-font.ttf').read_bytes()==font.read_bytes()
    text=(tmp_path/'zh/main.tex').read_text(encoding='utf-8')
    assert 'Path=fonts/' in text and '{cjk-font.ttf}' in text
    assert '{fonts/cjk-font.ttf}' not in text
    assert 'NEXUSMORE_CJK_FONT' not in text


def test_export_missing_dependency_keeps_early_failure_record(tmp_path,monkeypatch):
    from scripts import export_approved_paper as export
    def unavailable(*args,**kwargs):
        raise RuntimeError('Compiler not installed; no download attempted')
    monkeypatch.setattr(export,'discover_tool',unavailable)
    with pytest.raises(RuntimeError,match='not installed'):
        export.build(tmp_path/'source',tmp_path/'early-failure')
    error=json.loads((tmp_path/'early-failure/build-error.json').read_text(encoding='utf-8'))
    assert error['status']=='failed' and 'not installed' in error['error']
    assert not list((tmp_path/'early-failure').glob('*.pdf'))
