# M4 交付与复验说明

更新日期：2026-10-24。应用 **1.0.0**、核对规则 **v1**、报告格式 **m2-v1**。这是从源码启动的本地工具，包含页面、核对内核、静态 Excel 报告和验收材料。**v1 已按已验证范围完成；用户明确免除下载录像补录要求，既有证据与限制随包保留。** 逐项结论见 [总验收](m4-verification.md)、[状态清单](m4-release-status.json) 和 [收尾记录](m4-closeout.json)。

## 交付入口

| 入口 | 用途 |
| --- | --- |
| [中文 README](../README.md) / [English README](../README.en.md) | 安装、启动、规则、使用范围 |
| [页面操作指南](m3-workflow.md) | 导入、映射、筛选、追溯和恢复 |
| [两分钟演示](../outputs/m4/sheetcheck-demo.mp4) / [字幕](../outputs/m4/sheetcheck-demo.vtt) | 1.0.0 实际页面，120.600 秒，无音轨 |
| [最终虚构报告](../outputs/m4/final/sheetcheck_20261024T043417Z_a4accde15b7d46d8bbb024912cccf547.xlsx) / [复算结果](../outputs/m4/final/acceptance.json) | 五页报告、14 条源行、独立复算与安全回读 |
| [完整测试](m4-final-test-summary.json) | 同一套 502 项测试分别在两个环境通过，不相加 |
| [变更记录](../CHANGELOG.md) / [原蓝图](blueprint-v1.txt) | 实现范围与历史 |
| [容量性能](m4-capacity.md) / [断外网](m4-offline.md) / [日志安全](m4-log-security.md) | 条件、命令、原始结果及限制 |

源目录中的包为 `deliveries/SheetCheck-1.0.0.zip`。包包含源码、配置、43 个锁定 wheel、测试、虚构样例、报告、文档、视频及录制证据；不包含 Python、虚拟环境、FFmpeg 或系统字体。它不是可双击安装的桌面安装包。

## 实测兼容范围

已测试 **macOS 27.0.1 / Apple arm64、CPython 3.12.14、Streamlit 1.66.0、openpyxl 3.1.5、defusedxml 0.7.1**。机器为 Apple M4、10 个逻辑 CPU、24 GiB 内存。43 个精确 wheel 哈希含 macOS arm64 原生包，不是跨平台锁文件。Windows、Linux、Intel Mac、其他 Python 版本未验收，不能删除哈希绕过不匹配。

Microsoft Excel for Mac 16.114（build 16.114.26101123）实际打开过一份 0.3.0 开发快照的虚构报告，未见修复、外链或宏提示，差额、空缺/零与源行显示正确，关闭后哈希不变。这不是最终 1.0.0 报告的原生软件重复测试，也不代表 Windows Excel、WPS 或 LibreOffice 已兼容。见 [Excel 观察](m4-excel.json)。

## 已经执行的干净安装

恢复工作时，旧临时 wheelhouse 已不存在，校验明确失败，未算作通过。随后从 PyPI 重新取得同一锁文件指定的 **43 个 wheel**，哈希不变。首次受限网络下载失败及后续下载成功均保留，见 [依赖准备](m4-wheelhouse-refresh.json)。这是先联网准备、再离线安装，不能宣称准备过程从未联网。

最终由基础 CPython 3.12.14 创建全新 `.venv-m4-release`，`include-system-site-packages = false`。依赖使用本地 `outputs/m4/wheelhouse`、`--no-index --no-cache-dir --require-hashes` 安装；项目安装使用 `--no-build-isolation --no-deps`。实际命令、时间与退出码见 [安装 JSON](m4-release-install.json)，原始输出见 [安装日志](m4-release-install.txt)。`pip check` 和全部 wheel 名称、版本、哈希、平台标签通过。

