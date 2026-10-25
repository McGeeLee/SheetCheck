"""Readable issue guidance preserves the original source records and codes."""
from __future__ import annotations

import csv
from dataclasses import replace
import io
from pathlib import Path

import pytest

from sheetcheck import FileSpec, Mapping, Rules, Side, read_source, reconcile, validate
from sheetcheck.errors import PROBLEM_HELP
from sheetcheck.models import Status
from sheetcheck.ui_views import (PROBLEM_LABELS, issue_explanation, issue_next_steps,
                                issue_rows, result_page)


ROOT = Path(__file__).resolve().parents[1]
RULES = Rules(period="fictional", same_currency_confirmed=True, same_period_confirmed=True)


def run_csv(order_bytes, payment_bytes):
    tables = [validate(read_source(data, FileSpec(f"{side}.csv", side)), Mapping(1, 2), RULES)
              for side, data in ((Side.ORDER, order_bytes), (Side.PAYMENT, payment_bytes))]
    return reconcile(*tables, RULES)


def csv_bytes(rows):
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows([["id", "amount"], *rows])
    return buffer.getvalue().encode("utf-8")


def test_every_defined_problem_has_a_human_description():
    assert set(PROBLEM_LABELS) == set(PROBLEM_HELP)


@pytest.mark.parametrize("code", tuple(PROBLEM_HELP))
def test_defined_codes_have_actionable_guidance_without_raw_code_jargon(code):
    explanation = issue_explanation((code,))
    assert explanation and code not in explanation
    assert "未识别" not in explanation
    assert issue_next_steps((code,)) == PROBLEM_HELP[code]


def test_canonical_sample_shows_six_issue_rows_with_original_values_and_positions():
    result = run_csv((ROOT / "samples/orders.csv").read_bytes(),
                     (ROOT / "samples/payments.csv").read_bytes())
    page = result_page(result, "数据问题")
    rows = issue_rows(page.items)
    assert page.total == 6 and len(rows) == 6
    actual = {(row["文件角色"], row["原始行号"]): row for row in rows}
    assert {(role, number, row["业务编号"], row["原始金额"])
            for (role, number), row in actual.items()} == {
        ("订单", "5", "A005", "10.00"), ("订单", "6", "A005", "20.00"),
        ("订单", "7", "（空字符串）", "5.00"), ("订单", "8", "A006", "X"),
        ("收款", "5", "A005", "30.00"), ("收款", "6", "A006", "12.00"),
    }
    assert "同编号在至少一张表中重复" in actual[("订单", "5")]["问题说明"]
    assert "当前版本不合并收款" in actual[("订单", "5")]["处理建议"]
    assert actual[("订单", "7")]["问题说明"] == "编号为空"
    assert "金额格式不符合要求" in actual[("订单", "8")]["问题说明"]
    associated = actual[("收款", "6")]
    assert associated["全部问题码"] == "BLOCKED_ID"
    assert "关联行有问题" in associated["问题说明"]
    assert "本行一并隔离" in associated["问题说明"]
    assert "两侧全部隔离" in associated["处理建议"]
    assert len(result.records) == 5 and len(result.ledger) == 14
    assert result.manifest.summaries[Side.ORDER].valid_total_minor == 18000
    assert result.manifest.summaries[Side.PAYMENT].valid_total_minor == 18900


def test_multiple_problems_do_not_expand_source_rows_and_keep_each_distinct_reason():
    result = run_csv(csv_bytes([("D", "X"), ("D", "2.00")]), csv_bytes([("D", "3.00")]))
    issues = [entry for entry in result.ledger if entry.status == Status.DATA_ISSUE]
    rows = issue_rows(issues)
    assert len(rows) == 3
    bad = next(row for row in rows if row["原始金额"] == "X")
    assert set(bad["全部问题码"].split(" · ")) == {"AMOUNT_FORMAT", "DUPLICATE_ID", "BLOCKED_ID"}
    assert "金额格式不符合要求" in bad["问题说明"]
    assert "同编号在至少一张表中重复" in bad["问题说明"]
    assert "十进制金额" in bad["处理建议"]
    assert "当前版本不合并收款" in bad["处理建议"]
    # Rendering duplicated diagnostic input never repeats a reason or invents a source row.
    repeated = replace(issues[0], problem_codes=("AMOUNT_FORMAT", "DUPLICATE_ID", "AMOUNT_FORMAT"))
    rendered = issue_rows([repeated])
    assert len(rendered) == 1
    assert rendered[0]["全部问题码"] == "AMOUNT_FORMAT · DUPLICATE_ID"
    assert rendered[0]["问题说明"] == "金额格式不符合要求；同编号在至少一张表中重复"
    assert rendered[0]["处理建议"].count("十进制金额") == 1


@pytest.mark.parametrize("codes", [(), ("UNKNOWN_PRIVATE_CODE",),
                                   ("UNKNOWN_PRIVATE_CODE", "ANOTHER_UNKNOWN", "UNKNOWN_PRIVATE_CODE")])
def test_unknown_or_missing_codes_use_a_fixed_safe_fallback(codes):
    explanation, hint = issue_explanation(codes), issue_next_steps(codes)
    assert explanation
    assert hint == "请查看全部问题码与来源详情，核实原始记录。"
    assert all(code not in explanation + hint for code in codes)
    if codes:
        assert explanation == "未识别的数据问题"


def test_unknown_codes_do_not_hide_known_repair_suggestions():
    codes = ("ID_MISSING", "PRIVATE_UNKNOWN", "ID_MISSING", "AMOUNT_MISSING")
    assert issue_explanation(codes) == "编号为空；未识别的数据问题；金额为空"
    hint = issue_next_steps(codes)
    assert "补充文本业务编号" in hint and "请补充非负" in hint
    assert hint.count("请从原系统补充文本业务编号。") == 1
    assert "PRIVATE_UNKNOWN" not in hint


def test_formula_like_business_values_are_only_present_in_original_value_columns(caplog):
    private_id = '=HYPERLINK("https://canary.invalid/record","PRIVATE_CANARY_ID")'
    private_amount = "PRIVATE_CANARY_BAD_AMOUNT"
    result = run_csv(csv_bytes([(private_id, private_amount)]), csv_bytes([(private_id, "1.00")]))
    rows = issue_rows(result_page(result, "数据问题").items)
    assert len(rows) == 2
    assert all(row["业务编号"] == private_id for row in rows)
    assert rows[0]["原始金额"] == private_amount
    assert rows[1]["原始金额"] == "1.00"
    guidance = " ".join(row["问题说明"] + row["处理建议"] for row in rows)
    assert "PRIVATE_CANARY" not in guidance
    assert "https://" not in guidance and "HYPERLINK" not in guidance
    assert "PRIVATE_CANARY" not in caplog.text
