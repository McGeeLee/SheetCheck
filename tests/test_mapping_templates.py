"""Mapping presets preserve choices, never prior business data or consent."""
from dataclasses import FrozenInstanceError, replace
import io
import json
import traceback

from openpyxl import Workbook
import pytest

from sheetcheck.errors import InputError
from sheetcheck.mapping_templates import (
    MAX_TEMPLATE_BYTES, MappingTemplate, SourceTemplate, TemplateRules,
    build_template, dump_template, load_template, match_template,
)
from sheetcheck.models import Cell, FileSpec, Mapping, Side
from sheetcheck.readers import read_source


CANARIES = ("SECRET_filename", "SECRET_sheet", "SECRET_header_id", "SECRET_header_amount", "SECRET_business_id", "8123456.78")


def source(side, kind="csv", *, header_row=1, encoding="utf-8-sig", delimiter=","):
    headers = [CANARIES[2], CANARIES[3], "SECRET_unmapped_header"]
    values = [CANARIES[4], CANARIES[5], "SECRET_unmapped_value"]
    if kind == "csv":
        lines = [delimiter.join(["preface", "", ""])] * (header_row - 1)
        lines += [delimiter.join(headers), delimiter.join(values)]
        data = ("\n".join(lines) + "\n").encode(encoding)
        spec = FileSpec(CANARIES[0] + ".csv", side, header_row=header_row, encoding=encoding, delimiter=delimiter)
    else:
        book = Workbook()
        sheet = book.active
        sheet.title = CANARIES[1]
        for _ in range(header_row - 1):
            sheet.append(["preface", "", ""])
        sheet.append(headers)
        sheet.append(values)
        buffer = io.BytesIO()
        book.save(buffer)
        book.close()
        data = buffer.getvalue()
        spec = FileSpec(CANARIES[0] + ".xlsx", side, sheet=CANARIES[1], header_row=header_row)
    return read_source(data, spec)


def inputs():
    return source(Side.ORDER), source(Side.PAYMENT, "xlsx")


def preset():
    order, payment = inputs()
    return build_template(order, payment, Mapping(1, 2), Mapping(3, 2), "CNY")


def payload():
    return json.loads(dump_template(preset()))


def load_dict(data):
    return load_template(json.dumps(data).encode())


def assert_safe_error(call, code="TEMPLATE_INVALID"):
    with pytest.raises(InputError) as caught:
        call()
    assert caught.value.code == code
    visible = "".join(traceback.format_exception(caught.value))
    # Tracebacks contain this test's source lines, so check actual canary values.
    assert all(secret not in str(caught.value) for secret in CANARIES)
    assert "DO_NOT_REFLECT_JSON" not in visible
    return caught.value


@pytest.mark.parametrize("order_kind,payment_kind", [("csv", "csv"), ("csv", "xlsx"), ("xlsx", "csv"), ("xlsx", "xlsx")])
def test_round_trip_preserves_explicit_choices_and_currency(order_kind, payment_kind):
    order, payment = source(Side.ORDER, order_kind), source(Side.PAYMENT, payment_kind)
    template = build_template(order, payment, Mapping(2, 3), Mapping(3, 1), "SGD")
    encoded = dump_template(template)
    assert encoded == dump_template(load_template(encoded))
    assert match_template(load_template(encoded), order, payment) == (Mapping(2, 3), Mapping(3, 1), "SGD")
    assert len(encoded) < MAX_TEMPLATE_BYTES
    if order_kind == "xlsx":
        assert template.order.encoding is None and template.order.delimiter is None


def test_allowlist_omits_all_business_identity_and_confirmations():
    order, payment = inputs()
    encoded = dump_template(build_template(order, payment, Mapping(1, 2), Mapping(1, 2), "USD"))
    text = encoded.decode()
    assert all(value not in text for value in (*CANARIES, order.sha256, payment.sha256))
    assert set(json.loads(text)) == {"schema_version", "order", "payment", "currency", "rules"}
    for side in ("order", "payment"):
        assert set(json.loads(text)[side]) == {"format", "header_row", "column_count", "id_column", "amount_column", "encoding", "delimiter"}
    assert set(json.loads(text)["rules"]) == {"version", "tolerance_minor", "minor_digits", "max_amount_minor"}


