# M4 容量与性能验收

所有数据均为脚本生成的虚构数据。本记录区分输入边界、功能正确性、机器上的耗时和峰值内存；输入字节上限不是进程资源上限。

验收结论（2026-10-24，Asia/Singapore）：**20 个真实默认边界全部符合预期；最终 1.0.0 的 XLSX 10k 三轮与 50k 一轮均完整通过计数、守恒及两次报告回读。** 最终 10k 核心为 0.247 / 0.254 / 0.251 秒、峰值最高 430.00 MiB，三轮均达到建议 3 秒 / 512 MiB 目标；50k 峰值 1951.33 MiB，应单独披露。原始 0.3.0 XLSX 10k 的 3.094 秒未达项和早期 50k 主动取消记录仍保留，不能将整个历史测量记录改称“全部性能通过”。最终 50k 完整流程已补测成功，不再列为未完成。

## 环境与测量方式

验收机为 Apple M4、10 个逻辑 CPU、24 GiB 物理内存，macOS 27.0.1 / arm64。硬件通过 `sysctl -n machdep.cpu.brand_string hw.memsize hw.logicalcpu` 读取。早期正式测量使用新建的 `.venv-m4-clean`，最终 1.0.0 复测使用新建并离线安装的 `.venv-m4-release`；两者均为 CPython 3.12.14、openpyxl 3.1.5、defusedxml 0.7.1、Streamlit 1.66.0。验收期间桌面仍运行本地 Streamlit 和浏览器；部分第一组 CSV 基准与安全回归重叠，XLSX 10k 组可能与首次启动 Microsoft Excel 重叠，不能描述为独占空闲机器，也不能据此断言某次波动的原因。

每轮使用一个全新的子进程，按顺序运行。`perf_counter` 测量两侧读取、核心校验与核对（包含核心审计）、静态 XLSX 导出（包含强制回读审计），随后再单独进行一次额外回读。虚构输入构建不计入各阶段时间，但计入进程峰值内存。`resource.getrusage(RUSAGE_SELF).ru_maxrss` 在 macOS 上按字节换算为 MiB；各阶段记录的是截至该阶段的累计高水位，不是阶段增量，也不包含浏览器和 Streamlit 服务进程。

较晚启动的子进程还记录 `process_time` CPU 秒，以辅助区分 CPU 消耗和墙钟等待；较早 JSON 没有该字段，不补造数值。性能目标比较仍使用墙钟秒。

2026-10-24 的第一次修复后单轮复测开始前，`ps` 只读检查未发现遗留的 benchmark、acceptance_capacity、pytest、ffmpeg 或 Streamlit 进程；同一工程的页面操作、编码和测试暂停至该轮结束。其余桌面进程未停止，因此这仍不是整机隔离或独占硬件实验。该轮 JSON 内的沙箱硬件查询只能得到逻辑 CPU 数；另一次只读 `sysctl` 复核 Apple M4 / 24 GiB / 10 个逻辑 CPU，记录在配套 context JSON。

最终 1.0.0 的三轮 10k 与一轮 50k 顺序执行，没有并行基准。开始前只读进程检查发现一个既有 Streamlit 服务（约 0.4% CPU），没有遗留基准、pytest、编码器或 Excel 进程；其他代理暂停页面、编码与测试工作，未停止用户其他进程。硬件复核与进程、系统内存上下文见 [final-context](m4-benchmark-final-context.json)。系统 swap 在前检、50k 中途及结束后均为 0，`vm_stat` 的 pageouts 均为 107；这些是机器级观察，不代表没有内存压缩，也不是固定资源保证。

基准每轮设置墙钟超时，超时会结束子进程并输出失败记录。这个验收器超时不是页面内核的资源隔离或自动取消机制。报告字节保留在子进程内存中，退出后释放。

## 真实默认边界

命令：

```sh
.venv-m4-clean/bin/python scripts/acceptance_capacity.py --timeout 120 > docs/m4-capacity-results.json
```

