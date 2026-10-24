"""Local Streamlit workflow. Run from this directory; no shared data cache."""
from __future__ import annotations

from hashlib import sha256
import logging
from pathlib import Path
import re

import streamlit as st

from sheetcheck.errors import InputError, PROBLEM_HELP, SheetCheckError
from sheetcheck.mapping_templates import (MAX_TEMPLATE_BYTES, build_template, dump_template,
                                         load_template, match_template)
from sheetcheck.models import APP_VERSION, FileSpec, Mapping, Rules, Side, Status
from sheetcheck.readers import list_worksheets
from sheetcheck.report_schema import SHEET_NAMES
from sheetcheck.ui_state import InputSelection, Workflow
from sheetcheck.ui_views import (PAGE_SIZE, STATUS_LABELS, VIEWS, business_rows, issue_rows,
                                money, outcome, preview_rows, result_page, text_value)
from sheetcheck.validators import SUPPORTED_CURRENCIES

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("sheetcheck.ui")
SIDE_LABELS = {Side.ORDER: "订单", Side.PAYMENT: "收款"}
BUSINESS_LABELS = [STATUS_LABELS[status] for status in tuple(Status)[:4]]


def _init():
    defaults = {"workflow": Workflow(), "generation": 0, "demo_sources": {}, "sheet_catalog": {},
                "currency": "CNY", "period": "", "confirm_currency": False, "confirm_period": False,
                "query": "", "result_view": VIEWS[0], "status_filter": BUSINESS_LABELS.copy(),
                "page_number": 1, "notice": None, "template_enabled": False,
                "template_generation": 0, "template_apply_requested": False,
                "template_notice": None, "template_error": None}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _page_reset():
    st.session_state.page_number = 1
    st.session_state.pop("detail_id", None)


def _invalidate():
    workflow = st.session_state.workflow
    if workflow.result is not None or workflow.report_bytes is not None:
        st.session_state.notice = "输入或核对设置已更改，旧结果和报告已失效。请重新核对。"
    workflow.invalidate()
    _page_reset()


def _reset():
    generation = st.session_state.get("generation", 0) + 1
    # Revoke the old object's report too: an old deferred download must fail.
    if "workflow" in st.session_state:
        st.session_state.workflow.reset()
    for key in list(st.session_state):
        del st.session_state[key]
    st.session_state.generation = generation
    _init()


def _load_demo():
    _reset()
    try:
        for side, filename in ((Side.ORDER, "orders.csv"), (Side.PAYMENT, "payments.csv")):
            st.session_state.demo_sources[side] = (filename, (ROOT / "samples" / filename).read_bytes())
            st.session_state[f"{side}_id"] = 1
            st.session_state[f"{side}_amount"] = 2
        st.session_state.period = "虚构样例期间"
    except OSError:
        st.session_state.demo_sources = {}
        st.session_state.notice = "SAMPLE_UNAVAILABLE：样例无法读取，请检查项目 samples 目录或上传自己的文件。"


def _upload_changed(side):
    _invalidate()
    _clear_template_import()
    # Once replaced/removed, that side cannot fall back to a hidden demo file.
    st.session_state.demo_sources.pop(side, None)
    st.session_state.sheet_catalog.pop(side, None)
    for suffix in ("sheet", "id", "amount", "header", "encoding", "delimiter"):
        st.session_state.pop(f"{side}_{suffix}", None)
    st.session_state.confirm_currency = False
    st.session_state.confirm_period = False


def _parse_changed(side):
    _invalidate()
    _clear_template_import()
    st.session_state.pop(f"{side}_id", None)
    st.session_state.pop(f"{side}_amount", None)


def _template_upload_key():
    return f"template_upload_{st.session_state.generation}_{st.session_state.template_generation}"


def _clear_template_import():
    # Changing either input revokes any pending application and removes the
    # uploaded template. Reuse on new inputs always requires a fresh action.
    st.session_state.pop(_template_upload_key(), None)
    st.session_state.template_generation += 1
    _template_upload_changed()


def _template_upload_changed():
    st.session_state.template_apply_requested = False
    st.session_state.template_notice = None
    st.session_state.template_error = None


