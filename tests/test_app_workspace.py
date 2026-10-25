"""Workspace navigation preserves the same audited, session-owned workflow.

Streamlit 1.66's AppTest Tab has no selection method, so navigation is driven
through the tab widget's session-state value before an actual script rerun.
These are state/interaction checks, not browser tab-click or visual evidence.
"""
from __future__ import annotations

import pytest

from sheetcheck.errors import InputError
from sheetcheck.models import Side
from test_app import (assert_result_invalidated, confirm_rules, csv_bytes,
                      demo_run, frame, fresh_app, healthy, set_widget, widget,
                      workflow)


WORKSPACES = ["准备数据", "核对结果", "使用指南"]


def select_workspace(app, label):
    assert label in WORKSPACES
    app.session_state["workspace_tab"] = label
    healthy(app.run())
    assert app.session_state["workspace_tab"] == label
    return app


def test_first_open_has_three_workspaces_and_no_premature_result_or_download():
    app = fresh_app()
    assert [tab.label for tab in app.tabs] == WORKSPACES
    assert app.session_state["workspace_tab"] == "准备数据"
    assert_result_invalidated(app)
    assert app.button(key="run_reconciliation").disabled
    select_workspace(app, "核对结果")
    assert not app.tabs[1].dataframe
    assert not app.tabs[1].download_button
    assert not any(button.key == "prepare_report" for button in app.tabs[1].button)
    assert not workflow(app).result


def test_visiting_guide_and_empty_results_keeps_sample_mappings_and_manual_confirmations():
    app = fresh_app()
    healthy(app.button(key="start_demo").click().run())
    selections = dict(workflow(app).selections)
    mappings = dict(workflow(app).mappings)
    for label in ("使用指南", "核对结果", "准备数据"):
        select_workspace(app, label)
        assert workflow(app).selections == selections
        assert workflow(app).mappings == mappings
        assert widget(app, "period").value == "虚构样例期间"
        assert not widget(app, "confirm_currency").value
        assert not widget(app, "confirm_period").value
        assert app.button(key="run_reconciliation").disabled
        assert len(frame(app, "order_preview")) == 8
        assert len(frame(app, "payment_preview")) == 6


def test_successful_reconciliation_opens_results_without_discarding_input_widgets():
    app = fresh_app()
    healthy(app.button(key="start_demo").click().run())
    confirm_rules(app)
    healthy(app.button(key="run_reconciliation").click().run())
    assert app.session_state["workspace_tab"] == "核对结果"
    assert len(frame(app, "result_table")) == 5
    for side in Side:
        assert widget(app, f"{side}_id").value == 1
        assert widget(app, f"{side}_amount").value == 2
        assert workflow(app).selections[side] is not None
    assert widget(app, "confirm_currency").value
    assert widget(app, "confirm_period").value


def test_switching_workspaces_preserves_filtered_result_source_and_report():
    app = demo_run(export=True)
    set_widget(app, "query", "A002")
    result, report = workflow(app).result, workflow(app).report_bytes
    record = next(item for item in result.records if item.id == "A002")
    set_widget(app, "detail_id", record.result_id)
    selections = dict(workflow(app).selections)
    mappings = dict(workflow(app).mappings)
    for label in ("准备数据", "使用指南", "核对结果"):
        select_workspace(app, label)
        assert workflow(app).result is result
        assert workflow(app).report_bytes is report
        assert workflow(app).selections == selections
        assert workflow(app).mappings == mappings
        assert widget(app, "query").value == "A002"
        assert widget(app, "detail_id").value == record.result_id
        assert list(frame(app, "result_table")["业务编号"]) == ["A002"]
        assert list(frame(app, "source_detail")["原始行号"]) == [3, 3]
        assert [button.label for button in app.download_button] == ["下载核对报告"]


def test_rule_change_revokes_results_and_returns_to_preparation():
    app = demo_run(export=True)
    set_widget(app, "period", "new-fictional-period")
    assert_result_invalidated(app)
    assert app.session_state["workspace_tab"] == "准备数据"
    assert widget(app, "period").value == "new-fictional-period"
    assert all(workflow(app).selections.values())


def test_replacing_input_revokes_results_and_returns_to_preparation():
    app = demo_run(export=True)
    healthy(app.file_uploader[0].set_value((
        "replacement.csv", csv_bytes([("NEW", "4.00")]), "text/csv")).run())
    assert_result_invalidated(app)
    assert app.session_state["workspace_tab"] == "准备数据"
    assert widget(app, "order_id").value is None
    assert widget(app, "order_amount").value is None
    assert not widget(app, "confirm_currency").value
    assert not widget(app, "confirm_period").value
    assert "NEW" in frame(app, "order_preview").to_string(index=False)


def test_reset_from_guide_restores_first_use_and_revokes_the_old_download():
    app = demo_run(export=True)
    old_workflow = workflow(app)
    old_run_id = old_workflow.result.manifest.run_id
    select_workspace(app, "使用指南")
    healthy(app.button(key="reset").click().run())
    assert_result_invalidated(app)
    assert app.session_state["workspace_tab"] == "准备数据"
    assert not app.button(key="start_demo").disabled
    assert all(selection is None for selection in workflow(app).selections.values())
    assert widget(app, "period").value == ""
    assert not widget(app, "confirm_currency").value
    assert not widget(app, "confirm_period").value
    with pytest.raises(InputError):
        old_workflow.report_for_run(old_run_id)