`scripts/acceptance_capacity.py` 不降低 `Limits()` 的默认值，每个案例由独立子进程读取实际文件。CSV 和 XLSX 分别检查恰好 10 MiB 与多 1 字节、50,000 条数据记录与多 1 条、100 列与多 1 列。其他 XLSX 案例检查：

| 边界 | 恰限构造 | 超限构造 | 预期拒绝码 |
| --- | --- | --- | --- |
| 解压累计大小 | 所有部件合计 104,857,600 字节；主要载荷为未选中 XML | 合计多 1 字节 | `XLSX_UNCOMPRESSED_LIMIT` |
| ZIP 条目数 | 2000 个真实条目 | 2001 个条目 | `XLSX_ZIP_ENTRY_LIMIT` |
| 条目压缩比 | 4400 字节内容实际 DEFLATE 为 22 字节，200:1 | 4401 / 22，约 200.045:1 | `XLSX_COMPRESSION_RATIO` |
| XML 嵌套 | 128 层 | 129 层 | `XLSX_XML_DEPTH` |

100 MiB XML 通过小块流式构造并实际解压、CRC 校验和 XML 预检；没有伪造 ZIP 长度字段。10 MiB XLSX 使用实际容器内存储部件达到精确压缩后长度。各维度单独达到上限，不能将这些结果解释为“50,000 行 × 100 列 × 最大字段”组合压力全部通过。

较快的默认边界另纳入 `tests/test_capacity_acceptance.py`：100 列、2000 条目、200:1、128 层的恰限与超限，以及超时不得标记成功，共 11 项。10 MiB / 50k / 100 MiB 的完整独立验收记录与缩小阈值的早期单测分别保留，不混为一类证据。

执行结果：[m4-capacity-results.json](m4-capacity-results.json) 中 `case_count=20`、`passed=20`，各案例均记录实际文件大小、行列数、ZIP 构造、拒绝码、耗时与进程峰值。没有超时或部分截断后返回成功的案例。

## 性能负载与复算

每组每侧 10,000 行或 50,000 行、2 列；虚构混合数据包含中英文编号、普通精确匹配、金额差异、缺项、坏金额、空编号、两侧重复编号、空行以及公式样式的文本前缀。每 10 行模式独立预期为：3 条一致、1 条金额差异、1 条仅订单、2 条仅收款、7 个问题源行及 2 个空源行。脚本校验这些计数与每侧完整行数，核心和报告审计继续校验守恒及逐行内容。

正式命令：

```sh
.venv-m4-clean/bin/python scripts/benchmark_export.py --format csv --rows 10000 --repeats 3 --timeout 300 > docs/m4-benchmark-csv-10k.json
.venv-m4-clean/bin/python scripts/benchmark_export.py --format xlsx --rows 10000 --repeats 3 --timeout 300 > docs/m4-benchmark-xlsx-10k.json
.venv-m4-clean/bin/python scripts/benchmark_export.py --format csv --rows 50000 --repeats 1 --timeout 600 > docs/m4-benchmark-csv-50k.json
.venv-m4-clean/bin/python scripts/benchmark_export.py --format xlsx --rows 50000 --repeats 1 --timeout 600 > docs/m4-benchmark-xlsx-50k.json
.venv-m4-clean/bin/python scripts/benchmark_export.py --format xlsx --rows 10000 --repeats 1 --timeout 300 > docs/m4-benchmark-xlsx-10k-postfix.json
.venv-m4-release/bin/python scripts/benchmark_export.py --format xlsx --rows 10000 --repeats 3 --timeout 300 > docs/m4-benchmark-xlsx-10k-final.json
.venv-m4-release/bin/python scripts/benchmark_export.py --format xlsx --rows 50000 --repeats 1 --timeout 900 > docs/m4-benchmark-xlsx-50k-final.json
```

