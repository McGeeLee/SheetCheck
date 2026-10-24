"""Deterministic run fingerprints and fail-closed, independent conservation checks."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json

from .errors import IntegrityError, SheetCheckError
from .models import (APP_VERSION, BUSINESS_STATUSES, COVERAGE_WARNING, ReconciliationResult, Side, SideSummary, Status)


def stable_hash(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def input_metadata(table) -> dict:
    source = table.source
    return {"side": str(source.spec.side), "filename": source.spec.filename,
            "sha256": source.sha256, "sheet": source.spec.sheet,
            "header_row": source.spec.header_row, "encoding": source.spec.encoding,
            "delimiter": source.spec.delimiter, "mapping": asdict(table.mapping),
            "preamble_count": source.preamble_count, "hidden_row_count": source.hidden_row_count,
            "limits": asdict(source.spec.limits)}


def run_fingerprint(tables, rules) -> str:
    # A rename cannot change business IDs; file bytes and parsing choices do.
    inputs = [{k: v for k, v in input_metadata(t).items() if k != "filename"} for t in tables]
    return stable_hash({"app_version": APP_VERSION, "rules": asdict(rules), "inputs": inputs})


def result_identity(fingerprint, identifier, order_source_id, payment_source_id) -> str:
    return stable_hash([fingerprint, identifier, order_source_id, payment_source_id])


def ledger_summary(ledger, side) -> SideSummary:
    rows = [e for e in ledger if e.row.source.side == side]
    business = [e for e in rows if e.status in BUSINESS_STATUSES]
    issues = [e for e in rows if e.status == Status.DATA_ISSUE]
    return SideSummary(len(rows), len(business), len(issues), sum(e.status == Status.SKIPPED_EMPTY for e in rows),
                       sum(e.row.amount_minor for e in business),
                       sum(e.row.amount_minor for e in issues if e.row.amount_minor is not None),
                       sum(e.row.amount_minor is None for e in issues))


def _require(condition, code):
    if not condition:
        raise IntegrityError(code, "完整性校验失败；本次结果不可作为成功核对结果。")


def assert_invariants(result: ReconciliationResult) -> None:
    """Validate both topology and arithmetic; never use Python's disableable assert."""
    try:
        _assert_invariants(result)
    except IntegrityError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, SheetCheckError) as exc:
        raise IntegrityError("AUDIT_STRUCTURE", "结果结构无效，已中止。") from exc


