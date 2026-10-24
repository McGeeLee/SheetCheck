"""Fast actual-default boundary regressions; large cases run via the M4 script.

No lower limits are substituted. Real 10 MiB, 50k and 100 MiB cases remain
explicit isolated acceptance runs rather than inflating every pytest run.
"""
from __future__ import annotations

import json
import gc
from pathlib import Path
import subprocess
import sys
import weakref

import pytest

from sheetcheck import FileSpec, Side, read_source
from sheetcheck.errors import InputError
from scripts.acceptance_capacity import fixture


@pytest.mark.parametrize("case, expected_error", [
    ("csv_columns_exact", None), ("csv_columns_over", "COLUMN_LIMIT"),
    ("xlsx_columns_exact", None), ("xlsx_columns_over", "COLUMN_LIMIT"),
    ("xlsx_entries_exact", None), ("xlsx_entries_over", "XLSX_ZIP_ENTRY_LIMIT"),
    ("xlsx_ratio_exact", None), ("xlsx_ratio_over", "XLSX_COMPRESSION_RATIO"),
    ("xlsx_depth_exact", None), ("xlsx_depth_over", "XLSX_XML_DEPTH"),
])
def test_actual_default_boundaries(case, expected_error):
    data, generated_spec, _, _, _, measured = fixture(case)
    spec = FileSpec(generated_spec.filename, Side.ORDER)
    over = case.endswith("_over")
    if "entries" in case:
        assert measured["zip_entries"] == 2000 + int(over)
    if "ratio" in case:
        assert measured["max_member_compression_ratio"] == (4400 + int(over)) / 22
    if "depth" in case:
        assert measured["constructed_xml_depth"] == 128 + int(over)
    if expected_error:
        with pytest.raises(InputError) as caught:
            read_source(data, spec)
        assert caught.value.code == expected_error
    else:
        table = read_source(data, spec)
        assert len(table.rows) == 1
        assert len(table.headers) == (100 if "columns" in case else 2)


def test_benchmark_timeout_is_a_failed_json_record_not_a_success():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([
        sys.executable, str(root / "scripts" / "benchmark_export.py"),
        "--rows", "1", "--repeats", "1", "--timeout", "0.000000001",
    ], cwd=root, capture_output=True, text=True, timeout=10, check=False)
    assert completed.returncode == 1
    evidence = json.loads(completed.stdout)
    assert evidence["successful_trials"] == 0
    assert evidence["trials"][0]["status"] == "timeout"
    assert "median_core_seconds" not in evidence
    assert "target_assessment" not in evidence


def test_export_releases_workbook_before_mandatory_readback(monkeypatch):
    """Even with automatic cyclic GC disabled, readback must not overlap cells."""
    from sheetcheck import Mapping, Rules, validate, reconcile
    import sheetcheck.report as report

    rules = Rules(period="synthetic resource test", same_currency_confirmed=True,
                  same_period_confirmed=True)
    result = reconcile(*(validate(read_source(b"id,amount\nS1,1.00\n",
                      FileSpec("synthetic.csv", side)), Mapping(1, 2), rules)
                         for side in Side), rules)
    real_workbook, real_audit = report.Workbook, report.audit_xlsx
    workbook_refs, audit_calls = [], []

    def observe_workbook(*args, **kwargs):
        workbook = real_workbook(*args, **kwargs)
        workbook_refs.append(weakref.ref(workbook))
        return workbook

    def verify_release_then_really_audit(data, source):
        assert workbook_refs and all(reference() is None for reference in workbook_refs)
        audit_calls.append(True)
        real_audit(data, source)

    monkeypatch.setattr(report, "Workbook", observe_workbook)
    monkeypatch.setattr(report, "audit_xlsx", verify_release_then_really_audit)
    automatic_gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(2):
            assert report.export_xlsx(result).startswith(b"PK\x03\x04")
    finally:
        if automatic_gc_enabled:
            gc.enable()
    assert len(workbook_refs) == len(audit_calls) == 2
