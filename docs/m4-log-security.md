# M4 日志脱敏、留存与导出安全复验

验收日期：2026-10-24（Asia/Singapore）。本记录针对应用 0.3.0 的 M4 修复；核对规则仍为 v1。执行环境为 macOS 27.0.1 / arm64、CPython 3.12.14、Streamlit 1.66.0、openpyxl 3.1.5，使用 `.venv-m3-clean`。这里的通过结论限于下列实际执行范围，最终干净环境全量回归和 v1 准入以 M4 总验收记录为准。

## 修复和诊断输出边界

安全审阅发现并修复三条异常出口：

1. CLI 的底层意外异常此前不属于已捕获的异常类型，可能由 Python 向 stderr 输出带原始字段的 traceback。现在统一返回退出码 2 和固定 `INTERNAL_ERROR` 恢复提示。读入、校验、核对、JSON 序列化、导出任一步失败，都不产生部分成功 JSON；Ctrl+C 的退出码 130 保持不变。
2. `argparse` 默认在参数解析错误中回显非法值，可能包含文件名。现在错误只输出固定 `CLI_ARGUMENTS` 与查看 `--help` 的说明；完整帮助仍可用。
3. Streamlit 的延迟下载回调运行在页面主函数的异常边界以外，框架会把回调异常字符串包装进 `MediaFileStorageError`。现在回调遇到意外异常时，只记 `phase=DOWNLOAD code=UI_DOWNLOAD_FAILED version=...`，抛出固定安全错误并阻断原异常链。已知 `REPORT_STALE` 保持其固定提示。

页面应用 logger `sheetcheck.ui` 只记录 `phase`、`code`、`version`，不包含 `exc_info`、stack trace 或异常原文。CLI 错误诊断是固定错误码与固定恢复文字，不拼入用户值。CLI 成功导出到明确指定目录时，stderr 现在仅为 `code=EXPORTED stage=EXPORT version=<应用版本>`，连生成报告文件名也不再写入 stderr。完整文件名仍可在用户选择的导出目录中查看，并可由运行元数据复现。

UI 的文件名、原始编号和金额预览，以及用户主动请求的 CLI JSON、XLSX，是业务输出，按设计保留来源证据；它们不是诊断日志。测试同时检查成功业务输出确实包含虚构 canary，避免把“根本没处理数据”误判为脱敏通过。

代码位置：[CLI](../sheetcheck/__main__.py)、[页面异常和下载边界](../app.py)、[新增回归](../tests/test_m4_logging.py)。

## 实际执行结果

```sh
.venv-m3-clean/bin/python -m pytest tests/test_m4_logging.py tests/test_cli.py tests/test_cli_export.py tests/test_app.py -q
```

**85 passed in 41.28s，0 failed**，见 [原始输出](m4-log-tests.txt)。其中新增 M4 canary / 留存测试 **32 项**，既有 CLI 与页面兼容回归 53 项。这些时间包含同机其他验收任务负载，不作为性能成绩。

| 执行范围 | 检查内容 | 最终结果 |
| --- | --- | --- |
| 正常页面导入、核对、生成报告 | 用独特虚构编号、金额、备注、CSV/XLSX 文件名扫描真实 Python logger 与 stderr；业务结果正向确认数据已处理 | 通过 |
| 实际坏 CSV / 坏 XLSX | 真实上传控件与实际 CLI 进程分别拒绝；日志只含固定错误码/提示 | 通过 |
| UI 读入、校验、核对、导出、页面渲染失败 | 注入含全部 canary 的底层 `RuntimeError`，执行真实 AppTest 页面脚本，捕获真实 logger | 通过 |
| CLI 读入、校验、核对、JSON 序列化、导出失败 | 独立 Python 进程注入含 canary 的异常；退出 2、stdout 为空、无 traceback、无报告文件 | 通过 |
| CLI 非法参数和帮助 | 非法整数、枚举、未知参数不回显原值；`--help` 仍完整输出并退出 0 | 通过 |
| 陈旧下载和意外下载失败 | 实际调用 Streamlit 1.66 的 `MediaFileManager.execute_deferred`，检查框架包装后的错误和异常链不含 canary | 通过 |
| Excel 无效日期警告 | openpyxl 可能包含数值的警告被抑制，单元格仍按错误类型处理 | 通过 |
| CSV / XLSX 完整内存业务流程 | 依赖预载后禁止 `builtins.open`、`io.open`、`Path.open` 与三类 tempfile API；重新执行读入、核对、导出和回读 | 通过 |
| 会话重置与独立会话 | 重置后源选择、源表、映射、规则期间、结果和报告引用释放；另一 Workflow 无上述数据 | 通过 |

