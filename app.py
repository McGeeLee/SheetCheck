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
from sheetcheck.ui_design import get_html, get_styles
from sheetcheck.ui_i18n import translate
from sheetcheck.ui_views import (PAGE_SIZE, STATUS_LABELS, VIEWS, business_rows, issue_rows,
                                issue_explanation, issue_next_steps, money, outcome,
                                preview_rows, result_page, text_value)
from sheetcheck.validators import SUPPORTED_CURRENCIES

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("sheetcheck.ui")
SIDE_LABELS = {Side.ORDER: "订单", Side.PAYMENT: "收款"}
BUSINESS_LABELS = [STATUS_LABELS[status] for status in tuple(Status)[:4]]
WORKSPACES = ("准备数据", "核对结果", "使用指南")


def _t(text, *values):
    translated = translate(text, st.session_state.get("language", "zh"))
    return translated.format(*values) if values else translated


def _language():
    return st.session_state.get("language", "zh")


def _language_changed():
    """Resend translated option labels without changing their canonical values."""
    keys = ["appearance", "result_view", "status_filter", "detail_id"]
    keys.extend(f"{side}_{field}" for side in Side
                for field in ("delimiter", "sheet", "id", "amount"))
    for key in keys:
        if key in st.session_state:
            # Streamlit sends formatted strings to the browser. Explicit writes
            # force the new locale's wire values even when the selection is the
            # same; they do not invoke input-change/invalidation callbacks.
            st.session_state[key] = st.session_state[key]


def _text(value, limit=None):
    return text_value(value, limit, _language())


def _localized_fields(row):
    """Translate metadata labels and our role names, never raw business values."""
    return {_t(key): _t(value) if key == "文件角色" else value for key, value in row.items()}


def _init():
    defaults = {"workflow": Workflow(), "generation": 0, "demo_sources": {}, "sheet_catalog": {},
                "currency": "CNY", "period": "", "confirm_currency": False, "confirm_period": False,
                "query": "", "result_view": VIEWS[0], "status_filter": BUSINESS_LABELS.copy(),
                "page_number": 1, "notice": None, "template_enabled": False,
                "template_generation": 0, "template_apply_requested": False,
                "template_notice": None, "template_error": None,
                "workspace_tab": "准备数据", "navigate_to": None,
                "language": "zh", "appearance": "light"}
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
        st.session_state.navigate_to = "准备数据"
    workflow.invalidate()
    _page_reset()


def _reset():
    generation = st.session_state.get("generation", 0) + 1
    preferences = {key: st.session_state.get(key, default)
                   for key, default in (("language", "zh"), ("appearance", "light"))}
    # Revoke the old object's report too: an old deferred download must fail.
    if "workflow" in st.session_state:
        st.session_state.workflow.reset()
    for key in list(st.session_state):
        del st.session_state[key]
    st.session_state.generation = generation
    st.session_state.update(preferences)
    _init()


def _load_demo():
    _reset()
    try:
        for side, filename in ((Side.ORDER, "orders.csv"), (Side.PAYMENT, "payments.csv")):
            st.session_state.demo_sources[side] = (filename, (ROOT / "samples" / filename).read_bytes())
            st.session_state[f"{side}_id"] = 1
            st.session_state[f"{side}_amount"] = 2
        st.session_state.period = _t("虚构样例期间")
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
    enabled = st.checkbox(_t("使用映射模板（可选）"), key="template_enabled", on_change=_clear_template_import)
    if not enabled:
        return
    with st.container(border=True):
        st.markdown(_t("**保存或应用字段映射模板**"))
        st.caption(_t("模板仅保存列位置、读取结构、币种和固定核对规则；不含文件名、工作表名、表头文字、业务数据、期间或确认状态。"))
        st.warning(_t("结构相同不代表字段含义相同。模板无法发现同列数下的列顺序变化；应用后必须检查两侧预览与映射示例。"))
        uploaded = st.file_uploader(_t("上传映射模板 JSON（最多 16 KiB）"), type=["json"], max_upload_size=1,
                                    key=_template_upload_key(), on_change=_template_upload_changed)
        oversized = uploaded is not None and len(uploaded.getvalue()) > MAX_TEMPLATE_BYTES
        if oversized:
            st.error(_t("TEMPLATE_TOO_LARGE：模板不得超过 16 KiB，请使用 SheetCheck 导出的映射模板。"))
        st.button(_t("应用到当前两份文件"), key="apply_template", on_click=_request_template_apply,
                  disabled=uploaded is None or oversized or any(side not in workflow.sources for side in Side))
        if st.session_state.template_error is not None:
            code, message = st.session_state.template_error
            _show_error(InputError(code, message), "TEMPLATE")
        if st.session_state.template_notice:
            st.info(_t(st.session_state.template_notice))
        if all(isinstance(mappings.get(side), Mapping) and side in workflow.sources for side in Side):
            try:
                payload = dump_template(build_template(
                    workflow.sources[Side.ORDER], workflow.sources[Side.PAYMENT],
                    mappings[Side.ORDER], mappings[Side.PAYMENT], st.session_state.currency))
                st.download_button(_t("保存当前映射模板"), data=payload, file_name="sheetcheck-mapping-v1.json",
                                   mime="application/json", key="download_template", on_click="ignore")
            except Exception as exc:
                _show_error(exc, "TEMPLATE")
        else:
            st.caption(_t("完成两侧字段映射后，可保存模板。上传模板不会自动改变当前选择。"))