def _assert_invariants(result):
    from .validators import validate
    from .readers import _source_id

    tables, records, ledger, manifest = result.tables, result.records, result.ledger, result.manifest
    _require(len(tables) == 2 and tuple(t.source.spec.side for t in tables) == (Side.ORDER, Side.PAYMENT), "AUDIT_SIDES")
    # Do not trust a cached ValidatedTable if a caller changes raw source metadata.
    for table in tables:
        _require(table.rules == manifest.rules, "AUDIT_RULES")
        _require(validate(table.source, table.mapping, table.rules) == table, "AUDIT_VALIDATION")
        _require(all(r.source.side == table.source.spec.side for r in table.rows), "AUDIT_SOURCE_SIDE")
        _require(all(r.source.position.sheet == table.source.spec.sheet for r in table.rows), "AUDIT_SOURCE_SHEET")
        _require(all(r.source.position.row == table.source.spec.header_row + i
                     for i, r in enumerate(table.rows, 1)), "AUDIT_SOURCE_POSITION")
        _require(table.source.preamble_count == table.source.spec.header_row - 1
                 and table.source.hidden_row_count == sum(r.source.position.hidden for r in table.rows), "AUDIT_SOURCE_METADATA")
        _require(all(r.source.source_id == _source_id(table.source.spec.side, table.source.sha256,
                                                      table.source.spec.sheet, r.source.position)
                     for r in table.rows), "AUDIT_SOURCE_ID")
    originals = [r for table in tables for r in table.rows]
    source_ids = [r.source.source_id for r in originals]
    _require(len(set(source_ids)) == len(source_ids), "AUDIT_SOURCE_DUPLICATE")
    _require(Counter(e.source_id for e in ledger) == Counter(source_ids), "AUDIT_LEDGER_COVERAGE")
    original_by_id = {r.source.source_id: r for r in originals}
    entries = {e.source_id: e for e in ledger}
    _require(all(e.row == original_by_id[e.source_id] for e in ledger), "AUDIT_SOURCE_CHANGED")

    duplicate_ids = set()
    invalid_ids = set()
    for table in tables:
        counts = Counter(r.normalized_id for r in table.rows if r.normalized_id is not None)
        duplicate_ids.update(i for i, n in counts.items() if n > 1)
        invalid_ids.update(r.normalized_id for r in table.rows if r.problem_codes and r.normalized_id is not None)
    blocked = duplicate_ids | invalid_ids
    _require(result.blocked_ids == tuple(sorted(blocked)), "AUDIT_BLOCKED_IDS")
    record_ids = [r.result_id for r in records]
    _require(len(set(record_ids)) == len(record_ids), "AUDIT_RESULT_DUPLICATE")
    used = Counter()
    for record in records:
        _require(record.status in BUSINESS_STATUSES and record.id not in blocked, "AUDIT_RESULT_STATUS")
        order = original_by_id.get(record.order_source_id)
        payment = original_by_id.get(record.payment_source_id)
        _require((record.order_source_id is None) == (order is None), "AUDIT_UNKNOWN_SOURCE")
        _require((record.payment_source_id is None) == (payment is None), "AUDIT_UNKNOWN_SOURCE")
        _require(order is not None or payment is not None, "AUDIT_EMPTY_RESULT")
        for row, side, amount in ((order, Side.ORDER, record.order_minor), (payment, Side.PAYMENT, record.payment_minor)):
            if row is None:
                _require(amount is None, "AUDIT_ABSENT_AMOUNT")
                continue
            _require(row.source.side == side and row.normalized_id == record.id, "AUDIT_PAIR_IDENTITY")
            _require(not row.problem_codes and not row.skipped_empty and row.amount_minor == amount
                     and type(amount) is int, "AUDIT_RESULT_AMOUNT")
            entry = entries[row.source.source_id]
            _require(entry.result_id == record.result_id and entry.status == record.status and not entry.problem_codes,
                     "AUDIT_LEDGER_LINK")
            used[row.source.source_id] += 1
        if order and payment:
            delta = payment.amount_minor - order.amount_minor
            _require(record.delta_minor == delta and type(record.delta_minor) is int, "AUDIT_DELTA")
            _require(record.status == (Status.EXACT_MATCH if delta == 0 else Status.AMOUNT_MISMATCH), "AUDIT_MATCH_STATUS")
        else:
            _require(record.delta_minor is None and record.status == (Status.ONLY_ORDER if order else Status.ONLY_PAYMENT),
                     "AUDIT_SINGLE_SIDE")
        _require(record.result_id == result_identity(manifest.fingerprint, record.id, record.order_source_id,
                                                     record.payment_source_id), "AUDIT_RESULT_ID")
    _require(len({r.id for r in records}) == len(records), "AUDIT_BUSINESS_ID_UNIQUE")
    for entry in ledger:
        row = entry.row
        if row.skipped_empty:
            _require(entry.status == Status.SKIPPED_EMPTY and not entry.problem_codes and entry.result_id is None,
                     "AUDIT_EMPTY_ROW")
            _require(used[entry.source_id] == 0, "AUDIT_EMPTY_USED")
        elif row.problem_codes or row.normalized_id in blocked:
            required = set(row.problem_codes)
            if row.normalized_id in duplicate_ids:
                required.add("DUPLICATE_ID")
            if row.normalized_id in blocked:
                required.add("BLOCKED_ID")
            _require(entry.status == Status.DATA_ISSUE and set(entry.problem_codes) == required
                     and len(entry.problem_codes) == len(required) and entry.result_id is None
                     and used[entry.source_id] == 0, "AUDIT_PROBLEM_ROW")
        else:
            _require(used[entry.source_id] == 1, "AUDIT_BUSINESS_MEMBERSHIP")
    expected_counts = {str(s): sum(r.status == s for r in records) for s in BUSINESS_STATUSES}
    expected_counts.update({str(s): sum(e.status == s for e in ledger) for s in (Status.DATA_ISSUE, Status.SKIPPED_EMPTY)})
    _require(manifest.status_counts == expected_counts, "AUDIT_COUNTS")
    _require(all(type(n) is int for n in manifest.status_counts.values()), "AUDIT_COUNT_TYPES")
    _require(set(manifest.summaries) == {str(s) for s in Side}, "AUDIT_SUMMARY_SIDES")
    for side in Side:
        summary = ledger_summary(ledger, side)
        _require(manifest.summaries[str(side)] == summary, "AUDIT_TOTALS")
        _require(all(type(n) is int for n in asdict(manifest.summaries[str(side)]).values()), "AUDIT_TOTAL_TYPES")
        paired = expected_counts[str(Status.EXACT_MATCH)] + expected_counts[str(Status.AMOUNT_MISMATCH)]
        singles = expected_counts[str(Status.ONLY_ORDER if side == Side.ORDER else Status.ONLY_PAYMENT)]
        _require(summary.input_count == paired + singles + summary.data_issue_count + summary.skipped_empty_count,
                 "AUDIT_CONSERVATION")
        record_total = sum((r.order_minor if side == Side.ORDER else r.payment_minor) or 0 for r in records)
        _require(summary.valid_total_minor == record_total, "AUDIT_RECORD_TOTAL")
    risk = any(r.normalized_id is None and not r.skipped_empty for r in originals)
    _require(manifest.unidentifiable_id_risk is risk, "AUDIT_COVERAGE_RISK")
    _require(manifest.warnings == ((COVERAGE_WARNING,) if risk else ()), "AUDIT_COVERAGE_WARNING")
    _require(manifest.inputs == tuple(input_metadata(t) for t in tables), "AUDIT_INPUT_METADATA")
    _require(manifest.app_version == APP_VERSION and manifest.fingerprint == run_fingerprint(tables, manifest.rules),
             "AUDIT_FINGERPRINT")
    _require(tuple(records) == tuple(sorted(records, key=lambda r: (BUSINESS_STATUSES.index(r.status), r.id,
                                                                  r.order_source_id or "", r.payment_source_id or ""))),
             "AUDIT_RESULT_ORDER")
    _require(tuple(ledger) == tuple(sorted(ledger, key=lambda e: (list(Side).index(e.row.source.side),
                                                                e.row.source.position.row, e.source_id))), "AUDIT_LEDGER_ORDER")