def _request_template_apply():
    # The next main() run reads and synchronizes BOTH current inputs before
    # applying this request, and does so before creating mapping/rule widgets.
    st.session_state.template_apply_requested = True


def _apply_requested_template(workflow):
    if not st.session_state.template_apply_requested:
        return
    st.session_state.template_apply_requested = False
    st.session_state.template_notice = None
    st.session_state.template_error = None
    try:
        uploaded = st.session_state.get(_template_upload_key())
        if not st.session_state.template_enabled or uploaded is None:
            raise InputError("TEMPLATE_REQUIRED", "请先上传一个映射模板，再点击应用。")
        template = load_template(uploaded.getvalue())
        # No mapping or rule widget is changed until both sources pass. Never
        # reuse the sources captured when the apply button was first rendered.
        selections = dict(workflow.selections)
        sources = {side: workflow.get_source(side) for side in Side}
        order_mapping, payment_mapping, currency = match_template(
            template, sources[Side.ORDER], sources[Side.PAYMENT])
        if selections != workflow.selections or any(workflow.sources.get(side) is not sources[side] for side in Side):
            raise InputError("TEMPLATE_INPUT_CHANGED", "当前文件已变化，模板未应用。请检查新的两侧预览后重试。")
    except Exception as exc:
        if isinstance(exc, SheetCheckError):
            st.session_state.template_error = (exc.code, exc.message)
        else:
            st.session_state.template_error = (
                "UI_TEMPLATE_FAILED", "模板未应用，原字段选择仍保留。请检查模板与两侧文件后重试。")
        return
    _invalidate()
    for side, mapping in ((Side.ORDER, order_mapping), (Side.PAYMENT, payment_mapping)):
        st.session_state[f"{side}_id"] = mapping.id_column
        st.session_state[f"{side}_amount"] = mapping.amount_column
    st.session_state.currency = currency
    st.session_state.period = ""
    st.session_state.confirm_currency = False
    st.session_state.confirm_period = False
    st.session_state.query = ""
    st.session_state.result_view = VIEWS[0]
    st.session_state.status_filter = BUSINESS_LABELS.copy()
    _page_reset()
    workflow.configure({Side.ORDER: order_mapping, Side.PAYMENT: payment_mapping}, Rules(currency=currency))
    st.session_state.template_notice = "模板已应用，旧结果和报告已失效。请检查两侧映射示例，重新填写期间并确认币种与期间。"


def _mapping_templates(workflow, mappings):
    enabled = st.checkbox("使用映射模板（可选）", key="template_enabled", on_change=_clear_template_import)
    if not enabled:
        return
    with st.expander("保存或应用字段映射模板", expanded=True):
        st.caption("模板仅保存列位置、读取结构、币种和固定核对规则；不含文件名、工作表名、表头文字、业务数据、期间或确认状态。")
        st.warning("结构相同不代表字段含义相同。模板无法发现同列数下的列顺序变化；应用后必须检查两侧预览与映射示例。")
        uploaded = st.file_uploader("上传映射模板 JSON（最多 16 KiB）", type=["json"], max_upload_size=1,
                                    key=_template_upload_key(), on_change=_template_upload_changed)
        oversized = uploaded is not None and len(uploaded.getvalue()) > MAX_TEMPLATE_BYTES
        if oversized:
            st.error("TEMPLATE_TOO_LARGE：模板不得超过 16 KiB，请使用 SheetCheck 导出的映射模板。")
        st.button("应用到当前两份文件", key="apply_template", on_click=_request_template_apply,
                  disabled=uploaded is None or oversized or any(side not in workflow.sources for side in Side))
        if st.session_state.template_error is not None:
            code, message = st.session_state.template_error
            _show_error(InputError(code, message), "TEMPLATE")
        if st.session_state.template_notice:
            st.info(st.session_state.template_notice)
        if all(isinstance(mappings.get(side), Mapping) and side in workflow.sources for side in Side):
            try:
                payload = dump_template(build_template(
                    workflow.sources[Side.ORDER], workflow.sources[Side.PAYMENT],
                    mappings[Side.ORDER], mappings[Side.PAYMENT], st.session_state.currency))
                st.download_button("保存当前映射模板", data=payload, file_name="sheetcheck-mapping-v1.json",
                                   mime="application/json", key="download_template", on_click="ignore")
            except Exception as exc:
                _show_error(exc, "TEMPLATE")
        else:
            st.caption("完成两侧字段映射后，可保存模板。上传模板不会自动改变当前选择。")


