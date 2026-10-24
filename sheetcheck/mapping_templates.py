"""Small, explicit mapping presets without filenames, headers or business data.

Matching verifies only the selected table's structure and CSV parsing settings.
Equal structure cannot establish that columns still have the same meaning. A UI
must ask the user to apply a preset explicitly, review both mappings, and confirm
the currency and period again; presets never contain those confirmations.

The module accepts already parsed sources and bytes. It performs no file or
network IO and does not change a source, mapping, or application session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import PurePosixPath

from .errors import InputError
from .models import FileSpec, Limits, Mapping, MAX_AMOUNT_MINOR, RULES_VERSION, Side, SourceTable
from .validators import SUPPORTED_CURRENCIES

MAX_TEMPLATE_BYTES = 16 * 1024
TEMPLATE_SCHEMA_VERSION = 1
_ENCODINGS = frozenset({"utf-8", "utf-8-sig", "gb18030"})
_DELIMITERS = frozenset({",", "\t", ";"})
_SIDE_KEYS = frozenset({"format", "header_row", "column_count", "id_column", "amount_column", "encoding", "delimiter"})
_RULE_KEYS = frozenset({"version", "tolerance_minor", "minor_digits", "max_amount_minor"})
_ROOT_KEYS = frozenset({"schema_version", "order", "payment", "currency", "rules"})
_DEFAULT_LIMITS = Limits()


@dataclass(frozen=True, slots=True)
class TemplateRules:
    version: str = RULES_VERSION
    tolerance_minor: int = 0
    minor_digits: int = 2
    max_amount_minor: int = MAX_AMOUNT_MINOR


@dataclass(frozen=True, slots=True)
class SourceTemplate:
    format: str
    header_row: int
    column_count: int
    id_column: int
    amount_column: int
    encoding: str | None
    delimiter: str | None


@dataclass(frozen=True, slots=True)
class MappingTemplate:
    order: SourceTemplate
    payment: SourceTemplate
    currency: str
    schema_version: int = TEMPLATE_SCHEMA_VERSION
    rules: TemplateRules = field(default_factory=TemplateRules)


def _invalid() -> None:
    raise InputError("TEMPLATE_INVALID", "映射模板无效；请使用本程序导出的当前版本模板。")


def _too_large() -> None:
    raise InputError("TEMPLATE_TOO_LARGE", "映射模板超过 16 KiB 上限。")


def _mismatch() -> None:
    raise InputError("TEMPLATE_STRUCTURE_MISMATCH", "映射模板与当前两表结构或 CSV 读取参数不一致；请重新选择字段。")


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _check_side(side: SourceTemplate) -> None:
    if type(side) is not SourceTemplate:
        _invalid()
    if (type(side.format) is not str or side.format not in {"csv", "xlsx"}
            or not _integer(side.header_row, 1, _DEFAULT_LIMITS.max_records + 1)
            or not _integer(side.column_count, 2, _DEFAULT_LIMITS.max_columns)
            or not _integer(side.id_column, 1, side.column_count)
            or not _integer(side.amount_column, 1, side.column_count)
            or side.id_column == side.amount_column):
        _invalid()
    if side.format == "csv":
        if (type(side.encoding) is not str or side.encoding not in _ENCODINGS
                or type(side.delimiter) is not str or side.delimiter not in _DELIMITERS):
            _invalid()
    elif side.encoding is not None or side.delimiter is not None:
        _invalid()


def _check_template(template: MappingTemplate) -> None:
    if type(template) is not MappingTemplate:
        _invalid()
    if (type(template.schema_version) is not int or template.schema_version != TEMPLATE_SCHEMA_VERSION
            or type(template.currency) is not str or template.currency not in SUPPORTED_CURRENCIES
            or type(template.rules) is not TemplateRules):
        _invalid()
    rules = template.rules
    if (type(rules.version) is not str or rules.version != RULES_VERSION
            or type(rules.tolerance_minor) is not int or rules.tolerance_minor != 0
            or type(rules.minor_digits) is not int or rules.minor_digits != 2
            or type(rules.max_amount_minor) is not int or rules.max_amount_minor != MAX_AMOUNT_MINOR):
        _invalid()
    _check_side(template.order)
    _check_side(template.payment)


def _from_source(source: SourceTable, mapping: Mapping, side: Side) -> SourceTemplate:
    if (type(source) is not SourceTable or type(source.spec) is not FileSpec
            or source.spec.side != side or type(source.spec.filename) is not str
            or type(source.headers) is not tuple or type(mapping) is not Mapping):
        _invalid()
    extension = PurePosixPath(source.spec.filename).suffix.lower()
    if extension not in {".csv", ".xlsx"}:
        _invalid()
    is_csv = extension == ".csv"
    result = SourceTemplate(
        format=extension[1:], header_row=source.spec.header_row,
        column_count=len(source.headers), id_column=mapping.id_column,
        amount_column=mapping.amount_column,
        encoding=source.spec.encoding if is_csv else None,
        delimiter=source.spec.delimiter if is_csv else None,
    )
    _check_side(result)
    return result


def build_template(order: SourceTable, payment: SourceTable, order_mapping: Mapping,
                   payment_mapping: Mapping, currency: str) -> MappingTemplate:
    """Create a privacy-preserving preset from explicit current column choices."""
    template = MappingTemplate(
        order=_from_source(order, order_mapping, Side.ORDER),
        payment=_from_source(payment, payment_mapping, Side.PAYMENT), currency=currency,
    )
    _check_template(template)
    return template


def _side_payload(side: SourceTemplate) -> dict:
    return {"format": side.format, "header_row": side.header_row,
            "column_count": side.column_count, "id_column": side.id_column,
            "amount_column": side.amount_column, "encoding": side.encoding,
            "delimiter": side.delimiter}


def dump_template(template: MappingTemplate) -> bytes:
    """Serialize only the allowlisted, validated fields as deterministic UTF-8."""
    _check_template(template)
    rules = template.rules
    payload = {
        "schema_version": template.schema_version, "order": _side_payload(template.order),
        "payment": _side_payload(template.payment), "currency": template.currency,
        "rules": {"version": rules.version, "tolerance_minor": rules.tolerance_minor,
                  "minor_digits": rules.minor_digits, "max_amount_minor": rules.max_amount_minor},
    }
    data = (json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(data) > MAX_TEMPLATE_BYTES:
        _too_large()
    return data


def _check_depth(text: str) -> None:
    # The allowlist contains only a root object and single-level child objects.
    # Bound nesting before the JSON decoder can recurse, ignoring quoted braces.
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 2:
                _invalid()
        elif char in "]}":
            depth -= 1


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    _invalid()


def _require_keys(value: object, keys: frozenset[str]) -> None:
    if type(value) is not dict or value.keys() != keys:
        _invalid()


def load_template(data: bytes) -> MappingTemplate:
    """Parse bounded untrusted JSON, rejecting additions and ambiguous keys."""
    if type(data) is not bytes:
        _invalid()
    if len(data) > MAX_TEMPLATE_BYTES:
        _too_large()
    try:
        text = data.decode("utf-8", errors="strict")
        _check_depth(text)
        payload = json.loads(text, object_pairs_hook=_unique_object,
                             parse_float=_reject_number, parse_constant=_reject_number)
    except (ValueError, RecursionError):
        # Decoder errors can contain user-controlled JSON snippets. Never expose
        # them in the public exception or its displayed traceback chain.
        _invalid_from_decoder()
    _require_keys(payload, _ROOT_KEYS)
    _require_keys(payload["order"], _SIDE_KEYS)
    _require_keys(payload["payment"], _SIDE_KEYS)
    _require_keys(payload["rules"], _RULE_KEYS)
    template = MappingTemplate(
        order=SourceTemplate(**payload["order"]), payment=SourceTemplate(**payload["payment"]),
        currency=payload["currency"], schema_version=payload["schema_version"],
        rules=TemplateRules(**payload["rules"]),
    )
    _check_template(template)
    return template


def _invalid_from_decoder() -> None:
    raise InputError("TEMPLATE_INVALID", "映射模板无效；请使用本程序导出的当前版本模板。") from None


def match_template(template: MappingTemplate, order: SourceTable,
                   payment: SourceTable) -> tuple[Mapping, Mapping, str]:
    """Check both sides before returning choices, without applying any changes.

    A match is structural only: renamed or reordered column labels do not become
    semantic evidence. Users must inspect the selected columns on every apply.
    """
    _check_template(template)
    order_mapping = Mapping(template.order.id_column, template.order.amount_column)
    payment_mapping = Mapping(template.payment.id_column, template.payment.amount_column)
    try:
        current_order = _from_source(order, order_mapping, Side.ORDER)
        current_payment = _from_source(payment, payment_mapping, Side.PAYMENT)
    except InputError:
        raise InputError("TEMPLATE_STRUCTURE_MISMATCH", "映射模板与当前两表结构或 CSV 读取参数不一致；请重新选择字段。") from None
    if (current_order, current_payment) != (template.order, template.payment):
        _mismatch()
    return order_mapping, payment_mapping, template.currency
