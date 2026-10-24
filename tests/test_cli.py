import json
import subprocess
import sys
from io import BytesIO
from zipfile import ZipFile

from openpyxl import Workbook


def test_demo_is_recalculable_json_and_has_no_ui_import():
    # Check the CLI's own interpreter: AppTest legitimately imports Streamlit
    # into pytest's shared process before this test is executed.
    probe = """
import runpy
import sys
sys.argv = ["sheetcheck", "--demo"]
try:
    runpy.run_module("sheetcheck", run_name="__main__")
except SystemExit as exc:
    if exc.code not in (0, None):
        raise
assert not any(name == "streamlit" or name.startswith("streamlit.") for name in sys.modules)
"""
    completed = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["manifest"]["summaries"]["order"]["valid_total_minor"] == 18000
    assert len(payload["ledger"]) == 14
    assert len(payload["records"]) == 5


def test_cli_file_error_is_redacted_and_does_not_print_partial_success(tmp_path):
    secret = tmp_path / "secret-client-name.csv"
    command = [sys.executable, "-m", "sheetcheck", "--order-file", str(secret), "--payment-file", str(secret)]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 2
    assert not completed.stdout
    assert "FILE_IO" in completed.stderr
    assert "secret-client-name" not in completed.stderr


def test_custom_file_rules_need_confirmation(tmp_path):
    source = tmp_path / "example.csv"
    source.write_text("id,amount\nA,0\n")
    base = [sys.executable, "-m", "sheetcheck", "--order-file", str(source), "--payment-file", str(source),
            "--period", "synthetic"]
    rejected = subprocess.run(base, capture_output=True, text=True)
    assert rejected.returncode == 2 and not rejected.stdout
    accepted = subprocess.run(base + ["--confirm-same-currency", "--confirm-same-period"], capture_output=True, text=True)
    assert accepted.returncode == 0
    assert json.loads(accepted.stdout)["records"][0]["status"] == "EXACT_MATCH"


def test_nonfinite_xlsx_numeric_is_a_serializable_data_issue(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["id", "amount"])
    ws.append(["A", 12345])
    original = BytesIO()
    wb.save(original)
    wb.close()
    modified = BytesIO()
    with ZipFile(original) as source, ZipFile(modified, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b"<v>12345</v>", b"<v>1e309</v>")
            target.writestr(item, data)
    path = tmp_path / "nonfinite.xlsx"
    path.write_bytes(modified.getvalue())
    completed = subprocess.run([sys.executable, "-m", "sheetcheck", "--order-file", str(path),
                                "--payment-file", str(path), "--period", "synthetic",
                                "--confirm-same-currency", "--confirm-same-period"], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["records"] == []
    assert payload["ledger"][0]["amount_raw"] == {"type": "nonfinite_number", "read_value": "inf"}
    assert "AMOUNT_FORMAT" in payload["ledger"][0]["problem_codes"]