def _literal_label(value):
    # Selectbox labels can render Markdown. Treat file/header/ID text literally.
    return re.sub(r"([\\`*_{}\[\]()#+.!<>|~-])", r"\\\1", text_value(value, 96)).replace("\n", " ↵ ")


def _show_error(exc, phase):
    if isinstance(exc, SheetCheckError):
        code, message = exc.code, exc.message
    else:
        code, message = f"UI_{phase}_FAILED", "本次操作未完成，输入仍保留。请重试，或从可信来源重新导出普通值表。"
    LOGGER.error("phase=%s code=%s version=%s", phase, code, APP_VERSION)
    st.error(f"{code}：{message}")


def _select_input(side):
    label = SIDE_LABELS[side]
    st.subheader(f"{label}表")
    uploaded = st.file_uploader(f"上传{label}文件", type=["csv", "xlsx"], max_upload_size=10,
                                key=f"{side}_upload_{st.session_state.generation}",
                                on_change=_upload_changed, args=(side,))
    demo = st.session_state.demo_sources.get(side)
    if uploaded is not None:
        filename, data = uploaded.name, uploaded.getvalue()
    elif demo is not None:
        filename, data = demo
    else:
        st.caption("选择一个 CSV 或 XLSX 文件，每份不超过 10 MiB。")
        return None
    st.text(f"{text_value(filename, 180)} · {len(data):,} 字节" + (" · 虚构样例" if uploaded is None else ""))
    sheet = None
    if Path(filename).suffix.lower() == ".xlsx":
        try:
            identity = (filename, sha256(data).hexdigest())
            catalog = st.session_state.sheet_catalog.get(side)
            if catalog is None or catalog[0] != identity:
                names = list_worksheets(data, FileSpec(filename, side))
                st.session_state.sheet_catalog[side] = (identity, names)
            else:
                names = catalog[1]
            options = [None, *names]
            key = f"{side}_sheet"
            if st.session_state.get(key) not in options:
                st.session_state[key] = None
            if key not in st.session_state:
                st.session_state[key] = names[0] if len(names) == 1 else None
            sheet = st.selectbox(f"{label}工作表", options, format_func=lambda value: "请选择工作表" if value is None else _literal_label(value),
                                 key=key, on_change=_parse_changed, args=(side,))
        except Exception as exc:
            _show_error(exc, "IMPORT")
    st.number_input(f"{label}表头行（CSV 为逻辑记录号）", min_value=1, max_value=50001, value=1,
                    step=1, key=f"{side}_header", on_change=_parse_changed, args=(side,))
    encoding, delimiter = "utf-8-sig", ","
    if Path(filename).suffix.lower() == ".csv":
        encoding = st.selectbox(f"{label}编码", ["utf-8-sig", "utf-8", "gb18030"],
                                format_func=lambda value: {"utf-8-sig": "UTF-8 / UTF-8 BOM", "utf-8": "UTF-8", "gb18030": "GB18030"}[value],
                                key=f"{side}_encoding", on_change=_parse_changed, args=(side,))
        delimiter = st.selectbox(f"{label}分隔符", [",", "\t", ";"],
                                 format_func=lambda value: {",": "逗号", "\t": "制表符", ";": "分号"}[value],
                                 key=f"{side}_delimiter", on_change=_parse_changed, args=(side,))
    return InputSelection(data, FileSpec(filename, side, sheet=sheet, header_row=int(st.session_state[f"{side}_header"]),
                                         encoding=encoding, delimiter=delimiter))


