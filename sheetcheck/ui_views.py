"""Bounded, text-only view models; never change reconciliation values."""
from dataclasses import dataclass
import unicodedata

from .errors import PROBLEM_HELP
from .models import Status
from .ui_i18n import translate

PAGE_SIZE = 100
PREVIEW_SIZE = 20
STATUS_LABELS = {
    Status.EXACT_MATCH: "一致", Status.AMOUNT_MISMATCH: "金额差异",
    Status.ONLY_ORDER: "仅订单有", Status.ONLY_PAYMENT: "仅收款有",
    Status.DATA_ISSUE: "数据问题", Status.SKIPPED_EMPTY: "空行跳过",
}
VIEWS = ("全部业务结果", "金额差异", "仅订单有", "仅收款有", "数据问题")
PROBLEM_LABELS = {
    "ID_MISSING": "编号为空",
    "ID_NOT_TEXT": "编号不是文本",
    "ID_WHITESPACE": "编号首尾含空白",
    "ID_CONTROL_CHARACTER": "编号含控制或不可见字符",
    "ID_TOO_LONG": "编号超过长度限制",
    "AMOUNT_MISSING": "金额为空",
    "AMOUNT_TYPE": "金额类型不支持",
    "AMOUNT_FORMAT": "金额格式不符合要求",
    "AMOUNT_PRECISION": "金额小数位超过两位",
    "AMOUNT_LIMIT": "金额超过单笔上限",
    "DUPLICATE_ID": "同编号在至少一张表中重复",
    "BLOCKED_ID": "同编号关联行有问题，本行一并隔离",
}


def issue_explanation(codes, language="zh"):
    """Describe issue codes without reflecting unknown codes or business data."""
    labels = dict.fromkeys(translate(PROBLEM_LABELS.get(code, "未识别的数据问题"), language) for code in codes)
    return ("; " if language == "en" else "；").join(labels) if labels else translate("未提供问题说明，请查看问题码与来源详情。", language)


def issue_next_steps(codes, language="zh"):
    """Keep all distinct fixed repair suggestions in the source code order."""
    fallback = translate("请查看全部问题码与来源详情，核实原始记录。", language)
    suggestions = dict.fromkeys(translate(PROBLEM_HELP.get(code, fallback), language) for code in codes)
    return " ".join(suggestions) if suggestions else fallback


def text_value(value, limit=None, language="zh"):
    if value is None:
        return translate("（空值）", language)
    if value == "":
        return translate("（空字符串）", language)
    text = str(value)
    # Render controls as visible escapes without changing the source. Arrow and
    # browser strings cannot carry unpaired Unicode surrogates.
    text = "".join(f"\\u{ord(char):04x}" if unicodedata.category(char) in {"Cc", "Cf", "Cs"}
                   and char not in "\n\t" else char for char in text)
    return text if limit is None or len(text) <= limit else text[:limit] + translate("…（显示已缩短）", language)


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


def preview_rows(source, language="zh"):
    names = [f"{i}: {text_value(cell.value, 64, language)}" for i, cell in enumerate(source.headers, 1)]
    result = []
    for row in source.rows[:PREVIEW_SIZE]:
        pos = row.position
        values = {translate("原始行号", language): str(pos.row), translate("CSV物理行", language): f"{pos.physical_start}–{pos.physical_end}" if pos.sheet is None else "—"}
        values.update({name: text_value(cell.value, 240, language) for name, cell in zip(names, row.cells)})
        result.append(values)
    return result


def business_rows(items, language="zh"):
    rows = [{"状态": translate(STATUS_LABELS[record.status], language), "业务编号": record.id,
             "订单金额": money(record.order_minor), "收款金额": money(record.payment_minor),
             "差额：收款减订单": money(record.delta_minor)} for record in items]
    return [{translate(key, language): value for key, value in row.items()} for row in rows]


def issue_rows(items, language="zh"):
    rows = [{"状态": translate("数据问题", language), "文件角色": translate("订单" if entry.row.source.side == "order" else "收款", language),
             "业务编号": text_value(entry.row.id_raw, 240, language), "原始金额": text_value(entry.row.amount_raw, 240, language),
             "原始行号": str(entry.row.source.position.row),
             "问题说明": issue_explanation(entry.problem_codes, language),
             "处理建议": issue_next_steps(entry.problem_codes, language),
             "全部问题码": " · ".join(dict.fromkeys(entry.problem_codes))}
            for entry in items]
    return [{translate(key, language): value for key, value in row.items()} for row in rows]