def _literal_label(value):
    # Selectbox labels can render Markdown. Treat file/header/ID text literally.
    return re.sub(r"([\\`*_{}\[\]()#+.!<>|~-])", r"\\\1", _text(value, 96)).replace("\n", " ↵ ")


def _show_error(exc, phase):
    if isinstance(exc, SheetCheckError):
        code, message = exc.code, exc.message
    else:
        code, message = f"UI_{phase}_FAILED", "本次操作未完成，输入仍保留。请重试，或从可信来源重新导出普通值表。"
    LOGGER.error("phase=%s code=%s version=%s", phase, code, APP_VERSION)
    translated = _t(message)
    if _language() == "en" and re.search(r"[\u4e00-\u9fff]", translated):
        translated = _t("本次操作未完成，输入仍保留。请重试，或从可信来源重新导出普通值表。")
    message = translated
    st.error(f"{code}：{message}")


def _welcome(workflow):
    empty = not st.session_state.demo_sources and all(
        st.session_state.get(f"{side}_upload_{st.session_state.generation}") is None for side in Side)
    if empty:
        with st.container(key="hero"):
            intro, example = st.columns([1.25, 1], gap="large", vertical_alignment="center")
            with intro:
                st.caption(_t("让每一笔差异，都有出处"))
                st.title(_t("订单和收款，哪里对不上？"))
                st.write(_t("放入两张表，找出金额不同和缺少配对的记录。\n\n从核对结果，一直查回原表的那一行。"))
                st.button(_t("用虚构样例试一遍"), key="start_demo", type="primary", on_click=_load_demo)
                st.caption(_t("无需准备文件 · 无需注册 · 不改写原文件"))
            with example:
                st.markdown(get_html("example", _language()), unsafe_allow_html=True)
    else:
        st.caption(_t("SHEETCHECK / 本地核对工作台"))
        st.title(_t("每一笔，都核对清楚。"))
        st.caption(_t("文件与选列保留在「准备数据」，核对完成后自动打开「核对结果」。"))


def _guide():
    st.header(_t("从两张表，到一份可回查的报告"))
    st.caption(_t("第一次用，先点击侧栏「加载虚构样例」。真实业务请先确认两张表来自相同币种和期间。"))
    for column, title, body in zip(st.columns(3),
            ("01 · 准备两张表", "02 · 先处理问题", "03 · 追溯与保存"),
            ("每侧选择编号和金额列。编号用来找到同一笔记录，不按行的顺序配对。",
             "检查数据问题，再看金额差异和单侧缺项。修正原表后，重新导入核对。",
             "选择一条结果，回查原文件与行号。生成报告并通过回读审计后，再下载保存。")):
        with column, st.container(border=True):
            st.subheader(_t(title))
            st.write(_t(body))
    with st.expander(_t("我的表能用吗？准备文件前看这里")):
        st.markdown(_t("每张表至少有两列：**编号**（例如订单号）和**金额**。两侧列名可以不同，但编号要能对应同一笔记录。\n\n"
                    "- 支持 CSV 和 XLSX，每份不超过 10 MiB；先导出同一币种、同一期间的数据。\n"
                    "- 每个编号在每张表中最多出现一次；编号应是文本，保留 `0001` 这样的前导零。\n"
                    "- 本版不自动合并重复编号，不处理分期、拆分收款、退款、手续费或换汇。\n"
                    "- 重复编号、缺失编号、金额格式错误会进入「数据问题」；先在原表修正，再重新导入。"))
        st.caption(_t("这里找出的是两张表的差异。差异或缺项本身不能证明欠款、欺诈或会计错误。"))
    with st.expander(_t("结果怎么看？")):
        st.markdown(_t("| 结果 | 表示什么 |\n| --- | --- |\n"
                    "| 一致 | 有效配对的两侧金额相同 |\n| 金额差异 | 差额为收款减订单；差 0.01 也会标记 |\n"
                    "| 仅订单有 / 仅收款有 | 本次有效记录中，另一侧没有配对 |\n"
                    "| 数据问题 | 暂未参与比较；查看原因，修正原表后重试 |"))
        st.write(_t("例如 A002：订单 50.00、收款 49.00，差额是 -1.00。差额的业务原因仍需你检查。"))
    with st.expander(_t("更换输入、清空筛选和重新开始，有什么区别？")):
        st.markdown(_t("- 更换文件、读取方式、选列或核对设置：旧结果和报告失效，回到「准备数据」。\n"
                    "- 切换工作区、清空筛选或翻页：保留输入、核对结果和已生成报告。\n"
                    "- 重新开始：清空当前会话。已经下载的文件由你自行管理。"))
    st.info(_t("本机启动时，文件由这台电脑处理。刷新或关闭页面可能丢失未下载结果；报告包含原始业务字段，请妥善保管。"))