def _preview_mapping(side, workflow):
    if workflow.selections[side] is None:
        return None
    label = SIDE_LABELS[side]
    try:
        source = workflow.get_source(side)
    except Exception as exc:
        _show_error(exc, "IMPORT")
        st.caption("请调整此侧文件、工作表、表头、编码或分隔符后重试读入。")
        st.button(f"重试读取{label}表", key=f"{side}_retry")
        return None
    st.caption(f"{len(source.rows):,} 条源记录 · 前言 {source.preamble_count} 行 · 隐藏 {source.hidden_row_count} 行")
    st.dataframe(preview_rows(source), hide_index=True, width="stretch", height=220, key=f"{side}_preview")
    st.caption("仅预览前 20 条；较长字段显示已缩短。编号按原文本保留，隐藏行参加核对。")
    options = [None, *range(1, len(source.headers) + 1)]
    key = f"{side}_id"
    if st.session_state.get(key) not in options:
        st.session_state[key] = None

    def column_label(column):
        if column is None:
            return "请选择列"
        return _literal_label(source.column_labels[column - 1])

    identifier = st.selectbox(f"{label}编号列", options, format_func=column_label,
                              key=key, on_change=_invalidate)
    amounts = [option for option in options if option is None or option != identifier]
    if st.session_state.get(f"{side}_amount") not in amounts:
        st.session_state[f"{side}_amount"] = None
    amount = st.selectbox(f"{label}金额列", amounts, format_func=column_label,
                          key=f"{side}_amount", on_change=_invalidate)
    if identifier is not None and amount is not None:
        examples = [f"编号 {text_value(row.cells[identifier - 1].value, 48)} ｜ 金额 {text_value(row.cells[amount - 1].value, 48)}"
                    for row in source.rows[:3]]
        st.text("映射示例\n" + "\n".join(examples) if examples else "该表只有表头，没有数据记录。")
        return Mapping(identifier, amount)
    return None


def _source_detail(result, item, issues):
    ids = [item.source_id] if issues else [item.order_source_id, item.payment_source_id]
    entries = {entry.source_id: entry for entry in result.ledger if entry.source_id in ids}
    rows, metadata = [], []
    for source_id in ids:
        if source_id is None:
            continue
        entry = entries[source_id]
        row, pos = entry.row, entry.row.source.position
        table = result.tables[0 if row.source.side == Side.ORDER else 1]
        details = {"文件角色": SIDE_LABELS[row.source.side], "文件名": text_value(table.source.spec.filename),
                   "工作表": pos.sheet if pos.sheet is not None else "CSV", "原始行号": pos.row,
                   "CSV物理起始行": pos.physical_start, "CSV物理结束行": pos.physical_end,
                   "编号列号": table.mapping.id_column, "金额列号": table.mapping.amount_column,
                   "原始编号": text_value(row.id_raw), "原始金额": text_value(row.amount_raw),
                   "编号原始类型": row.raw_types[0], "金额原始类型": row.raw_types[1],
                   "金额（分）": str(row.amount_minor) if row.amount_minor is not None else "—",
                   "source_id": source_id, "result_id": entry.result_id,
                   "SHA-256": table.source.sha256, "隐藏行": pos.hidden,
                   "问题码": list(entry.problem_codes), "规范化说明": list(row.normalization_notes)}
        metadata.append(details)
        rows.append({name: value for name, value in details.items() if name in (
            "文件角色", "文件名", "工作表", "原始行号", "CSV物理起始行", "CSV物理结束行", "编号列号", "金额列号",
            "原始编号", "原始金额", "金额（分）", "source_id")})
    st.dataframe(rows, hide_index=True, width="stretch", key="source_detail")
    with st.expander("完整来源、原始类型与问题修复建议"):
        st.json(metadata, expanded=True)
        codes = dict.fromkeys(code for entry in entries.values() for code in entry.problem_codes)
        for code in codes:
            st.text(f"{code}：{PROBLEM_HELP[code]}")
        if not codes:
            st.caption("此业务结果没有数据问题。修正源数据后重新核对，不在页面编辑金额。")


def _current_download(workflow, run_id):
    # Called by Streamlit's deferred download thread. Do not capture the old
    # bytes directly: any input change or reset revokes this callable too.
    try:
        return workflow.report_for_run(run_id)
    except SheetCheckError:
        raise
    except Exception:
        # This callback runs outside main() on Streamlit's download thread;
        # its framework error handler includes the exception's message.
        LOGGER.error("phase=DOWNLOAD code=UI_DOWNLOAD_FAILED version=%s", APP_VERSION)
        raise InputError("UI_DOWNLOAD_FAILED", "报告下载未完成，请重新核对并生成报告后重试。") from None


