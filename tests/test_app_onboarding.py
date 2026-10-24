"""First-use guidance follows the real input and reconciliation state.

Use the same fictional uploads and actual widget runner as the M3 suite. These
checks focus on decisions a newcomer can make, not an exact copy of every label.
"""
from __future__ import annotations

import pytest

from sheetcheck.models import Side
from sheetcheck.ui_views import STATUS_LABELS
from sheetcheck.models import Status
from test_app import (assert_result_invalidated, confirm_rules, csv_bytes,
                      displayed_frames, frame, fresh_app, healthy, messages,
                      set_widget, uploaded_app, widget, workflow)


def pending_tasks(app):
    notices = [element.value for element in app.info
               if element.value.startswith("开始前还需完成：")]
    assert len(notices) == 1, "Incomplete inputs should have one actionable task list"
    return notices[0]


def practice_run(*, export=False):
    app = fresh_app()
    healthy(app.button(key="start_demo").click().run())
    confirm_rules(app)
    healthy(app.button(key="run_reconciliation").click().run())
    assert workflow(app).result is not None
    assert not any("准备好了" in element.value for element in app.success)
    if export:
        healthy(app.button(key="prepare_report").click().run())
        assert workflow(app).report_bytes
    return app


def test_first_open_explains_the_job_and_offers_a_safe_practice_entry():
    app = fresh_app()
    assert "订单和收款，哪里对不上？" in [title.value for title in app.title]
    text = messages(app)
    assert all(word in text for word in ("订单", "收款", "A002", "50.00", "49.00", "-1.00"))
    assert app.button(key="start_demo").label == "用虚构样例试一遍"
    assert not app.button(key="start_demo").disabled
    assert app.button(key="run_reconciliation").disabled
    tasks = pending_tasks(app)
    assert "上传订单表" in tasks and "上传收款表" in tasks
    assert "填写核对期间" in tasks
    sidebar_text = "\n".join(element.value for category in ("caption", "markdown", "info")
                             for element in getattr(app.sidebar, category))
    assert not any(code in sidebar_text for code in ("EMPTY", "IMPORTED", "MAPPED", "RECONCILED", "EXPORTED"))
    assert not displayed_frames(app)


def test_main_practice_entry_loads_examples_but_requires_the_users_confirmations():
    app = fresh_app()
    healthy(app.button(key="start_demo").click().run())
    assert len(frame(app, "order_preview")) == 8
    assert len(frame(app, "payment_preview")) == 6
    assert not widget(app, "confirm_currency").value
    assert not widget(app, "confirm_period").value
    assert workflow(app).result is None
    assert app.button(key="run_reconciliation").disabled
    tasks = pending_tasks(app)
    assert "确认两张表的币种相同" in tasks
    assert "确认两张表的期间相同" in tasks
    assert "上传订单表" not in tasks and "上传收款表" not in tasks
    assert "填写核对期间" not in tasks
    confirm_rules(app)
    assert not app.button(key="run_reconciliation").disabled
    assert any("准备好了" in element.value for element in app.success)
    assert not any(element.value.startswith("开始前还需完成：") for element in app.info)


def test_partial_import_tasks_only_request_missing_files_and_fields():
    app = fresh_app()
    healthy(app.file_uploader[0].set_value(("orders.csv", csv_bytes([("A", "1.00")]), "text/csv")).run())
    tasks = pending_tasks(app)
    assert "上传订单表" not in tasks
    assert "上传收款表" in tasks
    assert "选择订单编号列" in tasks and "订单金额列" in tasks
    # Selecting both fields completes that part without masking the absent side.
    widget(app, "order_id").set_value(1)
    widget(app, "order_amount").set_value(2)
    healthy(app.run())
    tasks = pending_tasks(app)
    assert "订单编号列" not in tasks and "订单金额列" not in tasks
    assert "上传收款表" in tasks
    assert app.button(key="run_reconciliation").disabled


def test_unreadable_file_is_a_repair_task_and_never_reported_ready():
    app = fresh_app()
    app.file_uploader[0].set_value(("broken.csv", b'id,amount\n"unclosed,1\n', "text/csv"))
    app.file_uploader[1].set_value(("payments.csv", csv_bytes([("A", "1")]), "text/csv"))
    healthy(app.run())
    assert app.error
    assert Side.ORDER not in workflow(app).sources
    tasks = pending_tasks(app)
    assert "修复订单表的读取问题" in tasks
    assert "上传订单表" not in tasks
    assert "修复收款表的读取问题" not in tasks
    assert not any("准备好了" in element.value for element in app.success)
    assert app.button(key="run_reconciliation").disabled
    healthy(app.file_uploader[0].set_value(("corrected.csv", csv_bytes([("A", "1")]), "text/csv")).run())
    assert not app.error
    tasks = pending_tasks(app)
    assert "修复订单表的读取问题" not in tasks
    assert "选择订单编号列" in tasks


