"""Static presentation for the local workbench; never interpolate input data.

These constants contain only application-owned CSS and fictional example text.
Business values continue through Streamlit's text and table components.
"""

STYLES = """<style>
:root {
  --sc-canvas: #f5f6f2;
  --sc-paper: #ffffff;
  --sc-ink: #172f37;
  --sc-muted: #62747a;
  --sc-line: #dde5e1;
  --sc-teal: #137b70;
  --sc-navy: #122e3a;
  --sc-soft: #edf5f1;
}
.stApp, [data-testid="stAppViewContainer"] {
  background: var(--sc-canvas);
  color: var(--sc-ink);
}
[data-testid="stHeader"] {
  background: rgba(245, 246, 242, .94);
}
[data-testid="stMainBlockContainer"] {
  max-width: 1440px;
  padding: 4rem 2.6rem 3.5rem;
}
[data-testid="stMain"] h1 {
  color: var(--sc-ink);
  font-size: clamp(1.75rem, 2.65vw, 2.35rem);
  font-weight: 720;
  letter-spacing: -.045em;
  line-height: 1.3;
  padding-bottom: .75rem;
}
[data-testid="stMain"] h2 {
  color: var(--sc-ink);
  font-size: 1.45rem;
  font-weight: 680;
  letter-spacing: -.025em;
}
[data-testid="stMain"] h3 {
  color: var(--sc-ink);
  font-size: 1.15rem;
  font-weight: 680;
  letter-spacing: -.015em;
}
[data-testid="stMain"] p {
  line-height: 1.7;
}
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
  color: var(--sc-muted);
  line-height: 1.65;
}
[data-testid="stWidgetLabel"] p {
  font-weight: 600;
  color: var(--sc-ink);
  font-size: .875rem;
}
[data-testid="stSidebar"] {
  background: var(--sc-navy);
  color: #eaf2f3;
  width: 244px !important;
  min-width: 244px !important;
  max-width: 244px !important;
  border-right: 1px solid #213e49;
}
[data-testid="stSidebarContent"] {
  padding-top: 1rem;
}
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {
  color: #c0d4d9;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
  color: #eaf2f3;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
  color: #b1c6cc;
}
[data-testid="stSidebar"] a {
  color: #a3e0d4;
}
[data-testid="stSidebar"] hr {
  border-color: #35515c;
  margin: 1.25rem 0;
}
[data-testid="stSidebar"] button[kind="secondary"]:not(:disabled) {
  background: #203d49;
  border-color: #3d5a65;
  color: #edf5f5;
  border-radius: 10px;
}
[data-testid="stSidebar"] button[kind="secondary"]:not(:disabled) p {
  color: inherit;
}
[data-testid="stSidebar"] button[kind="secondary"]:hover:not(:disabled) {
  background: #2c4c57;
  border-color: #80b7b1;
  color: #ffffff;
}
[data-testid="stSidebar"] [data-testid="stAlert"] {
  border: 1px solid #3d6771;
  background: #1d414c;
  color: #e5f3f1;
}
.sc-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 0 1.4rem;
}
.sc-brand-mark {
  display: grid;
  grid-template-columns: repeat(2, 11px);
  gap: 4px;
  padding: 9px;
  background: #244a54;
  border: 1px solid #426771;
  border-radius: 11px;
  flex: none;
}
.sc-brand-mark i {
  width: 11px;
  height: 11px;
  border-radius: 3px;
  background: #a8d9cf;
}
.sc-brand-mark i:last-child {
  background: #63b6a7;
}
.sc-brand-name {
  color: #f4fbfa;
  font-size: 1.25rem;
  font-weight: 750;
  line-height: 1.25;
  letter-spacing: -.045em;
}
.sc-brand-caption {
  color: #b1c6cc;
  font-size: .74rem;
  margin-top: 5px;
  letter-spacing: .05em;
}
.st-key-hero {
  background: var(--sc-paper);
  border: 1px solid var(--sc-line);
  border-radius: 18px;
  padding: 1.8rem 2rem;
  box-shadow: 0 4px 18px rgba(25, 54, 48, .025);
}
.st-key-import_order, .st-key-import_payment,
.st-key-confirmation, .st-key-guidance, .st-key-report_card,
.st-key-session_overview, .st-key-results_empty {
  background: var(--sc-paper);
  border: 1px solid var(--sc-line);
  border-radius: 16px;
  padding: 1.4rem 1.5rem;
}
.st-key-import_order, .st-key-import_payment {
  border-top: 3px solid #5e9c91;
}
.st-key-confirmation {
  background: #f9fcfa;
  border-color: #ccded5;
}
.st-key-report_card {
  background: #f1f8f4;
  border-color: #c9ddd2;
}
[data-testid="stSidebar"] .st-key-session_overview {
  background: transparent;
  border: 0;
  padding: 1rem 0 0;
}
.st-key-result_summary [data-testid="stMetric"] {
  background: var(--sc-paper);
  border: 1px solid var(--sc-line);
  border-radius: 14px;
  padding: 1rem 1.15rem;
  min-height: 115px;
}
.st-key-result_summary [data-testid="stMetricLabel"] {
  color: var(--sc-muted);
}
.st-key-result_summary [data-testid="stMetricLabel"] .stMarkdownEllipsis,
.st-key-result_summary [data-testid="stMetricLabel"] p {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  line-height: 1.5;
  font-size: .8rem;
}
.st-key-result_summary [data-testid="stMetricLabel"] {
  min-height: 2.6rem;
  height: auto;
}
.st-key-result_summary [data-testid="stMetricValue"] {
  color: #173e41;
  font-size: 2rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.04em;
}
.st-key-result_summary [data-testid="stColumn"]:nth-child(2) [data-testid="stMetricValue"] {
  color: #98602f;
}
.st-key-result_summary [data-testid="stColumn"]:nth-child(5) [data-testid="stMetricValue"] {
  color: #a04c45;
}
[data-testid="stTabs"] [role="tablist"] {
  gap: 1.6rem;
  border-bottom: 1px solid var(--sc-line);
  padding: .25rem 0 0;
}
[data-testid="stTabs"] [role="tab"] {
  height: 3rem;
  color: var(--sc-muted);
}
[data-testid="stTabs"] [role="tab"] p {
  font-size: .95rem;
  font-weight: 650;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: #0e7165;
}
[data-testid="stTabs"] [role="tabpanel"] {
  padding-top: 1.4rem;
}
[data-testid="stFileUploaderDropzone"] {
  background: #f6faf8;
  border: 1px dashed #acc6bb;
  border-radius: 12px;
  padding: 1.1rem;
}
[data-testid="stExpander"] details {
  border-color: var(--sc-line);
  border-radius: 10px;
  background: rgba(255, 255, 255, .7);
}
[data-testid="stExpander"] summary {
  color: var(--sc-muted);
  font-size: .875rem;
}
[data-testid="stDataFrame"] {
  border-radius: 10px;
}
[data-testid="stAlert"] {
  border-radius: 11px;
}
[data-testid="stMain"] button[kind="primary"] {
  border-radius: 10px;
  font-weight: 650;
  min-height: 2.65rem;
}
[data-testid="stMain"] button[kind="primary"]:not(:disabled),
[data-testid="stMain"] button[kind="primary"]:not(:disabled) p {
  color: #ffffff;
}
[data-testid="stMain"] button[kind="secondary"] {
  border-radius: 10px;
}
[data-testid="stMain"] button[kind="secondary"]:not(:disabled) {
  border-color: #cedbd4;
  background: #ffffff;
}
[data-testid="stMain"] button[kind="secondary"]:hover:not(:disabled) {
  border-color: var(--sc-teal);
  background: #f2f8f5;
}
[data-testid="stMain"] button:focus-visible,
[data-testid="stSidebar"] button:focus-visible {
  outline: 3px solid #70b9ab;
  outline-offset: 3px;
}
.sc-example {
  padding: 1.25rem;
  background: #f2f7f4;
  border: 1px solid #d6e6dc;
  border-radius: 13px;
  color: var(--sc-ink);
}
.sc-example-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 1.1rem;
  font-size: .8rem;
  color: #46635c;
}
.sc-example-badge {
  padding: 3px 8px;
  background: #e2ede6;
  color: #426258;
  border-radius: 5px;
  font-size: .7rem;
  letter-spacing: .04em;
}
.sc-example-values {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.sc-example-value {
  padding: .9rem .75rem;
  background: #ffffff;
  border: 1px solid #dbe6df;
  border-radius: 9px;
}
.sc-example-label {
  color: #60756d;
  font-size: .75rem;
}
.sc-example-number {
  margin-top: 4px;
  color: #173d3c;
  font-size: clamp(1.1rem, 2vw, 1.7rem);
  white-space: nowrap;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.045em;
  line-height: 1.25;
}
.sc-example-difference {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: .9rem;
  padding-top: .85rem;
  border-top: 1px solid #d5e2d9;
  font-size: .8rem;
  color: #587065;
}
.sc-example-difference strong {
  color: #98602f;
  font-size: 1.15rem;
  font-variant-numeric: tabular-nums;
}
.sc-example-note {
  margin-top: .65rem;
  color: #62766b;
  font-size: .74rem;
  line-height: 1.6;
}
.sc-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 2.8rem 1rem;
  color: var(--sc-ink);
}
.sc-empty-mark {
  display: flex;
  gap: 7px;
  padding: 15px;
  margin-bottom: 1.3rem;
  background: #eaf3ed;
  border: 1px solid #d8e8de;
  border-radius: 16px;
}
.sc-empty-sheet {
  width: 27px;
  height: 35px;
  border: 2px solid #72968a;
  border-radius: 4px;
  background: repeating-linear-gradient(to bottom, #ffffff 0px, #ffffff 7px, #dbe8e0 7px, #dbe8e0 9px);
}
.sc-empty-title {
  margin-bottom: .6rem;
  font-size: 1.2rem;
  font-weight: 680;
}
.sc-empty-copy {
  max-width: 430px;
  color: var(--sc-muted);
  font-size: .9rem;
  line-height: 1.8;
}
.sc-empty-steps {
  margin-top: 1.2rem;
  padding: .65rem 1rem;
  border: 1px solid #e1e8e2;
  border-radius: 8px;
  color: #50685f;
  background: #f8faf7;
  font-size: .8rem;
  line-height: 1.8;
}
@media (max-width: 1050px) {
  [data-testid="stMainBlockContainer"] { padding: 3.75rem 1.5rem 3rem; }
  .st-key-hero { padding: 1.5rem; }
  .st-key-import_order, .st-key-import_payment { padding: 1.15rem; }
  .st-key-result_summary [data-testid="stMetric"] { padding: .85rem; }
  .st-key-result_summary [data-testid="stMetricValue"] { font-size: 1.7rem; }
}
@media (max-width: 760px) {
  [data-testid="stMainBlockContainer"] { padding: 3.5rem 1rem 2.5rem; }
  [data-testid="stSidebar"] {
    width: min(82vw, 244px) !important;
    min-width: 0 !important;
    max-width: 82vw !important;
  }
  [data-testid="stMain"] h1 { font-size: 1.8rem; }
  .st-key-hero, .st-key-import_order, .st-key-import_payment,
  .st-key-confirmation, .st-key-guidance, .st-key-report_card,
  .st-key-session_overview, .st-key-results_empty { padding: 1.1rem; border-radius: 12px; }
  [data-testid="stTabs"] [role="tablist"] { gap: .85rem; }
  [data-testid="stTabs"] [role="tab"] p { font-size: .85rem; }
  .sc-example { padding: 1rem; }
  .sc-example-number { font-size: clamp(1.1rem, 4vw, 1.5rem); }
  .sc-empty { padding: 2rem .25rem; }
}
</style>"""

