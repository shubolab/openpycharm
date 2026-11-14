# Installation / 安装说明

## Release status / 发行状态

Current preview: [v0.1.0-dev.3](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.3),
built from source `9a243e6` by
[dual-platform CI 43565932969](https://github.com/shubolab/openpycharm/actions/runs/43565932969).
The final macOS installation passed the Python, Notebook and SQLite workflows
listed in [acceptance](acceptance.md). Windows passed installer/startup/uninstall,
native API Notebook save/undo/reopen and local-kernel checks; physical
keyboard-and-mouse workflows remain unverified.

当前预览版：[v0.1.0-dev.3](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.3)，
来源为 `9a243e6`，对应[双平台 CI 43565932969](https://github.com/shubolab/openpycharm/actions/runs/43565932969)。
最终 macOS 安装版的 Python、Notebook 和 SQLite 实测范围见[验收矩阵](acceptance.md)。
Windows 已通过安装/启动/卸载、原生 API Notebook 保存/撤销/重开及本地内核检查，
实际键盘、鼠标工作流仍待验收。

| System / 系统 | Download / 下载 |
| --- | --- |
| macOS Apple silicon | [OpenPyCharm-0.1.0-dev.3-macos-arm64.dmg](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.3/OpenPyCharm-0.1.0-dev.3-macos-arm64.dmg) |
| Windows x64 | [OpenPyCharm-0.1.0-dev.3-windows-x64-setup.exe](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.3/OpenPyCharm-0.1.0-dev.3-windows-x64-setup.exe) |
| SHA-256 | [SHA256SUMS.txt](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.3/SHA256SUMS.txt) |

The README's [installed-version GIF and capture manifest](../README.md) use real
native captures. [Previous preview dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2)
remains available.

README 的[安装版 GIF 与拍摄清单](../README.zh-CN.md)使用真实原生截屏。
[上一预览版 dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2)保留下载。

## Verify a download / 核对下载

On macOS, replace the filename with your downloaded DMG:

在 macOS 中，将文件名替换为你实际下载的 DMG：

```sh
shasum -a 256 OpenPyCharm-0.1.0-dev.3-macos-arm64.dmg
```

On Windows PowerShell / Windows PowerShell：

```powershell
Get-FileHash .\OpenPyCharm-0.1.0-dev.3-windows-x64-setup.exe -Algorithm SHA256
```

Compare the complete SHA-256 with that release's `SHA256SUMS.txt`. Do not use a
checksum from a different version or an earlier candidate.

将完整 SHA-256 与同一版本的 `SHA256SUMS.txt` 对照。不要使用其他版本或较早候选
安装包的摘要。

## macOS Apple silicon

Mount `OpenPyCharm-0.1.0-dev.3-macos-arm64.dmg`, then drag **OpenPyCharm.app** to
**Applications** or `~/Applications`. Launch that installed copy. The application
includes its Java runtime. It is ad-hoc signed and **not notarized**; this preview
does not have an Apple Developer ID signature.

打开 `OpenPyCharm-0.1.0-dev.3-macos-arm64.dmg`，将 **OpenPyCharm.app** 拖到
**Applications** 或 `~/Applications`，再启动安装后的应用。应用内置 Java 运行时。
预览版使用临时签名，**未经 Apple 公证**，没有 Apple Developer ID 签名。

The independent bundle ID is `dev.openpycharm.ide`.

| Data / 数据 | Location / 位置 |
| --- | --- |
| Configuration and plugins / 配置与插件 | `~/Library/Application Support/OpenPyCharm` |
| Caches / 缓存 | `~/Library/Caches/OpenPyCharm` |
| Logs / 日志 | `~/Library/Logs/OpenPyCharm` |

Remove the app to uninstall. Project files and these settings are retained.
The installed reference PyCharm and its data are not modified.

卸载时移除应用即可，项目文件和上述设置会保留。不会修改作为对照的已安装 PyCharm
及其数据。

## Windows x64

Run `OpenPyCharm-0.1.0-dev.3-windows-x64-setup.exe`. The installer installs per user,
does not require an administrator, and offers an optional `.py` association.
The EXE is **unsigned**. Native Windows CI ran 125 repository tests
(122 passed, three POSIX-only skips), actual Notebook save/undo/reopen through the
normal IDE new-project lifecycle, local JVM/kernel controls, and silent
install/startup/uninstall. Physical Python/Notebook/Database/HTTP keyboard-and-mouse
workflows remain unverified on Windows.

运行 `OpenPyCharm-0.1.0-dev.3-windows-x64-setup.exe`。安装器按当前用户安装，不需要管理员
权限，并提供可选的 `.py` 文件关联。EXE **未签名**。原生 Windows CI 共运行 125 项
仓库测试，122 项通过、3 项仅限 POSIX 的检查跳过；正常 IDE 新建项目生命周期下的
Notebook 保存/撤销/重开、本地 JVM/内核、静默安装/启动/卸载检查通过。Python、
Notebook、数据库和 HTTP 的实际键盘、鼠标工作流仍未在 Windows 验收。

| Data / 数据 | Location / 位置 |
| --- | --- |
| Configuration and plugins / 配置与插件 | `%USERPROFILE%\AppData\Roaming\OpenPyCharm` |
| Caches and logs / 缓存与日志 | `%USERPROFILE%\AppData\Local\OpenPyCharm` |

Use the installed uninstaller to remove the application. Projects and user
settings are retained.

使用安装后的卸载程序移除应用，项目和用户设置会保留。

## Python and framework projects / Python 与框架项目

Select an installed Python interpreter or create a virtual environment in the
native project settings. Java is included; the project's Python interpreter is
separate. In dev.3, Django/Flask/FastAPI generators retain this native
interpreter/venv flow. Installing their pinned example dependencies is optional
and off by default; it uses the selected Python environment and network access.

通过原生项目设置选择本机 Python 解释器或创建虚拟环境。应用内置 Java，但 Python
项目解释器需要另行选择。dev.3 的 Django/Flask/FastAPI 生成器保留原生解释器/
venv 流程。示例依赖安装可选、默认关闭；开启后使用所选 Python 环境并需要网络。

Framework examples and their Run/Debug configurations are a bounded starting
point. They do not imply complete framework, template or ORM intelligence.

框架示例及其运行/调试配置仅覆盖当前实现范围，不代表完整框架、模板或 ORM 智能
支持。

## Local Notebooks / 本地 Notebook

Choose a local module/project Python interpreter and trust the project before
execution. Install these dependencies yourself into that **selected interpreter**;
the IDE does not install them automatically:

先选择本机模块/项目 Python 解释器，并在执行前信任项目。请自行在**所选解释器**中
安装以下依赖，IDE 不会自动安装：

```sh
/absolute/path/to/selected/python -m pip install jupyter_client==8.6.3 ipykernel==6.29.5
```

On PowerShell, use `& 'C:\path\to\selected\python.exe' -m pip install` with the
same package pins. The [rich-output fixture](../fixtures/notebooks/native-demo.ipynb)
also uses optional `pandas`, `matplotlib` and `Pillow`; install those separately in
the same environment when running that example.

PowerShell 使用 `& 'C:\path\to\selected\python.exe' -m pip install` 加相同版本的包。
[富媒体示例](../fixtures/notebooks/native-demo.ipynb)还使用可选的 `pandas`、`matplotlib`
和 `Pillow`；运行该示例时在同一环境中另行安装。

Open `.ipynb`, then use **Run Cell**, **Shift+Enter**, **Run All**, **Interrupt** or
**Restart Kernel**. Opening a notebook never executes it. Output supports
PNG/JPEG, static HTML/DataFrame tables, styled Markdown, text and tracebacks.
Use normal Save, then close/reopen to retain cells and outputs. Remote kernels,
interactive stdin, widget comms and notebook debugging are not implemented;
scripts and external resources in rich output do not run or load.

打开 `.ipynb` 后使用 **Run Cell**、**Shift+Enter**、**Run All**、**Interrupt** 或
**Restart Kernel**。打开文件不会执行代码。输出支持 PNG/JPEG、静态 HTML/DataFrame
表格、带样式的 Markdown、文本和错误堆栈。使用普通保存，再关闭/重开以保留单元及
输出。尚不支持远程内核、交互式 stdin、widgets 通信和 Notebook 调试；富媒体输出
不执行脚本、不加载外部资源。

## Database / 数据库

Open **Database**, click **+**, choose SQLite and a local file, then **Connect**.
The [disposable SQLite example](../fixtures/database/README.md) creates a separate
sample database. Click **Refresh tables**, choose a table and **Select rows**,
then **Run statement**. The result grid is read-only, with previews capped at
500 rows. Use **Begin transaction**, **Commit**, **Rollback** and **Cancel** for
the corresponding operations; direct transaction-control SQL is rejected.

打开 **Database**，点 **+**，选择 SQLite 与本地文件，再点 **Connect**。
[独立 SQLite 示例](../fixtures/database/README.md)可生成单独的样例数据库。
点 **Refresh tables**，选择表及 **Select rows**，再点 **Run statement**。
结果表格只读，预览最多 500 行。事务与取消使用 **Begin transaction**、**Commit**、
**Rollback**、**Cancel**；不接受直接控制事务的 SQL。

For native **Basic** completion in a `.sql` source file or the console, click
**Refresh tables** after connecting, invoke Basic and accept with Return. For the
sample `products` table, `pro` after FROM becomes `"main"."products"`, and `p.na`
with `FROM main.products p` becomes `p."name"`. The metadata snapshot expires after
five minutes; ordinary SELECT queries do not refresh it. Refresh again after
expiry or external schema changes. **Disconnect** clears the connection snapshot.

在 `.sql` 源文件或控制台使用原生 **Basic** 补全时，连接后先点 **Refresh tables**，
调用 Basic 并按 Return 接受。例如样例表中 FROM 后的 `pro` 补为
`"main"."products"`；存在 `FROM main.products p` 时，`p.na` 补为 `p."name"`。
元数据快照五分钟后过期，普通 SELECT 不会刷新；过期或外部结构改变后需再次刷新。
**Disconnect** 会清除该连接的快照。

Project opening does not connect or run SQL. Optional password storage uses
native PasswordSafe. PostgreSQL and MySQL profiles/drivers (MariaDB Connector/J
for MySQL) are included, with their notices and matching source where required;
real network/TLS/authentication and network cancellation remain unverified.
Editable results, export, SSH tunnels and complete dialect intelligence are not
implemented.

打开项目不会自动连接或执行 SQL；可选的密码保存使用原生 PasswordSafe。随包包含
PostgreSQL、MySQL 配置与驱动（MySQL 使用 MariaDB Connector/J），保留相关声明及
要求随附的对应源码。真实网络/TLS/认证及网络取消尚未验收。结果编辑、导出、SSH
隧道及完整方言智能分析尚未实现。

## Isolated development profile / 隔离开发配置

```sh
python3 scripts/launch.py --profile .state/development fixtures/hello-python
```

This source-development profile has separate configuration, caches, plugins and
logs. It does not import the reference PyCharm configuration. Use `python` on
Windows. A source build or successful launch is not complete desktop acceptance.

这个源码开发配置使用独立的设置、缓存、插件和日志，不导入对照 PyCharm 的配置。
Windows 使用 `python`。源码构建或启动成功不等于完整桌面验收。

Local IDE use has no IDE account, billing, subscription, trial or upgrade-promotion
flow. Git/GitHub/private-repository and user-selected service authentication are
preserved. Upstream licenses and third-party notices remain in the application's
`license` directory.

本地 IDE 使用不包含 IDE 账号、计费、订阅、试用和升级推广流程；保留 Git、GitHub、
私有仓库及用户选择的服务认证。应用 `license` 目录保留上游与第三方声明。
