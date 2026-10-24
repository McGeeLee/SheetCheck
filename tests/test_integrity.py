"""Adversarial checks against forged results, independent of successful pairing.

The fixture is deliberately small enough to recount by hand. These tests mutate
one part of a completed result and require the public audit boundary to fail
closed, rather than treating the kernel's own successful output as proof.
"""
from dataclasses import replace

import pytest

from sheetcheck.audit import assert_invariants
from sheetcheck.engine import reconcile
from sheetcheck.errors import IntegrityError
from sheetcheck.models import FileSpec, Mapping, Rules, Side, Status
from sheetcheck.readers import read_source
from sheetcheck.validators import validate


@pytest.fixture
def checked_result():
    rules = Rules(
        currency="CNY",
        period="2026-10",
        same_currency_confirmed=True,
        same_period_confirmed=True,
    )
    order_data = (
        b"id,amount\n"
        b"A100,10.00\n"
        b"A200,20.00\n"
        b"A300,0.00\n"
        b"BLOCKED,1.00\n"
        b"BLOCKED,BAD\n"
        b",5.00\n"
        b",\n"
    )
    payment_data = (
        b"id,amount\n"
        b"A100,10.00\n"
        b"A200,21.00\n"
        b"A400,0.00\n"
        b"BLOCKED,2.00\n"
    )
    orders = validate(
        read_source(order_data, FileSpec("orders.csv", Side.ORDER)),
        Mapping(1, 2),
        rules,
    )
    payments = validate(
        read_source(payment_data, FileSpec("payments.csv", Side.PAYMENT)),
        Mapping(1, 2),
        rules,
    )
    return reconcile(orders, payments, rules)


def replace_record(result, record_id, **changes):
    return replace(
        result,
        records=tuple(
            replace(record, **changes) if record.id == record_id else record
            for record in result.records
        ),
    )


def replace_ledger(result, entry, replacement):
    return replace(
        result,
        ledger=tuple(replacement if item is entry else item for item in result.ledger),
    )


def test_audit_baseline_has_manually_counted_rows(checked_result):
    result = checked_result
    assert_invariants(result)
    assert len(result.ledger) == 11
    assert len(result.records) == 4
    assert result.blocked_ids == ("BLOCKED",)
    order = result.manifest.summaries[Side.ORDER]
    payment = result.manifest.summaries[Side.PAYMENT]
    assert (order.input_count, order.business_count, order.data_issue_count, order.skipped_empty_count) == (7, 3, 3, 1)
    assert (payment.input_count, payment.business_count, payment.data_issue_count, payment.skipped_empty_count) == (4, 3, 1, 0)
    assert (order.valid_total_minor, payment.valid_total_minor) == (3000, 3100)
    assert (order.issue_parseable_minor, payment.issue_parseable_minor) == (600, 200)
    assert (order.issue_unparseable_count, payment.issue_unparseable_count) == (1, 0)


@pytest.mark.parametrize("mode", ["missing", "duplicated", "replaced_with_duplicate"])
def test_audit_requires_exactly_one_ledger_entry_per_source(checked_result, mode):
    ledger = checked_result.ledger
    if mode == "missing":
        ledger = ledger[1:]
    elif mode == "duplicated":
        ledger = ledger + (ledger[0],)
    else:
        ledger = (ledger[1],) + ledger[1:]
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, ledger=ledger))


@pytest.mark.parametrize("mode", ["missing", "duplicated"])
def test_audit_detects_missing_or_duplicate_business_result(checked_result, mode):
    records = checked_result.records
    records = records[1:] if mode == "missing" else records + (records[0],)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, records=records))


@pytest.mark.parametrize(
    ("record_id", "changes"),
    [
        ("A100", {"delta_minor": 1}),
        ("A100", {"status": Status.AMOUNT_MISMATCH}),
        ("A200", {"status": Status.EXACT_MATCH}),
        ("A200", {"delta_minor": -100}),
        ("A100", {"id": "ALTERED"}),
        ("A100", {"order_minor": 999}),
        ("A100", {"payment_minor": 999}),
        ("A100", {"order_source_id": None}),
        ("A100", {"payment_source_id": None}),
        ("A100", {"result_id": "forged-result-id"}),
        ("A300", {"payment_minor": 0}),
        ("A400", {"order_minor": 0}),
        ("A300", {"delta_minor": 0}),
    ],
)
def test_audit_rejects_incorrect_record_semantics(checked_result, record_id, changes):
    with pytest.raises(IntegrityError):
        assert_invariants(replace_record(checked_result, record_id, **changes))


