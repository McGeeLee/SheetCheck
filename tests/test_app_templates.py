"""Opt-in mapping templates through real Streamlit widgets and uploaded bytes.

No browser or download-directory access is needed: template downloads are
captured at the Streamlit API and exercised through AppTest's widget event.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import sheetcheck.mapping_templates as templates
from sheetcheck.errors import InputError
from sheetcheck.models import Mapping, Side


APP = Path(__file__).resolve().parents[1] / "app.py"
CANARY = "PRIVATE_TEMPLATE_TEST_ZX719"


def healthy(page):
    assert not page.exception, [item.message for item in page.exception]
    return page


def state(page):
    return page.session_state["workflow"]


def text(page):
    return "\n".join(item.value for kind in ("error", "warning", "caption", "info") for item in getattr(page, kind))


def demo(*, report=False):
    page = healthy(AppTest.from_file(str(APP), default_timeout=20).run())
    healthy(page.button(key="load_demo").click().run())
    page.checkbox(key="confirm_currency").set_value(True)
    page.checkbox(key="confirm_period").set_value(True)
    healthy(page.run())
    healthy(page.button(key="run_reconciliation").click().run())
    if report:
        healthy(page.button(key="prepare_report").click().run())
    return page


def payload(page, *, currency="USD", order_mapping=None, payment_mapping=None):
    current = state(page)
    return templates.dump_template(templates.build_template(
        current.sources[Side.ORDER], current.sources[Side.PAYMENT],
        order_mapping or current.mappings[Side.ORDER], payment_mapping or current.mappings[Side.PAYMENT], currency))


def enable(page):
    healthy(page.checkbox(key="template_enabled").set_value(True).run())
    assert len(page.file_uploader) == 3
    return page


def upload_template(page, data):
    healthy(page.file_uploader[2].set_value((CANARY + ".json", data, "application/json")).run())
    return page


def apply(page):
    return healthy(page.button(key="apply_template").click().run())


def selection_snapshot(page):
    return tuple(page.selectbox(key=key).value for key in
                 ("order_id", "order_amount", "payment_id", "payment_amount", "currency"))


def test_templates_are_opt_in_and_opening_them_preserves_current_report():
    page = demo(report=True)
    original, report = state(page).result, state(page).report_bytes
    assert len(page.file_uploader) == 2
    assert [item.label for item in page.download_button] == ["下载核对报告"]
    enable(page)
    assert state(page).result is original and state(page).report_bytes == report
    assert "列顺序变化" in text(page)
    healthy(page.checkbox(key="template_enabled").set_value(False).run())
    assert len(page.file_uploader) == 2
    assert state(page).result is original


@pytest.mark.parametrize("currency", ["CNY", "USD"])
def test_explicit_application_revokes_even_identical_mapping_and_requires_reconfirmation(currency):
    page = demo(report=True)
    current = state(page)
    run_id = current.result.manifest.run_id
    config = payload(page, currency=currency)
    healthy(page.text_input(key="query").set_value("A002").run())
    record = next(record for record in current.result.records if record.id == "A002")
    healthy(page.selectbox(key="detail_id").set_value(record.result_id).run())
    healthy(page.multiselect(key="status_filter").set_value(["金额差异"]).run())
    enable(page)
    upload_template(page, config)
    assert current.result is not None and current.report_bytes is not None
    assert page.selectbox(key="currency").value == "CNY"  # upload alone is inert
    apply(page)
    assert selection_snapshot(page) == (1, 2, 1, 2, currency)
    assert current.result is None and current.report_bytes is None and current.report_name is None
    with pytest.raises(InputError, match="REPORT_STALE"):
        current.report_for_run(run_id)
    assert page.text_input(key="period").value == ""
    assert not page.checkbox(key="confirm_currency").value
    assert not page.checkbox(key="confirm_period").value
    assert page.session_state["query"] == ""
    assert page.session_state["page_number"] == 1
    assert page.session_state["result_view"] == "全部业务结果"
    assert len(page.session_state["status_filter"]) == 4
    assert "detail_id" not in page.session_state
    assert page.button(key="run_reconciliation").disabled
    assert all(item.label != "下载核对报告" for item in page.download_button)
    page.text_input(key="period").set_value("new fictional period")
    page.checkbox(key="confirm_currency").set_value(True)
    healthy(page.run())
    assert page.button(key="run_reconciliation").disabled
    healthy(page.checkbox(key="confirm_period").set_value(True).run())
    healthy(page.button(key="run_reconciliation").click().run())
    assert current.result is not None and current.result.manifest.run_id != run_id
    assert current.result.manifest.rules.currency == currency


def test_template_updates_both_mappings_together_without_changing_reading_options():
    page = demo()
    config = payload(page, order_mapping=Mapping(2, 1), payment_mapping=Mapping(2, 1))
    options = tuple(page.session_state[key] for key in
                    ("order_header", "payment_header", "order_encoding", "payment_encoding"))
    upload_template(enable(page), config)
    apply(page)
    assert selection_snapshot(page) == (2, 1, 2, 1, "USD")
    assert options == tuple(page.session_state[key] for key in
                            ("order_header", "payment_header", "order_encoding", "payment_encoding"))
    assert "映射示例" in "\n".join(item.value for item in page.text)


@pytest.mark.parametrize("data", [b'{"private":"' + CANARY.encode() + b'"}',
                                   b'not json: ' + CANARY.encode(), b'\xff\xfe',
                                   b'{"schema_version":1,"schema_version":1}'])
def test_invalid_template_is_atomic_and_redacted(data, caplog, capsys):
    caplog.set_level(logging.ERROR)
    page = demo(report=True)
    original, report, choices = state(page).result, state(page).report_bytes, selection_snapshot(page)
    upload_template(enable(page), data)
    apply(page)
    assert "TEMPLATE_INVALID" in text(page)
    assert selection_snapshot(page) == choices
    assert state(page).result is original and state(page).report_bytes == report
    assert page.checkbox(key="confirm_currency").value
    assert page.checkbox(key="confirm_period").value
    assert CANARY not in text(page) + caplog.text + capsys.readouterr().err
    assert any("phase=TEMPLATE code=TEMPLATE_INVALID" in record.getMessage() for record in caplog.records)


def test_oversized_template_is_rejected_before_apply_without_losing_work():
    page = demo(report=True)
    original, report = state(page).result, state(page).report_bytes
    upload_template(enable(page), b" " * (templates.MAX_TEMPLATE_BYTES + 1))
    assert "TEMPLATE_TOO_LARGE" in text(page)
    assert page.button(key="apply_template").disabled
    assert state(page).result is original and state(page).report_bytes == report


def test_second_side_mismatch_does_not_partially_apply_first_side():
    page = demo(report=True)
    template = json.loads(payload(page, order_mapping=Mapping(2, 1)))
    template["payment"]["column_count"] += 1
    choices, original = selection_snapshot(page), state(page).result
    upload_template(enable(page), json.dumps(template).encode())
    apply(page)
    assert "TEMPLATE_STRUCTURE_MISMATCH" in text(page)
    assert selection_snapshot(page) == choices
    assert state(page).result is original and state(page).report_bytes is not None


@pytest.mark.parametrize("change", ["upload", "parser"])
def test_changing_inputs_clears_template_and_prevents_silent_reuse(change):
    page = demo(report=True)
    upload_template(enable(page), payload(page))
    old_key = page.file_uploader[2].key
    if change == "upload":
        healthy(page.file_uploader[0].set_value(("new.csv", b"other id,other amount\nNEW,3\n", "text/csv")).run())
    else:
        healthy(page.selectbox(key="order_encoding").set_value("utf-8").run())
    assert page.file_uploader[2].value is None and page.file_uploader[2].key != old_key
    assert page.button(key="apply_template").disabled
    assert page.selectbox(key="order_id").value is None
    assert page.selectbox(key="order_amount").value is None
    assert state(page).result is None and state(page).report_bytes is None
    assert page.selectbox(key="currency").value == "CNY"


def test_same_structure_different_contents_requires_explicit_apply_and_shows_meaning_warning():
    page = demo()
    config = payload(page)
    enable(page)
    healthy(page.file_uploader[0].set_value(("new.csv", b"different id,different amount\nNEW,3\n", "text/csv")).run())
    assert page.selectbox(key="order_id").value is None
    upload_template(page, config)
    assert page.selectbox(key="order_id").value is None
    apply(page)
    assert selection_snapshot(page) == (1, 2, 1, 2, "USD")
    assert "结构相同不代表字段含义相同" in text(page)
    assert "检查两侧映射示例" in text(page)
    assert not page.checkbox(key="confirm_currency").value
    assert page.button(key="run_reconciliation").disabled
    assert "NEW" in page.dataframe[0].value.to_string(index=False)


def test_reset_removes_template_upload_notice_and_pending_action():
    page = demo(report=True)
    upload_template(enable(page), payload(page))
    apply(page)
    healthy(page.button(key="reset").click().run())
    assert not page.checkbox(key="template_enabled").value
    assert len(page.file_uploader) == 2 and all(item.value is None for item in page.file_uploader)
    assert not page.download_button
    assert not page.session_state["template_apply_requested"]
    assert page.session_state["template_notice"] is None
    assert page.session_state["template_error"] is None
    assert state(page).sources == {}


def test_exported_template_bytes_exclude_business_context_and_widget_click_does_not_change_report(monkeypatch):
    captured = []
    real_download = st.download_button

    def capture_download(label, *args, **kwargs):
        if kwargs.get("key") == "download_template":
            captured.append(kwargs.copy())
        return real_download(label, *args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)
    page = demo(report=True)
    healthy(page.text_input(key="period").set_value(CANARY).run())
    healthy(page.button(key="run_reconciliation").click().run())
    healthy(page.button(key="prepare_report").click().run())
    original, report = state(page).result, state(page).report_bytes
    enable(page)
    assert captured and captured[-1]["mime"] == "application/json"
    assert captured[-1]["file_name"] == "sheetcheck-mapping-v1.json"
    raw = captured[-1]["data"]
    assert isinstance(raw, bytes) and len(raw) <= templates.MAX_TEMPLATE_BYTES
    parsed = json.loads(raw)
    assert parsed["currency"] == "CNY"
    for secret in (CANARY, "orders.csv", "payments.csv", "A001", "虚构样例期间", "same_period_confirmed"):
        assert secret not in raw.decode()
    healthy(page.download_button(key="download_template").click().run())
    assert state(page).result is original and state(page).report_bytes == report
    templates.load_template(raw)


def test_unexpected_apply_error_does_not_leak_exception_or_change_widgets(monkeypatch, caplog, capsys):
    page = demo(report=True)
    upload_template(enable(page), payload(page))
    choices, original = selection_snapshot(page), state(page).result

    def failure(*args, **kwargs):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(templates, "match_template", failure)
    caplog.set_level(logging.ERROR)
    apply(page)
    assert "UI_TEMPLATE_FAILED" in text(page)
    assert selection_snapshot(page) == choices and state(page).result is original
    assert CANARY not in text(page) + caplog.text + capsys.readouterr().err


def test_source_changed_during_validation_is_detected_before_mapping_mutation(monkeypatch):
    page = demo()
    upload_template(enable(page), payload(page, order_mapping=Mapping(2, 1)))
    current = state(page)
    real_match = templates.match_template

    def changed_source(*args):
        matched = real_match(*args)
        current.sync_inputs({Side.ORDER: current.selections[Side.ORDER], Side.PAYMENT: None})
        return matched

    monkeypatch.setattr(templates, "match_template", changed_source)
    apply(page)
    assert "TEMPLATE_INPUT_CHANGED" in text(page)
    assert page.selectbox(key="order_id").value == 1
    assert page.selectbox(key="order_amount").value == 2
    assert page.selectbox(key="currency").value == "CNY"
    assert page.text_input(key="period").value == "虚构样例期间"
