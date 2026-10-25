"""Use real widgets to recover from sheet selection, filtering and paging.

All inputs are fictional in-memory files. View controls must not change the
audited run or report; replacing inputs and resetting must revoke both.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
import pytest

from sheetcheck.models import Side
from test_app import (assert_result_invalidated, confirm_rules, csv_bytes,
                      demo_run, displayed_frames, frame, fresh_app, healthy,
                      messages, set_widget, uploaded_app, widget, workflow)


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ALL_BUSINESS_STATES = ["一致", "金额差异", "仅订单有", "仅收款有"]


def workbook_bytes(titles, *, hidden=()):
    book = Workbook()
    for index, title in enumerate(titles):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = title
        sheet.append(["id", "amount"])
        sheet.append([f"ROW-{index}", index + 1])
        if title in hidden:
            sheet.sheet_state = "hidden"
    content = io.BytesIO()
    book.save(content)
    book.close()
    return content.getvalue()


def xlsx_run():
    app = fresh_app()
    content = workbook_bytes(("Original",))
    for index, name in enumerate(("orders.xlsx", "payments.xlsx")):
        app.file_uploader[index].set_value((name, content, XLSX_MIME))
    healthy(app.run())
    for side in Side:
        widget(app, f"{side}_id").set_value(1)
        widget(app, f"{side}_amount").set_value(2)
    widget(app, "period").set_value("fictional-period")
    healthy(app.run())
    confirm_rules(app)
    healthy(app.button(key="run_reconciliation").click().run())
    healthy(app.button(key="prepare_report").click().run())
    assert workflow(app).report_bytes
    return app


def paginated_run():
    rows = [(f"A{number:04d}", "1.00") for number in range(1, 206)]
    app = uploaded_app(rows, rows)
    healthy(app.button(key="run_reconciliation").click().run())
    healthy(app.button(key="prepare_report").click().run())
    return app


@pytest.mark.parametrize("side,index", [(Side.ORDER, 0), (Side.PAYMENT, 1)])
def test_one_sheet_selection_matches_the_actual_preview_without_confirmation(side, index):
    app = fresh_app()
    healthy(app.file_uploader[index].set_value(("single.xlsx", workbook_bytes(("Only",)), XLSX_MIME)).run())
    assert not app.error
    assert widget(app, f"{side}_sheet").value == "Only"
    assert workflow(app).selections[side].spec.sheet == "Only"
    assert workflow(app).sources[side].spec.sheet == "Only"
    assert "ROW-0" in frame(app, f"{side}_preview").to_string(index=False)
    assert not widget(app, "confirm_currency").value
    assert not widget(app, "confirm_period").value
    assert app.button(key="run_reconciliation").disabled


@pytest.mark.parametrize("hide_second", [False, True])
def test_multiple_sheets_require_a_choice_without_presenting_a_read_failure(hide_second):
    app = fresh_app()
    content = workbook_bytes(("First", "Second"), hidden=("Second",) if hide_second else ())
    healthy(app.file_uploader[0].set_value(("multi.xlsx", content, XLSX_MIME)).run())
    assert widget(app, "order_sheet").value is None
    assert Side.ORDER not in workflow(app).sources
    assert not app.error
    assert "选择订单工作表" in messages(app)
    assert app.button(key="run_reconciliation").disabled
    # Hidden worksheets remain selectable; no new "visible-only" heuristic.
    set_widget(app, "order_sheet", "Second")
    assert not app.error
    assert workflow(app).sources[Side.ORDER].spec.sheet == "Second"
    assert "ROW-1" in frame(app, "order_preview").to_string(index=False)


def test_replacing_a_single_sheet_file_selects_its_new_sheet_and_revokes_old_report():
    app = xlsx_run()
    healthy(app.file_uploader[0].set_value(("orders.xlsx", workbook_bytes(("NewOnly",)), XLSX_MIME)).run())
    assert_result_invalidated(app)
    assert widget(app, "order_sheet").value == "NewOnly"
    assert workflow(app).sources[Side.ORDER].spec.sheet == "NewOnly"
    assert widget(app, "order_id").value is None
    assert widget(app, "order_amount").value is None
    assert not widget(app, "confirm_currency").value
    assert app.button(key="run_reconciliation").disabled


def test_replacing_with_a_multiple_sheet_file_does_not_reuse_an_existing_name():
    app = xlsx_run()
    content = workbook_bytes(("Original", "Another"))
    healthy(app.file_uploader[0].set_value(("orders.xlsx", content, XLSX_MIME)).run())
    assert_result_invalidated(app)
    assert widget(app, "order_sheet").value is None
    assert Side.ORDER not in workflow(app).sources
    assert not app.error
    assert "选择订单工作表" in messages(app)


def test_clear_filters_recovers_from_empty_search_without_recomputing_the_report():
    app = demo_run(export=True)
    result, report = workflow(app).result, workflow(app).report_bytes
    assert app.button(key="clear_filters").disabled
    set_widget(app, "query", "NO-SUCH-ID")
    assert len(frame(app, "result_table")) == 0
    assert not app.button(key="clear_filters").disabled
    healthy(app.button(key="clear_filters").click().run())
    assert widget(app, "query").value == ""
    assert list(frame(app, "result_table")["业务编号"]) == ["A001", "A007", "A002", "A003", "A004"]
    assert app.button(key="clear_filters").disabled
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_clear_filters_resets_view_status_and_detail_while_preserving_the_run():
    app = demo_run(export=True)
    result, report = workflow(app).result, workflow(app).report_bytes
    set_widget(app, "status_filter", ["金额差异"])
    set_widget(app, "result_view", "数据问题")
    set_widget(app, "query", "A005")
    issue_id = next(entry.source_id for entry in result.ledger if entry.problem_codes)
    set_widget(app, "detail_id", issue_id)
    assert "source_detail" in displayed_frames(app)
    healthy(app.button(key="clear_filters").click().run())
    assert widget(app, "result_view").value == "全部业务结果"
    assert widget(app, "status_filter").value == ALL_BUSINESS_STATES
    assert widget(app, "query").value == ""
    assert widget(app, "page_number").value == 1
    assert widget(app, "detail_id").value is None
    assert "source_detail" not in displayed_frames(app)
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_previous_next_page_respect_boundaries_and_clear_source_selection():
    app = paginated_run()
    result, report = workflow(app).result, workflow(app).report_bytes
    assert app.button(key="previous_page").disabled
    assert not app.button(key="next_page").disabled
    set_widget(app, "detail_id", result.records[0].result_id)
    healthy(app.button(key="next_page").click().run())
    assert widget(app, "page_number").value == 2
    assert widget(app, "detail_id").value is None
    assert "source_detail" not in displayed_frames(app)
    assert list(frame(app, "result_table")["业务编号"]) == [f"A{number:04d}" for number in range(101, 201)]
    healthy(app.button(key="next_page").click().run())
    assert widget(app, "page_number").value == 3
    assert len(frame(app, "result_table")) == 5
    assert app.button(key="next_page").disabled
    healthy(app.button(key="previous_page").click().run())
    assert widget(app, "page_number").value == 2
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_a_filter_from_the_last_page_returns_to_one_page_and_disables_both_arrows():
    app = paginated_run()
    result, report = workflow(app).result, workflow(app).report_bytes
    set_widget(app, "page_number", 3)
    set_widget(app, "query", "A0001")
    assert widget(app, "page_number").value == 1
    assert list(frame(app, "result_table")["业务编号"]) == ["A0001"]
    assert app.button(key="previous_page").disabled
    assert app.button(key="next_page").disabled
    healthy(app.button(key="clear_filters").click().run())
    assert len(frame(app, "result_table")) == 100
    assert not app.button(key="next_page").disabled
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_issue_rows_explain_the_problem_and_preserve_the_original_codes_and_values():
    app = demo_run(export=True)
    result, report = workflow(app).result, workflow(app).report_bytes
    set_widget(app, "result_view", "数据问题")
    table = frame(app, "result_table")
    assert len(table) == 6
    assert {"问题说明", "处理建议", "全部问题码", "原始金额", "原始行号"} <= set(table.columns)
    blocked = table[(table["业务编号"] == "A006") & (table["文件角色"] == "收款")]
    assert len(blocked) == 1
    assert blocked.iloc[0]["业务编号"] == "A006"
    assert blocked.iloc[0]["全部问题码"] == "BLOCKED_ID"
    assert blocked.iloc[0]["原始金额"] == "12.00"
    assert blocked.iloc[0]["问题说明"]
    assert blocked.iloc[0]["处理建议"]
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_new_inputs_and_reset_remove_view_controls_and_revoke_the_export():
    app = demo_run(export=True)
    set_widget(app, "query", "A002")
    healthy(app.file_uploader[0].set_value(("replacement.csv", csv_bytes([("NEW", "1")]), "text/csv")).run())
    assert_result_invalidated(app)
    assert not {"clear_filters", "previous_page", "next_page"}.intersection(button.key for button in app.button)
    healthy(app.button(key="reset").click().run())
    assert_result_invalidated(app)
    assert not {"clear_filters", "previous_page", "next_page"}.intersection(button.key for button in app.button)
    assert widget(app, "period").value == ""
    assert not app.button(key="start_demo").disabled