def _using_demo(workflow):
    # A replaced side must never retain the fictional-practice banner.
    for side in Side:
        demo = st.session_state.demo_sources.get(side)
        selected = workflow.selections.get(side)
        if demo is None or selected is None or (selected.spec.filename, selected.data) != demo:
            return False
    return True


def _pending_steps(workflow):
    pending = []
    for side in Side:
        label = SIDE_LABELS[side]
        if workflow.selections.get(side) is None:
            pending.append(_t('上传{0}表', _t(label)))
        elif (workflow.selections[side].spec.filename.lower().endswith(".xlsx")
              and workflow.selections[side].spec.sheet is None
              and side in st.session_state.sheet_catalog):
            pending.append(_t('选择{0}工作表', _t(label)))
        elif side not in workflow.sources:
            pending.append(_t('修复{0}表的读取问题：检查文件、工作表和读取选项', _t(label)))
        else:
            for suffix, field in (("id", "编号"), ("amount", "金额")):
                if st.session_state.get(f"{side}_{suffix}") is None:
                    pending.append(_t('选择{0}{1}列', _t(label), _t(field)))
    if not workflow.rules.period.strip():
        pending.append(_t("填写核对期间"))
    if not workflow.rules.same_currency_confirmed:
        pending.append(_t("确认两张表的币种相同"))
    if not workflow.rules.same_period_confirmed:
        pending.append(_t("确认两张表的期间相同"))
    return pending


def _show_result_view(view):
    # Navigation changes only what is displayed, never the audited result.
    st.session_state.result_view = view
    st.session_state.query = ""
    st.session_state.status_filter = BUSINESS_LABELS.copy()
    _page_reset()


def _move_page(offset):
    st.session_state.page_number += offset
    st.session_state.pop("detail_id", None)


def _session_progress(workflow):
    if workflow.report_bytes is not None:
        return "报告已生成，等待你下载"
    if workflow.result is not None:
        return "结果已生成，可以查看来源"
    if workflow.ready:
        return "准备好了，可以开始核对"
    if any(workflow.selections.values()):
        return "检查文件、选列与确认项"
    return "等待两张表，也可以先试样例"


