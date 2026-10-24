"""M4 canary-based diagnostics and in-memory retention acceptance.

Business output (UI previews and explicit CLI JSON/XLSX) intentionally contains
source values. Only diagnostic logs/stderr are scanned for disclosure here.
"""
from __future__ import annotations

import builtins
from io import BytesIO
import io
import json
import logging
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
import warnings

from openpyxl import Workbook
import pytest
from streamlit.testing.v1 import AppTest

import app as ui
import sheetcheck.ui_state as state
import sheetcheck.ui_views as views
from sheetcheck.errors import InputError
from sheetcheck.models import APP_VERSION, FileSpec, Mapping, Rules, Side
from sheetcheck.readers import read_source
from sheetcheck.ui_state import InputSelection, Workflow

ROOT = Path(__file__).resolve().parents[1]
CANARIES = ("SC_M4_ID_A7B93", "976431.29", "SC_M4_PRIVATE_ROW_C1F8",
            "SC_M4_CUSTOMER_FILE_E649.csv", "SC_M4_CUSTOMER_FILE_E649.xlsx")
CSV = f"id,amount,note\n{CANARIES[0]},{CANARIES[1]},{CANARIES[2]}\n".encode()
SECRET_ERROR = " | ".join(CANARIES)
RULES = Rules(period="fictional-M4", same_currency_confirmed=True, same_period_confirmed=True)


def assert_private(text):
    for canary in CANARIES:
        assert canary not in text
    assert "Traceback" not in text


def assert_safe_logs(caplog):
    assert_private(caplog.text)
    application_records = [record for record in caplog.records if record.name == "sheetcheck.ui"]
    for record in application_records:
        assert re.fullmatch(r"phase=[A-Z_]+ code=[A-Z_]+ version=" + re.escape(APP_VERSION), record.getMessage())
        assert record.exc_info is None
        assert record.stack_info is None
    return application_records


def configured_workflow(data=CSV, filename=CANARIES[3]):
    workflow = Workflow()
    workflow.sync_inputs({side: InputSelection(data, FileSpec(filename, side)) for side in Side})
    for side in Side:
        workflow.get_source(side)
    workflow.configure({side: Mapping(1, 2) for side in Side}, RULES)
    return workflow


def fresh_uploaded_app():
    page = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    for uploader in page.file_uploader:
        uploader.set_value((CANARIES[3], CSV, "text/csv"))
    page.run()
    assert not page.exception
    for key in ("order_id", "payment_id"):
        page.selectbox(key=key).set_value(1)
    for key in ("order_amount", "payment_amount"):
        page.selectbox(key=key).set_value(2)
    page.text_input(key="period").set_value("fictional-M4")
    page.checkbox(key="confirm_currency").set_value(True)
    page.checkbox(key="confirm_period").set_value(True)
    page.run()
    assert not page.exception
    return page


def fail_with_private_data(*args, **kwargs):
    raise RuntimeError(SECRET_ERROR)


def test_normal_ui_flow_has_no_business_diagnostics(caplog, capsys):
    caplog.set_level(logging.ERROR)
    page = fresh_uploaded_app()
    page.button(key="run_reconciliation").click().run()
    page.button(key="prepare_report").click().run()
    assert not page.exception
    result = page.session_state["workflow"].result
    assert result.records[0].id == CANARIES[0]  # positive control: data was handled
    assert result.records[0].order_minor == 97643129
    assert page.session_state["workflow"].report_bytes
    assert_safe_logs(caplog)
    assert_private(capsys.readouterr().err)


@pytest.mark.parametrize("name,data,code", [
    (CANARIES[3], CSV + b'"unclosed', "CSV_PARSE_ERROR"),
    (CANARIES[4], b"PK\x03\x04" + SECRET_ERROR.encode(), "XLSX_INVALID"),
])
def test_actual_bad_uploads_log_only_stable_codes(name, data, code, caplog, capsys):
    caplog.set_level(logging.ERROR)
    page = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    page.file_uploader[0].set_value((name, data, "application/octet-stream")).run()
    assert not page.exception
    assert any(code in error.value for error in page.error)
    records = assert_safe_logs(caplog)
    assert records and all(record.getMessage().startswith("phase=IMPORT code=") for record in records)
    assert_private(capsys.readouterr().err)


@pytest.mark.parametrize("target,phase", [("read_source", "IMPORT"), ("validate", "RECONCILE"),
                                         ("reconcile", "RECONCILE"), ("export_xlsx", "EXPORT"),
                                         ("business_rows", "PAGE")])
