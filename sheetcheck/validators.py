"""Validate types and exact source values without silently repairing IDs."""
from __future__ import annotations

from decimal import Context, Decimal, localcontext
import re
import unicodedata

from .errors import InputError
from .models import (Cell, Mapping, Rules, SourceTable, ValidatedRow, ValidatedTable,
                     MAX_AMOUNT_MINOR, RULES_VERSION)

# Explicit v1 UI/API choices: no automatic currency inference or conversion.
SUPPORTED_CURRENCIES = frozenset({"CNY", "USD", "EUR", "GBP", "HKD", "SGD", "AUD", "CAD", "NZD", "CHF"})
_DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z", re.ASCII)


def check_rules(rules: Rules) -> None:
    if (any(type(v) is not int for v in (rules.tolerance_minor, rules.minor_digits, rules.max_amount_minor))
            or rules.version != RULES_VERSION or rules.tolerance_minor != 0
            or rules.minor_digits != 2 or rules.max_amount_minor != MAX_AMOUNT_MINOR):
        raise InputError("RULES_UNSUPPORTED", "v1 固定两位小数、容差 0 和单笔上限，不支持改变规则。")
    if rules.currency not in SUPPORTED_CURRENCIES:
        raise InputError("CURRENCY_UNSUPPORTED", "请选择 v1 支持的两位小数币种代码。")
    if (rules.same_currency_confirmed is not True or rules.same_period_confirmed is not True
            or not isinstance(rules.period, str) or not rules.period.strip()):
        raise InputError("CONFIRMATION_REQUIRED", "请明确确认两表同币种、同期间，并记录核对期间。")


def parse_amount(cell: Cell) -> tuple[int | None, tuple[str, ...], tuple[str, ...]]:
    if cell.kind == "empty" or cell.value is None or (cell.kind == "text" and not cell.value.strip()):
        return None, ("AMOUNT_MISSING",), ()
    if cell.kind not in {"text", "number"} or isinstance(cell.value, bool):
        return None, ("AMOUNT_TYPE",), ()
    raw = str(cell.value)
    value = raw.strip() if cell.kind == "text" else raw
    notes = ("AMOUNT_TRIMMED",) if raw != value else ()
    if not _DECIMAL.fullmatch(value):
        return None, ("AMOUNT_FORMAT",), notes
    if "." in value and len(value.split(".")[1]) > 2:
        return None, ("AMOUNT_PRECISION",), notes
    amount = Decimal(value)  # never Decimal(float), never quantize/round
    if amount > Decimal("999999999.99"):
        return None, ("AMOUNT_LIMIT",), notes
    # Independent of a caller's global Decimal context and traps.
    with localcontext(Context(prec=32)):
        minor = int(amount * 100)
    return minor, (), notes


def _identifier(cell: Cell) -> tuple[str | None, tuple[str, ...]]:
    if cell.kind == "empty" or cell.value is None:
        return None, ("ID_MISSING",)
    if cell.kind != "text" or not isinstance(cell.value, str):
        return None, ("ID_NOT_TEXT",)
    value = cell.value
    if not value.strip():
        return None, ("ID_MISSING",)
    problems = []
    if value != value.strip():
        problems.append("ID_WHITESPACE")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value):
        problems.append("ID_CONTROL_CHARACTER")
    if len(value) > 128:
        problems.append("ID_TOO_LONG")
    # Identifiable even if invalid: exact original text remains the blocking key.
    return value, tuple(problems)


def validate(table: SourceTable, mapping: Mapping, rules: Rules) -> ValidatedTable:
    check_rules(rules)
    columns = (mapping.id_column, mapping.amount_column)
    if (any(type(c) is not int or not 1 <= c <= len(table.headers) for c in columns)
            or columns[0] == columns[1]):
        raise InputError("MAPPING_INVALID", "请选择不同的、在范围内的编号列和金额列（列号从 1 开始）。")
    last_row = table.rows[-1].position.row if table.rows else table.spec.header_row
    for regions, code in ((table.merged_regions, "MAPPED_MERGE"), (table.formula_regions, "MAPPED_FORMULA")):
        if any(r.min_row <= last_row and r.max_row >= table.spec.header_row
               and any(r.min_col <= c <= r.max_col for c in columns) for r in regions):
            raise InputError(code, "映射列或映射表头涉及合并单元格/公式区域，请从可信来源导出普通值表。")
    if any(table.headers[c - 1].kind == "formula" for c in columns):
        raise InputError("MAPPED_FORMULA", "映射表头包含公式，请使用普通值表。")
    rows = []
    for row in table.rows:
        if len(row.cells) != len(table.headers):
            raise InputError("ROW_WIDTH", "输入行列数与表头不一致。")
        id_cell, amount_cell = (row.cells[c - 1] for c in columns)
        if id_cell.kind == "formula" or amount_cell.kind == "formula":
            raise InputError("MAPPED_FORMULA", "映射列包含公式，请从可信来源导出纯值副本。")
        empty = all(c.value is None or (c.kind == "text" and c.value == "") for c in row.cells)
        if empty:
            rows.append(ValidatedRow(row, id_cell.value, amount_cell.value,
                                     (id_cell.kind, amount_cell.kind), None, None, skipped_empty=True))
            continue
        identifier, id_problems = _identifier(id_cell)
        minor, amount_problems, notes = parse_amount(amount_cell)
        rows.append(ValidatedRow(row, id_cell.value, amount_cell.value, (id_cell.kind, amount_cell.kind),
                                 identifier, minor, id_problems + amount_problems, notes))
    return ValidatedTable(table, mapping, rules, tuple(rows))