def _select_input(side):
    label = SIDE_LABELS[side]
    st.subheader(_t('{0}表', _t(label)))
    st.caption((_t("这里放订单记录，金额代表这笔订单应收多少。") if side == Side.ORDER else _t("这里放收款记录，金额代表同一笔订单实际收了多少。")))
    upload_key = f"{side}_upload_{st.session_state.generation}"
    has_input = st.session_state.get(upload_key) is not None or side in st.session_state.demo_sources
    # Keep the uploader mounted when a file is loaded, but give its preview and
    # mapping more space. Replacing the file still uses the same callback/key.
    upload_area = st.expander(_t('更换{0}文件', _t(label))) if has_input else st.container()
    with upload_area:
        uploaded = st.file_uploader(_t('上传{0}文件', _t(label)), type=["csv", "xlsx"], max_upload_size=10,
                                    key=upload_key, on_change=_upload_changed, args=(side,))
    demo = st.session_state.demo_sources.get(side)
    if uploaded is not None:
        filename, data = uploaded.name, uploaded.getvalue()
    elif demo is not None:
        filename, data = demo
    else:
        st.caption(_t("选择一个 CSV 或 XLSX 文件，每份不超过 10 MiB。"))
        return None
    st.text((_t('{0} · {1:,} 字节', _text(filename, 180), len(data)) + (_t(" · 虚构样例") if uploaded is None else "")))
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
            options = names if len(names) == 1 else [None, *names]
            key = f"{side}_sheet"
            if key not in st.session_state or st.session_state[key] not in options:
                st.session_state[key] = names[0] if len(names) == 1 else None
            sheet_labels = {value: _t("请选择工作表") if value is None else _literal_label(value) for value in options}
            sheet = st.selectbox(_t('{0}工作表', _t(label)), options, format_func=sheet_labels.__getitem__,
                                 key=key, on_change=_parse_changed, args=(side,), disabled=len(names) == 1)
            st.caption((_t("已选中此文件唯一的工作表。") if len(names) == 1 else _t('此文件有 {0} 个工作表，请选择本次要核对的一张；隐藏工作表也列在选项中。', len(names))))
        except Exception as exc:
            _show_error(exc, "IMPORT")
    encoding, delimiter = "utf-8-sig", ","
    with st.expander(_t('{0}读取选项', _t(label))):
        st.caption(_t("表头不在首行、乱码或整行挤成一列时，调整后检查预览。"))
        st.number_input(_t('{0}表头行（CSV 为逻辑记录号）', _t(label)), min_value=1, max_value=50001, value=1,
                        step=1, key=f"{side}_header", on_change=_parse_changed, args=(side,),
                        help=_t("写着「订单号、金额」等列名的那一行，通常是第 1 行。CSV 带引号换行时按逻辑记录计数。"))
        if Path(filename).suffix.lower() == ".csv":
            encoding = st.selectbox(_t('{0}编码', _t(label)), ["utf-8-sig", "utf-8", "gb18030"],
                                    format_func=lambda value: {"utf-8-sig": "UTF-8 / UTF-8 BOM", "utf-8": "UTF-8", "gb18030": "GB18030"}[value],
                                    key=f"{side}_encoding", on_change=_parse_changed, args=(side,),
                                    help=_t("中文乱码时检查编码。常见 UTF-8 文件可保留默认值；部分中文系统导出的文件使用 GB18030。"))
            delimiter = st.selectbox(_t('{0}分隔符', _t(label)), [",", "\t", ";"],
                                     format_func={value: _t(name) for value, name in {",": "逗号", "\t": "制表符", ";": "分号"}.items()}.__getitem__,
                                     key=f"{side}_delimiter", on_change=_parse_changed, args=(side,),
                                     help=_t("整行内容挤在同一列时，选择文件实际使用的列分隔符，再检查预览。"))
    if Path(filename).suffix.lower() == ".csv":
        st.caption(_t('读取方式：表头第 {0} 条记录 · {1} · ', st.session_state[f'{side}_header'], encoding)
                   + _t({",": "逗号分隔", "\t": "制表符分隔", ";": "分号分隔"}[delimiter]))
    else:
        st.caption(_t('读取方式：表头第 {0} 行', st.session_state[f'{side}_header']))
    return InputSelection(data, FileSpec(filename, side, sheet=sheet, header_row=int(st.session_state[f"{side}_header"]),
                                         encoding=encoding, delimiter=delimiter))