BRAND_HTML = """<div class="sc-brand">
<div class="sc-brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
<div><div class="sc-brand-name">SheetCheck</div><div class="sc-brand-caption">本地核对工作台</div></div>
</div>"""

EXAMPLE_HTML = """<div class="sc-example" role="group" aria-label="虚构样例：A002 金额差异">
<div class="sc-example-heading"><span>同一编号 · <strong>A002</strong></span><span class="sc-example-badge">虚构演示</span></div>
<div class="sc-example-values">
<div class="sc-example-value"><div class="sc-example-label">订单应收</div><div class="sc-example-number">50.00</div></div>
<div class="sc-example-value"><div class="sc-example-label">收款实收</div><div class="sc-example-number">49.00</div></div>
</div>
<div class="sc-example-difference"><span>金额差异 · 收款减订单</span><strong>-1.00</strong></div>
<div class="sc-example-note">找到差额，再沿原表行号检查原因。</div>
</div>"""

EMPTY_RESULTS_HTML = """<div class="sc-empty" role="status">
<div class="sc-empty-mark" aria-hidden="true"><div class="sc-empty-sheet"></div><div class="sc-empty-sheet"></div></div>
<div class="sc-empty-title">准备好两张表，就能开始核对</div>
<div class="sc-empty-copy">先在「准备数据」中导入文件、选择编号与金额列，确认核对范围后点击「开始核对」。结果会显示在这里。</div>
<div class="sc-empty-steps">比较金额 · 找到缺项 · 追溯原行 · 保存报告</div>
</div>"""

