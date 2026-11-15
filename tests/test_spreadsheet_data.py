"""Project-owned complete spreadsheet reads; no upstream reader or test imports."""
import json
from datetime import date
import pytest
from openpyxl import Workbook
from modelcrew.document_tools import read_spreadsheet, run, sha


def workbook(path):
    book = Workbook()
    sheet = book.active
    sheet.title = "observations"
    for index in range(8193):
        sheet.append([index + 0.125, index, "=B1+1" if index == 0 else None])
    extra = book.create_sheet("metadata")
    extra.append([date(2026, 1, 2), "source", None])
    book.save(path)
    book.close()


def test_full_read_preserves_first_last_rows_formula_and_other_sheets(tmp_path):
    path = tmp_path / "observations.xlsx"
    workbook(path)
    before = sha(path)
    data = read_spreadsheet(path, expected_rows={"observations": 8193, "metadata": 1})
    rows = data["sheets"][0]["rows"]
    assert len(rows) == 8193 and rows[0] == [0.125, 0, "=B1+1"]
    assert rows[-1][:2] == [8192.125, 8192]
    assert data["sheets"][1]["rows"][0][0].startswith("2026-01-02")
    assert data["complete"] and data["header_handling"] == "preserved_as_data"
    assert data["formula_values_recalculated"] is False and sha(path) == before


def test_count_mismatch_missing_sheet_and_size_limit_return_no_partial_success(tmp_path):
    path = tmp_path / "observations.xlsx"
    workbook(path)
    for options, message in [({"expected_rows": {"observations": 8192}}, "row count"),
                             ({"expected_rows": {"missing": 1}}, "missing"),
                             ({"max_cells": 100}, "max_cells")]:
        with pytest.raises(ValueError, match=message):
            read_spreadsheet(path, **options)


@pytest.mark.parametrize("options", [{"max_cells": True}, {"max_cells": 0},
    {"expected_rows": {"observations": True}}, {"expected_rows": {"observations": -1}}])
def test_invalid_read_limits_are_rejected_before_loading_a_file(options):
    with pytest.raises(ValueError):
        read_spreadsheet("missing.xlsx", **options)


def test_registered_read_is_distinct_from_preview_and_keeps_input(tmp_path):
    source = tmp_path / "observations.xlsx"
    workbook(source)
    original = sha(source)
    output = tmp_path / "complete-read"
    assert run("xlsx_read", source, output)["status"] == "passed"
    data = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    assert data["sheets"][0]["row_count"] == 8193 and data["complete"]
    assert sha(source) == original
    with pytest.raises(FileExistsError):
        run("xlsx_read", source, output)
