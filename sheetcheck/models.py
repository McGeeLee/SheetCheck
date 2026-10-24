"""Immutable data contracts for the UI-independent SheetCheck v1 kernel."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

APP_VERSION = "1.1.0"
RULES_VERSION = "v1"
MAX_AMOUNT_MINOR = 99_999_999_999
COVERAGE_WARNING = "存在无法识别编号的问题行；缺项结果需要人工复核，坏行可能隐藏对方记录。"


class Side(StrEnum):
    ORDER = "order"
    PAYMENT = "payment"


class Status(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    ONLY_ORDER = "ONLY_ORDER"
    ONLY_PAYMENT = "ONLY_PAYMENT"
    DATA_ISSUE = "DATA_ISSUE"
    SKIPPED_EMPTY = "SKIPPED_EMPTY"


BUSINESS_STATUSES = tuple(Status)[:4]


@dataclass(frozen=True, slots=True)
class Limits:
    max_file_bytes: int = 10 * 1024 * 1024
    max_records: int = 50_000
    max_columns: int = 100
    max_uncompressed_bytes: int = 100 * 1024 * 1024
    max_zip_entries: int = 2_000
    max_compression_ratio: int = 200


@dataclass(frozen=True, slots=True)
class FileSpec:
    filename: str
    side: Side
    sheet: str | None = None
    header_row: int = 1
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    limits: Limits = field(default_factory=Limits)


@dataclass(frozen=True, slots=True)
class Cell:
    value: Any
    kind: str  # text, number, date, boolean, error, formula, empty


@dataclass(frozen=True, slots=True)
class SourcePosition:
    row: int  # CSV logical record number (including header) or Excel row
    sheet: str | None = None
    physical_start: int | None = None
    physical_end: int | None = None
    hidden: bool = False


@dataclass(frozen=True, slots=True)
class Region:
    min_row: int
    max_row: int
    min_col: int
    max_col: int


@dataclass(frozen=True, slots=True)
class SourceRow:
    source_id: str
    side: Side
    position: SourcePosition
    cells: tuple[Cell, ...]


@dataclass(frozen=True, slots=True)
class SourceTable:
    spec: FileSpec
    sha256: str
    headers: tuple[Cell, ...]
    rows: tuple[SourceRow, ...]
    preamble_count: int = 0
    merged_regions: tuple[Region, ...] = ()
    formula_regions: tuple[Region, ...] = ()
    hidden_row_count: int = 0

    @property
    def column_labels(self) -> tuple[str, ...]:
        return tuple(f"{i}: {c.value if c.value is not None else ''}" for i, c in enumerate(self.headers, 1))


@dataclass(frozen=True, slots=True)
class Mapping:
    id_column: int  # one-based; never resolve ambiguous header names
    amount_column: int


@dataclass(frozen=True, slots=True)
class Rules:
    currency: str = "CNY"
    period: str = ""
    same_currency_confirmed: bool = False
    same_period_confirmed: bool = False
    version: str = RULES_VERSION
    tolerance_minor: int = 0
    minor_digits: int = 2
    max_amount_minor: int = MAX_AMOUNT_MINOR


@dataclass(frozen=True, slots=True)
class ValidatedRow:
    source: SourceRow
    id_raw: Any
    amount_raw: Any
    raw_types: tuple[str, str]
    normalized_id: str | None
    amount_minor: int | None
    problem_codes: tuple[str, ...] = ()
    normalization_notes: tuple[str, ...] = ()
    skipped_empty: bool = False


@dataclass(frozen=True, slots=True)
class ValidatedTable:
    source: SourceTable
    mapping: Mapping
    rules: Rules
    rows: tuple[ValidatedRow, ...]


@dataclass(frozen=True, slots=True)
class ResultRecord:
    result_id: str
    status: Status
    id: str
    order_source_id: str | None
    payment_source_id: str | None
    order_minor: int | None
    payment_minor: int | None
    delta_minor: int | None


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    row: ValidatedRow
    status: Status
    result_id: str | None = None
    problem_codes: tuple[str, ...] = ()

    @property
    def source_id(self) -> str:
        return self.row.source.source_id


@dataclass(frozen=True, slots=True)
class SideSummary:
    input_count: int
    business_count: int
    data_issue_count: int
    skipped_empty_count: int
    valid_total_minor: int
    issue_parseable_minor: int
    issue_unparseable_count: int


@dataclass(frozen=True, slots=True)
class RunManifest:
    app_version: str
    rules: Rules
    fingerprint: str
    run_id: str
    started_at: str
    finished_at: str
    inputs: tuple[dict, ...]
    status_counts: dict[str, int]
    summaries: dict[str, SideSummary]
    unidentifiable_id_risk: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    tables: tuple[ValidatedTable, ValidatedTable]
    records: tuple[ResultRecord, ...]
    ledger: tuple[LedgerEntry, ...]
    blocked_ids: tuple[str, ...]
    manifest: RunManifest