# These are application-owned translations, not transformations of uploaded text.
BRAND_HTML_EN = """<div class="sc-brand">
<div class="sc-brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
<div><div class="sc-brand-name">SheetCheck</div><div class="sc-brand-caption">Local reconciliation workbench</div></div>
</div>"""

EXAMPLE_HTML_EN = """<div class="sc-example" role="group" aria-label="Fictional example: A002 amount difference">
<div class="sc-example-heading"><span>Same ID · <strong>A002</strong></span><span class="sc-example-badge">FICTIONAL EXAMPLE</span></div>
<div class="sc-example-values">
<div class="sc-example-value"><div class="sc-example-label">Order amount</div><div class="sc-example-number">50.00</div></div>
<div class="sc-example-value"><div class="sc-example-label">Payment received</div><div class="sc-example-number">49.00</div></div>
</div>
<div class="sc-example-difference"><span>Difference · payment minus order</span><strong>-1.00</strong></div>
<div class="sc-example-note">Find the difference, then trace its original rows.</div>
</div>"""

EMPTY_RESULTS_HTML_EN = """<div class="sc-empty" role="status">
<div class="sc-empty-mark" aria-hidden="true"><div class="sc-empty-sheet"></div><div class="sc-empty-sheet"></div></div>
<div class="sc-empty-title">Two tables are all you need to get started</div>
<div class="sc-empty-copy">In “Prepare data”, import both files, select the ID and amount columns, and confirm the scope. Click “Reconcile” to see the results here.</div>
<div class="sc-empty-steps">Compare amounts · Find missing pairs · Trace source rows · Save a report</div>
</div>"""

