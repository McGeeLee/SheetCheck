# M0 / M1 验收记录

结论：**M0 与 M1 已完成，最终完整测试 224 项通过，0 项失败，耗时 1.41 秒。** 证据为本目录 `m1-test-results.txt`；代码在独立项目目录中，没有修改父目录其他项目。范围仅为无界面内核及可复算 CLI，未宣称完成 SheetCheck v1 的 M2—M4。

## 变更摘要

M0：保存原蓝图，冻结 `v1` 规则，建立虚构 CSV/XLSX 样例和独立手写 `samples/expected.json`。预期包括每个状态、编号、两侧源行、整数分、逐源行归属和问题金额；样例生成脚本不调用核对引擎、不改预期文件。

M1：提供 `read_source`、`validate`、`reconcile`、`assert_invariants`；核心不导入 Streamlit。实现严格 CSV 逻辑/物理源位置、XLSX 原始类型及公式区域检查、文件防护、跨两表 `blocked_ids`、一对一配对、逐源行账本、输入与参数指纹、稳定排序、独立账本守恒检查。CLI 可直接对样例或显式输入文件复算 JSON。

独立审计测试会篡改结果、来源位置、问题码、风险提示、计数与金额类型、配对关系和指纹，要求失败关闭。发现并修复了 Decimal 调用方上下文影响、风险提示移除未被审计发现、源位置与身份不一致、非有限数值 JSON 输出失败、伪装空 ZIP 被误读为 CSV 等问题。

## 运行环境及安装

- 硬件：Apple M4，arm64；CPU 型号由 `sysctl -n machdep.cpu.brand_string` 实际读取。
- 系统：macOS 27.0.1；Python 3.12.14。
- 解析依赖：openpyxl 3.1.5、defusedxml 0.7.1、et_xmlfile 2.0.0。
- 测试：pytest 8.4.2；所有直接、传递、构建与测试依赖以准确版本及实际下载 wheel 的 SHA-256 写入 `requirements.lock`。
- 首次下载依赖需要网络；隔离复验使用预下载 wheel，以 `--no-index --require-hashes` 安装到新建 `.venv-clean`，然后安装项目，`pip check` 显示 `No broken requirements found.`。记录见 `clean-install.txt`。

在项目目录实际执行的最终命令：

```sh
.venv-clean/bin/python -m pytest -q
.venv-clean/bin/python -m sheetcheck --demo
.venv-clean/bin/python -m sheetcheck \
  --order-file samples/orders.xlsx --order-sheet 数据 \
  --payment-file samples/payments.xlsx --payment-sheet 数据 \
  --order-id 1 --order-amount 2 --payment-id 1 --payment-amount 2 \
  --currency CNY --period synthetic \
  --confirm-same-currency --confirm-same-period
.venv-clean/bin/python scripts/benchmark.py --format csv
.venv-clean/bin/python scripts/benchmark.py --format xlsx
```

日常环境 `.venv` 也通过了当时完整测试，最终验收以上述新建环境为准。README 中 XLSX 命令已实际运行并成功返回。

## 测试证据

测试先建立且确实出现失败：`m0-red-test.txt` 记录核心模块尚未存在时的收集失败；`m0-acceptance-red.txt` 记录独立样例验收因读取模块未实现而失败。这两份是**收集阶段失败**，不是伪装的业务断言失败。最终记录是执行全部断言后的 `224 passed in 1.41s`。

覆盖范围：