def test_identical_structure_with_different_private_data_has_identical_template():
    order, payment = inputs()
    before = build_template(order, payment, Mapping(1, 2), Mapping(1, 2), "CNY")
    modified_order = replace(order, sha256="new-hash", spec=replace(order.spec, filename="another.csv"),
                             headers=(Cell("amount", "text"), Cell("id", "text"), Cell("different", "text")), rows=())
    modified_payment = replace(payment, sha256="other-hash", spec=replace(payment.spec, filename="other.xlsx", sheet="another-sheet"),
                               headers=(Cell("a", "text"), Cell("b", "text"), Cell("c", "text")), rows=())
    after = build_template(modified_order, modified_payment, Mapping(1, 2), Mapping(1, 2), "CNY")
    assert dump_template(before) == dump_template(after)
    # This deliberate structural match is NOT a claim of semantic equivalence.
    assert match_template(before, modified_order, modified_payment) == (Mapping(1, 2), Mapping(1, 2), "CNY")


def test_contracts_are_immutable():
    template = preset()
    for target, name, value in [(template, "currency", "USD"), (template.order, "id_column", 3), (template.rules, "minor_digits", 3)]:
        with pytest.raises(FrozenInstanceError):
            setattr(target, name, value)


@pytest.mark.parametrize("side,key,value", [
    (None, "schema_version", 2), (None, "schema_version", True), (None, "schema_version", "1"),
    (None, "currency", "JPY"), (None, "currency", "cny"), (None, "currency", None), (None, "currency", []),
    ("order", "format", "CSV"), ("order", "format", "xlsm"), ("order", "format", False),
    ("order", "header_row", 0), ("order", "header_row", 50_002), ("order", "header_row", True),
    ("order", "column_count", 1), ("order", "column_count", 101), ("order", "column_count", False),
    ("order", "id_column", 0), ("order", "id_column", 4), ("order", "id_column", "1"), ("order", "id_column", True),
    ("payment", "amount_column", -1), ("payment", "amount_column", 4), ("payment", "amount_column", 3),
    ("order", "encoding", "latin1"), ("order", "encoding", None), ("order", "delimiter", "|"), ("order", "delimiter", []),
    ("payment", "encoding", "utf-8"), ("payment", "delimiter", ","),
    ("rules", "version", "v2"), ("rules", "version", True),
    ("rules", "minor_digits", 3), ("rules", "minor_digits", "2"),
    ("rules", "tolerance_minor", 1), ("rules", "tolerance_minor", False),
    ("rules", "max_amount_minor", 99999999998), ("rules", "max_amount_minor", True),
])
def test_rejects_wrong_types_bounds_options_and_rule_changes(side, key, value):
    data = payload()
    (data if side is None else data[side])[key] = value
    assert_safe_error(lambda: load_dict(data))


@pytest.mark.parametrize("side,extra", [(None, "name"), (None, "period"), (None, "confirmed"), ("order", "filename"), ("payment", "sheet"), ("order", "headers"), ("rules", "same_currency_confirmed")])
def test_rejects_extra_keys_in_every_object(side, extra):
    data = payload()
    (data if side is None else data[side])[extra] = "DO_NOT_REFLECT_JSON"
    assert_safe_error(lambda: load_dict(data))


@pytest.mark.parametrize("side,key", [(None, "schema_version"), (None, "order"), ("order", "encoding"), ("payment", "delimiter"), ("rules", "version")])
def test_rejects_missing_keys_even_for_canonical_nulls(side, key):
    data = payload()
    del (data if side is None else data[side])[key]
    assert_safe_error(lambda: load_dict(data))


@pytest.mark.parametrize("data", [
    b"", b"null", b"[]", b"false", b"1", b"NaN", b"Infinity", b"{", b"{} trailing",
    b'"DO_NOT_REFLECT_JSON"', b'{"DO_NOT_REFLECT_JSON":}', b"\xff", b"\xef\xbb\xbf{}",
    b"[" * 5000 + b"]" * 5000,
    b'{"order":{"a":{"nested":true}}}',
    b'{"schema_version":1,"schema_version":1}',
    b'{"order":{"id_column":1,"id_column":2}}',
])
def test_malformed_deep_duplicate_or_non_object_json_is_safe(data):
    assert_safe_error(lambda: load_template(data))


@pytest.mark.parametrize("literal", ["1.0", "1e0", "NaN", "Infinity", "-Infinity", "9" * 5000])
def test_numbers_are_strict_json_integers(literal):
    data = dump_template(preset()).replace(b'"schema_version": 1', ('"schema_version": ' + literal).encode())
    assert_safe_error(lambda: load_template(data))


@pytest.mark.parametrize("data", [None, "{}", bytearray(b"{}"), memoryview(b"{}")])
def test_only_bytes_are_accepted(data):
    assert_safe_error(lambda: load_template(data))


def test_exact_size_boundary_and_oversized_payload_preflight():
    data = dump_template(preset())
    padded = data + b" " * (MAX_TEMPLATE_BYTES - len(data))
    assert load_template(padded) == preset()
    assert_safe_error(lambda: load_template(padded + b" "), "TEMPLATE_TOO_LARGE")
    assert_safe_error(lambda: load_template(b"\xff" * (MAX_TEMPLATE_BYTES + 1)), "TEMPLATE_TOO_LARGE")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030"])
