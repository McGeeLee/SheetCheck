"""Exact one-to-one reconciliation, with symmetric quarantine before matching."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from .audit import assert_invariants, input_metadata, ledger_summary, result_identity, run_fingerprint
from .errors import InputError
from .models import (APP_VERSION, BUSINESS_STATUSES, COVERAGE_WARNING, LedgerEntry, ReconciliationResult, ResultRecord,
                     Rules, RunManifest, Side, Status, ValidatedTable)
from .validators import check_rules


def reconcile(order_table: ValidatedTable, payment_table: ValidatedTable, rules: Rules) -> ReconciliationResult:
    started = datetime.now(timezone.utc).isoformat()
    check_rules(rules)
    tables = (order_table, payment_table)
    if tuple(t.source.spec.side for t in tables) != (Side.ORDER, Side.PAYMENT):
        raise InputError("SIDE_INVALID", "核对需要一份订单表和一份收款表，参数顺序必须正确。")
    if any(t.rules != rules for t in tables):
        raise InputError("RULES_CHANGED", "核对规则与校验时不同，请重新校验两表。")
    duplicate_ids, invalid_ids = set(), set()
    for table in tables:
        counts = Counter(r.normalized_id for r in table.rows if r.normalized_id is not None)
        duplicate_ids.update(i for i, n in counts.items() if n > 1)
        invalid_ids.update(r.normalized_id for r in table.rows if r.problem_codes and r.normalized_id is not None)
    blocked_ids = duplicate_ids | invalid_ids
    maps = [{r.normalized_id: r for r in t.rows if not r.skipped_empty and not r.problem_codes
             and r.normalized_id not in blocked_ids} for t in tables]
    fingerprint = run_fingerprint(tables, rules)
    records, memberships = [], {}
    for identifier in sorted(maps[0].keys() | maps[1].keys()):
        order, payment = maps[0].get(identifier), maps[1].get(identifier)
        delta = payment.amount_minor - order.amount_minor if order and payment else None
        status = ((Status.EXACT_MATCH if delta == 0 else Status.AMOUNT_MISMATCH) if order and payment
                  else (Status.ONLY_ORDER if order else Status.ONLY_PAYMENT))
        order_id = order.source.source_id if order else None
        payment_id = payment.source.source_id if payment else None
        record = ResultRecord(result_identity(fingerprint, identifier, order_id, payment_id), status, identifier,
                              order_id, payment_id, order.amount_minor if order else None,
                              payment.amount_minor if payment else None, delta)
        records.append(record)
        for row in (order, payment):
            if row is not None:
                memberships[row.source.source_id] = record
    records.sort(key=lambda r: (BUSINESS_STATUSES.index(r.status), r.id, r.order_source_id or "", r.payment_source_id or ""))
    ledger = []
    for table in tables:
        for row in table.rows:
            if row.skipped_empty:
                entry = LedgerEntry(row, Status.SKIPPED_EMPTY)
            elif row.problem_codes or row.normalized_id in blocked_ids:
                problems = list(row.problem_codes)
                if row.normalized_id in duplicate_ids:
                    problems.append("DUPLICATE_ID")
                if row.normalized_id in blocked_ids:
                    problems.append("BLOCKED_ID")
                entry = LedgerEntry(row, Status.DATA_ISSUE, problem_codes=tuple(dict.fromkeys(problems)))
            else:
                record = memberships[row.source.source_id]
                entry = LedgerEntry(row, record.status, record.result_id)
            ledger.append(entry)
    ledger.sort(key=lambda e: (list(Side).index(e.row.source.side), e.row.source.position.row, e.source_id))
    counts = {str(s): sum(r.status == s for r in records) for s in BUSINESS_STATUSES}
    counts.update({str(s): sum(e.status == s for e in ledger) for s in (Status.DATA_ISSUE, Status.SKIPPED_EMPTY)})
    risk = any(e.row.normalized_id is None and not e.row.skipped_empty for e in ledger)
    warnings = (COVERAGE_WARNING,) if risk else ()
    manifest = RunManifest(APP_VERSION, rules, fingerprint, uuid4().hex, started, datetime.now(timezone.utc).isoformat(),
                           tuple(input_metadata(t) for t in tables), counts,
                           {str(side): ledger_summary(ledger, side) for side in Side}, risk, warnings)
    result = ReconciliationResult(tables, tuple(records), tuple(ledger), tuple(sorted(blocked_ids)), manifest)
    assert_invariants(result)
    return result
