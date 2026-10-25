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
  padding: .9rem 1rem;
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
  font-size: 1.7rem;
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
  .sc-example-number { font-size: 1.5rem; }
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