@pytest.mark.parametrize("delimiter", [",", "\t", ";"])
def test_all_supported_csv_options_round_trip(encoding, delimiter):
    order, payment = (source(side, encoding=encoding, delimiter=delimiter, header_row=2) for side in (Side.ORDER, Side.PAYMENT))
    template = build_template(order, payment, Mapping(1, 2), Mapping(1, 2), "EUR")
    assert template.order.encoding == encoding and template.order.delimiter == delimiter
    assert template.order.header_row == 2
    assert match_template(load_template(dump_template(template)), order, payment)[2] == "EUR"


@pytest.mark.parametrize("change", [
    {"filename": "different.xlsx"}, {"header_row": 2}, {"encoding": "utf-8"}, {"delimiter": ";"}, {"side": Side.PAYMENT},
])
def test_match_rejects_changed_order_structure(change):
    order, payment = inputs()
    template = preset()
    modified = replace(order, spec=replace(order.spec, **change))
    assert_safe_error(lambda: match_template(template, modified, payment), "TEMPLATE_STRUCTURE_MISMATCH")


@pytest.mark.parametrize("headers", [(), (Cell("only", "text"),), (Cell("a", "text"), Cell("b", "text")), tuple(Cell("h", "text") for _ in range(4))])
def test_match_checks_current_width_and_mapping_bounds(headers):
    order, payment = inputs()
    assert_safe_error(lambda: match_template(preset(), order, replace(payment, headers=headers)), "TEMPLATE_STRUCTURE_MISMATCH")


def test_match_rejects_payment_difference_without_mutating_any_input():
    order, payment = inputs()
    template = preset()
    before = dump_template(template), order, payment
    altered = replace(payment, spec=replace(payment.spec, header_row=2))
    assert_safe_error(lambda: match_template(template, order, altered), "TEMPLATE_STRUCTURE_MISMATCH")
    assert before == (dump_template(template), order, payment)


def test_xlsx_irrelevant_csv_options_are_canonical_null_and_not_compared():
    order, payment = inputs()
    changed = replace(payment, spec=replace(payment.spec, encoding="SECRET_unused", delimiter="SECRET_unused"))
    assert match_template(preset(), order, changed) == (Mapping(1, 2), Mapping(3, 2), "CNY")
    template = build_template(order, changed, Mapping(1, 2), Mapping(3, 2), "CNY")
    assert template.payment.encoding is None and template.payment.delimiter is None
    assert b"SECRET_unused" not in dump_template(template)


@pytest.mark.parametrize("mapping", [Mapping(1, 1), Mapping(0, 2), Mapping(1, 4), Mapping(True, 2), Mapping(1, 2.0), None])
def test_build_validates_current_mapping_bounds(mapping):
    order, payment = inputs()
    assert_safe_error(lambda: build_template(order, payment, mapping, Mapping(1, 2), "CNY"))


def test_build_rejects_swapped_roles_and_unsupported_currency():
    order, payment = inputs()
    assert_safe_error(lambda: build_template(payment, order, Mapping(1, 2), Mapping(1, 2), "CNY"))
    assert_safe_error(lambda: build_template(order, payment, Mapping(1, 2), Mapping(1, 2), "JPY"))


@pytest.mark.parametrize("invalid", [
    None, {},
    MappingTemplate(SourceTemplate("csv", 1, 3, 1, 1, "utf-8", ","), SourceTemplate("xlsx", 1, 3, 1, 2, None, None), "CNY"),
])
def test_public_operations_do_not_trust_manually_constructed_templates(invalid):
    order, payment = inputs()
    assert_safe_error(lambda: dump_template(invalid))
    assert_safe_error(lambda: match_template(invalid, order, payment))


def test_full_template_is_validated_before_source_matching():
    invalid = replace(preset(), rules=TemplateRules(tolerance_minor=1))
    assert_safe_error(lambda: match_template(invalid, None, None), "TEMPLATE_INVALID")


def test_build_accepts_default_upper_structural_boundaries():
    order, payment = inputs()
    headers = tuple(Cell("unused-private-header", "text") for _ in range(100))
    order = replace(order, spec=replace(order.spec, header_row=50_001), headers=headers, rows=())
    template = build_template(order, payment, Mapping(99, 100), Mapping(1, 2), "CNY")
    assert template.order.header_row == 50_001 and template.order.column_count == 100
    assert match_template(load_template(dump_template(template)), order, payment)[0] == Mapping(99, 100)
