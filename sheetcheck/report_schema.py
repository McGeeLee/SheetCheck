"""Versioned static workbook schema. Column keys are stable; titles are user-facing."""
from dataclasses import dataclass

REPORT_VERSION = "m2-v1"
TEXT_ESCAPE_PREFIX = "SC_ESC:"
SHEET_NAMES = ("运行说明", "业务结果", "异常明细", "数据问题", "源行账本")
RUN_HEADERS = ("分区", "字段", "值", "说明")


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    title: str
    width: float = 22


BUSINESS_COLUMNS = (
    Column("status", "状态", 25), Column("id", "业务编号", 24),
    Column("order_amount", "订单金额（两位小数）", 23), Column("payment_amount", "收款金额（两位小数）", 23),
    Column("delta_amount", "差额：收款减订单", 23),
    Column("order_minor", "订单金额（分）", 20), Column("payment_minor", "收款金额（分）", 20),
    Column("delta_minor", "差额（分）", 18), Column("result_id", "result_id", 22),
) + tuple(Column(f"{side}_{key}", f"{title}{label}", width) for side, title in (("order", "订单"), ("payment", "收款"))
          for key, label, width in (("source_id", " source_id", 22), ("filename", "文件名", 25), ("sheet", "工作表", 18),
                                   ("row", "源行 / CSV逻辑记录", 24), ("physical_start", "CSV物理起始行", 22),
                                   ("physical_end", "CSV物理结束行", 22), ("id_column", "编号列号", 18),
                                   ("amount_column", "金额列号", 18)))

LEDGER_COLUMNS = (
    Column("status", "状态", 25), Column("side", "文件角色", 13),
    Column("id_raw", "原始编号", 24), Column("amount_raw", "原始金额", 24),
    Column("amount_display", "可解析金额（两位小数）", 26), Column("amount_minor", "可解析金额（分）", 22),
    Column("problem_codes", "全部问题码（JSON）", 42), Column("normalization_notes", "规范化说明（JSON）", 32),
    Column("source_id", "source_id", 22), Column("result_id", "result_id", 22),
    Column("normalized_id", "用于匹配的编号", 24), Column("id_type", "编号原始类型", 18),
    Column("amount_type", "金额原始类型", 18), Column("filename", "文件名", 25),
    Column("sha256", "文件 SHA-256", 22), Column("sheet", "工作表", 18),
    Column("row", "Excel行 / CSV逻辑记录", 25), Column("physical_start", "CSV物理起始行", 22),
    Column("physical_end", "CSV物理结束行", 22), Column("id_column", "编号列号", 16),
    Column("amount_column", "金额列号", 16), Column("hidden", "隐藏行", 12),
)
ISSUE_COLUMNS = LEDGER_COLUMNS + (Column("repair_suggestions", "修复建议", 65),)