测试扫描的是虚构 canary，不使用客户文件或真实业务数据。测试并非对任意第三方库未来版本、任意系统日志、浏览器遥测或进程崩溃转储的无泄露证明；锁定依赖升级后必须重新验收。应用自身不配置业务日志文件；终端输出是否被 shell、IDE 或操作系统保存取决于运行环境。

## 公式注入、坏文件与回读复验

```sh
.venv-m3-clean/bin/python -m pytest tests/test_report_security.py tests/test_report.py tests/test_file_disguises.py tests/test_readers.py tests/test_rules.py -q
```

**226 passed in 48.29s，0 failed**，见 [原始输出](m4-security-tests.txt)。这些用例与完整回归重叠，不与全量测试数相加。

复验包含：`=HYPERLINK` 及 `+`、`-`、`@`、危险控制字符的显式文本和可逆转义；每个报告页的公式植入；内部/外部超链接和孤立关系；宏、活动内容及未引用恶意部件；损坏 ZIP/XML、XML 实体、重复 ZIP 条目、伪装 CSV；映射字段公式、数组公式、公式缓存和合并区域；编号、分值、源行、列映射、数据范围、工作表顺序及零/缺失值篡改；只有回读审计通过后才返回报告字节。

这些结果证明当前读取和输出协议按测试样例拒绝危险或不一致内容。原生 Excel、LibreOffice 或其他表格软件的实际显示/行为兼容性未在本子项验收中运行，不能由 openpyxl 回读成功推导。

## 默认留存和取消边界

应用没有跨会话业务缓存或数据库；上传数据交给本机 Streamlit 的内存上传管理器，应用的 SourceTable、Workflow 和报告字节属于当前会话。核心与报告 API 接收内存字节；默认不保存源文件或报告，不创建工作表临时文件。CLI 仅在显式指定 `--export-dir` 时保存已审计报告，并拒绝覆盖已有文件或符号链接。既有测试也复验保存失败/取消时仅删除本次创建的半成品。

页面重置释放应用会话引用，并使旧操作不能提交结果；Streamlit 自己的上传/媒体引用还受框架会话清理时机管理。这里不声称立即安全擦除内存、系统交换区、浏览器缓存、下载历史或已经交付的报告字节。主动下载文件由用户保管，重新开始不能删除或撤回它们。

页面重置或输入修改是逻辑取消，不会立即抢占已经开始的 Python 计算；终端 Ctrl+C 可停止同步业务处理或整个页面服务。没有自动墙钟超时，容量拒绝阈值也不等于进程内存上界。此处没有把单位测试的 socket 拦截或内存 API 检查称为整机断网验收；网络隔离证据由 M4 独立记录提供。

## 失败项和未运行项

上述两条最终命令均无失败项。原生表格软件、其他操作系统/架构、系统崩溃转储和运行环境外部日志的保密性不在本子项执行范围内；未运行即不声明通过。M4 性能、容量、干净环境全量测试、断网浏览器流程和演示视频由总验收记录逐项给出，完成这些证据前不能仅凭本记录标记 v1 完成。