| 测试文件 | 验证内容 |
| --- | --- |
| `test_acceptance.py` | 手算样例、CSV/XLSX 一致、源行明细、12 组随机乱序、列重映射、重复运行 |
| `test_rules.py` / `test_contract.py` | 编号文本与类型、金额语法/精度/上限、全局 Decimal 上下文、坏金额重复、隔离传播、零金额、公式、空行及规则确认 |
| `test_readers.py` | BOM/GB18030/分隔符、多行 CSV、重复表头、默认 10 MiB/50000 行/100 列及超限拒绝、隐藏行、日期/错误/公式、数组范围、格式尾部、坏 ZIP/XML、外链/活动内容、解析警告脱敏 |
| `test_integrity.py` | 59 项独立审计测试；重复/丢失账本、来源及配对篡改、差额、金额与计数、问题集合、风险提示、指纹 |
| `test_cli.py` / `test_file_disguises.py` | 样例 CLI、显式确认、错误脱敏、非有限 XLSX 数值的带类型 JSON 表示、ZIP 伪装 |
| `test_local_runtime.py` | 对预载 CSV/XLSX 字节禁止文件打开和 socket 后，完整核心处理仍成功 |

## 实际样例输出

完整实际输出保存为 `sample-actual.json`，与手写预期分开。金额均为整数分。

| 状态 | 数量 | 业务结论 |
| --- | ---: | --- |
| EXACT_MATCH | 2 对 | A001、A007 |
| AMOUNT_MISMATCH | 1 对 | A002，差额 -100 |
| ONLY_ORDER | 1 条 | A003，3000 |
| ONLY_PAYMENT | 1 条 | A004，4000 |
| DATA_ISSUE | 6 源行 | 订单 4，收款 2 |
| SKIPPED_EMPTY | 0 源行 | 样例无全空记录 |

业务结果 5 条，参与业务源行 8 条，账本 14 条；`blocked_ids = [A005, A006]`。订单可核对 18000 分、收款 18900 分，`900 = -100 + 4000 - 3000`。订单问题可解析部分 3500 分，另有 1 行金额不可解析；收款问题 4200 分。存在无法识别编号风险，并带人工复核提示。

## 性能测量

在上述机器与版本上，两个文件各 10,000 条虚构记录、各 2 列、全部唯一精确配对。CSV 为 160010 字节/文件；XLSX 约 108450 字节/文件，内容是文本编号和合法金额。每格式 3 次，**每次独立子进程，CSV 与 XLSX 测量依次执行**。计时排除样例构造；核心阶段包括校验、核对及独立审计；读取单独计时。峰值使用 macOS `resource.getrusage(RUSAGE_SELF).ru_maxrss`（字节）换算 MiB，涵盖解释器、依赖、样例构造、读取及核心整个子进程。

| 输入格式 | 两侧读取中位数 | 核心中位数 | 3 次进程峰值最大值 |
| --- | ---: | ---: | ---: |
| CSV | 0.0753 秒 | 0.2473 秒 | 58.75 MiB |
| XLSX | 0.7507 秒 | 0.2687 秒 | 59.47 MiB |

原始测量见 `benchmark-csv.json`、`benchmark-xlsx.json`。此虚构规模下达到蓝图 3 秒 / 512 MiB 的目标；未证明所有允许的极端 XLSX、共享字符串或其他硬件都满足目标。XLSX **导出未实现、未计时**。

## 失败项与已知限制

最终回归无失败。尚未实施或验证的内容明确保留：

- M2 静态 Excel 报告与导出回读、公式注入防护；M3 页面、分页、状态失效与下载；M4 完整断网业务流程、网络观察、演示视频及最终交付。
- 仅验证上述 macOS / Python 3.12 环境，未验证 Windows、Linux 或其他 Python 版本。
- 支持币种目前为规则文档列出的 10 种两位小数币种；未自动校验输入实际币种和期间。CSV 单字段额外限制为 131072 个字符；部分合法但含外链/活动内容的 XLSX 会拒绝。
- 默认容量边界有测试，但未做最大共享字符串/100 MiB 解压文件的全面峰值压力验收。同步 CLI 通过 Ctrl+C 取消，没有自动墙钟超时。
- 源文件真伪与上游损坏无法由内核证明。完整性检查证明内存来源、账本与业务结果的关系；SHA-256 用于标识输入，不是文件真实性认证。
- 全局断网及整机网络监控未运行。已验证的是核心对预载样例在禁止文件打开/socket 的测试条件下仍可执行，不能扩大为已完成未来页面的隐私验收。