def _results(workflow):
    result = workflow.result
    if result is None:
        return
    st.divider()
    st.header("3 · 核对结果")
    summary, counts = result.manifest.summaries, result.manifest.status_counts
    columns = st.columns(4)
    columns[0].metric("订单输入记录", summary[Side.ORDER].input_count)
    columns[1].metric("收款输入记录", summary[Side.PAYMENT].input_count)
    columns[2].metric(f"订单可核对金额 · {result.manifest.rules.currency}", money(summary[Side.ORDER].valid_total_minor))
    columns[3].metric(f"收款可核对金额 · {result.manifest.rules.currency}", money(summary[Side.PAYMENT].valid_total_minor))
    for column, status in zip(st.columns(6), Status):
        unit = "配对" if status in (Status.EXACT_MATCH, Status.AMOUNT_MISMATCH) else "源行" if status in (Status.DATA_ISSUE, Status.SKIPPED_EMPTY) else "条"
        column.metric(f"{STATUS_LABELS[status]}（{unit}）", counts[status])
    message = outcome(result)
    if counts[Status.DATA_ISSUE] or any(counts[s] for s in (Status.AMOUNT_MISMATCH, Status.ONLY_ORDER, Status.ONLY_PAYMENT)):
        st.warning(message)
    else:
        st.info(message)
    for warning in result.manifest.warnings:
        st.warning(warning)
    st.caption("差额 = 收款减订单；缺项只表示本次有效集合中未配对。问题金额不计入可核对金额。")
    st.caption("问题行可解析部分：订单 " + money(summary[Side.ORDER].issue_parseable_minor) + "，收款 "
               + money(summary[Side.PAYMENT].issue_parseable_minor) + "；金额不可解析行数：订单 "
               + str(summary[Side.ORDER].issue_unparseable_count) + "，收款 " + str(summary[Side.PAYMENT].issue_unparseable_count) + "。")
    view = st.radio("结果分类", VIEWS, horizontal=True, key="result_view", on_change=_page_reset)
    left, right = st.columns(2)
    query = left.text_input("搜索业务编号（区分大小写，包含匹配）", max_chars=128, key="query", on_change=_page_reset)
    selected = right.multiselect("业务状态筛选", BUSINESS_LABELS, key="status_filter", disabled=view == "数据问题", on_change=_page_reset)
    statuses = [status for status in tuple(Status)[:4] if STATUS_LABELS[status] in selected]
    page = result_page(result, view, query, statuses, int(st.session_state.page_number))
    if st.session_state.page_number != page.number:
        st.session_state.page_number = page.number
    st.number_input("页码", min_value=1, max_value=page.pages, step=1, key="page_number",
                    on_change=lambda: st.session_state.pop("detail_id", None))
    st.caption(f"共 {page.total} 条 · 第 {page.number} / {page.pages} 页 · 每页 {PAGE_SIZE} 条")
    issues = view == "数据问题"
    st.dataframe(issue_rows(page.items) if issues else business_rows(page.items), hide_index=True,
                 width="stretch", key="result_table")
    if page.items:
        current = {item.source_id if issues else item.result_id: item for item in page.items}
        options = [None, *current]
        if st.session_state.get("detail_id") not in options:
            st.session_state.detail_id = None
        selected_id = st.selectbox("查看来源详情（当前页）", options, key="detail_id",
                                   format_func=lambda key: "选择一条结果" if key is None else _literal_label(
                                       f"{text_value(current[key].row.id_raw) if issues else current[key].id} · {SIDE_LABELS[current[key].row.source.side] if issues else STATUS_LABELS[current[key].status]}"
                                       + (f" · 源行 {current[key].row.source.position.row}" if issues else "")))
        if selected_id is not None:
            _source_detail(result, current[selected_id], issues)
    else:
        st.info("没有符合当前筛选条件的记录。")
    st.subheader("4 · 下载报告")
    st.caption("报告包含：" + "、".join(SHEET_NAMES) + f"。数据问题 {counts[Status.DATA_ISSUE]} 行；规则 {result.manifest.rules.version}。")
    st.caption("报告包含本次完整结果，当前分类、搜索和分页不会改变报告内容。")
    if st.button("生成报告", key="prepare_report", disabled=workflow.report_bytes is not None):
        try:
            with st.spinner("正在生成并回读审计报告，请等待完成。"):
                workflow.prepare_report()
        except Exception as exc:
            _show_error(exc, "EXPORT")
    if workflow.report_bytes is not None:
        st.download_button("下载核对报告", data=lambda: _current_download(workflow, result.manifest.run_id),
                           file_name=workflow.report_name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key=f"download_{result.manifest.run_id}", on_click="ignore", type="primary")
        st.caption("已通过回读审计。下载文件包含原始业务字段，请妥善保管。")


