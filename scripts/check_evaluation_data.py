"""Check H1 data integrity and smoke oracles; never run a model or approve H1."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = "configs/evaluation/data-catalog-1.0.0.json"


def checked_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("invalid catalog path")
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("catalog path escapes root")
    return path


def verify_hash(root, relative, expected):
    path = checked_path(root, relative)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"hash mismatch: {relative}")
    return path


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("oracle requires bounded nonnegative integers")
    return value


def smoke_oracle(fixture):
    data = fixture["input"]
    if fixture["oracle"] == "integer_mass_balance":
        storage = initial = integer(data["initial_m3"])
        capacity = integer(data["capacity_m3"], 1)
        if storage > capacity:
            raise ValueError("initial storage exceeds capacity")
        integer(data["step_hours"], 1)
        inflow, demand = data["inflow_m3"], data["demand_m3"]
        if not inflow or len(inflow) != len(demand) or len(inflow) > 10000:
            raise ValueError("invalid time series length")
        result = {k: [] for k in ("end_storage_m3", "supplied_m3", "shortage_m3", "spill_m3")}
        for incoming, needed in zip(inflow, demand, strict=True):
            incoming, needed = integer(incoming), integer(needed)
            available = storage + incoming
            spill = max(available - capacity, 0)
            available -= spill
            supply = min(available, needed)
            storage = available - supply
            for key, value in zip(result, (storage, supply, needed - supply, spill), strict=True):
                result[key].append(value)
        result["balance_residual_m3"] = initial + sum(inflow) - sum(result["supplied_m3"]) - sum(result["spill_m3"]) - storage
        return result
    if fixture["oracle"] == "bounded_exhaustive_enumeration":
        budget = integer(data["budget_hours"])
        products = data["products"]
        if not products or len(products) > 4:
            raise ValueError("invalid product count")
        names = [p["name"] for p in products]
        if any(not isinstance(n, str) or not n or n in {"used_hours", "slack_hours"} for n in names) or len(set(names)) != len(names):
            raise ValueError("invalid product names")
        combinations = 1
        for product in products:
            integer(product["hours"], 1)
            integer(product["revenue_cny"])
            combinations *= integer(product["max_units"]) + 1
        if combinations > 100000:
            raise ValueError("oracle search too large")
        best, solutions = -1, []
        for units in itertools.product(*(range(p["max_units"] + 1) for p in products)):
            used = sum(n * p["hours"] for n, p in zip(units, products, strict=True))
            if used > budget:
                continue
            value = sum(n * p["revenue_cny"] for n, p in zip(units, products, strict=True))
            allocation = dict(zip(names, units, strict=True), used_hours=used, slack_hours=budget-used)
            if value > best:
                best, solutions = value, [allocation]
            elif value == best:
                solutions.append(allocation)
        return {"optimal_revenue_cny": best, "optimal_allocations": solutions}
    raise ValueError("unknown smoke oracle")


def check_catalog(root=ROOT, catalog_relative=DEFAULT_CATALOG):
    root = Path(root).resolve()
    catalog_path = checked_path(root, catalog_relative)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog["schema_version"] != "1.0.0" or catalog["status"] != "draft_preparation_not_user_accepted":
        raise ValueError("unsupported preparation catalog")
    if catalog["public_release_approved"] is not False or catalog["real_llm_evaluation_executed"] is not False:
        raise ValueError("preparation is not release approval or real LLM evaluation")
    baseline = catalog["baseline"]
    verify_hash(root, baseline["path"], baseline["sha256"])
    for asset in catalog["public_assets"]:
        verify_hash(root, asset["path"], asset["sha256"])
    ids, families, input_hashes, checked = set(), {}, set(), []
    counts = {"public_smoke": 0, "development": 0, "holdout": 0}
    for case in catalog["cases"]:
        if case["id"] in ids:
            raise ValueError("duplicate case id")
        ids.add(case["id"])
        split = case["split"]
        if split not in counts:
            raise ValueError("unknown split")
        family = case["family_id"]
        if family in families and families[family] != split:
            raise ValueError("problem family crosses splits")
        families[family] = split
        if case["eligible_for_research_solve_rate"] is not False:
            raise ValueError("smoke or historical case cannot enter research solve rate")
        if split == "public_smoke":
            if case["tier"] != "smoke" or case["origin"] != "project_authored_synthetic" or case["license"] != "AGPL-3.0-only" or case["exposure"] != "public_reference_in_repository":
                raise ValueError("invalid public smoke provenance")
            fixture_path = verify_hash(root, case["path"], case["sha256"])
            if not fixture_path.is_relative_to(root / "examples/validation"):
                raise ValueError("smoke asset outside example directory")
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            if fixture["id"] != case["id"] or fixture["kind"] != "synthetic_smoke" or fixture["license"] != case["license"] or not fixture["statement"].strip() or not fixture["origin"].strip():
                raise ValueError("fixture identity or provenance mismatch")
            identity = hashlib.sha256(json.dumps(fixture["input"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if identity in input_hashes:
                raise ValueError("duplicate smoke input")
            input_hashes.add(identity)
            result = smoke_oracle(fixture)
            if result != fixture["expected"]:
                raise ValueError("smoke oracle differs from expected")
            checked.append({"id": case["id"], "oracle": "passed", "sha256": case["sha256"]})
        elif split == "development":
            if case["tier"] != "research" or case["status"] != "historical_reference_only" or case["input_registered"] is not False or case["exposure"] != "seen_in_development_with_external_references" or not case["coverage"] or not case["exposure_details"] or case["redistribution"] != "not_authorized_by_this_catalog":
                raise ValueError("invalid historical development boundary")
            if case["source_role"] == "historical_evidence":
                verify_hash(root, case["source_reference"], case["source_sha256"])
            elif case["source_role"] != "historical_navigation_only" or not checked_path(root, case["source_reference"]).is_file() or case["source_sha256"] is not None:
                raise ValueError("invalid historical navigation")
        else:
            raise ValueError("holdout admission requires a new frozen catalog version")
        counts[split] += 1
    if not counts["public_smoke"]:
        raise ValueError("missing smoke examples")
    holdout = catalog["holdout"]
    if holdout["status"] != "not_registered" or holdout["cases"] != [] or not holdout["blockers"]:
        raise ValueError("holdout is not registered; cannot claim readiness")
    return {"status": "passed", "scope": "H1 data preparation integrity only", "counts": counts,
            "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(), "smoke_oracles": checked,
            "research_inputs_registered": 0, "holdout_ready": False, "H1_accepted": False,
            "H2_verified": False, "real_llm_runs": 0, "public_release_approved": False,
            "blockers": holdout["blockers"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help="Repository-relative catalog path")
    parser.add_argument("--output", type=Path, help="New JSON report path; never overwrite")
    args = parser.parse_args()
    try:
        result = check_catalog(catalog_relative=args.catalog)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
