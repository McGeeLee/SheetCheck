"""Explicit-save CLI contract, including refusal and partial-write cleanup."""
import json
import re

import pytest
from openpyxl import load_workbook

from sheetcheck import __main__ as cli
from sheetcheck import report
from sheetcheck.errors import ExportError
from sheetcheck.models import APP_VERSION


def test_default_cli_does_not_export_or_create_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def forbidden_export(*_args):
        raise AssertionError("Default JSON inspection must not export")

    monkeypatch.setattr(report, "export_xlsx", forbidden_export)
    assert cli.main(["--demo"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["manifest"]["summaries"]["order"]["valid_total_minor"] == 18000
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []


def test_cli_export_roundtrips_and_keeps_stdout_json(tmp_path, monkeypatch, capsys):
    results = []
    original_reconcile = cli.reconcile

    def capture_result(*args):
        result = original_reconcile(*args)
        results.append(result)
        return result

    monkeypatch.setattr(cli, "reconcile", capture_result)
    assert cli.main(["--demo", "--export-dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    paths = list(tmp_path.iterdir())
    assert len(paths) == 1
    path = paths[0]
    assert re.fullmatch(r"sheetcheck_\d{8}T\d{6}Z_[A-Za-z0-9-]+\.xlsx", path.name)
    assert payload["manifest"]["run_id"] == results[0].manifest.run_id
    assert captured.err == f"code=EXPORTED stage=EXPORT version={APP_VERSION}\n"
    assert path.name not in captured.err
    assert str(tmp_path) not in captured.err
    report.audit_xlsx(path.read_bytes(), results[0])
    workbook = load_workbook(path, data_only=False)
    try:
        assert len(workbook.worksheets) == 5
        assert not workbook._external_links
        for sheet in workbook:
            for row in sheet:
                assert all(cell.data_type != "f" and cell.hyperlink is None for cell in row)
    finally:
        workbook.close()


def test_export_refuses_existing_file_without_success_json(tmp_path, monkeypatch, capsys):
    existing = tmp_path / "sheetcheck_existing.xlsx"
    existing.write_bytes(b"preserve this existing file")
    monkeypatch.setattr(report, "report_filename", lambda _result: existing.name)
    assert cli.main(["--demo", "--export-dir", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FILE_IO" in captured.err
    assert "EXPORTED" not in captured.err
    assert existing.read_bytes() == b"preserve this existing file"


def test_explicit_export_keeps_both_source_files_unchanged(tmp_path, capsys):
    sources = [tmp_path / "private_orders.csv", tmp_path / "private_payments.csv"]
    originals = [b"id,amount\n001,1.00\n", b"id,amount\n001,0.99\n"]
    for source, data in zip(sources, originals, strict=True):
        source.write_bytes(data)
    assert cli.main(["--order-file", str(sources[0]), "--payment-file", str(sources[1]),
                     "--period", "synthetic", "--confirm-same-currency", "--confirm-same-period",
                     "--export-dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["records"][0]["delta_minor"] == -1
    assert all(source.read_bytes() == data for source, data in zip(sources, originals, strict=True))
    assert all(source.name not in captured.err for source in sources)
    assert len(list(tmp_path.glob("sheetcheck_*.xlsx"))) == 1


def test_export_refuses_existing_symlink_without_modifying_target(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.csv"
    source.write_bytes(b"source data")
    target = tmp_path / "sheetcheck_existing.xlsx"
    target.symlink_to(source)
    monkeypatch.setattr(report, "report_filename", lambda _result: target.name)
    assert cli.main(["--demo", "--export-dir", str(tmp_path)]) == 2
    assert capsys.readouterr().out == ""
    assert target.is_symlink()
    assert source.read_bytes() == b"source data"


def test_export_does_not_create_missing_destination(tmp_path, capsys):
    missing = tmp_path / "private-client-directory"
    assert cli.main(["--demo", "--export-dir", str(missing)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FILE_IO" in captured.err
    assert missing.name not in captured.err
    assert not missing.exists()


def test_audit_rejection_cannot_save_or_emit_success(tmp_path, monkeypatch, capsys):
    def reject(_result):
        raise ExportError("EXPORT_AUDIT", "报告回读审计失败。")

    monkeypatch.setattr(report, "export_xlsx", reject)
    assert cli.main(["--demo", "--export-dir", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "EXPORT_AUDIT" in captured.err
    assert "EXPORTED" not in captured.err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure,expected_code", [(OSError, 2), (KeyboardInterrupt, 130)])
def test_failed_or_cancelled_write_removes_only_its_partial_report(tmp_path, monkeypatch, capsys,
                                                                  failure, expected_code):
    existing = tmp_path / "preserve.csv"
    existing.write_bytes(b"existing source")

    def fail_sync(_descriptor):
        raise failure()

    monkeypatch.setattr(cli.os, "fsync", fail_sync)
    assert cli.main(["--demo", "--export-dir", str(tmp_path)]) == expected_code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "EXPORTED" not in captured.err
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_bytes() == b"existing source"


def test_write_cleanup_preserves_concurrently_replaced_file(tmp_path, monkeypatch):
    destination = tmp_path / "report.xlsx"

    def replace_then_fail(_descriptor):
        destination.unlink()
        destination.write_bytes(b"another writer's file")
        raise OSError()

    monkeypatch.setattr(cli.os, "fsync", replace_then_fail)
    with pytest.raises(OSError):
        cli._write_report(tmp_path, destination.name, b"audited bytes")
    assert destination.read_bytes() == b"another writer's file"