def test_audit_rejects_wrong_opposite_source(checked_result):
    other = next(item for item in checked_result.records if item.id == "A200")
    with pytest.raises(IntegrityError):
        assert_invariants(
            replace_record(checked_result, "A100", payment_source_id=other.payment_source_id)
        )


def test_audit_rejects_source_on_wrong_side(checked_result):
    exact = next(item for item in checked_result.records if item.id == "A100")
    with pytest.raises(IntegrityError):
        assert_invariants(
            replace_record(
                checked_result,
                "A100",
                order_source_id=exact.payment_source_id,
                payment_source_id=exact.order_source_id,
            )
        )


@pytest.mark.parametrize("field", ["status", "result_id", "problem_codes"])
def test_audit_rejects_forged_ledger_membership(checked_result, field):
    entry = next(item for item in checked_result.ledger if item.status == Status.EXACT_MATCH)
    bad_value = {
        "status": Status.DATA_ISSUE,
        "result_id": "unknown-result-id",
        "problem_codes": ("AMOUNT_FORMAT",),
    }[field]
    bad = replace_ledger(checked_result, entry, replace(entry, **{field: bad_value}))
    with pytest.raises(IntegrityError):
        assert_invariants(bad)


def test_audit_rejects_dropped_problem_codes(checked_result):
    entry = next(item for item in checked_result.ledger if item.status == Status.DATA_ISSUE)
    with pytest.raises(IntegrityError):
        assert_invariants(replace_ledger(checked_result, entry, replace(entry, problem_codes=())))


@pytest.mark.parametrize("field", ["id_raw", "amount_raw", "normalized_id", "amount_minor", "raw_types"])
def test_audit_detects_ledger_row_detached_from_validated_source(checked_result, field):
    entry = next(item for item in checked_result.ledger if item.status == Status.EXACT_MATCH)
    bad_value = {
        "id_raw": "different-source-value",
        "amount_raw": "999.99",
        "normalized_id": "different-id",
        "amount_minor": 99999,
        "raw_types": ("number", "text"),
    }[field]
    changed_row = replace(entry.row, **{field: bad_value})
    with pytest.raises(IntegrityError):
        assert_invariants(replace_ledger(checked_result, entry, replace(entry, row=changed_row)))


def test_audit_detects_forged_source_position(checked_result):
    entry = checked_result.ledger[0]
    source = entry.row.source
    changed_source = replace(source, position=replace(source.position, row=999))
    changed_row = replace(entry.row, source=changed_source)
    with pytest.raises(IntegrityError):
        assert_invariants(replace_ledger(checked_result, entry, replace(entry, row=changed_row)))


@pytest.mark.parametrize("blocked_ids", [(), ("A100", "BLOCKED"), ("BLOCKED", "BLOCKED")])
def test_audit_rederives_blocked_ids(checked_result, blocked_ids):
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, blocked_ids=blocked_ids))


def test_audit_prevents_blocked_source_leaking_into_business(checked_result):
    blocked = next(
        entry for entry in checked_result.ledger
        if entry.row.normalized_id == "BLOCKED" and entry.row.source.side == Side.PAYMENT
    )
    # An apparently valid, parseable amount on the other side of a duplicate
    # must never become a single-sided business result.
    with pytest.raises(IntegrityError):
        assert_invariants(
            replace_record(
                checked_result,
                "A400",
                id="BLOCKED",
                payment_source_id=blocked.source_id,
                payment_minor=200,
            )
        )


@pytest.mark.parametrize(
    "field",
    [
        "input_count", "business_count", "data_issue_count", "skipped_empty_count",
        "valid_total_minor", "issue_parseable_minor", "issue_unparseable_count",
    ],
)
def test_audit_recomputes_each_side_summary(checked_result, field):
    summaries = dict(checked_result.manifest.summaries)
    current = summaries[Side.ORDER]
    summaries[Side.ORDER] = replace(current, **{field: getattr(current, field) + 1})
    manifest = replace(checked_result.manifest, summaries=summaries)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("valid_total_minor", 3000.0), ("business_count", 3.0), ("skipped_empty_count", True)],
)
def test_audit_requires_real_integers_in_summaries(checked_result, field, replacement):
    summaries = dict(checked_result.manifest.summaries)
    summaries[Side.ORDER] = replace(summaries[Side.ORDER], **{field: replacement})
    manifest = replace(checked_result.manifest, summaries=summaries)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