# Streamlit's public theme API is read-only per session. Keep these preferences
# local to this page rather than changing the process-wide configuration, which
# could affect another session. Native dataframe cells are painted on a canvas:
# the scoped display filter below adapts their palette only when it differs from
# the selected appearance. It never transforms values, tables or report bytes.
DARK_STYLES = """<style>
:root {
  color-scheme: dark;
  --sc-canvas: #101b22;
  --sc-paper: #192932;
  --sc-ink: #e4eef0;
  --sc-muted: #a7bcc3;
  --sc-line: #36505c;
  --sc-teal: #76d1be;
  --sc-navy: #0c1921;
  --sc-soft: #203a40;
  --sc-field: #223640;
}
[data-testid="stHeader"] { background: rgba(16, 27, 34, .96); }
[data-testid="stMain"] [data-testid="stMarkdownContainer"],
[data-testid="stMain"] [data-testid="stText"],
[data-testid="stMain"] [data-testid="stText"] pre,
[data-testid="stMain"] [data-testid="stText"] span,
[data-testid="stMain"] [data-testid="stText"] code,
[data-testid="stWidgetLabel"] p,
[data-testid="stMain"] label {
  color: var(--sc-ink);
}
[data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stMain"] [data-testid="stCaptionContainer"] p {
  color: var(--sc-muted);
}
[data-testid="stMain"] a { color: #8cddcd; }
[data-testid="stMain"] hr { border-color: var(--sc-line); }
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] > div {
  border-color: var(--sc-line);
}
.st-key-confirmation, .st-key-report_card { background: #182f32; border-color: #3d635e; }
.st-key-guidance { background: #1a2d36; }
[data-testid="stExpander"] details { background: #182932; border-color: var(--sc-line); }
[data-testid="stExpander"] summary { color: var(--sc-muted); }
[data-testid="stExpander"] summary p { color: var(--sc-muted); }
[data-testid="stExpander"] summary svg { color: var(--sc-muted); }
[data-testid="stTabs"] [role="tab"],
[data-testid="stTabs"] [role="tab"] p { color: var(--sc-muted); }
[data-testid="stTabs"] [role="tab"][aria-selected="true"],
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p { color: #89dfcc; }
.st-key-result_summary [data-testid="stMetricValue"],
[data-testid="stMetricValue"] { color: #e0f3ed; }
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p { color: var(--sc-muted); }
.st-key-result_summary [data-testid="stColumn"]:nth-child(2) [data-testid="stMetricValue"] { color: #ecc18b; }
.st-key-result_summary [data-testid="stColumn"]:nth-child(5) [data-testid="stMetricValue"] { color: #eeaaa0; }
.sc-example { background: #203a3d; border-color: #3b5c5a; }
.sc-example-heading, .sc-example-label, .sc-example-note { color: #b1cac6; }
.sc-example-badge { background: #30534f; color: #c2e7da; }
.sc-example-value { background: #182b32; border-color: #3d5b5b; }
.sc-example-number { color: #e5f7ef; }
.sc-example-difference { color: #b1cac6; border-color: #456763; }
.sc-example-difference strong { color: #edc58e; }
.sc-empty-mark { background: #29453f; border-color: #46685b; }
.sc-empty-sheet { border-color: #96b9a8; background: repeating-linear-gradient(to bottom, #223e36 0px, #223e36 7px, #46685b 7px, #46685b 9px); }
.sc-empty-steps { color: #bdd1c7; background: #20372f; border-color: #466052; }
[data-testid="stFileUploaderDropzone"] { background: #20343a; border-color: #60877d; color: var(--sc-ink); }
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] [data-testid="stMarkdownContainer"] { color: var(--sc-muted); }
[data-testid="stMain"] button[kind="secondary"]:not(:disabled) { background: #223a44; border-color: #54717b; color: #e3eef0; }
[data-testid="stMain"] button[kind="secondary"]:not(:disabled) p { color: inherit; }
[data-testid="stMain"] button[kind="secondary"]:hover:not(:disabled) { background: #2c4c54; border-color: #82c6b8; }
[data-testid="stMain"] button[kind="primary"]:not(:disabled) { background: #197d70; border-color: #79c8b8; color: #ffffff; }
[data-testid="stMain"] button[kind="primary"]:not(:disabled) p { color: #ffffff; }
[data-testid="stMain"] button:disabled { background: #26353d; color: #a4b2b8; border-color: #42535c; }
[data-testid="stMain"] button:disabled p { color: #a4b2b8; }
[data-testid="stMain"] button[kind="headerNoPadding"],
[data-testid="stMain"] [data-testid="stTooltipIcon"],
[data-testid="stMain"] [data-testid="stTooltipIcon"] svg { color: #bbced3; }
[data-testid="stMain"] button:focus-visible { outline-color: #8ddccb; }
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
  background: var(--sc-field);
  border-color: #526c77;
  color: var(--sc-ink);
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] input,
[data-testid="stMultiSelect"] input {
  color: var(--sc-ink);
  -webkit-text-fill-color: var(--sc-ink);
  caret-color: #b8e8d9;
  background: transparent;
}
[data-testid="stMain"] input::placeholder,
[data-testid="stMain"] textarea::placeholder { color: #a7bbc2; opacity: 1; }
/* Streamlit 1.66 uses React Aria for these widgets. Select only its documented
   roles and stable test IDs, not generated Emotion class names. */
[data-testid="stTextInputRootElement"],
[data-testid="stTextArea"] .react-aria-TextField,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInputContainer"],
[data-testid="stSelectbox"] .react-aria-ComboBox > [role="group"],
[data-testid="stMultiSelect"] .react-aria-ComboBox > [role="group"] {
  background: var(--sc-field);
  border-color: #526c77;
  color: var(--sc-ink);
}
[data-testid="stTextInputField"],
[data-testid="stNumberInputField"],
[data-testid="stSelectbox"] input[role="combobox"],
[data-testid="stMultiSelect"] input[role="combobox"] {
  color: var(--sc-ink);
  -webkit-text-fill-color: var(--sc-ink);
  caret-color: #b8e8d9;
  background: transparent;
}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stSelectbox"] [role="group"][data-focus-within],
[data-testid="stMultiSelect"] [role="group"][data-focus-within] { border-color: #8bd5c5; }
[data-testid="stSelectbox"] input::placeholder,
[data-testid="stMultiSelect"] input::placeholder { color: #a7bbc2; opacity: 1; }
[data-testid="stSelectbox"] button,
[data-testid="stMultiSelect"] button,
[data-testid="stTextInputRootElement"] button,
[data-testid="stNumberInputContainer"] button {
  color: #d7e8ed;
  background: transparent;
}
[data-testid="stSelectbox"] button svg,
[data-testid="stMultiSelect"] button svg,
[data-testid="stTextInputRootElement"] button svg,
[data-testid="stNumberInputContainer"] [data-testid="stIconMaterial"] { color: inherit; }
[data-testid="stSelectbox"] [data-disabled],
[data-testid="stMultiSelect"] [data-disabled],
[data-testid="stTextInputField"]:disabled,
[data-testid="stNumberInputField"]:disabled {
  color: #a0b4bc;
  -webkit-text-fill-color: #a0b4bc;
}
[data-testid="stSelectbox"] .react-aria-ComboBox[data-disabled] > [role="group"],
[data-testid="stMultiSelect"] .react-aria-ComboBox[data-disabled] > [role="group"],
[data-testid="stTextInputRootElement"]:has(input:disabled),
[data-testid="stNumberInputContainer"]:has(input:disabled) { background: #26353d; border-color: #42535c; }
[data-testid="stMultiSelectTagsContainer"] [data-tag] { background: #28695f; color: #f0fbf6; }
[data-testid="stMultiSelect"] .react-aria-ComboBox[data-disabled] [data-tag] { background: #3c5057; color: #b9c9ce; }
[data-testid="stSelectboxVirtualDropdown"],
[data-testid="stMultiSelectDropdown"],
.react-aria-Popover, .react-aria-ListBox { background: #20333d; color: #e4eef0; border-color: #526c77; }
.react-aria-ListBoxItem { background: #20333d; color: #e4eef0; }
.react-aria-ListBoxItem[data-focused],
.react-aria-ListBoxItem[data-selected] { background: #355b60; color: #f5fffc; }
[data-testid="stRadioOption"], [data-testid="stRadioCaption"],
[data-testid="stCheckbox"] label { color: var(--sc-ink); }
[data-testid="stRadioOption"][data-disabled],
[data-testid="stRadioGroup"][aria-disabled="true"] [data-testid="stMarkdownContainer"],
[data-testid="stCheckbox"][data-disabled] [data-testid="stMarkdownContainer"] { color: #a0b4bc; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: #e4eef0; }
[data-testid="stNumberInput"] button { background: #29424c; color: #d5e5e9; border-color: #526c77; }
[data-testid="stNumberInput"] button:disabled { color: #8eabb5; background: #26353d; }
[data-baseweb="select"] [role="combobox"],
[data-baseweb="select"] [role="combobox"] ~ div,
[data-baseweb="select"] svg { color: var(--sc-ink); }
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label { color: var(--sc-ink); }
[data-testid="stCheckbox"] input,
[data-testid="stRadio"] input { accent-color: #72c8b6; }
[data-baseweb="popover"], [data-baseweb="popover"] > div,
[role="listbox"], [role="listbox"] ul, [role="listbox"] li {
  color: var(--sc-ink);
  background: #20333d;
  border-color: #526c77;
}
[role="option"] { color: #e4eef0; background: #20333d; }
[role="option"][aria-selected="true"], [role="option"]:hover { color: #f5fffc; background: #355b60; }
[data-baseweb="tooltip"], [role="tooltip"] { color: #e7f0f2; background: #293f48; }
[data-testid="stAlert"] { color: #daeaf0; background: #233d49; border: 1px solid #466574; }
[data-testid="stAlert"] [data-testid="stAlertContainer"] { color: inherit; background: inherit; border-color: inherit; }
[data-testid="stAlert"] [data-testid^="stAlertContent"] { color: inherit; background: transparent; }
[data-testid="stAlert"] [data-testid="stMarkdownContainer"],
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p { color: inherit; }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) { color: #f0dcb0; background: #433b24; border-color: #7a6840; }
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) { color: #ffd2cc; background: #472f34; border-color: #875560; }
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) { color: #c1eed4; background: #243e32; border-color: #4a745c; }
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) { color: #c8e5f0; background: #233d49; border-color: #466574; }
[data-testid="stJson"] { background: #182932; border-radius: 10px; }
[data-testid="stJson"] .react-json-view { background: #182932 !important; color: #dce9ed !important; }
[data-testid="stJson"] .object-key,
[data-testid="stJson"] .node-ellipsis,
[data-testid="stJson"] .object-size,
[data-testid="stJson"] .data-type-label { color: #c3d4da !important; }
[data-testid="stJson"] .string-value { color: #b9e4c9 !important; }
[data-testid="stJson"] .variable-value { color: #cfe3ed !important; }
[data-testid="stJson"] svg { color: #afc5cc !important; }
[data-testid="stMarkdownContainer"] table th { background: #263f48; color: #e4eef0; border-color: #526c77; }
[data-testid="stMarkdownContainer"] table td { color: #d6e5e9; border-color: #425d68; }
[data-testid="stMarkdownContainer"] code,
[data-testid="stCode"] { color: #c9e8df; background: #233a40; }
</style>"""