`m4-benchmark-preliminary-m3-env-csv-10k.json` 是更早在 `.venv-m3-clean` 的预运行，明确排除出正式 M4 干净环境统计。旧核心专用脚本 `benchmark.py` 已纠正陈旧的“导出未实现”元数据；它本身依然只测核心，导出测量应使用 `benchmark_export.py`。

## 已完成测量与未达项

下表中三轮组列中位数，单轮组列实测值；峰值列取组内最大值。单位分别为秒和 MiB。导出列**已包含**一次强制回读，额外回读列是验收时增加的第二次审计，不是页面下载必经的另一轮工作。

| 输入 / 每侧行数 | 完成轮数 | 读取 | 核心含审计 | 导出含强制回读 | 额外回读 | 进程峰值 | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CSV / 10k，修复前 | 3 | 0.214 | 0.761 | 42.524 | 23.314 | 405.17 | 三轮核心和峰值均达到建议目标 |
| XLSX / 10k，修复前 | 3 | 3.804 | 2.621 | 59.884 | 31.758 | 413.20 | 核心逐轮 3.094 / 2.621 / 1.153；首轮未达 3 秒，内存三轮达标 |
| CSV / 50k，修复前 | 1 | 1.282 | 8.605 | 411.069 | 129.506 | 1681.39 | 功能及两次回读通过；50k 不适用 10k 建议目标 |
| XLSX / 10k，释放修复后 | 1 | 0.683 | 0.266 | 16.868 | 7.268 | 429.59 | 本轮功能、回读及 10k 两项目标通过；只测一轮 |
| XLSX / 50k，修复前 | 0 | — | — | — | — | — | 早期启动约 36.9 秒后主动取消；该轮没有完整结论 |
| XLSX / 10k，最终 1.0.0 | 3 | 0.677 | 0.251 | 15.550 | 6.682 | 430.00 | 三轮完整通过且均达到 10k 建议目标 |
| XLSX / 50k，最终 1.0.0 | 1 | 3.505 | 1.473 | 85.946 | 35.170 | 1951.33 | 完整功能及两次回读通过；50k 不适用 10k 建议目标 |

原始证据分别为 [CSV 10k](m4-benchmark-csv-10k.json)、[XLSX 10k](m4-benchmark-xlsx-10k.json)、[CSV 50k](m4-benchmark-csv-50k.json)、[修复后 XLSX 10k](m4-benchmark-xlsx-10k-postfix.json)。所有文件均保留原始各轮数值，没有用中位数替换最慢轮。以上四组已完成旧测量的应用版本均为 M4 开发快照 `0.3.0`、规则版本 `v1`；第一次修复后源码散列及上下文见 [postfix-context](m4-benchmark-xlsx-10k-postfix-context.json)。新补测的 [最终 XLSX 10k 三轮](m4-benchmark-xlsx-10k-final.json) 与 [最终 XLSX 50k 一轮](m4-benchmark-xlsx-50k-final.json) 实际运行应用 `1.0.0`，以新文件保存，不改写旧版本和数值。最终 10k 三轮核心分别为 0.246984125 / 0.254272667 / 0.251301167 秒；峰值分别为 429.546875 / 429.640625 / 430.0 MiB。

XLSX 50k 的 `returncode=-15` 是验收人员对准确所属子进程发送 SIGTERM 的结果，原因是已完成 CSV 50k 后发现工作簿生命周期问题，暂停可选重复压力测量进行修复。它既不是通过，也不是产品读取错误或 600 秒超时；见 [原始进程记录](m4-benchmark-xlsx-50k.json) 和 [取消原因](m4-benchmark-xlsx-50k-cancellation.json)。最终 1.0.0 已另启新子进程完整补测 XLSX 50k，子进程总墙钟 127.406 秒，未触发 900 秒超时，也未手工终止。新通过结果不删除或覆盖该早期取消证据。

## 工作簿释放修复与瓶颈解释

