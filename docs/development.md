# 开发、复算与 GitHub 仓库

从仓库根目录执行以下命令。项目使用 Python 3.12，核对内核不依赖页面；运行应用不需要数据库、账户、云端业务 API 或密钥。GitHub 仅托管源代码和虚构验收材料，不接收你在本机页面导入的业务文件。

## 本机开发

本机正式验收环境为 macOS 27.0.1 / Apple arm64 / CPython 3.12.14。`requirements.lock` 固定 43 个依赖及其 wheel 的 SHA-256，其中原生包针对 macOS arm64；其他系统和架构需要单独生成并验证锁文件，不能从这份锁文件推断兼容。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e '.[ui,test]'
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python scripts/acceptance_final_sample.py --output-dir outputs/local-check-001
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

样例验收脚本拒绝覆盖已有输出目录；再次运行请换一个新目录名。脚本通过 CLI 导出 Excel，另行读取源文件，逐项核对手写期望答案、完整 JSON、五张工作表与源行账本，并检查公式、超链接、外部链接和宏。报告生成过程本身也强制回读审计。测试或脚本成功不能替代原生 Excel 手工检查、性能实测或真实业务数据验收。

`samples/` 与测试夹具全部为虚构数据。样例的 `expected.json` 是独立期望答案：修改规则时先明确预期，不要用运行结果自动覆盖它。页面变更需检查旧结果失效、重置、分页和会话隔离；规则与报告安全变更需运行相应回归后再运行完整测试。不要为得到通过结果而放宽容量边界或关闭回读审计。

## 仓库与本地交付材料

Git 跟踪应用源码、测试、锁文件、虚构样例、文档，以及明确列入 `.gitignore` 例外的历史验收报告、截图、视频及原始录制帧。历史 M4 文档保留原测量版本与未通过项，不作为每次后续版本都重新执行过的证明。

虚拟环境、缓存、`deliveries/` 交付 ZIP、依赖 wheel、真实输入目录和新的 `outputs/` 文件默认忽略。现有 `outputs/m3/`、`outputs/m4/` 的虚构证据逐文件允许；`outputs/v1.1/final/` 仅允许本次虚构验收脚本的四类产物。普通 `outputs/ci-*`、`outputs/local-check-*` 仍被忽略。没有笼统忽略所有 CSV/XLSX，因此测试和样例不会丢失。新增证据应先核查内容，再添加精确例外；不要用 `git add -f` 绕过输入保护。

`.env*`、`.streamlit/secrets.toml`、密钥文件以及根目录 `inputs/`、`uploads/`、`reports/`、`local-data/`、`private-data/` 被忽略。`.gitignore` 只防止通常的意外暂存，不会清除已提交文件，也不替代提交前检查。JSON、报告和映射模板都可能包含业务信息；真实材料请保存于仓库之外。

源代码克隆不包含 `outputs/m4/wheelhouse` 或本机交付 ZIP；文档中指向这些位置的历史链接说明的是本机 M4 交付材料。联网准备一份经锁文件校验的依赖目录后，才可在断网环境安装：

```sh
.venv/bin/python -m pip download --only-binary=:all: --require-hashes \
  -r requirements.lock --dest outputs/local-wheelhouse
python3.12 -m venv .venv-offline
.venv-offline/bin/python -m pip install --no-index --find-links outputs/local-wheelhouse \
  --require-hashes -r requirements.lock
.venv-offline/bin/python -m pip install --no-build-isolation --no-deps -e '.[ui,test]'
.venv-offline/bin/python -m pip check
```

首次下载依赖需要网络。离线安装、应用流程的断外网验证和整机物理断网是不同范围，详见 [M4 断网记录](m4-offline.md)。在新版本上复用历史 wheelhouse 只说明依赖可以复用，不代表历史源码哈希仍对应新版本。

## GitHub Actions 模板（未启用）

2026-10-24 首次推送时，GitHub 服务端因当前 OAuth 凭据缺少 `workflow` scope，拒绝写入 `.github/workflows/ci.yml`。本次没有追加授权或重复弹出权限确认，改为交付 [github-actions.yml 模板](ci/github-actions.yml)。它位于文档目录，不会触发 GitHub Actions；**GitHub CI 尚未运行**。当前源码交付无需用户新增权限。本地 1.1.0 的完整回归已通过 **635 项测试**，该结果属于本机验证，不能记为托管 CI 成功。

模板预设在 push、pull request 和手动触发时运行完整 pytest，再导出并独立复算虚构样例报告。它配置了 `contents: read`、不持久化 checkout 凭据、10 分钟超时以及同分支旧任务取消；不使用 `pull_request_target`，不需要仓库密钥，不上传业务文件或报告。YAML 已在本机解析检查，四段 shell 命令通过语法检查；这些静态检查不能替代 GitHub 实际执行。若今后决定启用，应使用已有 workflow 写入权限的维护方式，将模板放入 `.github/workflows/`，然后检查对应提交的 Actions 结果；本次交付不要求完成这一步。

模板指定 `macos-15` / arm64 / CPython 3.12.10，与本机 M4 的 macOS 27.0.1 / CPython 3.12.14 分开记录。GitHub 官方将 `macos-15` 列为公有及私有仓库均可用的标准 arm64 runner；其硬件和系统镜像也不等同于本机，未来即使 CI 通过，也不能拿 CI 时间冒充本机性能验收。[官方 runner 表](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for-private-repositories)

选择 3.12.10 是因为检查时官方 `actions/python-versions` 清单提供该版本的 macOS arm64 构建，而 3.12.14 仅提供 Linux 构建。模板仍要求安装同一 `cp312` 锁定 wheel 并执行架构检查；安装或测试失败时，配置会让任务直接失败，不切换平台或绕过哈希。3.12.10 是此模板所选的可用构建，不是为用户推荐替换本机 3.12.14。[官方版本清单](https://github.com/actions/python-versions/blob/main/versions-manifest.json) · [3.12.10 构建](https://github.com/actions/python-versions/releases/tag/3.12.10-14343898437)

模板使用从上游 tag 解引用核实的完整提交 SHA：checkout v6.0.3 为 `df4cb1c069e1874edd31b4311f1884172cec0e10`，setup-python v6.3.0 为 `ece7cb06caefa5fff74198d8649806c4678c61a1`。升级时重新核对上游 release 与实际提交，并检查 runner 兼容性。[checkout release](https://github.com/actions/checkout/releases/tag/v6.0.3) · [setup-python release](https://github.com/actions/setup-python/releases/tag/v6.3.0)

以上模板配置与上游信息核实日期为 2026-10-24。它未覆盖原生 Excel、桌面浏览器录屏、整机断网或完整 50k 性能测试，也不扩展 Windows、Linux、Intel Mac、WPS 或 LibreOffice 的产品兼容结论。当前继续使用上文的本机开发、测试及样例导出命令复算。