# Native dark themes are an optional user preference in Streamlit's own menu.
# If that menu is set to dark while SheetCheck selects light, keep forms readable
# rather than only switching the surrounding app canvas back to white.
LIGHT_NATIVE_OVERRIDES = """<style>
:root { color-scheme: light; }
[data-testid="stMain"] [data-testid="stMarkdownContainer"],
[data-testid="stMain"] [data-testid="stText"],
[data-testid="stMain"] [data-testid="stText"] span,
[data-testid="stMain"] [data-testid="stText"] pre,
[data-testid="stMain"] [data-testid="stText"] code,
[data-testid="stMain"] label { color: #172f37; }
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div { background: #f1f4f3; border-color: #a1b4b6; color: #172f37; }
[data-testid="stMain"] input,
[data-testid="stMain"] textarea { color: #172f37; -webkit-text-fill-color: #172f37; caret-color: #172f37; }
[data-testid="stMain"] input::placeholder,
[data-testid="stMain"] textarea::placeholder { color: #62747a; }
[data-testid="stTextInputRootElement"],
[data-testid="stTextArea"] .react-aria-TextField,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInputContainer"],
[data-testid="stSelectbox"] .react-aria-ComboBox > [role="group"],
[data-testid="stMultiSelect"] .react-aria-ComboBox > [role="group"] { background: #f1f4f3; border-color: #a1b4b6; color: #172f37; }
[data-testid="stTextInputField"], [data-testid="stNumberInputField"],
[data-testid="stSelectbox"] input[role="combobox"],
[data-testid="stMultiSelect"] input[role="combobox"] { color: #172f37; -webkit-text-fill-color: #172f37; background: transparent; caret-color: #172f37; }
[data-testid="stSelectbox"] input::placeholder,
[data-testid="stMultiSelect"] input::placeholder { color: #62747a; opacity: 1; }
[data-testid="stSelectbox"] button, [data-testid="stMultiSelect"] button,
[data-testid="stTextInputRootElement"] button, [data-testid="stNumberInputContainer"] button { color: #34535d; background: transparent; }
[data-testid="stSelectbox"] button svg, [data-testid="stMultiSelect"] button svg,
[data-testid="stTextInputRootElement"] button svg,
[data-testid="stNumberInputContainer"] [data-testid="stIconMaterial"] { color: inherit; }
[data-testid="stSelectbox"] [data-disabled], [data-testid="stMultiSelect"] [data-disabled],
[data-testid="stTextInputField"]:disabled, [data-testid="stNumberInputField"]:disabled { color: #667b80; -webkit-text-fill-color: #667b80; }
[data-testid="stSelectbox"] .react-aria-ComboBox[data-disabled] > [role="group"],
[data-testid="stMultiSelect"] .react-aria-ComboBox[data-disabled] > [role="group"],
[data-testid="stTextInputRootElement"]:has(input:disabled),
[data-testid="stNumberInputContainer"]:has(input:disabled) { background: #e7edeb; border-color: #bdccc6; }
[data-testid="stSelectboxVirtualDropdown"], [data-testid="stMultiSelectDropdown"],
.react-aria-Popover, .react-aria-ListBox, .react-aria-ListBoxItem { background: #ffffff; color: #172f37; border-color: #a1b4b6; }
.react-aria-ListBoxItem[data-focused], .react-aria-ListBoxItem[data-selected] { background: #deeee6; color: #173c35; }
[data-testid="stMultiSelectTagsContainer"] [data-tag] { background: #0f766e; color: #ffffff; }
[data-testid="stMultiSelect"] .react-aria-ComboBox[data-disabled] [data-tag] { background: #d6e2dc; color: #536b64; }
[data-testid="stRadioOption"], [data-testid="stRadioCaption"],
[data-testid="stCheckbox"] label { color: #172f37; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: #e4eef0; }
[data-testid="stMain"] button[kind="secondary"]:not(:disabled) { color: #172f37; }
[data-testid="stMain"] button[kind="primary"]:not(:disabled),
[data-testid="stMain"] button[kind="primary"]:not(:disabled) [data-testid="stMarkdownContainer"],
[data-testid="stMain"] button[kind="primary"]:not(:disabled) p { color: #ffffff; }
[data-testid="stMain"] button:disabled { color: #667b80; background: #edf2ef; border-color: #cbd6d0; }
[data-testid="stMain"] button:disabled p { color: #667b80; }
[data-baseweb="popover"], [data-baseweb="popover"] > div,
[role="listbox"], [role="option"] { background: #ffffff; color: #172f37; }
[role="option"][aria-selected="true"], [role="option"]:hover { background: #deeee6; color: #173c35; }
[data-testid="stMetricValue"] { color: #173e41; }
</style>"""


