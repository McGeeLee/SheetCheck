"""M3 user-flow acceptance through Streamlit's actual widget test runner.

These tests upload fictional bytes, change real widget values, and inspect the
serialized tables sent to the browser.  Expected totals and source positions
are handwritten; no production formatting helpers generate the oracle.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from openpyxl import Workbook
import pytest
from streamlit.testing.v1 import AppTest

from sheetcheck.errors import ExportError
from sheetcheck.models import Rules, Side
from sheetcheck.report import audit_xlsx


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


def fresh_app():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    healthy(app)
    return app


def healthy(app):
    assert not app.exception, [exception.message for exception in app.exception]
    return app


def workflow(app):
    return app.session_state["workflow"]


def widget(app, key):
    for category in ("selectbox", "text_input", "number_input", "checkbox", "radio", "multiselect"):
        for element in getattr(app, category):
            if element.key == key:
                return element
    raise AssertionError(f"Widget {key!r} is absent")


def set_widget(app, key, value):
    widget(app, key).set_value(value)
    return healthy(app.run())


def displayed_frames(app):
    """Static dataframe protobufs omit IDs, even with a supplied Streamlit key.

    Locate previews in source-side order and check their source-position columns;
    the remaining result/detail tables retain their visible layout order.
    This also works for an empty result table with no serialized columns.
    """
    frames = [element.value for element in app.dataframe]
    sides = [side for side in Side if side in workflow(app).sources]
    previews = frames[:len(sides)]
    assert len(previews) == len(sides)
    assert all(not len(table) or "CSV物理行" in table.columns for table in previews)
    located = {f"{side}_preview": table for side, table in zip(sides, previews)}
    remaining = frames[len(sides):]
    if workflow(app).result is not None:
        assert remaining, "A successful run must display a result table"
        located["result_table"] = remaining[0]
        if len(remaining) > 1:
            assert "source_id" in remaining[1].columns
            located["source_detail"] = remaining[1]
    else:
        assert not remaining, "Stale results must not remain in browser tables"
    return located


def frame(app, key):
    return displayed_frames(app)[key]


def messages(app):
    return "\n".join(element.value for category in ("warning", "error", "info", "success", "markdown", "caption")
                     for element in getattr(app, category))


def confirm_rules(app):
    widget(app, "confirm_currency").set_value(True)
    widget(app, "confirm_period").set_value(True)
    return healthy(app.run())


def demo_run(*, export=False):
    app = fresh_app()
    app.button(key="load_demo").click().run()
    healthy(app)
    confirm_rules(app)
    assert not app.button(key="run_reconciliation").disabled
    healthy(app.button(key="run_reconciliation").click().run())
    assert workflow(app).result is not None
    if export:
        healthy(app.button(key="prepare_report").click().run())
        assert workflow(app).report_bytes
    return app


def csv_bytes(rows, headers=("id", "amount")):
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows([headers, *rows])
    return buffer.getvalue().encode("utf-8")


def uploaded_app(order_rows, payment_rows, *, headers=("id", "amount")):
    app = fresh_app()
    app.file_uploader[0].set_value(("orders.csv", csv_bytes(order_rows, headers), "text/csv"))
    app.file_uploader[1].set_value(("payments.csv", csv_bytes(payment_rows, headers), "text/csv"))
    healthy(app.run())
    for key, value in (("order_id", 1), ("order_amount", 2), ("payment_id", 1), ("payment_amount", 2)):
        widget(app, key).set_value(value)
    widget(app, "period").set_value("fictional-period")
    healthy(app.run())
    confirm_rules(app)
    return app


def assert_result_invalidated(app):
    state = workflow(app)
    assert state.result is None
    assert state.report_bytes is None
    assert state.report_name is None
    assert "result_table" not in displayed_frames(app)
    assert not app.download_button or all(button.disabled for button in app.download_button)


def test_empty_screen_cannot_run_and_discloses_local_session_limits():
    app = fresh_app()
    assert str(workflow(app).stage) == "EMPTY"
    assert app.button(key="run_reconciliation").disabled
    assert workflow(app).result is None
    assert len(app.file_uploader) == 2
    text = messages(app)
    assert "本机" in text or "本地" in text
    assert "刷新" in text


def test_demo_requires_confirmation_then_completes_search_trace_and_download():
    app = fresh_app()
    healthy(app.button(key="load_demo").click().run())
    assert not widget(app, "confirm_currency").value
    assert not widget(app, "confirm_period").value
    assert app.button(key="run_reconciliation").disabled
    assert len(frame(app, "order_preview")) == 8
    assert len(frame(app, "payment_preview")) == 6
    confirm_rules(app)
    healthy(app.button(key="run_reconciliation").click().run())
    result = workflow(app).result
    assert [(record.id, record.order_minor, record.payment_minor, record.delta_minor)
            for record in result.records] == [
                ("A001", 10000, 10000, 0), ("A007", 0, 0, 0),
                ("A002", 5000, 4900, -100), ("A003", 3000, None, None),
                ("A004", None, 4000, None),
            ]
    assert len(result.ledger) == 14
    assert result.manifest.status_counts["DATA_ISSUE"] == 6
    assert {metric.label: metric.value for metric in app.metric} == {
        "订单输入记录": "8", "收款输入记录": "6",
        "订单可核对金额 · CNY": "180.00", "收款可核对金额 · CNY": "189.00",
        "一致（配对）": "2", "金额差异（配对）": "1",
        "仅订单有（条）": "1", "仅收款有（条）": "1",
        "数据问题（源行）": "6", "空行跳过（源行）": "0",
    }
    assert list(frame(app, "result_table")["业务编号"]) == ["A001", "A007", "A002", "A003", "A004"]
    set_widget(app, "query", "A002")
    assert list(frame(app, "result_table")["业务编号"]) == ["A002"]
    record = next(record for record in result.records if record.id == "A002")
    set_widget(app, "detail_id", record.result_id)
    detail = frame(app, "source_detail")
    assert list(detail["原始行号"]) == [3, 3]
    assert list(detail["原始编号"]) == ["A002", "A002"]
    assert set(detail["source_id"]) == {record.order_source_id, record.payment_source_id}
    assert {str(value) for value in detail["金额（分）"]} == {"5000", "4900"}
    assert "人工复核" in messages(app)
    healthy(app.button(key="prepare_report").click().run())
    state = workflow(app)
    assert str(state.stage) == "EXPORTED"
    assert state.report_name.startswith("sheetcheck_") and state.report_name.endswith(".xlsx")
    audit_xlsx(state.report_bytes, state.result)
    assert [button.label for button in app.download_button] == ["下载核对报告"]
    # AppTest exercises the widget event; bytes are independently audited above.
    healthy(app.download_button[0].click().run())
    assert workflow(app).report_bytes == state.report_bytes


@pytest.mark.parametrize("key,value", [
    ("order_id", None), ("order_amount", None),
    ("payment_id", None), ("payment_amount", None),
    ("currency", "USD"), ("period", "other-period"),
    ("confirm_currency", False), ("confirm_period", False),
    ("order_header", 2), ("payment_header", 2),
    ("order_encoding", "utf-8"), ("payment_encoding", "utf-8"),
    ("order_delimiter", ";"), ("payment_delimiter", ";"),
])
def test_configuration_change_invalidates_old_result_and_download(key, value):
    app = demo_run(export=True)
    set_widget(app, key, value)
    assert_result_invalidated(app)


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize("change", ["content", "filename"])
def test_upload_replacement_invalidates_even_when_only_filename_changes(side, change):
    app = uploaded_app([("0001", "1.00")], [("0001", "1.00")])
    healthy(app.button(key="run_reconciliation").click().run())
    healthy(app.button(key="prepare_report").click().run())
    original_name = ("orders.csv", "payments.csv")[side]
    replacement_name = "renamed.csv" if change == "filename" else original_name
    data = csv_bytes([("0001", "2.00" if change == "content" else "1.00")])
    healthy(app.file_uploader[side].set_value((replacement_name, data, "text/csv")).run())
    assert_result_invalidated(app)


@pytest.mark.parametrize("side", [0, 1])
def test_removing_upload_invalidates_and_prevents_run(side):
    app = uploaded_app([("A", "1.00")], [("A", "1.00")])
    healthy(app.button(key="run_reconciliation").click().run())
    healthy(app.button(key="prepare_report").click().run())
    healthy(app.file_uploader[side].clear().run())
    assert_result_invalidated(app)
    assert app.button(key="run_reconciliation").disabled


@pytest.mark.parametrize("side", [0, 1])
def test_replacing_then_removing_demo_file_never_resurrects_old_sample(side):
    app = demo_run(export=True)
    healthy(app.file_uploader[side].set_value(("replacement.csv", csv_bytes([("NEW", "1")]), "text/csv")).run())
    assert_result_invalidated(app)
    healthy(app.file_uploader[side].clear().run())
    assert_result_invalidated(app)
    assert app.button(key="run_reconciliation").disabled
    assert ("order_preview", "payment_preview")[side] not in displayed_frames(app)


def test_unmapped_and_same_column_mapping_cannot_run():
    app = fresh_app()
    for index, name in enumerate(("orders.csv", "payments.csv")):
        app.file_uploader[index].set_value((name, csv_bytes([("0001", "1.00")]), "text/csv"))
    healthy(app.run())
    assert all(widget(app, key).value is None for key in ("order_id", "order_amount", "payment_id", "payment_amount"))
    assert "0001" in frame(app, "order_preview").to_string(index=False)
    assert "0001" in frame(app, "payment_preview").to_string(index=False)
    widget(app, "period").set_value("fictional")
    healthy(app.run())
    confirm_rules(app)
    assert app.button(key="run_reconciliation").disabled
    for key, value in (("order_id", 1), ("order_amount", 2), ("payment_id", 1), ("payment_amount", 2)):
        widget(app, key).set_value(value)
    healthy(app.run())
    assert not app.button(key="run_reconciliation").disabled
    # AppTest options are formatted labels: column 1 must not be selectable.
    assert not any(label.startswith("1:") for label in widget(app, "order_amount").options)
    assert widget(app, "order_amount").value == 2


@pytest.mark.parametrize("view,ids", [
    ("金额差异", ["A002"]), ("仅订单有", ["A003"]), ("仅收款有", ["A004"]),
])
def test_result_views_filter_without_invalidating_run(view, ids):
    app = demo_run(export=True)
    original = workflow(app).result
    report = workflow(app).report_bytes
    set_widget(app, "result_view", view)
    assert list(frame(app, "result_table")["业务编号"]) == ids
    assert workflow(app).result is original
    assert workflow(app).report_bytes == report


def test_problem_view_has_one_row_per_source_and_repair_guidance():
    app = demo_run()
    set_widget(app, "result_view", "数据问题")
    problem = frame(app, "result_table")
    assert len(problem) == 6
    assert "DUPLICATE_ID" in problem.to_string(index=False)
    assert "AMOUNT_FORMAT" in problem.to_string(index=False)
    first_issue = next(entry for entry in workflow(app).result.ledger if "DUPLICATE_ID" in entry.problem_codes)
    set_widget(app, "detail_id", first_issue.source_id)
    assert any("DUPLICATE_ID" in element.value and "当前版本不合并收款" in element.value for element in app.text)
    assert len(frame(app, "source_detail")) == 1
    set_widget(app, "query", "A005")
    assert len(frame(app, "result_table")) == 3


def test_pagination_transmits_only_current_hundred_and_search_resets_page():
    rows = [(f"A{number:04d}", "1.00") for number in range(1, 206)]
    app = uploaded_app(rows, rows)
    for key in ("order_preview", "payment_preview"):
        assert len(frame(app, key)) == 20
    healthy(app.button(key="run_reconciliation").click().run())
    first = frame(app, "result_table")
    assert list(first["业务编号"]) == [f"A{number:04d}" for number in range(1, 101)]
    assert len(widget(app, "detail_id").options) <= 101  # optional empty selection
    first_id = workflow(app).result.records[0].result_id
    set_widget(app, "detail_id", first_id)
    assert len(frame(app, "source_detail")) == 2
    set_widget(app, "page_number", 2)
    second = frame(app, "result_table")
    assert list(second["业务编号"]) == [f"A{number:04d}" for number in range(101, 201)]
    assert widget(app, "detail_id").value is None
    assert "source_detail" not in displayed_frames(app)
    set_widget(app, "page_number", 3)
    assert list(frame(app, "result_table")["业务编号"]) == [f"A{number:04d}" for number in range(201, 206)]
    set_widget(app, "query", "A0001")
    assert widget(app, "page_number").value == 1
    assert list(frame(app, "result_table")["业务编号"]) == ["A0001"]
    set_widget(app, "query", "NO-SUCH-ID")
    assert widget(app, "page_number").value == 1
    assert len(frame(app, "result_table")) == 0
    assert all(len(table.value) <= 100 for table in app.dataframe)


def test_status_filter_uses_browser_rows_and_resets_page_without_revoking_report():
    app = demo_run(export=True)
    result, report = workflow(app).result, workflow(app).report_bytes
    set_widget(app, "status_filter", ["金额差异", "仅订单有"])
    assert list(frame(app, "result_table")["业务编号"]) == ["A002", "A003"]
    assert list(frame(app, "result_table")["状态"]) == ["金额差异", "仅订单有"]
    set_widget(app, "status_filter", [])
    assert len(frame(app, "result_table")) == 0
    assert widget(app, "page_number").value == 1
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_custom_header_delimiter_and_mapping_complete_without_code_changes():
    app = fresh_app()
    payload = b"fictional;notice;only\nnote;id;amount\nx;000001;0.00\n"
    for index, filename in enumerate(("custom-orders.csv", "custom-payments.csv")):
        app.file_uploader[index].set_value((filename, payload, "text/csv"))
    healthy(app.run())
    for side in ("order", "payment"):
        widget(app, f"{side}_delimiter").set_value(";")
        widget(app, f"{side}_header").set_value(2)
    healthy(app.run())
    for side in ("order", "payment"):
        widget(app, f"{side}_id").set_value(2)
        widget(app, f"{side}_amount").set_value(3)
        preview = frame(app, f"{side}_preview")
        assert list(preview["原始行号"]) == ["3"]
        assert list(preview["CSV物理行"]) == ["3–3"]
        assert list(preview["2: id"]) == ["000001"]
    widget(app, "period").set_value("fictional")
    healthy(app.run())
    confirm_rules(app)
    healthy(app.button(key="run_reconciliation").click().run())
    result = workflow(app).result
    assert [(record.id, record.order_minor, record.payment_minor, record.delta_minor)
            for record in result.records] == [("000001", 0, 0, 0)]
    set_widget(app, "detail_id", result.records[0].result_id)
    details = frame(app, "source_detail")
    assert list(details["原始行号"]) == [3, 3]
    assert list(details["编号列号"]) == [2, 2]
    assert list(details["金额列号"]) == [3, 3]
    healthy(app.button(key="prepare_report").click().run())
    audit_xlsx(workflow(app).report_bytes, result)
    set_widget(app, "order_id", 3)
    assert_result_invalidated(app)


def test_single_sided_zero_is_visible_as_zero_and_missing_side_stays_missing():
    app = uploaded_app([("ORDER-ONLY", "0.00")], [("PAYMENT-ONLY", "0.00")])
    healthy(app.button(key="run_reconciliation").click().run())
    table = frame(app, "result_table")
    assert list(table["业务编号"]) == ["ORDER-ONLY", "PAYMENT-ONLY"]
    result = workflow(app).result
    assert [(row.order_minor, row.payment_minor, row.delta_minor) for row in result.records] == [(0, None, None), (None, 0, None)]
    # The browser table must not replace both missing values with numeric zero.
    assert "0.00" in table.to_string(index=False)
    money_columns = [column for column in table.columns if "金额" in column or "差额" in column]
    assert money_columns
    assert any(table[column].isna().any() or table[column].eq("").any() or table[column].eq("—").any()
               for column in money_columns)


def test_all_match_with_bad_rows_never_claims_everything_passed():
    app = uploaded_app([("A", "1.00"), ("B", "bad")], [("A", "1.00"), ("B", "2.00")])
    healthy(app.button(key="run_reconciliation").click().run())
    assert len(workflow(app).result.records) == 1
    assert workflow(app).result.manifest.status_counts["DATA_ISSUE"] == 2
    text = messages(app)
    assert "可核对部分一致，仍有数据问题" in text
    assert "全部通过" not in text


def test_file_error_retains_bytes_and_accepts_corrected_reupload():
    app = fresh_app()
    app.file_uploader[0].set_value(("broken.csv", b'id,amount\n"unclosed,1\n', "text/csv"))
    app.file_uploader[1].set_value(("payments.csv", csv_bytes([("A", "1")]), "text/csv"))
    healthy(app.run())
    assert app.error
    assert app.file_uploader[0].value.getvalue() == b'id,amount\n"unclosed,1\n'
    assert app.button(key="run_reconciliation").disabled
    healthy(app.file_uploader[0].set_value(("corrected.csv", csv_bytes([("A", "1")]), "text/csv")).run())
    assert not app.error
    for key, value in (("order_id", 1), ("order_amount", 2), ("payment_id", 1), ("payment_amount", 2)):
        widget(app, key).set_value(value)
    widget(app, "period").set_value("fictional")
    healthy(app.run())
    confirm_rules(app)
    healthy(app.button(key="run_reconciliation").click().run())
    assert len(workflow(app).result.records) == 1


def test_export_failure_retains_result_and_can_retry(monkeypatch):
    import sheetcheck.report as report_module
    import sheetcheck.ui_state as state_module

    app = demo_run()
    original = workflow(app).result

    def failed_export(*args, **kwargs):
        raise ExportError("EXPORT_TEST_FAILURE", "测试导出失败；请重试。")

    with monkeypatch.context() as patch:
        patch.setattr(report_module, "export_xlsx", failed_export)
        if hasattr(state_module, "export_xlsx"):
            patch.setattr(state_module, "export_xlsx", failed_export)
        healthy(app.button(key="prepare_report").click().run())
    assert workflow(app).result is original
    assert workflow(app).report_bytes is None
    assert app.error
    assert "EXPORT_TEST_FAILURE" in messages(app)
    assert len(frame(app, "order_preview")) == 8
    healthy(app.button(key="prepare_report").click().run())
    audit_xlsx(workflow(app).report_bytes, original)


def test_reset_clears_inputs_rules_result_report_and_widget_generation():
    app = uploaded_app([("A", "1.00")], [("A", "1.00")])
    healthy(app.button(key="run_reconciliation").click().run())
    healthy(app.button(key="prepare_report").click().run())
    keys = [upload.key for upload in app.file_uploader]
    healthy(app.button(key="reset").click().run())
    assert_result_invalidated(app)
    assert str(workflow(app).stage) == "EMPTY"
    assert all(selection is None for selection in workflow(app).selections.values())
    assert workflow(app).sources == {}
    assert all(mapping is None for mapping in workflow(app).mappings.values())
    assert workflow(app).rules == Rules()
    assert all(upload.value is None for upload in app.file_uploader)
    assert [upload.key for upload in app.file_uploader] != keys
    assert widget(app, "period").value == ""
    assert not widget(app, "confirm_currency").value
    assert not widget(app, "confirm_period").value
    assert not displayed_frames(app)
    assert app.button(key="run_reconciliation").disabled


def test_two_sessions_do_not_share_sources_result_or_report():
    first = demo_run(export=True)
    second = fresh_app()
    assert workflow(first) is not workflow(second)
    assert workflow(second).result is None
    assert workflow(second).report_bytes is None
    assert str(workflow(second).stage) == "EMPTY"
    healthy(second.button(key="load_demo").click().run())
    confirm_rules(second)
    healthy(second.button(key="run_reconciliation").click().run())
    assert workflow(first).result.manifest.run_id != workflow(second).result.manifest.run_id
    healthy(first.button(key="reset").click().run())
    assert workflow(second).result is not None


def test_excel_sheet_change_invalidates_old_result():
    book = Workbook()
    for index, title in enumerate(("First", "Second")):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = title
        sheet.append(["id", "amount"])
        sheet.append(["0001", index + 1])
    buffer = io.BytesIO()
    book.save(buffer)
    book.close()
    app = fresh_app()
    for index, name in enumerate(("orders.xlsx", "payments.xlsx")):
        app.file_uploader[index].set_value((name, buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    healthy(app.run())
    for key, value in (("order_sheet", "First"), ("payment_sheet", "First")):
        widget(app, key).set_value(value)
    healthy(app.run())
    for key, value in (("order_id", 1), ("order_amount", 2), ("payment_id", 1), ("payment_amount", 2)):
        widget(app, key).set_value(value)
    widget(app, "period").set_value("fictional")
    healthy(app.run())
    confirm_rules(app)
    healthy(app.button(key="run_reconciliation").click().run())
    healthy(app.button(key="prepare_report").click().run())
    set_widget(app, "order_sheet", "Second")
    assert_result_invalidated(app)
