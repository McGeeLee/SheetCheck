"""Bounded, text-only view models; never change reconciliation values."""
from dataclasses import dataclass
import unicodedata

from .models import Status

PAGE_SIZE = 100
PREVIEW_SIZE = 20
STATUS_LABELS = {
    Status.EXACT_MATCH: "一致", Status.AMOUNT_MISMATCH: "金额差异",
    Status.ONLY_ORDER: "仅订单有", Status.ONLY_PAYMENT: "仅收款有",
    Status.DATA_ISSUE: "数据问题", Status.SKIPPED_EMPTY: "空行跳过",
}
VIEWS = ("全部业务结果", "金额差异", "仅订单有", "仅收款有", "数据问题")


def text_value(value, limit=None):
    if value is None:
        return "（空值）"
    if value == "":
        return "（空字符串）"
    text = str(value)
    # Render controls as visible escapes without changing the source. Arrow and
    # browser strings cannot carry unpaired Unicode surrogates.
    text = "".join(f"\\u{ord(char):04x}" if unicodedata.category(char) in {"Cc", "Cf", "Cs"}
                   and char not in "\n\t" else char for char in text)
    return text if limit is None or len(text) <= limit else text[:limit] + "…（显示已缩短）"


def money(minor):
    if minor is None:
        return "—"
    return f"{'-' if minor < 0 else ''}{abs(minor) // 100}.{abs(minor) % 100:02d}"


def outcome(result):
    counts = result.manifest.status_counts
    has_issues = counts[Status.DATA_ISSUE] > 0
    has_exceptions = any(counts[status] for status in (Status.AMOUNT_MISMATCH, Status.ONLY_ORDER, Status.ONLY_PAYMENT))
    if not result.records:
        return "无可核对业务记录，仍有数据问题" if has_issues else "无可核对业务记录"
    if has_exceptions:
        return "存在差额或缺项，仍有数据问题" if has_issues else "存在差额或缺项"
    return "可核对部分一致，仍有数据问题" if has_issues else "本次可核对部分全部一致"


@dataclass(frozen=True)
class Page:
    items: tuple
    total: int
    number: int
    pages: int


def result_page(result, view, query="", statuses=None, number=1):
    """Filter on the server and send only a single 100-row slice to the UI."""
    if view not in VIEWS:
        raise ValueError("Unknown result view")
    if view == "数据问题":
        matches = [entry for entry in result.ledger if entry.status == Status.DATA_ISSUE
                   and query in str(entry.row.id_raw if entry.row.id_raw is not None else "")]
    else:
        selected = set(STATUS_LABELS) if statuses is None else set(statuses)
        if view != "全部业务结果":
            selected &= {status for status, label in STATUS_LABELS.items() if label == view}
        matches = [record for record in result.records if record.status in selected and query in record.id]
    pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    number = max(1, min(number, pages))
    offset = (number - 1) * PAGE_SIZE
    return Page(tuple(matches[offset:offset + PAGE_SIZE]), len(matches), number, pages)


def preview_rows(source):
    names = [f"{i}: {text_value(cell.value, 64)}" for i, cell in enumerate(source.headers, 1)]
    result = []
    for row in source.rows[:PREVIEW_SIZE]:
        pos = row.position
        values = {"原始行号": str(pos.row), "CSV物理行": f"{pos.physical_start}–{pos.physical_end}" if pos.sheet is None else "—"}
        values.update({name: text_value(cell.value, 240) for name, cell in zip(names, row.cells)})
        result.append(values)
    return result


def business_rows(items):
    return [{"状态": STATUS_LABELS[record.status], "业务编号": record.id,
             "订单金额": money(record.order_minor), "收款金额": money(record.payment_minor),
             "差额：收款减订单": money(record.delta_minor)} for record in items]


def issue_rows(items):
    return [{"状态": "数据问题", "文件角色": "订单" if entry.row.source.side == "order" else "收款",
             "业务编号": text_value(entry.row.id_raw, 240), "原始金额": text_value(entry.row.amount_raw, 240),
             "原始行号": str(entry.row.source.position.row), "全部问题码": " · ".join(entry.problem_codes)}
            for entry in items]