def test_ui_dependency_exceptions_do_not_log_canaries(target, phase, monkeypatch, caplog, capsys):
    caplog.set_level(logging.ERROR)
    if target == "read_source":
        monkeypatch.setattr(state, target, fail_with_private_data)
        page = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        page.file_uploader[0].set_value((CANARIES[3], CSV, "text/csv")).run()
    else:
        page = fresh_uploaded_app()
        if target == "export_xlsx":
            page.button(key="run_reconciliation").click().run()
        monkeypatch.setattr(views if target == "business_rows" else state, target, fail_with_private_data)
        page.button(key="prepare_report" if target == "export_xlsx" else "run_reconciliation").click().run()
    assert not page.exception
    assert any(f"UI_{phase}_FAILED" in error.value for error in page.error)
    assert any(record.getMessage().startswith(f"phase={phase} code=UI_{phase}_FAILED ")
               for record in assert_safe_logs(caplog))
    assert_private("\n".join(error.value for error in page.error))
    assert_private(capsys.readouterr().err)
    assert page.session_state["workflow"].report_bytes is None


@pytest.mark.parametrize("phase", ["IMPORT", "RECONCILE", "EXPORT", "PAGE"])
def test_ui_error_boundary_never_formats_dependency_exception(phase, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    displayed = []
    monkeypatch.setattr(ui.st, "error", displayed.append)
    ui._show_error(RuntimeError(SECRET_ERROR), phase)
    assert len(assert_safe_logs(caplog)) == 1
    assert_private("\n".join(displayed))


def test_invalid_excel_date_library_warning_does_not_disclose_amount(caplog, capsys):
    workbook = Workbook()
    workbook.active.append(["id", "amount"])
    workbook.active.append([CANARIES[0], 97643129])
    workbook.active["B2"].number_format = "yyyy-mm-dd"
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        source = read_source(buffer.getvalue(), FileSpec(CANARIES[4], Side.ORDER))
    assert source.rows[0].cells[1].kind == "error"
    assert not caught
    assert_safe_logs(caplog)
    assert "97643129" not in capsys.readouterr().err


def test_stale_download_raises_only_safe_error_and_no_payload(caplog):
    workflow = configured_workflow()
    run_id = workflow.run().manifest.run_id
    workflow.prepare_report()
    workflow.invalidate()
    with pytest.raises(InputError, match="REPORT_STALE") as raised:
        ui._current_download(workflow, run_id)
    assert_private(str(raised.value))
    assert_safe_logs(caplog)


def test_unexpected_deferred_download_exception_has_safe_traceback(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    workflow = configured_workflow()
    monkeypatch.setattr(Workflow, "report_for_run", fail_with_private_data)
    with pytest.raises(InputError, match="UI_DOWNLOAD_FAILED") as raised:
        ui._current_download(workflow, "fictional-run-id")
    # Streamlit 1.66 formats the callback error in MediaFileStorageError. Both
    # the message and a normal Python chained traceback must be safe.
    formatted = "".join(traceback.format_exception(raised.value))
    for canary in CANARIES:
        assert canary not in formatted
    assert "RuntimeError" not in formatted
    assert len(assert_safe_logs(caplog)) == 1


@pytest.mark.parametrize("unexpected", [False, True])
def test_streamlit_deferred_manager_receives_only_sanitized_callback_errors(unexpected, monkeypatch, caplog):
    from streamlit.runtime import media_file_manager
    from streamlit.runtime.media_file_storage import MediaFileStorageError
    from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage

    monkeypatch.setattr(media_file_manager, "_get_session_id", lambda: "fictional-session")
    manager = media_file_manager.MediaFileManager(MemoryMediaFileStorage("/media"))
    workflow = configured_workflow()
    if unexpected:
        monkeypatch.setattr(Workflow, "report_for_run", fail_with_private_data)
    file_id = manager.add_deferred(lambda: ui._current_download(workflow, "fictional-run-id"),
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   "1.2.3", file_name="sheetcheck_fictional.xlsx")
    with pytest.raises(MediaFileStorageError) as raised:
        manager.execute_deferred(file_id)
    assert_private(str(raised.value))
    assert ("UI_DOWNLOAD_FAILED" if unexpected else "REPORT_STALE") in str(raised.value)
    for canary in CANARIES:
        assert canary not in "".join(traceback.format_exception(raised.value))
    assert_safe_logs(caplog)


def cli_command(path):
    return ["--order-file", str(path), "--payment-file", str(path), "--period", "fictional-M4",
            "--confirm-same-currency", "--confirm-same-period"]


def test_cli_normal_success_keeps_audit_output_separate_from_diagnostics(tmp_path):
    path = tmp_path / CANARIES[3]
    path.write_bytes(CSV)
    completed = subprocess.run([sys.executable, "-m", "sheetcheck", *cli_command(path)], capture_output=True, text=True)
    assert completed.returncode == 0
    assert CANARIES[0] in completed.stdout  # explicit JSON is business output, not logs
    assert json.loads(completed.stdout)["records"][0]["order_minor"] == 97643129
    assert_private(completed.stderr)


@pytest.mark.parametrize("name,data,code", [
    (CANARIES[3], CSV + b'"unclosed', "CSV_PARSE_ERROR"),
    (CANARIES[4], b"PK\x03\x04" + SECRET_ERROR.encode(), "XLSX_INVALID"),
])
def test_cli_bad_files_do_not_disclose_source_name_or_values(name, data, code, tmp_path):
    path = tmp_path / name
    path.write_bytes(data)
    completed = subprocess.run([sys.executable, "-m", "sheetcheck", *cli_command(path)], capture_output=True, text=True)
    assert completed.returncode == 2 and not completed.stdout
    assert completed.stderr.startswith(code + ":")
    assert_private(completed.stderr)


@pytest.mark.parametrize("target", ["read_source", "validate", "reconcile", "serialize", "export"])
def test_cli_unexpected_errors_are_redacted_before_any_success_json(target, tmp_path):
    path = tmp_path / CANARIES[3]
    path.write_bytes(CSV)
    code = """
import json, sys
import sheetcheck.__main__ as cli
import sheetcheck.report as report
secret, target, args = json.loads(sys.argv[1])
def fail(*a, **k): raise RuntimeError(secret)
if target == 'serialize': cli.json.dumps = fail
elif target == 'export': report.export_xlsx = fail
else: setattr(cli, target, fail)
sys.exit(cli.main(args))
"""
    args = cli_command(path) + (["--export-dir", str(tmp_path)] if target == "export" else [])
    completed = subprocess.run([sys.executable, "-c", code, json.dumps([SECRET_ERROR, target, args])], capture_output=True, text=True)
    assert completed.returncode == 2
    assert not completed.stdout
    assert completed.stderr.startswith("INTERNAL_ERROR:")
    assert_private(completed.stderr)
    assert sorted(p.name for p in tmp_path.iterdir()) == [CANARIES[3]]


@pytest.mark.parametrize("flag", ["--order-header", "--order-encoding", "--unknown-private-flag"])
def test_cli_argument_errors_do_not_echo_raw_values(flag):
    completed = subprocess.run([sys.executable, "-m", "sheetcheck", flag, SECRET_ERROR], capture_output=True, text=True)
    assert completed.returncode == 2
    assert not completed.stdout
    assert completed.stderr.startswith("CLI_ARGUMENTS:") and "--help" in completed.stderr
    assert_private(completed.stderr)


def test_cli_help_remains_available_after_redacted_argument_errors():
    completed = subprocess.run([sys.executable, "-m", "sheetcheck", "--help"], capture_output=True, text=True)
    assert completed.returncode == 0
    assert "--order-file" in completed.stdout and "--export-dir" in completed.stdout
    assert not completed.stderr


@pytest.mark.parametrize("input_format", ["csv", "xlsx"])
def test_core_workflow_never_opens_or_stages_business_files(input_format, monkeypatch):
    # Warm imports before monitoring. Runtime/dependency bytecode reads are not
    # business retention; every business operation below is rerun under guards.
    data, filename = CSV, CANARIES[3]
    if input_format == "xlsx":
        workbook = Workbook()
        workbook.active.append(["id", "amount", "note"])
        workbook.active.append([CANARIES[0], CANARIES[1], CANARIES[2]])
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()
        data, filename = buffer.getvalue(), CANARIES[4]
    configured_workflow(data, filename).run()
    warm = configured_workflow()
    warm.run()
    warm.prepare_report()

    def forbid(*args, **kwargs):
        raise AssertionError("Business workflow attempted disk I/O")

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", forbid)
        guard.setattr(io, "open", forbid)
        guard.setattr(Path, "open", forbid)
        guard.setattr(tempfile, "NamedTemporaryFile", forbid)
        guard.setattr(tempfile, "TemporaryFile", forbid)
        guard.setattr(tempfile, "mkstemp", forbid)
        workflow = configured_workflow(data, filename)
        workflow.run()
        workflow.prepare_report()
        assert workflow.report_bytes
        workflow.reset()
    assert all(selection is None for selection in workflow.selections.values())
    assert workflow.sources == {} and workflow.result is None
    assert workflow.report_bytes is None and workflow.report_name is None
    assert all(mapping is None for mapping in workflow.mappings.values())
    assert workflow.rules.period == ""


def test_distinct_sessions_never_share_private_sources_results_or_reports():
    first, second = configured_workflow(), Workflow()
    first.run()
    first.prepare_report()
    assert all(selection is None for selection in second.selections.values())
    assert not second.sources and second.result is None and second.report_bytes is None
    first.reset()
    assert not first.sources and first.result is None and first.report_bytes is None