def get_styles(appearance="light", native_dark=False):
    """Return only local presentation CSS; preferences never reach core data."""
    if appearance not in ("light", "dark"):
        raise ValueError("Unknown appearance")
    # Emit one style element: adjacent wrappers can be retained as CSS text by
    # Streamlit's Markdown parser, preventing later theme rules from applying.
    def css_body(block):
        return block.removeprefix("<style>").removesuffix("</style>").strip()

    blocks = [css_body(STYLES)]
    if appearance == "dark":
        blocks.append(css_body(DARK_STYLES))
    elif native_dark:
        blocks.append(css_body(LIGHT_NATIVE_OVERRIDES))
    if (appearance == "dark") != bool(native_dark):
        # Scope to native grid canvases, never business text, images or the app.
        amount = ".9" if appearance == "dark" else "1"
        blocks.append('[data-testid="stDataFrame"] canvas '
                      '{filter: invert(' + amount + ') hue-rotate(180deg);}')
    return "<style>\n" + "\n".join(blocks) + "\n</style>"


def get_html(kind, language="zh"):
    """Select complete static text; no source values are accepted or inserted."""
    variants = {
        "brand": (BRAND_HTML, BRAND_HTML_EN),
        "example": (EXAMPLE_HTML, EXAMPLE_HTML_EN),
        "empty": (EMPTY_RESULTS_HTML, EMPTY_RESULTS_HTML_EN),
    }
    return variants[kind][language == "en"]