@pytest.mark.parametrize("key,view,expected_rows", [
    ("review_issues", "数据问题", 6),
    ("review_differences", "金额差异", 1),
])
def test_result_shortcuts_clear_hidden_filters_without_changing_the_report(key, view, expected_rows):
    app = practice_run(export=True)
    result, report = workflow(app).result, workflow(app).report_bytes
    assert not any(element.value.startswith("开始前还需完成：") for element in app.info)
    assert not any("准备好了" in element.value for element in app.success)
    set_widget(app, "status_filter", ["一致"])
    set_widget(app, "query", "NO-SUCH-ID")
    assert len(frame(app, "result_table")) == 0
    healthy(app.button(key=key).click().run())
    assert widget(app, "result_view").value == view
    assert widget(app, "query").value == ""
    assert widget(app, "status_filter").value == [STATUS_LABELS[status] for status in tuple(Status)[:4]]
    assert widget(app, "page_number").value == 1
    assert len(frame(app, "result_table")) == expected_rows
    if view == "金额差异":
        assert list(frame(app, "result_table")["业务编号"]) == ["A002"]
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_result_shortcut_resets_a_later_page_and_source_detail():
    orders = [(f"A{number:04d}", "2.00") for number in range(1, 206)] + [("BAD", "broken")]
    payments = [(f"A{number:04d}", "1.00") for number in range(1, 206)] + [("BAD", "1.00")]
    app = uploaded_app(orders, payments)
    healthy(app.button(key="run_reconciliation").click().run())
    healthy(app.button(key="prepare_report").click().run())
    result, report = workflow(app).result, workflow(app).report_bytes
    set_widget(app, "page_number", 3)
    assert list(frame(app, "result_table")["业务编号"]) == [f"A{number:04d}" for number in range(201, 206)]
    set_widget(app, "detail_id", result.records[200].result_id)
    assert "source_detail" in displayed_frames(app)
    healthy(app.button(key="review_issues").click().run())
    assert widget(app, "page_number").value == 1
    assert widget(app, "detail_id").value is None
    assert "source_detail" not in displayed_frames(app)
    assert len(frame(app, "result_table")) == 2
    healthy(app.button(key="review_differences").click().run())
    assert list(frame(app, "result_table")["业务编号"]) == [f"A{number:04d}" for number in range(1, 101)]
    assert widget(app, "page_number").value == 1
    assert workflow(app).result is result
    assert workflow(app).report_bytes == report


def test_all_matching_result_does_not_offer_empty_problem_shortcuts():
    app = uploaded_app([("A", "1.00")], [("A", "1.00")])
    healthy(app.button(key="run_reconciliation").click().run())
    button_keys = {button.key for button in app.button}
    assert "review_issues" not in button_keys
    assert "review_differences" not in button_keys
    assert not app.button(key="prepare_report").disabled
    assert workflow(app).result.manifest.status_counts[Status.EXACT_MATCH] == 1


def test_header_only_files_guide_the_user_to_check_the_input_range():
    app = uploaded_app([], [])
    healthy(app.button(key="run_reconciliation").click().run())
    assert not workflow(app).result.records
    text = messages(app)
    assert "没有可核对的业务记录" in text
    assert "检查工作表、表头行和数据范围" in text
    assert "抽查来源" not in text


def test_replacing_an_input_and_resetting_returns_to_current_actionable_guidance():
    app = practice_run(export=True)
    healthy(app.file_uploader[0].set_value(("new-orders.csv", csv_bytes([("NEW", "3.00")]), "text/csv")).run())
    assert_result_invalidated(app)
    tasks = pending_tasks(app)
    assert "订单编号列" in tasks and "订单金额列" in tasks
    assert "确认两张表的币种相同" in tasks and "确认两张表的期间相同" in tasks
    assert "旧结果和报告已失效" in messages(app)
    assert not any(button.key in ("review_issues", "review_differences", "prepare_report") for button in app.button)
    healthy(app.button(key="reset").click().run())
    assert_result_invalidated(app)
    tasks = pending_tasks(app)
    assert "上传订单表" in tasks and "上传收款表" in tasks
    assert "填写核对期间" in tasks
    assert "旧结果和报告已失效" not in messages(app)
    assert not app.button(key="start_demo").disabled