def _preview_mapping(side, workflow):
    if workflow.selections[side] is None:
        return None
    label = SIDE_LABELS[side]
    selection = workflow.selections[side]
    if (selection.spec.filename.lower().endswith(".xlsx") and selection.spec.sheet is None
            and side in st.session_state.sheet_catalog):
        st.info(_t('请选择{0}工作表，再查看预览。', _t(label)))
        return None
    try:
        source = workflow.get_source(side)
    except Exception as exc:
        _show_error(exc, "IMPORT")
        st.caption(_t("请调整此侧文件、工作表、表头、编码或分隔符后重试读入。"))
        st.button(_t('重试读取{0}表', _t(label)), key=f"{side}_retry")
        return None
    st.caption(_t('{0:,} 条源记录 · 前言 {1} 行 · 隐藏 {2} 行', len(source.rows), source.preamble_count, source.hidden_row_count))
    with st.expander(_t('预览{0}数据 · 查看前 20 条', _t(label))):
        st.dataframe(preview_rows(source, _language()), hide_index=True, width="stretch", height=220, key=f"{side}_preview")
        st.caption(_t("仅预览前 20 条；较长字段显示已缩短。编号按原文本保留，隐藏行参加核对。"))
    options = [None, *range(1, len(source.headers) + 1)]
    key = f"{side}_id"
    if st.session_state.get(key) not in options:
        st.session_state[key] = None

    # Freeze labels for this render. Deferred widget serialization must not
    # read a different session's locale or rely on an active script context.
    column_labels = {column: _t("请选择列") if column is None
                     else _literal_label(source.column_labels[column - 1]) for column in options}

    st.markdown(_t("**告诉我，哪两列需要比较？**"))
    st.caption(_t("编号用于找到同一笔记录，金额用于比较数值；两张表的列名可以不同。"))
    id_column, amount_column = st.columns(2)
    identifier = id_column.selectbox(_t('{0}编号列', _t(label)), options, format_func=column_labels.__getitem__,
                              key=key, on_change=_invalidate,
                              help=_t("例如订单号。请选两张表中含义一致的编号，不按行的先后顺序配对。"))
    amounts = [option for option in options if option is None or option != identifier]
    if st.session_state.get(f"{side}_amount") not in amounts:
        st.session_state[f"{side}_amount"] = None
    amount = amount_column.selectbox(_t('{0}金额列', _t(label)), amounts, format_func=column_labels.__getitem__,
                          key=f"{side}_amount", on_change=_invalidate,
                          help=_t("选择本次要比较的金额列，不能和编号选同一列。"))
    if identifier is not None and amount is not None:
        examples = [_t("编号 {0} ｜ 金额 {1}", _text(row.cells[identifier - 1].value, 48), _text(row.cells[amount - 1].value, 48))
                    for row in source.rows[:3]]
        st.text(((_t("映射示例\n") + "\n".join(examples)) if examples else _t("该表只有表头，没有数据记录。")))
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
        details = {"文件角色": SIDE_LABELS[row.source.side], "文件名": _text(table.source.spec.filename),
                   "工作表": pos.sheet if pos.sheet is not None else "CSV", "原始行号": pos.row,
                   "CSV物理起始行": pos.physical_start, "CSV物理结束行": pos.physical_end,
                   "编号列号": table.mapping.id_column, "金额列号": table.mapping.amount_column,
                   "原始编号": _text(row.id_raw), "原始金额": _text(row.amount_raw),
                   "编号原始类型": row.raw_types[0], "金额原始类型": row.raw_types[1],
                   "金额（分）": str(row.amount_minor) if row.amount_minor is not None else "—",
                   "source_id": source_id, "result_id": entry.result_id,
                   "SHA-256": table.source.sha256, "隐藏行": pos.hidden,
                   "问题码": list(entry.problem_codes), "规范化说明": list(row.normalization_notes)}
        metadata.append(details)
        rows.append({name: value for name, value in details.items() if name in (
            "文件角色", "文件名", "工作表", "原始行号", "CSV物理起始行", "CSV物理结束行", "编号列号", "金额列号",
            "原始编号", "原始金额", "金额（分）", "source_id")})
    st.caption(_t("按下面的文件、工作表和原始行号回到源表检查。需要修改时，请修正源表并重新上传。"))
    if issues:
        st.warning(issue_explanation(item.problem_codes, _language()))
        st.info(_t("处理建议：") + issue_next_steps(item.problem_codes, _language()))
    roles = [metadata[0]["文件角色"]] if issues else ["订单", "收款"]
    for column, role in zip(st.columns(len(roles)), roles):
        with column, st.container(border=True):
            st.markdown(_t('**{0}来源**', _t(role)))
            detail = next((entry for entry in metadata if entry["文件角色"] == role), None)
            if detail is None:
                st.write(_t("本次有效记录中未找到这一侧的配对；不代表金额为零。"))
                continue
            st.text((_t("文件：") + _text(detail["文件名"], 160)))
            st.text((_t("工作表：") + _text(detail["工作表"], 100)))
            st.text(_t('原始行号：{0}', detail['原始行号']))
            st.text((_t("原始编号：") + _text(detail["原始编号"], 240)))
            st.text((_t("原始金额：") + _text(detail["原始金额"], 240)))
    st.caption(_t("较长字段在上方注明显示已缩短；下方完整来源保留全部原值及 CSV 物理行范围。"))
    with st.expander(_t("完整来源、原始类型与问题修复建议")):
        st.dataframe([_localized_fields(row) for row in rows], hide_index=True, width="stretch", key="source_detail")
        st.json([_localized_fields(row) for row in metadata], expanded=True)
        codes = dict.fromkeys(code for entry in entries.values() for code in entry.problem_codes)
        for code in codes:
            st.text(f"{code}: {_t(PROBLEM_HELP[code])}")
        if not codes:
            st.caption(_t("此业务结果没有数据问题。修正源数据后重新核对，不在页面编辑金额。"))


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
        with st.container(key="results_empty"):
            st.markdown(get_html("empty", _language()), unsafe_allow_html=True)
        return
    st.header(_t("3 · 核对结果"), anchor="review-results")
    summary, counts = result.manifest.summaries, result.manifest.status_counts
    st.caption(_t("先看需要检查的记录，再选择一条查看来源。筛选与翻页不会改变完整报告。"))
    with st.container(key="result_summary"):
        for column, status in zip(st.columns(5), tuple(Status)[:5]):
            unit = "配对" if status in (Status.EXACT_MATCH, Status.AMOUNT_MISMATCH) else "源行" if status == Status.DATA_ISSUE else "条"
            column.metric(_t("{0}（{1}）", _t(STATUS_LABELS[status]), _t(unit)), counts[status])
    message = _t(outcome(result))
    if counts[Status.DATA_ISSUE] or any(counts[s] for s in (Status.AMOUNT_MISMATCH, Status.ONLY_ORDER, Status.ONLY_PAYMENT)):
        st.warning(message)
    else:
        st.info(message)
    for warning in result.manifest.warnings:
        st.warning(_t(warning))
    with st.expander(_t("核对范围与金额口径 · 输入记录、可核对金额和问题金额")):
        columns = st.columns(4)
        columns[0].metric(_t("订单输入记录"), summary[Side.ORDER].input_count)
        columns[1].metric(_t("收款输入记录"), summary[Side.PAYMENT].input_count)
        columns[2].metric(_t('订单可核对金额 · {0}', result.manifest.rules.currency), money(summary[Side.ORDER].valid_total_minor))
        columns[3].metric(_t('收款可核对金额 · {0}', result.manifest.rules.currency), money(summary[Side.PAYMENT].valid_total_minor))
        st.metric(_t("空行跳过（源行）"), counts[Status.SKIPPED_EMPTY])
        st.caption(_t("差额 = 收款减订单；缺项只表示本次有效集合中未配对。问题金额不计入可核对金额。"))
        st.caption(_t("问题行可解析部分：订单 {0}，收款 {1}；金额不可解析行数：订单 {2}，收款 {3}。",
                      money(summary[Side.ORDER].issue_parseable_minor), money(summary[Side.PAYMENT].issue_parseable_minor),
                      summary[Side.ORDER].issue_unparseable_count, summary[Side.PAYMENT].issue_unparseable_count))
    with st.container(border=True, key="guidance"):
        explanation, actions = st.columns([2, 1], vertical_alignment="center")
        explanation.markdown(_t("**接下来怎么看？**"))
        if counts[Status.DATA_ISSUE]:
            explanation.write(_t("先查看「数据问题」：这些源行尚未参与金额比较。检查原因，在原表修正后重新上传。"))
            actions.button(_t("先看数据问题"), key="review_issues", on_click=_show_result_view, args=("数据问题",), width="stretch")
        if counts[Status.AMOUNT_MISMATCH]:
            actions.button(_t("查看金额差异"), key="review_differences", on_click=_show_result_view, args=("金额差异",), width="stretch")
        if counts[Status.ONLY_ORDER] or counts[Status.ONLY_PAYMENT]:
            explanation.caption(_t("单侧缺项需检查导出期间和数据范围；金额差异可回查两侧原始行。"))
        if not result.records and not counts[Status.DATA_ISSUE]:
            explanation.write(_t("这次没有可核对的业务记录。检查工作表、表头行和数据范围，确认原表是否只有表头或空行。"))
        elif not any(counts[status] for status in (Status.DATA_ISSUE, Status.AMOUNT_MISMATCH,
                                                  Status.ONLY_ORDER, Status.ONLY_PAYMENT)):
            explanation.write(_t("可继续抽查来源，再到第 4 步生成报告保存本次结果。是否包含全部业务，仍需核实原表的导出范围。"))
        actions.markdown(_t("[前往生成报告 ↓](#save-report)"))
    view = st.radio(_t("结果分类"), VIEWS, format_func={value: _t(value) for value in VIEWS}.__getitem__,
                    horizontal=True, key="result_view", on_change=_page_reset)
    if view == "数据问题":
        st.caption(_t("同一源行只计一次。重复编号不会自动合并；一侧编号关联行有问题时，该编号在两侧的相关行一起列入数据问题。"))
    left, right = st.columns(2)
    query = left.text_input(_t("搜索业务编号（区分大小写，包含匹配）"), max_chars=128, key="query", on_change=_page_reset)
    selected = right.multiselect(_t("业务状态筛选"), BUSINESS_LABELS,
                                 format_func={value: _t(value) for value in BUSINESS_LABELS}.__getitem__,
                                 key="status_filter", disabled=view == "数据问题", on_change=_page_reset)
    filtered = view != VIEWS[0] or bool(query) or set(selected) != set(BUSINESS_LABELS)
    st.button(_t("清空筛选"), key="clear_filters", on_click=_show_result_view, args=(VIEWS[0],),
              disabled=not filtered, help=_t("恢复全部业务结果、清空搜索并回到第一页，不改变核对结果或报告。"))
    st.caption((_t("筛选只改变当前显示，完整报告不受影响。") if not filtered else _t("正在显示筛选后的记录；没有匹配项时，可点击「清空筛选」查看全部业务结果。")))
    statuses = [status for status in tuple(Status)[:4] if STATUS_LABELS[status] in selected]
    page = result_page(result, view, query, statuses, int(st.session_state.page_number))
    if st.session_state.page_number != page.number:
        st.session_state.page_number = page.number
    previous, page_selector, following = st.columns([1, 2, 1], vertical_alignment="bottom")
    previous.button(_t("上一页"), key="previous_page", on_click=_move_page, args=(-1,),
                    disabled=page.number <= 1, width="stretch")
    page_selector.number_input(_t("页码"), min_value=1, max_value=page.pages, step=1, key="page_number",
                               on_change=lambda: st.session_state.pop("detail_id", None))
    following.button(_t("下一页"), key="next_page", on_click=_move_page, args=(1,),
                     disabled=page.number >= page.pages, width="stretch")
    st.caption(_t('共 {0} 条 · 第 {1} / {2} 页 · 每页 {3} 条', page.total, page.number, page.pages, PAGE_SIZE))
    issues = view == "数据问题"
    st.dataframe(issue_rows(page.items, _language()) if issues else business_rows(page.items, _language()), hide_index=True,
                 width="stretch", key="result_table",
                 column_order=tuple(_t(key) for key in ("业务编号", "问题说明", "文件角色", "原始行号", "原始金额", "处理建议", "全部问题码", "状态")) if issues else None)
    if page.items:
        current = {item.source_id if issues else item.result_id: item for item in page.items}
        options = [None, *current]
        if st.session_state.get("detail_id") not in options:
            st.session_state.detail_id = None
        detail_labels = {key: _t("选择一条结果") if key is None else _literal_label(
                         f"{_text(current[key].row.id_raw) if issues else current[key].id} · {_t(SIDE_LABELS[current[key].row.source.side] if issues else STATUS_LABELS[current[key].status])}"
                         + (_t(" · 源行 {0}", current[key].row.source.position.row) if issues else "")) for key in options}
        selected_id = st.selectbox(_t("查看来源详情（当前页）"), options, key="detail_id", format_func=detail_labels.__getitem__)
        if selected_id is not None:
            _source_detail(result, current[selected_id], issues)
    else:
        st.info(_t("没有符合当前筛选条件的记录。"))
    with st.container(border=True, key="report_card"):
        st.subheader(_t("4 · 下载报告"), anchor="save-report")
        description, contents = st.columns([2, 1], gap="large")
        with contents:
            st.markdown(_t("**一份 Excel，五张工作表**"))
            st.caption(" · ".join(_t(name) for name in SHEET_NAMES))
            st.caption(_t("Excel 报告保持中文格式；界面语言切换不会改写报告。"))
            st.caption(_t('数据问题 {0} 行 · 规则 {1}', counts[Status.DATA_ISSUE], result.manifest.rules.version))
        with description:
            st.write(_t("先生成并检查，再下载保存。"))
            st.caption(_t("报告包含本次完整结果，当前分类、搜索和分页不会改变报告内容。"))
            if st.button(_t("生成报告"), key="prepare_report", disabled=workflow.report_bytes is not None):
                try:
                    with st.spinner(_t("正在生成并回读审计报告，请等待完成。")):
                        workflow.prepare_report()
                except Exception as exc:
                    _show_error(exc, "EXPORT")
            if workflow.report_bytes is not None:
                st.success(_t("报告已生成。下一步点击「下载核对报告」，由浏览器保存文件。"))
                st.download_button(_t("下载核对报告"), data=lambda: _current_download(workflow, result.manifest.run_id),
                                   file_name=workflow.report_name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key=f"download_{result.manifest.run_id}", on_click="ignore", type="primary")
                st.caption(_t("已通过回读审计。下载文件包含原始业务字段，请妥善保管。"))
            else:
                st.caption(_t("生成成功不代表文件已保存到电脑；生成后还需点击下载。"))