本机使用的基础解释器是 `/Users/mcgee/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3.12`，不是其他机器的预装路径。本机 PATH 没有 `python3.12`；下文命令需先安装 Python 3.12，或替换为确认过的绝对路径。系统 Python 3.9 不满足要求。

| 环境 | 实际命令 | 结果 |
| --- | --- | --- |
| `.venv-m4-clean` | `.venv-m4-clean/bin/python -m pytest -q` | 502 passed，27.40 秒 |
| 新建 `.venv-m4-release` | `.venv-m4-release/bin/python -m pytest -q` | 502 passed，33.88 秒 |

这是同一套测试的两次通过，不能说有 1004 个独立用例。[release 环境](m4-release-environment.json) 和 [clean 环境](m4-environment.json) 校验应用版本一致、核心不导入 Streamlit、实际生效配置和源码。冻结后的 [交付清单](m4-delivery-manifest.json) 另覆盖 README、沙箱配置、视频和全部选中证据。

## 解压后离线安装和启动

以下是同平台、已经准备 Python 3.12 的机器上的复现方法，不冒称另一台机器实测。从解压后项目根目录执行：

```sh
python3.12 -m venv .venv
PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_CONFIG_FILE=/dev/null \
  .venv/bin/python -m pip install --no-index --no-cache-dir \
  --find-links outputs/m4/wheelhouse --require-hashes -r requirements.lock
PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_CONFIG_FILE=/dev/null \
  .venv/bin/python -m pip install --no-index --no-cache-dir \
  --no-build-isolation --no-deps -e '.[ui,test]'
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_install.py \
  --wheelhouse outputs/m4/wheelhouse --output install-verification.json
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

打开 `http://127.0.0.1:8501`，在启动终端按 Ctrl+C 停止。必须从项目目录运行，保留 `.streamlit/config.toml`。已有本项目服务时继续使用，不要结束不明进程或改成公网监听。

缺少 wheelhouse 时，可在有网阶段按 README 安装，或用 `pip download --only-binary=:all: --require-hashes -r requirements.lock --dest wheelhouse` 准备同平台包。Python 需另行安装；应用不需要 FFmpeg、API 密钥、数据库或云账户。

## 样例复算与报告

```sh
.venv/bin/python -m sheetcheck --demo
mkdir -p reports
.venv/bin/python -m sheetcheck --demo --export-dir reports
```

CLI 未指定 `--export-dir` 时仅输出 JSON，显式指定已存在的目录才保存 XLSX。手工预期来自 [expected.json](../samples/expected.json)，不是引擎生成自己的答案。A002 差额为 −100 分，A005 两侧 3 行隔离，全部 14 条源记录各有一条账本。最终报告独立复算、五页回读、无公式/超链接/外链/宏、源文件未改动均通过，见 [最终样例验收](../outputs/m4/final/acceptance.json)。

报告含原始映射字段，需按原账表敏感程度保存。页面默认不落盘业务数据；主动下载由用户保管。重置释放会话引用并使旧提交失效，不承诺安全擦除内存或撤回已下载文件。

## 断外网与视频的边界

此前 0.3.0 开发快照完成了真实 CSV/XLSX 选择、上传、映射、确认、核对、生成、下载和独立回读。Python 服务由 OS 沙箱限制为回环访问，页面另有 CSP 和请求记录；外部 IPv4/IPv6 连接及外部图片控制均被实际阻断。这是应用范围验证，**整台 Mac 没有物理断网，也没有 pcap**。测试夹具不是产品默认防火墙。原始版本与观察保留在 [断外网验收](m4-offline.md)。

正式视频为 1.0.0 页面六段真实截图序列，176 帧；选段内平均约 1.409 次截图/秒，输出 10 fps 使用重复帧。成品 1024×960、H.264 / yuv420p、120.600 秒、无音轨。段内保留原节奏、段间显式剪接，完整 UI 等比留边，字幕位于独立底栏。全片解码及七帧目视检查通过，见 [视频验证](m4-video-verification.json)。这是低采样率的真实操作演示，不是连续高帧率录像。

