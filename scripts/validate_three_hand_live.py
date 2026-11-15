"""Live three-hand acceptance case. Never grants or simulates user approvals.

Prepare an explicitly synthetic LP baseline, invoke real modeling/M1 through
Workflow, then stop at the durable user model gate. Later hands must use the
same task after genuine, separately recorded user decisions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from modelcrew.collaboration import sha_file
from modelcrew.config import ROOT, model_environment
from modelcrew.contracts import validate, digest
from modelcrew.mathematics import validate_package

TASK = "production-allocation-live-20261114"
CASE = ROOT / "runs" / "acceptance" / TASK
GUIDANCE = (
    "这是枢模真实三手链路验收的合成连续生产配比问题，不是实际企业预测或旧赛题。"
    "现有契约与数学包是助手构造并明确暴露的未批准基线，请结合真实附件核对、补充而不是盲目照抄。"
    "采用Python，选择内置优化类lp资料，逐项确认线性、连续性、单位、非负与有界条件。"
    "基准与11个工时容量情景均独立重求解，保留原约束残差、目标回算、求解状态、"
    "二维顶点枚举交叉核验及合法原始对偶证书；不得虚构迭代轨迹、数值结果或用户确认。"
    "本步只形成可审阅方案并独立M1，不执行数值求解，不写论文，不批准模型。"
    "后续遵守三类各3张共9张有不同证据作用的候选图及至少8张正式图要求；"
    "所有PDF必须全页预览、检查并保留哈希，不能以P2文本审查冒充实际读图。"
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def prepare(recover=False):
    from openpyxl import Workbook
    if CASE.exists():
        expected={"input-data.json","problem-statement.md","production-input.xlsx"}
        if not recover or {p.name for p in CASE.iterdir()} != expected:
            raise ValueError("Acceptance case already exists; inspect before explicit recovery")
        previous=CASE/"preparation-attempt-001"; previous.mkdir()
        for name in sorted(expected): (CASE/name).rename(previous/name)
    else:
        CASE.mkdir(parents=True)
    data = {"synthetic": True, "products": ["A", "B"], "profit_cny_per_unit": [40, 30],
            "hours_per_unit": [2, 1], "material_kg_per_unit": [1, 2],
            "base_hours": 100, "base_material_kg": 80,
            "hours_scenarios": list(range(80, 121, 4)),
            "assumptions": ["continuous divisible production", "constant linear coefficients", "no demand limits or fixed costs"]}
    save(CASE/"input-data.json", data)
    statement = (
        "# 合成生产配比验收题（非真实企业数据）\n"
        "单个规划周期生产可分割的A、B两类产品，产量单位为标准单位，可为非负实数。\n"
        "A/B单位净收益分别40/30元，工时消耗分别2/1小时，原料消耗分别1/2千克。\n"
        "基准可用工时100小时、原料80千克。总收益最大化，不考虑需求上限、固定成本、整数或随机性。\n"
        "另外固定原料80千克，将工时设为80、84、88、92、96、100、104、108、112、116、120小时，逐情景重求解。\n"
        "附件production-input.xlsx的products表首行为字段名，后两行是A/B；resources表为容量；"
        "scenarios表是完整11项工时列表。所有值无缺失，不含公式，列名包含单位。JSON为同一数据副本。\n"
        "输出result.json应含基准产量、收益、原约束残差、求解真实状态、对偶可行性与间隙、"
        "独立二维顶点枚举交叉校验及每个情景的数据。不可行/无界/超时/数值失败必须区分。\n"
        "当前是方法审阅，禁止预填最优数值。后续候选图raw/process/result三类各3张，全部PNG/PDF/SVG，"
        "正式入文至少8幅，Python统一后端，全部PDF逐页检查，正文及选图分别待真实用户确认。\n"
    )
    (CASE/"problem-statement.md").write_text(statement, encoding="utf-8")
    wb=Workbook(); ws=wb.active; ws.title="products"
    for row in [["product","profit_cny_per_unit","hours_per_unit","material_kg_per_unit"],["A",40,2,1],["B",30,1,2]]: ws.append(row)
    ws=wb.create_sheet("resources")
    for row in [["resource","capacity","unit"],["labor",100,"hour"],["material",80,"kg"]]: ws.append(row)
    ws=wb.create_sheet("scenarios"); ws.append(["hours","material_kg"])
    for hours in data["hours_scenarios"]: ws.append([hours,80])
    wb.save(CASE/"production-input.xlsx")
    files=[("statement","problem-statement.md","problem_statement"),("table","production-input.xlsx","dataset"),("data","input-data.json","dataset")]
    sources=[{"id":key,"kind":"problem_statement" if key=="statement" else "reference","locator":str(CASE/name),"sha256":sha_file(CASE/name)} for key,name,_ in files]
    inputs=[{"id":"input"+str(i),"source_id":key,"path":str(CASE/name),"sha256":sha_file(CASE/name),"role":role} for i,(key,name,role) in enumerate(files)]
    parameters=[{"id":k,"value":v,"unit":u,"source_id":"data","origin":"given","derivation":None} for k,v,u in [
        ("profit_a",40,"CNY/unit"),("profit_b",30,"CNY/unit"),("hours_a",2,"hour/unit"),("hours_b",1,"hour/unit"),
        ("material_a",1,"kg/unit"),("material_b",2,"kg/unit"),("labor_capacity",100,"hour"),("material_capacity",80,"kg")]]
    checks=[]
    for key,desc,method,tol,unit in [
        ("feasibility","所有基准/情景的非负、工时及原料残差合格","逐行原约束回代；分别记录hour/kg/unit残差，阈值均1e-7对应单位",1e-7,"row-specific: hour/kg/unit"),
        ("objective","收益回算与输出一致","使用输入收益系数与产量重新点乘",1e-6,"CNY"),
        ("optimality","独立顶点枚举及原始对偶证书一致","枚举所有边界交点并筛原约束；核验非负对偶、A^T lambda>=profit以及绝对对偶间隙",1e-6,"CNY"),
        ("completeness","11项情景、9逻辑候选图和三格式完整","回读JSON和目录；每类至少3图，禁止伪造迭代轨迹；全页PDF审查另留证据",None,"boolean")]:
        checks.append({"id":key,"description":desc,"method":method,"tolerance":tol,"unit":unit,"evidence_required":"逐情景真实状态、原值与验证记录；不可把未执行写成通过","initial_status":"unknown"})
    contract={"schema_version":"1.0.0","problem":{"case_id":"SYNTHETIC-PRODUCTION-ALLOCATION","subproblem_id":"Q1","title":"合成连续生产配比与容量敏感性验证","scope":"单周期、2产品、2资源，基准及11工时情景；仅连续线性规划，非企业实际决策","objective":{"kind":"optimization","description":"在给定工时与原料容量内最大化净收益"}},
        "sources":sources,"inputs":inputs,"conventions":{"length_unit":"not applicable","time_unit":"hour","coordinate_system":"x_A,x_B为产品标准单位","time_origin":"一个规划周期，不模拟时间演化","direction":"净收益最大化","indexing":"A在前B在后；情景按工时升序"},
        "parameters":parameters,"variables":[{"id":"production","meaning":"A、B产量","unit":"unit","domain":"非负实数向量[2]"},{"id":"profit","meaning":"总净收益","unit":"CNY","domain":"非负实数"}],
        "assumptions":[{"id":"linear_divisible","statement":"可连续分割、单位系数常数，无需求上限/固定成本/随机性","source_id":"statement"}],
        "constraints":[{"id":"labor","expression":"2*x_A+x_B <= H","meaning":"工时消耗不超过该情景容量，基准H=100hour","check_id":"feasibility"},{"id":"material","expression":"x_A+2*x_B <= 80","meaning":"原料不超过80kg","check_id":"feasibility"},{"id":"nonnegative","expression":"x_A>=0 and x_B>=0","meaning":"连续可分割非负产量","check_id":"feasibility"}],
        "method":{"steps":["读取并交叉核对工作簿、JSON及题意，检查单位/缺失/维度","以负收益向量调用scipy.optimize.linprog(method=highs)，逐情景独立求解","检查真实状态与原约束、收益回算","使用二维边界交点枚举和合法对偶上界独立核验","由实际情景结果生成9项不同证据候选图及可复算JSON；固定图元数据保证字节复跑"],"root_selection":"不适用：不是求根或整数规划","allowed_equivalent_changes":["不改变变量域、约束、目标或检查的等价数值实现"],"requires_new_confirmation":["更改连续/整数域、输入、目标、约束或容差；扩大业务结论"]},
        "outputs":[{"id":"result","path":"result.json","format":"json","fields":[{"name":"production","shape":[2],"unit":"unit"},{"name":"profit","shape":[1],"unit":"CNY"}],"decimal_places":None}],"checks":checks,
        "risks":["合成小例不证明任意规模泛化","只在已给容量情景作重求解，影子价格不得无限外推","文本质检不替代全页PDF读图及用户确认"],"alternatives":["二维顶点枚举为独立交叉校验，不作为大规模算法承诺"]}
    symbols=[]
    for key,latex,meaning,unit,domain in [("xA","x_A","A产量","unit","nonnegative real"),("xB","x_B","B产量","unit","nonnegative real"),("z","z","净收益","CNY","real"),("pA","p_A","A单位收益","CNY/unit","40"),("pB","p_B","B单位收益","CNY/unit","30"),("hA","h_A","A工时系数","hour/unit","2"),("hB","h_B","B工时系数","hour/unit","1"),("mA","m_A","A原料系数","kg/unit","1"),("mB","m_B","B原料系数","kg/unit","2"),("H","H","工时容量","hour","80..120 scenario grid"),("M","M","原料容量","kg","80")]:
        symbols.append({"id":"sym:"+key,"latex":latex,"meaning":meaning,"unit":unit,"domain":domain,"shape":"scalar","first_definition":"全局符号说明","scope":"基准及全部情景"})
    equations=[]
    for key,tex,meaning,unit,ids in [("profit",r"z=p_Ax_A+p_Bx_B","总收益，求最大值","CNY",["z","pA","pB","xA","xB"]),("labor",r"h_Ax_A+h_Bx_B\le H","工时容量约束","hour",["hA","hB","xA","xB","H"]),("material",r"m_Ax_A+m_Bx_B\le M","原料容量约束","kg",["mA","mB","xA","xB","M"]),("domain",r"x_A\ge0,\quad x_B\ge0","非负连续变量域","unit",["xA","xB"])]:
        equations.append({"id":"eq:"+key,"latex":tex,"meaning":meaning,"lhs_dimension":unit,"rhs_dimension":unit,"evidence_type":"project_formalization","symbol_ids":["sym:"+x for x in ids],"assumption_ids":["asm:linear"],"required_symbol_units":{}})
    candidate={"id":"lp","decision":"selected","premises":["目标和约束线性","产量为连续变量","各行单位一致","原点可行且正资源系数给出有限上界"],"data":"合成工作簿与JSON，无统计样本","sources":["内置优化lp资料（本次运行须实际读取）"],"reason":"任务为连续线性规划，禁止擅自整数化或用启发式代替证书","complexity":"调用HiGHS；小例顶点交叉核验，不承诺通用固定耗时","risks":["状态错误或原约束残差超限需阻断"],"validation":["原约束回代","二维顶点枚举","对偶可行与间隙"],"fallback":"不可行/无界/数值失败分别报告并暂停；不回传末迭代作为最优解"}
    package={"schema_version":"1.0.0","method_selection":{"schema_version":"1.0.0","id":"method:production-lp","fingerprint":{"objective":"maximize deterministic linear profit","data":"synthetic fixed coefficients","domain":"continuous nonnegative two-dimensional"},"model":"两产品两资源连续线性规划","solver":"Python SciPy linprog/HiGHS + independent vertex and dual checks","selected_candidate_id":"lp","candidates":[candidate],"coverage_gap":"只覆盖合成小型LP，非通用企业决策或整数规划","conditions_evidence":"题意明示连续线性和正资源系数；模型尚待独立审查与用户批准"},
        "dossier":{"schema_version":"1.0.0","id":"math:production-lp","structure":"continuous_linear_program","problem_setting":{"scope":contract["problem"]["scope"],"inputs":"problem-statement.md, production-input.xlsx, input-data.json；完整数据和单位已说明","requested_conclusion":"基准及11情景最优可行产量与收益，并有独立数值证书；本步不执行"},"symbols":symbols,"assumptions":[{"id":"asm:linear","statement":"连续可分割、系数固定且线性、单周期无随机项","type":"given_scope","source":str(CASE/"problem-statement.md"),"impact":"不适用于整数件数、固定成本或需求不确定情形"}],"equations":equations,
        "derivations":[{"id":"derive:formulation","conditions":["单位收益/消耗与数量呈线性关系","连续非负产量"],"equation_ids":[e["id"] for e in equations],"steps":["单位收益乘产量逐产品求和得到总收益，单位CNY","工时与原料分别按每单位用量乘产量求和，不能将hour与kg跨行相加","各资源和不超过容量，最大化收益；调用最小化API时仅将目标取负"],"status":"derived","open_gaps":[]}],
        "propositions":[{"id":"prop:existence","conditions":["所有情景H>0且M=80kg","两产品工时系数严格为正","线性连续约束"],"equation_ids":["eq:labor","eq:material","eq:domain","eq:profit"],"steps":["原点满足全部约束，故非空","工时行与非负域推出x_A<=H/h_A、x_B<=H/h_B，因此有界","线性不等式交集闭，有限维闭有界可行域紧；连续目标在紧集取到最大值"],"status":"proved","open_gaps":[]}],"unproved_or_out_of_scope":["未声称唯一最优、未执行数值求解","未推断未采样情景的影子价格有效区间","无统计总体/真实企业结论"],"statistical_inference":"不适用：确定性合成数据，不生成置信区间"},
        "contract_links":[{"equation_id":e["id"],"role":"executable" if e["id"]!="eq:profit" else "explanatory","targets":[] if e["id"]=="eq:profit" else [{"group":"constraints","id":{"eq:labor":"labor","eq:material":"material","eq:domain":"nonnegative"}[e["id"]]}],"reason":"逐项映射；收益公式对应problem.objective及输出，不伪造约束目标"} for e in equations],
        "validation_plan":[{"id":"check:"+c["id"],"description":c["description"]+"；"+c["method"],"threshold":c["tolerance"],"unit":c["unit"],"evidence_kind":"structural" if c["id"]=="completeness" else "numerical"} for c in checks],"figures":[],"provenance":[{"path":str(CASE/name),"sha256":sha_file(CASE/name),"role":"新合成题目与数据；未引用历史批准"} for _,name,_ in files],"presentation":{"equation_spacing":"normal"}}
    validate(contract); validate_package(package,contract)
    save(CASE/"baseline-contract.json",contract); save(CASE/"baseline-mathematics.json",package)
    reads=["AGENTS.md","docs/hand-runtime.md","docs/scientific-figure-contract.md","src/modelcrew/resources/paper/workflow.json","src/modelcrew/resources/paper/writer-instructions.md","src/modelcrew/resources/paper/chinese-modeling-policy.json","src/modelcrew/resources/algorithms/index.md","src/modelcrew/resources/algorithms/knowledge/optimization.md"]
    save(CASE/"operator-preparation.json",{"task_id":TASK,"synthetic":True,"baseline_exposure":"Operator-authored baseline supplied; not blind modeling","real_user_approvals":0,"files":[{"path":n,"sha256":sha_file(ROOT/n)} for n in reads],"contract_sha256":digest(contract),"mathematics_sha256":digest(package)})
    return {"task_id":TASK,"case_directory":str(CASE),"status":"prepared_unapproved"}


def inspect_state(w):
    state=w.inspect(TASK)
    runs=w.db.execute("SELECT id,status,version,payload FROM mc_modeling_runs WHERE task_id=%s ORDER BY sequence",(TASK,)).fetchall()
    return {"task_id":TASK,"phase":state["task"]["phase"],"version":state["task"]["current_version"],"model_approved":state["task"]["model_approved"],"execution_created":state["execution"] is not None,"checkpoint_next":state["checkpoint_next"],"modeling_runs":[{"run_id":str(r["id"]),"status":r["status"],"version":r["version"],"folder":r["payload"]["folder"],"calls":r["payload"].get("calls",[]),"attempts":r["payload"].get("attempts",[])} for r in runs]}



def audit_user_gate():
    """Verify real-call provenance, cached recovery and refusals without approving."""
    from modelcrew.workflow import Workflow, WorkflowError
    from modelcrew.collaboration import CollaborationStore, Receipt
    from modelcrew.mathematics import snapshot as math_snapshot
    from modelcrew.modeling_hand import assert_m1
    def files(folder):
        return {str(p.relative_to(folder)):sha_file(p) for p in folder.rglob("*") if p.is_file()}
    with Workflow() as w:
        row=w.db.execute("SELECT * FROM mc_modeling_runs WHERE task_id=%s ORDER BY sequence DESC LIMIT 1",(TASK,)).fetchone()
        if row is None or row["status"] not in {"blocked","ready"}:
            raise ValueError("Audit requires a completed latest modeling/M1 attempt")
        folder=ROOT/row["payload"]["folder"]; before=files(folder)
        state=w.inspect(TASK); version=state["task"]["current_version"]
        assert not state["task"]["model_approved"] and state["execution"] is None
        store=CollaborationStore(folder/"records"); payload=row["payload"]
        receipt=store.load(Receipt,payload["receipt_sha256"])
        assert store.accept_review(receipt,payload["snapshot_sha256"])==payload["receipt_sha256"]
        assert receipt.status=="PASS"
        contracts=w.db.execute("SELECT content,sha256 FROM mc_contracts WHERE task_id=%s AND version=%s",(TASK,version)).fetchone()
        math=math_snapshot(w,TASK,version)
        primary={m["call_id"] for m in payload["calls"] if m["stage"]!="M1"}
        for meta in payload["calls"]:
            assert meta["status"]=="completed" and meta["http_status"]==200
            request_path=next(folder.rglob(meta["stage"]+"-"+meta["call_id"]+"-request.json"))
            request=json.loads(request_path.read_text(encoding="utf-8"))
            assert [message["role"] for message in request["messages"]]==["system","user"]
            assert request["response_format"]["type"]=="json_object"
            if meta["stage"]=="M1":
                assert meta["call_id"] not in primary
                packet=json.loads(request["messages"][1]["content"])
                assert "M1_feedback" not in packet and "messages" not in packet
                assert packet["nexusmore_guidance"]["read_only"]
        replay=w.run_modeling(TASK,version=row["base_version"],actor=row["actor"],request_id=row["request_id"],guidance=row["guidance"])
        assert replay["run_id"]==str(row["id"]) and files(folder)==before
        hand_count=w.db.execute("SELECT count(*) AS n FROM mc_hand_runs WHERE task_id=%s",(TASK,)).fetchone()["n"]
        refusals=[]
        for hand in ["coding","writing"]:
            try:
                w.start_hand(TASK,hand,version=version,actor="acceptance-operator",request_id="verify-unapproved-"+hand,guidance="Negative gate check; no approval was supplied")
            except WorkflowError as error:
                assert "explicit model approval" in str(error)
                refusals.append({"operation":"start_"+hand,"status":"refused","reason":str(error)})
            else: raise AssertionError("An unapproved hand started")
        assert w.db.execute("SELECT count(*) AS n FROM mc_hand_runs WHERE task_id=%s",(TASK,)).fetchone()["n"]==hand_count==0
        open_gate=None
        if row["status"]=="blocked":
            try: assert_m1(w,w.task(TASK))
            except WorkflowError as error: open_gate=str(error)
            else: raise AssertionError("Open model questions were bypassed")
        approved=w.db.execute("SELECT count(*) AS n FROM mc_events WHERE task_id=%s AND kind IN ('model_approve','result_approve')",(TASK,)).fetchone()["n"]
        assert approved==0
        calls=[]; history=[]; operations=[]
        for run in w.db.execute("SELECT id,status,payload FROM mc_modeling_runs WHERE task_id=%s ORDER BY sequence",(TASK,)).fetchall():
            root=ROOT/run["payload"]["folder"]
            history.append({"run_id":str(run["id"]),"status":run["status"],"attempts":run["payload"].get("attempts",[])})
            for meta_file in sorted(root.rglob("*-metadata.json")):
                meta=json.loads(meta_file.read_text(encoding="utf-8")); calls.append({"path":str(meta_file.relative_to(ROOT)),"sha256":sha_file(meta_file),**meta})
            for route in root.rglob("resource-routing.json"):
                routed=json.loads(route.read_text(encoding="utf-8")); operations += [{"route_path":str(route.relative_to(ROOT)),"route_sha256":sha_file(route),"tool":op["tool"],"status":op["status"],"returncode":op["returncode"],"input_sha256":op["input"]["sha256"]} for op in routed["operations"]]
        result={"schema_version":"1.0.0","date":"2026-11-14","milestone":"F6.6","task_id":TASK,"status":"independent_m1_passed_waiting_scope_clarification" if row["status"]=="blocked" else "independent_m1_passed_waiting_model_approval","runtime_modeling_status":row["status"],"version":version,"contract_sha256":contracts["sha256"],"mathematics_semantic_sha256":math["semantic_sha256"],"mathematics_package_sha256":math["package_sha256"],"modeling_run_id":str(row["id"]),"modeling_folder":str(folder.relative_to(ROOT)),"M1_receipt_sha256":payload["receipt_sha256"],"M1_snapshot_sha256":payload["snapshot_sha256"],"M1_checks":[c.model_dump(mode="json") for c in receipt.checks],"open_questions":payload.get("open_questions",[]),"actual_provider_calls":calls,"provider_call_count":len(calls),"actual_independent_reviews":sum(c["stage"]=="M1" for c in calls),"actual_routed_tool_operations":operations,"history":history,"cached_request_reused_without_calls_or_file_writes":True,"premature_hand_refusals":refusals,"open_questions_block_admission":open_gate,"real_user_approvals":approved,"hand_runs_created":hand_count,"execution_created":False,"all_F6_completed":False,"all_F6_6_completed":False,"formal_exports_created":False,"private_candidate_rebuilt_after_code_changes":False,"not_yet_validated":["live coding and P1/P2","actual user model/result/manuscript/figure approvals","live writing and W1","formal export/full-page visual check and independent W2","DeepSeek Harness host integration"]}
        save(CASE/"current-contract.json",contracts["content"]);save(CASE/"current-mathematics.json",math["content"])
    with Workflow() as w:
        restarted=w.resume(TASK)
        assert restarted["task"]["current_version"]==version and not restarted["task"]["model_approved"] and restarted["execution"] is None
        assert restarted["checkpoint_next"]==["model_gate"]
        result["database_reconnect_and_checkpoint_resume_preserved_gate"]=True
    old=json.loads((ROOT/"tmp/resource-routing-validation-20261114/protected-history-verification.json").read_text(encoding="utf-8"))
    assert all(sha_file(ROOT/item["path"])==item["sha256"] for item in old["files"])
    result["protected_history_hashes_verified"]=old["files"]
    save(CASE/"gate-validation.json",result)
    return {k:result[k] for k in ["task_id","status","runtime_modeling_status","version","provider_call_count","actual_independent_reviews","real_user_approvals","hand_runs_created"]}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("operation",choices=["prepare","modeling","status","audit"]); parser.add_argument("--request-id",choices=["production-modeling-v001","production-modeling-json-v002","production-modeling-scope-v003","production-modeling-guards-v004"],default="production-modeling-v001"); parser.add_argument("--recover-preparation",action="store_true"); args=parser.parse_args()
    if args.operation=="prepare": print(json.dumps(prepare(args.recover_preparation),ensure_ascii=False)); return
    if args.operation=="audit": print(json.dumps(audit_user_gate(),ensure_ascii=False)); return
    from modelcrew.workflow import Workflow
    with Workflow() as w:
        if args.operation=="modeling":
            config=model_environment()
            if not all(config.get(k) for k in ["MODELCREW_LLM_API_KEY","MODELCREW_LLM_MODEL","MODELCREW_LLM_BASE_URL"]): raise ValueError("Real provider configuration missing")
            w.setup()
            if w.db.execute("SELECT 1 FROM mc_tasks WHERE id=%s",(TASK,)).fetchone() is None:
                w.create(TASK,json.loads((CASE/"baseline-contract.json").read_text(encoding="utf-8")),project="three-hand-live-acceptance",executor_key="pending-code",math_package=json.loads((CASE/"baseline-mathematics.json").read_text(encoding="utf-8")))
            # Existing request IDs are idempotent; unknown transmissions must be inspected, not resent.
            prior=w.db.execute("SELECT base_version FROM mc_modeling_runs WHERE task_id=%s AND request_id=%s",(TASK,args.request_id)).fetchone()
            latest=w.db.execute("SELECT status,payload FROM mc_modeling_runs WHERE task_id=%s ORDER BY sequence DESC LIMIT 1",(TASK,)).fetchone()
            scope_repair=(args.request_id in {"production-modeling-scope-v003","production-modeling-guards-v004"} and latest is not None
                and latest["status"]=="needs_human" and "receipt_sha256" not in latest["payload"]
                and latest["payload"].get("attempts") and all(x["status"]=="STRUCTURE_FAIL" for x in latest["payload"]["attempts"]))
            if prior is None and latest is not None and latest["status"]!="failed" and not scope_repair:
                raise ValueError("New request allowed only after inspected terminal failure; never bypass unknown/review gates")
            version=prior["base_version"] if prior else w.task(TASK)["current_version"]
            guidance=GUIDANCE
            if args.request_id=="production-modeling-guards-v004":
                guidance += ("明确验收口径：基准单列记录，scenarios仍完整列11项（含100hour），这是重复容量的交叉一致性检查，不是12次独立实验。"
                    "result.json顶层production长度2与profit长度1沿用已声明字段，另加验证和情景字段属于默认实现选择，不需用户发明新schema。"
                    "对偶检查方向已由基线要求定义：lambda>=0、A^T lambda>=p，数值乘子须核对API符号后验证原式。"
                    "当前基线已结构通过且无需为风格改写；除实质缺口外优先edits=[]，但source_decisions必须完整逐字覆盖references.cards。"
                    "所有补丁必须带/contract/或/mathematics/前缀；proposal写入顶层proposal字段，禁止对/proposal打补丁。"
                    "以上为工程验收指导而非用户对模型的批准。")
            result=w.run_modeling(TASK,version=version,actor="acceptance-operator",request_id=args.request_id,guidance=guidance)
            save(CASE/(args.request_id+"-outcome.json"),result)
        state=inspect_state(w); save(CASE/"progress.json",state)
        print(json.dumps(state,ensure_ascii=False,default=str))


if __name__=="__main__": main()