def _prepare_data(workflow):
    st.header(_t("1 · 导入文件，选好两列"), anchor="import-files")
    st.caption(_t("每侧各选编号列和金额列。按相同编号对应，不要求两张表的行顺序相同。"))
    practice_notice = st.empty()
    columns = st.columns(2, gap="medium")
    cards = [column.container(border=True, key=f"import_{side}") for side, column in zip(Side, columns)]
    selections = {}
    for side, card in zip(Side, cards):
        with card:
            selections[side] = _select_input(side)
    workflow.sync_inputs(selections)
    _apply_requested_template(workflow)
    mappings = {}
    for side, card in zip(Side, cards):
        with card:
            mappings[side] = _preview_mapping(side, workflow)
    if _using_demo(workflow):
        practice_notice.info(_t("正在练习虚构样例。检查两侧预览和编号 / 金额选择，再到第 2 步确认币种与期间。样例故意包含差异和问题行，不是操作失败。"))
    with st.container(border=True, key="confirmation"):
        st.header(_t("2 · 确认币种和期间"), anchor="confirm-rules")
        st.caption(_t("只比较同一币种、同一期间的记录。程序不会替你确认导出范围。"))
        left, right = st.columns([1, 2])
        currency = left.selectbox(_t("币种"), ["CNY", *sorted(SUPPORTED_CURRENCIES - {"CNY"})], key="currency", on_change=_invalidate)
        period = right.text_input(_t("核对期间"), key="period", max_chars=200, placeholder=_t("例如：2026-10-01 至 2026-10-31"), on_change=_invalidate)
        confirmed_currency = st.checkbox(_t("我确认两个文件属于同一币种"), key="confirm_currency", on_change=_invalidate)
        confirmed_period = st.checkbox(_t("我确认两个文件属于上述同一核对期间"), key="confirm_period", on_change=_invalidate)
        workflow.configure(mappings, Rules(currency=currency, period=period, same_currency_confirmed=confirmed_currency,
                                            same_period_confirmed=confirmed_period))
        with st.expander(_t("这次会按什么规则核对？")):
            st.markdown(_t("- 编号按文本精确对应，保留前导零；每个编号在每张表中最多出现一次。\n"
                        "- 金额按两位小数比较，差 0.01 也会标为金额差异。\n"
                        "- 不合并重复编号；某编号关联行有问题时，两侧相关记录一起隔离。\n"
                        "- 不处理退款、手续费、分期或拆分收款。差异不直接代表欠款、欺诈或会计错误。"))
        with st.expander(_t("经常处理同一格式？复用字段映射（可选）"), expanded=st.session_state.template_enabled):
            st.caption(_t("第一次使用可跳过。模板只帮你复用选列设置，仍需检查当前文件并重新确认。"))
            _mapping_templates(workflow, mappings)
        readiness_notice = st.empty()
        if st.button(_t("开始核对"), key="run_reconciliation", type="primary", disabled=not workflow.ready, width="stretch"):
            try:
                with st.spinner(_t("正在校验、隔离问题编号并核对来源账本。")):
                    workflow.run()
                st.session_state.notice = None
                _page_reset()
                st.session_state.navigate_to = "核对结果"
                st.rerun()
            except Exception as exc:
                _show_error(exc, "RECONCILE")
        if not workflow.ready:
            pending = _pending_steps(workflow)
            readiness_notice.info((_t("开始前还需完成：\n\n") + "\n".join(f"- {item}" for item in pending)))
        elif workflow.result is None:
            readiness_notice.success(_t("准备好了。点击「开始核对」，查看哪些记录一致、哪些需要检查。"))