def main():
    st.set_page_config(page_title="SheetCheck · 两表核对", page_icon="📋", layout="wide")
    _init()
    workflow = st.session_state.workflow
    with st.sidebar:
        st.title("SheetCheck")
        st.caption("本机运行 · 一对一核对")
        st.button("加载虚构样例", key="load_demo", on_click=_load_demo, width="stretch")
        st.button("重新开始", key="reset", on_click=_reset, width="stretch")
        st.divider()
        st.markdown("**操作顺序**\n\n1. 导入并检查预览\n2. 选择字段、确认规则\n3. 核对并追溯来源\n4. 生成和下载报告")
        st.caption("刷新浏览器可能丢失未下载结果。重新开始会清空本会话；已下载文件需自行管理。")
    st.title("让每条核对结果都有来源")
    st.write("按文本唯一编号核对订单与收款，查看一致、差额、缺项和数据问题。")
    st.caption("仅处理同币种、同期间的一对一记录；不处理退款、手续费或拆分收款。异常不直接等于欠款、欺诈或会计错误。")
    if st.session_state.notice:
        st.info(st.session_state.notice)
    st.header("1 · 导入与预览")
    columns = st.columns(2, gap="large")
    selections = {}
    for side, column in zip(Side, columns):
        with column:
            selections[side] = _select_input(side)
    workflow.sync_inputs(selections)
    _apply_requested_template(workflow)
    mappings = {}
    for side, column in zip(Side, columns):
        with column:
            mappings[side] = _preview_mapping(side, workflow)
    st.header("2 · 确认核对规则")
    st.caption("文本编号精确匹配 · 保留前导零 · 金额两位小数 · 容差 0 分 · 坏编号在两侧全部隔离")
    left, right = st.columns(2)
    currency = left.selectbox("币种", ["CNY", *sorted(SUPPORTED_CURRENCIES - {"CNY"})], key="currency", on_change=_invalidate)
    period = right.text_input("核对期间", key="period", max_chars=200, placeholder="例如：2026-10-01 至 2026-10-31", on_change=_invalidate)
    confirmed_currency = st.checkbox("我确认两个文件属于同一币种", key="confirm_currency", on_change=_invalidate)
    confirmed_period = st.checkbox("我确认两个文件属于上述同一核对期间", key="confirm_period", on_change=_invalidate)
    workflow.configure(mappings, Rules(currency=currency, period=period, same_currency_confirmed=confirmed_currency,
                                        same_period_confirmed=confirmed_period))
    _mapping_templates(workflow, mappings)
    if st.button("开始核对", key="run_reconciliation", type="primary", disabled=not workflow.ready):
        try:
            with st.spinner("正在校验、隔离问题编号并核对来源账本。"):
                workflow.run()
            st.session_state.notice = None
            _page_reset()
        except Exception as exc:
            _show_error(exc, "RECONCILE")
    if not workflow.ready:
        st.caption("请先完成两侧导入、不同字段映射、币种和期间确认。")
    _results(workflow)
    st.sidebar.caption(f"阶段：{workflow.stage} · 应用 {APP_VERSION} · 规则 v1")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print uploaded rows/filenames through an uncaught traceback.
        workflow = st.session_state.get("workflow")
        if workflow is not None:
            workflow.invalidate()
        _show_error(error, "PAGE")