用户此前已明确授权下载，但工具反复请求同一权限并造成中断。2026-10-24，用户明确要求不再补录，保留此前成功证据，在已验证范围内完成 v1，且不再弹权限确认。因此收尾没有再次点击下载或请求授权。末尾字幕明确说明：“本片仅展示下载入口；此前真实下载报告已完成回读与 Excel 检查”。**新片没有录到浏览器保存文件和原生 Excel 打开过程**；前次真实下载与 Excel 验收是独立证据，不能称新片拍到了这些步骤。这是用户已接受的录制限制，不再作为本版完成的阻塞，也不归因于用户拒绝。

编码使用本机 Android Studio 自带 FFmpeg 7.1.1 与系统 STHeiti 字体，见 [工具记录](m4-video-tools.json)。这些工具不随包分发，也不是应用运行依赖。复用本机工具时的实际参数：

```sh
.venv-m4-clean/bin/python scripts/encode_demo.py \
  --frames outputs/m4/demo-v1-frames/frames.json \
  --segments outputs/m4/segments-v1.json \
  --captions outputs/m4/captions-v1.json \
  --output outputs/m4/sheetcheck-demo.mp4 --width 1024 --height 960
```

已有产物会拒绝覆盖；重制时指定新输出路径。其他机器自行配置 `--ffmpeg`、`--ffprobe` 和 `--font`。

## 打包与文件完整性

[build_delivery.py](../scripts/build_delivery.py) 收录明确指定的应用、配置、文档及已确认的虚构验收目录，排除虚拟环境、缓存、符号链接与系统工具。清单逐文件记录 SHA-256 和字节数；包内顶层为 `SheetCheck-1.0.0/`，包含隐藏的 `.streamlit`。重建：

```sh
.venv-m4-release/bin/python scripts/build_delivery.py
```

脚本检查实际 ZIP 成员名、CRC 和逐文件哈希，解压到新临时目录再逐文件核对；成功后写外置 `docs/m4-package-verification.json` 和 `deliveries/SheetCheck-1.0.0.zip.sha256`。回执与包自身不能收入所描述的包，以免自引用。清单排除清单自身和外置回执，其余选中文件全部覆盖。修改源码或文档后应重新打包。

该检查证明包与验收目录文件一致，**不等于从解压目录再次安装并执行过测试**。全新环境安装与 502 项回归以 `.venv-m4-release` 独立记录为准。

## 已接受的限制、历史未达及未测范围

新演示没有实际下载和 Excel 打开步骤；用户已明确免除补录要求，前次成功证据继续保留，不重触发权限循环。原始 10k XLSX 曾有一轮核心 3.094 秒超过 3 秒建议，旧结果保留。最终 1.0.0 的 XLSX 10k 三轮均达到建议目标（核心中位数 0.251 秒，峰值最大 430.00 MiB）；XLSX 每侧 50k 的完整流程也通过，核心 1.473 秒、导出含回读 85.946 秒、额外回读 35.170 秒，峰值 1951.33 MiB（约 1.91 GiB）。50k 不适用 10k 的 512 MiB 建议目标，但其资源成本必须披露。

修复前 CSV 每侧 50k 的导出含回读约 411 秒、峰值约 1.64 GiB，修复前 XLSX 50k 的取消均作为历史保留。详细方法和新旧独立记录见 [容量性能记录](m4-capacity.md)，不把旧取消记录回写成通过，也不把最终一次大表成功推断为所有最大维度组合的保证。

其他系统、表格软件、并发会话、所有最大维度组合及整机物理断网未验收。页面没有自动墙钟超时，重置不能抢占已开始计算；Ctrl+C 可以停止服务。v1 完成限于已有证据及用户确认的收尾范围，上述限制均随包披露，不扩展为全部平台和场景通过。
