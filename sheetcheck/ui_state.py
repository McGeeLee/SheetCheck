"""Per-session workflow state without Streamlit, global caches, or file I/O.

The UI must synchronize all inputs and configuration on every rerun, before
rendering a result or download. A change drops every derived result immediately;
only the unchanged side's parsed table may be reused inside this instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock

from .engine import reconcile
from .errors import InputError
from .models import FileSpec, Mapping, ReconciliationResult, Rules, Side, SourceTable
from .readers import read_source
from .report import export_xlsx, report_filename
from .validators import check_rules, validate


class Stage(StrEnum):
    EMPTY = "EMPTY"
    IMPORTED = "IMPORTED"
    MAPPED = "MAPPED"
    VALIDATED = "VALIDATED"
    RECONCILED = "RECONCILED"
    EXPORTED = "EXPORTED"


@dataclass(frozen=True, slots=True)
class InputSelection:
    data: bytes
    spec: FileSpec


def _empty_sides() -> dict:
    return {side: None for side in Side}


@dataclass(slots=True)
class Workflow:
    """Session-owned references; callers update through the methods below.

    ``reset`` releases references. It does not promise secure erasure of RAM,
    swap, or a browser's downloaded files. No object is shared between sessions.
    """

    selections: dict[Side, InputSelection | None] = field(default_factory=_empty_sides)
    sources: dict[Side, SourceTable] = field(default_factory=dict)
    mappings: dict[Side, Mapping | None] = field(default_factory=_empty_sides)
    rules: Rules = field(default_factory=Rules)
    stage: Stage = Stage.EMPTY
    result: ReconciliationResult | None = None
    report_bytes: bytes | None = None
    report_name: str | None = None
    _revision: int = field(default=0, init=False, repr=False)
    _lock: object = field(default_factory=RLock, init=False, repr=False, compare=False)
    _report_result: ReconciliationResult | None = field(default=None, init=False, repr=False)
    _source_operations: dict[Side, int] = field(default_factory=dict, init=False, repr=False)

    def _clear_report(self) -> None:
        self.report_bytes = None
        self.report_name = None
        self._report_result = None

    def _clear_result(self) -> None:
        self.result = None
        self._clear_report()

    def _require_revision(self, revision: int) -> None:
        # Call only while holding the instance lock. A stale task must never
        # clear or overwrite a newer task's inputs, result, stage, or report.
        if self._revision != revision:
            raise InputError("OPERATION_STALE", "输入或核对设置已变化，本次旧操作已停止；请使用当前输入重新运行。")

    def _require_source_operation(self, revision: int, side: Side, operation: int) -> None:
        self._require_revision(revision)
        if self._source_operations.get(side) != operation:
            raise InputError("OPERATION_STALE", "已开始新的读入操作，本次旧操作已停止；请使用当前输入重新运行。")

    def invalidate(self) -> None:
        """Revoke old success and in-flight work in a widget change callback."""
        with self._lock:
            self._revision += 1
            self._clear_result()
            self.stage = self._base_stage()

    def _mapped(self) -> bool:
        for side in Side:
            source, mapping = self.sources.get(side), self.mappings.get(side)
            if source is None or not isinstance(mapping, Mapping):
                return False
            columns = (mapping.id_column, mapping.amount_column)
            if (any(type(column) is not int or not 1 <= column <= len(source.headers) for column in columns)
                    or columns[0] == columns[1]):
                return False
        return True

    def _base_stage(self) -> Stage:
        if self._mapped():
            return Stage.MAPPED
        return Stage.IMPORTED if self.sources else Stage.EMPTY

    @property
    def ready(self) -> bool:
        with self._lock:
            if not self._mapped():
                return False
            try:
                check_rules(self.rules)
            except InputError:
                return False
            return True

    def sync_inputs(self, selections: dict[Side, InputSelection | None]) -> bool:
        """Synchronize both sides, invalidating on bytes or any FileSpec change.

        An omitted side means removal. A bad selection also removes stale
        success state before raising a safe error for the UI.
        """
        with self._lock:
            normalized = {side: selections.get(side) for side in Side}
            for side, selection in normalized.items():
                if selection is not None and (
                    not isinstance(selection, InputSelection)
                    or not isinstance(selection.data, bytes)
                    or not isinstance(selection.spec, FileSpec)
                    or selection.spec.side != side
                ):
                    self._revision += 1
                    self._clear_result()
                    self.sources.pop(side, None)
                    self.mappings[side] = None
                    self.selections[side] = None
                    self.stage = self._base_stage()
                    raise InputError("INPUT_SELECTION_INVALID", "文件选择与订单/收款角色不一致，请重新选择该侧文件。")
            changed = [side for side in Side if normalized[side] != self.selections[side]]
            if not changed:
                return False
            self._revision += 1
            self._clear_result()
            for side in changed:
                self.selections[side] = normalized[side]
                self.sources.pop(side, None)
                self.mappings[side] = None
            self.stage = self._base_stage()
            return True

    def get_source(self, side: Side) -> SourceTable:
        """Parse outside the lock; commit only if this selection is still current."""
        with self._lock:
            if side not in Side:
                raise InputError("FILE_SIDE_INVALID", "文件角色必须为订单或收款。")
            selection = self.selections.get(side)
            if selection is None:
                self._clear_result()
                self.sources.pop(side, None)
                self.stage = self._base_stage()
                raise InputError("INPUT_REQUIRED", "请先选择该侧的 CSV 或 XLSX 文件。")
            if side in self.sources:
                return self.sources[side]
            self._clear_result()
            revision = self._revision
            operation = self._source_operations.get(side, 0) + 1
            self._source_operations[side] = operation
        try:
            source = read_source(selection.data, selection.spec)
        except Exception:
            with self._lock:
                self._require_source_operation(revision, side, operation)
                self.sources.pop(side, None)
                self.stage = self._base_stage()
            raise
        with self._lock:
            self._require_source_operation(revision, side, operation)
            self.sources[side] = source
            self.stage = self._base_stage()
            return source

    def configure(self, mappings: dict[Side, Mapping | None], rules: Rules) -> bool:
        """Set complete current choices; all rule changes revoke old reports."""
        with self._lock:
            normalized = {side: mappings.get(side) for side in Side}
            if not isinstance(rules, Rules) or any(
                mapping is not None and not isinstance(mapping, Mapping) for mapping in normalized.values()
            ):
                self._revision += 1
                self._clear_result()
                self.mappings = {side: mapping if isinstance(mapping, Mapping) else None
                                 for side, mapping in normalized.items()}
                self.rules = rules if isinstance(rules, Rules) else Rules()
                self.stage = self._base_stage()
                raise InputError("CONFIGURATION_INVALID", "请选择有效字段映射和核对规则。")
            changed = normalized != self.mappings or rules != self.rules
            if changed:
                self._revision += 1
                self._clear_result()
                self.mappings = normalized
                self.rules = rules
                self.stage = self._base_stage()
            return changed

    def run(self) -> ReconciliationResult:
        """Reconcile a fixed snapshot; only the newest operation may commit."""
        with self._lock:
            # Also supersedes earlier runs/exports for otherwise identical input.
            self._revision += 1
            revision = self._revision
            self._clear_result()
            self.stage = self._base_stage()
            if not self._mapped():
                raise InputError("MAPPING_REQUIRED", "请先读入两份文件，并为每侧选择不同的编号列和金额列。")
            sources, mappings, rules = dict(self.sources), dict(self.mappings), self.rules
            check_rules(rules)
        try:
            tables = tuple(validate(sources[side], mappings[side], rules) for side in Side)
        except Exception:
            with self._lock:
                self._require_revision(revision)
                self.stage = Stage.IMPORTED
            raise
        with self._lock:
            self._require_revision(revision)
            self.stage = Stage.VALIDATED
        try:
            result = reconcile(tables[0], tables[1], rules)
        except Exception:
            with self._lock:
                self._require_revision(revision)
            raise
        with self._lock:
            self._require_revision(revision)
            self.result = result
            self.stage = Stage.RECONCILED
            return result

    def prepare_report(self) -> bytes:
        """Audit one captured result; an invalidated export cannot publish bytes."""
        with self._lock:
            if self.result is None:
                self._clear_report()
                self.stage = self._base_stage()
                raise InputError("RESULT_REQUIRED", "当前输入尚未完成核对，请先运行核对。")
            if self.report_bytes is not None and self._report_result is self.result:
                return self.report_bytes
            # A newer export supersedes a concurrent older export too.
            self._revision += 1
            revision, result = self._revision, self.result
            self._clear_report()
            self.stage = Stage.RECONCILED
        try:
            report = export_xlsx(result)
            name = report_filename(result)
        except Exception:
            with self._lock:
                self._require_revision(revision)
            raise
        with self._lock:
            self._require_revision(revision)
            if self.result is not result:
                raise InputError("REPORT_STALE", "输入已变化，请重新核对并生成报告。")
            self.report_bytes, self.report_name = report, name
            self._report_result = result
            self.stage = Stage.EXPORTED
            return report

    def report_for_run(self, run_id: str) -> bytes:
        """Atomically check current run identity and obtain its audited report.

        Bytes already handed to a download are outside this session's control;
        later calls after invalidation/reset are rejected.
        """
        with self._lock:
            if (self.result is None or self.result.manifest.run_id != run_id
                    or self.report_bytes is None or self._report_result is not self.result):
                raise InputError("REPORT_STALE", "输入已变化，请重新核对并生成报告。")
            return self.report_bytes

    def reset(self) -> None:
        with self._lock:
            self._revision += 1
            self._clear_result()
            self.selections = _empty_sides()
            self.sources = {}
            self.mappings = _empty_sides()
            self.rules = Rules()
            self._source_operations = {}
            self.stage = Stage.EMPTY