def main():
    st.set_page_config(page_title=_t("SheetCheck · 两表核对"), page_icon="▦", layout="wide")
    _init()
    workflow = st.session_state.workflow
    requested = st.session_state.navigate_to or st.session_state.workspace_tab
    canonical_tab = next((tab for tab in WORKSPACES if requested in (tab, translate(tab, "en"))), WORKSPACES[0])
    st.session_state.workspace_tab = _t(canonical_tab)
    st.session_state.navigate_to = None
    # Static, local presentation assets only; original business fields never
    # enter HTML. Keep all tab widgets mounted to retain their current values.
    st.markdown(get_styles(st.session_state.appearance, st.context.theme.type == "dark"), unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(get_html("brand", _language()), unsafe_allow_html=True)
        st.selectbox("界面语言 / Language", ["zh", "en"], key="language",
                     format_func=lambda value: {"zh": "简体中文", "en": "English"}[value],
                     on_change=_language_changed)
        st.radio(_t("外观"), ["light", "dark"], key="appearance", horizontal=True,
                 format_func={"light": _t("浅色"), "dark": _t("夜间")}.__getitem__)
        st.caption(_t("把两张表，核对清楚。"))
        st.button(_t("加载虚构样例"), key="load_demo", on_click=_load_demo, width="stretch",
                  help=_t("先清空本次输入和结果，再载入两张虚构样例表。"))
        st.button(_t("重新开始"), key="reset", on_click=_reset, width="stretch",
                  help=_t("清空本会话的输入、选择和结果；已经下载的文件不受影响。"))
        st.divider()
        st.markdown(_t("**工作方式**\n\n准备数据 → 核对结果 → 下载报告"))
        st.caption(_t("CSV / XLSX · 每份最多 10 MiB"))
        st.caption(_t("本机处理 · 无需账户 · 保留原文件"))
    _welcome(workflow)
    if st.session_state.notice:
        st.info(_t(st.session_state.notice))
    prepare, results, guide = st.tabs([_t(tab) for tab in WORKSPACES],
                                      key="workspace_tab", on_change="rerun")
    with prepare:
        _prepare_data(workflow)
    with results:
        _results(workflow)
    with guide:
        _guide()
    # A template may invalidate the run while input widgets are being rendered.
    # Apply its requested navigation before the next tab widget is instantiated.
    if st.session_state.navigate_to is not None:
        st.rerun()
    with st.sidebar, st.container(key="session_overview"):
        st.info(_t("当前进度：") + _t(_session_progress(workflow)))
        st.caption(_t("刷新浏览器可能丢失未下载结果。已下载文件需自行管理。"))
        st.caption(_t('应用 {0} · 核对规则 v1', APP_VERSION))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print uploaded rows/filenames through an uncaught traceback.
        workflow = st.session_state.get("workflow")
        if workflow is not None:
            workflow.invalidate()
        _show_error(error, "PAGE")
