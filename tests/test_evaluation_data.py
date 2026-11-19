"""H1 must reject contaminated splits, tampering and false readiness claims."""
import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from scripts.check_evaluation_data import DEFAULT_CATALOG, ROOT, check_catalog, checked_path, smoke_oracle


@pytest.fixture
def data_root(tmp_path):
    catalog = json.loads((ROOT / DEFAULT_CATALOG).read_text(encoding="utf-8"))
    paths = [DEFAULT_CATALOG, catalog["baseline"]["path"]]
    paths += [a["path"] for a in catalog["public_assets"]]
    paths += [c.get("path", c.get("source_reference")) for c in catalog["cases"]]
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path, catalog


def save(root, catalog):
    (root / DEFAULT_CATALOG).write_text(json.dumps(catalog), encoding="utf-8")


def test_preparation_does_not_claim_business_or_holdout_success():
    report = check_catalog()
    assert report["counts"] == {"public_smoke": 2, "development": 2, "holdout": 0}
    assert len(report["smoke_oracles"]) == 2
    assert report["research_inputs_registered"] == report["real_llm_runs"] == 0
    for field in ("holdout_ready", "H1_accepted", "H2_verified", "public_release_approved"):
        assert report[field] is False


@pytest.mark.parametrize("mutate, error", [
    (lambda c: c["cases"].append(copy.deepcopy(c["cases"][0])), "duplicate case"),
    (lambda c: c["cases"][2].update(family_id=c["cases"][0]["family_id"]), "family crosses"),
    (lambda c: c["cases"][0].update(eligible_for_research_solve_rate=True), "solve rate"),
    (lambda c: c["cases"][2].update(eligible_for_research_solve_rate=True), "solve rate"),
    (lambda c: c["cases"][2].update(exposure="unseen"), "development boundary"),
    (lambda c: c["cases"][0].update(license="unknown"), "provenance"),
    (lambda c: c["cases"][0].update(sha256="0"*64), "hash mismatch"),
    (lambda c: c["baseline"].update(sha256="0"*64), "hash mismatch"),
    (lambda c: c["holdout"].update(status="ready"), "holdout is not registered"),
    (lambda c: c["holdout"]["cases"].append("fabricated"), "holdout is not registered"),
    (lambda c: c.update(public_release_approved=True), "preparation is not"),
    (lambda c: c.update(real_llm_evaluation_executed=True), "preparation is not"),
    (lambda c: c["cases"][2].update(split="holdout"), "new frozen catalog"),
])
def test_boundary_mutations_fail_closed(data_root, mutate, error):
    root, catalog = data_root
    mutate(catalog)
    save(root, catalog)
    with pytest.raises(ValueError, match=error):
        check_catalog(root)


@pytest.mark.parametrize("relative", ["../secret.json", "/secret.json", "C:/secret.json", r"..\secret.json"])
def test_path_escape_rejected(tmp_path, relative):
    with pytest.raises(ValueError, match="path"):
        checked_path(tmp_path, relative)


def test_tampered_oracle_cannot_pass_even_after_rehash(data_root):
    root, catalog = data_root
    case = catalog["cases"][0]
    path = root / case["path"]
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected"]["balance_residual_m3"] = 1
    path.write_text(json.dumps(fixture), encoding="utf-8")
    case["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save(root, catalog)
    with pytest.raises(ValueError, match="oracle differs"):
        check_catalog(root)


def test_mass_balance_covers_overflow_and_shortage():
    result = smoke_oracle({"oracle": "integer_mass_balance", "input": {
        "initial_m3": 2, "capacity_m3": 5, "step_hours": 1,
        "inflow_m3": [10, 0], "demand_m3": [3, 8]}})
    assert result == {"end_storage_m3": [2, 0], "supplied_m3": [3, 2],
                      "shortage_m3": [0, 6], "spill_m3": [7, 0], "balance_residual_m3": 0}


def test_enumeration_includes_all_tied_optima():
    result = smoke_oracle({"oracle": "bounded_exhaustive_enumeration", "input": {
        "budget_hours": 1, "products": [
            {"name": "A", "hours": 1, "revenue_cny": 2, "max_units": 1},
            {"name": "B", "hours": 1, "revenue_cny": 2, "max_units": 1}]}})
    assert result["optimal_revenue_cny"] == 2
    assert result["optimal_allocations"] == [
        {"A": 0, "B": 1, "used_hours": 1, "slack_hours": 0},
        {"A": 1, "B": 0, "used_hours": 1, "slack_hours": 0}]


def test_series_length_mismatch_is_not_silently_truncated():
    with pytest.raises(ValueError, match="series length"):
        smoke_oracle({"oracle": "integer_mass_balance", "input": {
            "initial_m3": 0, "capacity_m3": 1, "step_hours": 1,
            "inflow_m3": [1, 1], "demand_m3": [1]}})