修复前的 [引用探针](m4-benchmark-workbook-reference-probe.json) 证实：开始强制回读时，五张写出工作表与其单元格对象仍通过局部工作表和循环引用保留，现场 `gc.collect()` 也不能释放仍可达的对象。该探针替换了审计函数，只能证明对象生命周期问题，不能充当报告正确性测试。

修复将完整写出过程移入 `_write_xlsx()` 的独立作用域，在作用域返回后回收不可达对象，再调用原有 `audit_xlsx()`。没有跳过审计、减少导出字段或改变报告内容。新增 weakref 回归在关闭自动循环回收的条件下连续导出两次，要求强制回读前写出工作簿已释放，并实际执行原有回读。容量、报告和安全等相关回归共 **109 项通过，30.76 秒**，见 [targeted-tests](m4-capacity-targeted-tests.txt)；最终完整测试结果由总验收文档记录。

修复后单轮的读取 / 核心 / 导出含回读 / 额外回读，CPU 秒分别为 **0.680 / 0.264 / 16.639 / 7.140**，约占对应墙钟的 99.6% / 99.3% / 98.6% / 98.2%。因此，本轮主要工作量落在静态工作簿构建、序列化和逐格安全回读，而非核心编号配对；这些阶段大部分时间都在消耗进程 CPU。计时未继续拆分工作簿构建、ZIP/XML 序列化和审计内部步骤，不能进一步精确分摊各自占比。

这不是受控 A/B 实验：两天的桌面负载、时间与代码均不同，原始组没有 CPU 时间，不能把较快的墙钟全部归因于释放修复。修复后的 429.59 MiB 峰值还高于原始 XLSX 10k 的 378.88–413.20 MiB，**没有测得整流程峰值内存下降**。修复证明的是写出对象不再与强制回读重叠保留；写出阶段依然一次建立完整格式化工作簿，累计峰值仍可能由这一阶段决定。修复前 CSV 50k 的 1681.39 MiB 和最终 XLSX 50k 的 1951.33 MiB 是不同格式、不同版本与运行时间的真实观察，不能据此推断修复降低或提高了所有 50k 输入的资源消耗。

最终 1.0.0 的 XLSX 50k 单轮返回 35,000 条业务结果、100,000 行源账本，状态计数与独立构造预期一致；27,728,560 字节报告通过强制及额外回读。读取 / 核心 / 导出含回读 / 额外回读 CPU 秒为 3.492 / 1.469 / 84.700 / 35.005，墙钟为 3.505 / 1.473 / 85.946 / 35.170，继续支持导出与回读占主导的结论。核心完成时累计峰值为 170.05 MiB，导出含回读完成时累计峰值为 1951.33 MiB；脚本没有测量该阶段内部瞬时峰值位置，不能把全部峰值精确归因于写出或审计中的某一步。

本次最终三轮 10k 与 50k 补测没有修改产品源码或测量脚本；核对的 `sheetcheck/report.py` 与 `scripts/benchmark_export.py` 散列和前次修复后记录一致，运行应用版本为 1.0.0。复测解决“最终版本未重复 10k”和“XLSX 50k 未完成”的证据缺口，不将当前结果扩展为其他机器、宽表、并发会话或恶意文件的性能保证。

## 已知范围

- 蓝图 3 秒核心 / 512 MiB 是每侧 10k 行的建议目标。50k 的内存即使高于 512 MiB，也应单独披露，不能用 10k 结果保证最大输入、UI 服务、并发会话或其他硬件的峰值。
- 当前覆盖单维度输入边界，以及两种格式的 2 列混合业务负载。尚未覆盖所有最大字段、共享字符串、样式、宽表和并发会话的组合压力。
- 所有真实边界拒绝都发生在返回 `SourceTable` 之前，不以部分截断结果继续核对。不能由此推导出恶意文件必定在固定时间或内存内退出；基准子进程保护也不等于应用运行时沙箱。
- 本记录没有原生 Excel / LibreOffice 打开兼容性结论，也没有 Windows、Linux 或 Intel Mac 的性能结论。