def test_audit_recomputes_status_counts(checked_result):
    counts = dict(checked_result.manifest.status_counts)
    key = next(iter(counts))
    counts[key] += 1
    manifest = replace(checked_result.manifest, status_counts=counts)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


@pytest.mark.parametrize("replacement", [True, 1.0])
def test_audit_requires_real_integers_in_status_counts(checked_result, replacement):
    counts = dict(checked_result.manifest.status_counts)
    assert counts[Status.EXACT_MATCH] == 1
    counts[Status.EXACT_MATCH] = replacement
    manifest = replace(checked_result.manifest, status_counts=counts)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


def test_audit_rejects_forged_fingerprint(checked_result):
    manifest = replace(checked_result.manifest, fingerprint="0" * 64)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


def test_audit_recomputes_unidentifiable_id_warning(checked_result):
    assert checked_result.manifest.unidentifiable_id_risk is True
    manifest = replace(checked_result.manifest, unidentifiable_id_risk=False)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


def test_audit_requires_human_readable_coverage_warning(checked_result):
    assert checked_result.manifest.unidentifiable_id_risk is True
    assert checked_result.manifest.warnings
    manifest = replace(checked_result.manifest, warnings=())
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


def test_audit_rejects_changed_manifest_rules(checked_result):
    rules = replace(checked_result.manifest.rules, currency="USD")
    manifest = replace(checked_result.manifest, rules=rules)
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


def test_audit_detects_changed_source_hash(checked_result):
    orders, payments = checked_result.tables
    changed_orders = replace(orders, source=replace(orders.source, sha256="0" * 64))
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, tables=(changed_orders, payments)))


def test_audit_detects_changed_source_mapping(checked_result):
    orders, payments = checked_result.tables
    changed_orders = replace(orders, mapping=Mapping(2, 1))
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, tables=(changed_orders, payments)))


def test_audit_detects_changed_source_table_metadata(checked_result):
    orders, payments = checked_result.tables
    changed_spec = replace(orders.source.spec, header_row=2)
    changed_orders = replace(orders, source=replace(orders.source, spec=changed_spec))
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, tables=(changed_orders, payments)))


def test_audit_requires_validation_for_every_raw_source_row(checked_result):
    orders, payments = checked_result.tables
    changed_orders = replace(orders, rows=orders.rows[:-1])
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, tables=(changed_orders, payments)))


def test_audit_rejects_manifest_input_metadata_tampering(checked_result):
    original = checked_result.manifest.inputs
    changed_first = dict(original[0])
    # Mutating an existing field avoids a test that merely invents an ignored
    # extension key; each manifest input must describe its actual source table.
    field = next(iter(changed_first))
    changed_first[field] = "forged-input-metadata"
    manifest = replace(checked_result.manifest, inputs=(changed_first, *original[1:]))
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, manifest=manifest))


@pytest.mark.parametrize("changed_field", ["row", "sheet"])
def test_audit_rederives_source_id_after_coordinated_position_tampering(checked_result, changed_field):
    """Internal equality alone cannot prove that a source ID owns its location.

    Change the same position in raw rows, validated rows and ledger together.
    Retaining the old source ID must still fail the audit. The empty last source
    row avoids incidentally invalidating a business reference or record sort.
    """
    orders, payments = checked_result.tables
    source = orders.source.rows[-1]
    assert orders.rows[-1].skipped_empty
    if changed_field == "row":
        changed_position = replace(
            source.position,
            row=source.position.row + 1,
            physical_start=source.position.physical_start + 1,
            physical_end=source.position.physical_end + 1,
        )
    else:
        changed_position = replace(source.position, sheet="forged-sheet")
    changed_source = replace(source, position=changed_position)
    changed_row = replace(orders.rows[-1], source=changed_source)
    changed_table = replace(
        orders,
        source=replace(orders.source, rows=(*orders.source.rows[:-1], changed_source)),
        rows=(*orders.rows[:-1], changed_row),
    )
    ledger = tuple(
        replace(entry, row=changed_row) if entry.source_id == source.source_id else entry
        for entry in checked_result.ledger
    )
    with pytest.raises(IntegrityError):
        assert_invariants(replace(checked_result, tables=(changed_table, payments), ledger=ledger))
