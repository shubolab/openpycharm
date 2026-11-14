# Installation / 安装说明

## Release status / 发行状态

Current preview: [v0.1.0-dev.4](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.4), source `63921a4`,
[successful native CI 43608150941](https://github.com/shubolab/openpycharm/actions/runs/43608150941).
Both installer ZIPs, independent installer hashes and source manifests were checked.
The CI DMG was copied to an owned installation folder and passed native startup,
post-startup tree identity and strict signature checks. The local DMG of the same
version supplied the [real native desktop captures](demo/v0.1.0-dev.4/capture.json);
its 171 production inputs and five plugin JARs match the CI app exactly.
Windows passed native API/kernel and silent install/startup/uninstall checks;
physical keyboard-and-mouse workflows remain unverified.

当前预览版为 [v0.1.0-dev.4](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.4)，源码 `63921a4`，
[双平台 CI 43608150941](https://github.com/shubolab/openpycharm/actions/runs/43608150941)通过。完整 ZIP、独立
安装包摘要和源码清单已核对；CI DMG 已复制安装并通过原生启动、产品树及严格签名
复核。同版本本机 DMG 提供[真实桌面演示](demo/v0.1.0-dev.4/capture.json)，其 171 项
生产输入和五个插件 JAR 与 CI 应用逐字节相同。Windows 安装/启动/卸载、原生 API
及内核门通过，实体键鼠桌面仍待验收。详见[发行验收](verification/2026-11-14-dev4-release.md)。

| System / 系统 | Download / 下载 |
| --- | --- |
| macOS Apple silicon | [DMG](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.4/OpenPyCharm-0.1.0-dev.4-macos-arm64.dmg) |
| Windows x64 | [EXE](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.4/OpenPyCharm-0.1.0-dev.4-windows-x64-setup.exe) |
| SHA-256 | [SHA256SUMS.txt](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.4/SHA256SUMS.txt) |

The Mac app is ad-hoc signed and not notarized. The Windows installer is unsigned.
[Previous dev.3](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.3) remains available.
Mac 使用临时签名、未经公证，Windows 安装器未签名；上一版保留下载。

## Verify a download / 核对下载

On macOS, replace the filename with your downloaded DMG:

在 macOS 中，将文件名替换为你实际下载的 DMG：

```sh
shasum -a 256 OpenPyCharm-0.1.0-dev.4-macos-arm64.dmg
```

On Windows PowerShell / Windows PowerShell：

```powershell
Get-FileHash .\OpenPyCharm-0.1.0-dev.4-windows-x64-setup.exe -Algorithm SHA256
```

Compare the complete SHA-256 with that release's `SHA256SUMS.txt`. Do not use a
checksum from a different version or an earlier candidate.

将完整 SHA-256 与同一版本的 `SHA256SUMS.txt` 对照。不要使用其他版本或较早候选
安装包的摘要。

## macOS Apple silicon

Mount `OpenPyCharm-0.1.0-dev.4-macos-arm64.dmg`, then drag **OpenPyCharm.app** to
**Applications** or `~/Applications`. Launch that installed copy. The application
includes its Java runtime. It is ad-hoc signed and **not notarized**; this preview
does not have an Apple Developer ID signature.

打开 `OpenPyCharm-0.1.0-dev.4-macos-arm64.dmg`，将 **OpenPyCharm.app** 拖到
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

Run `OpenPyCharm-0.1.0-dev.4-windows-x64-setup.exe`. The installer installs per user,
does not require an administrator, and offers an optional `.py` association.
The EXE is **unsigned**. Windows CI ran 177 repository controls (171 passed,
6 explicit skips), then passed all four actual-SDK frontend controls, native
Notebook/HTTP/framework/kernel gates and silent install/startup/uninstall.
Physical Python/Notebook/Database/HTTP/frontend keyboard-and-mouse workflows
remain unverified on Windows.

运行 `OpenPyCharm-0.1.0-dev.4-windows-x64-setup.exe`。按当前用户安装，不需要管理员
权限，并提供可选的 `.py` 文件关联。EXE **未签名**。Windows CI 的 177 项仓库控制
中 171 项通过、6 项明确跳过；随后四项前端实际 SDK 控制、原生 Notebook/HTTP/
框架/内核及静默安装/启动/卸载检查通过。实体键鼠桌面仍待验收。

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
same package pins. The [rich-output fixture](../fixtures/notebooks/native-rich-demo.ipynb)
also uses optional `pandas`, `matplotlib` and `Pillow`; install those separately in
the same environment when running that example.

PowerShell 使用 `& 'C:\path\to\selected\python.exe' -m pip install` 加相同版本的包。
[富媒体示例](../fixtures/notebooks/native-rich-demo.ipynb)还使用可选的 `pandas`、`matplotlib`
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

## JavaScript and TypeScript in dev.4 / dev.4 前端语言服务

In an assembled dev.4 candidate that includes the frontend plugin, trust the
local project and open a `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts` or
`.cts` file within its content roots. The native LSP service starts by default.
Use **Settings → Languages & Frameworks → JavaScript and TypeScript** to disable
or re-enable it for that project. Keep normal project trust in place.

在包含前端插件的 dev.4 候选中，先信任本地项目，再打开项目内容根下的 `.js`、`.jsx`、
`.mjs`、`.cjs`、`.ts`、`.tsx`、`.mts` 或 `.cts` 文件，原生 LSP 服务默认启动。
可在 **Settings → Languages & Frameworks → JavaScript and TypeScript** 中
按项目关闭或重新启用；保留普通项目的信任流程。

The distribution includes Node.js 24.22.3, TypeScript 6.0.3 and
typescript-language-server 6.1.0. It authenticates the complete pinned runtime
before starting, with no runtime download or dependency installation on editor
opening. Completion/diagnostics/definition support does not imply complete
JavaScript/TypeScript PSI/refactoring, HTML/CSS or frontend framework support.

发行包携带 Node.js 24.22.3、TypeScript 6.0.3 和 typescript-language-server 6.1.0，
启动前核对完整固定运行时；打开编辑器不下载运行时或安装依赖。已有补全、诊断和
定义跳转不代表完整 JavaScript/TypeScript PSI/重构、HTML/CSS 或前端框架支持。

## Build the five-plugin dev.4 candidate / 构建五插件 dev.4 候选

The ordinary build CLI still defaults to dev.3. Explicitly provision the frontend
build inputs, then supply its printed `receipt` path and the dev.4 version. The
provision step is a build-time network action; regular editor opening uses
bundled tools. Install the pinned build dependencies and provision the HTTP
compiler/JDBC drivers as shown in the root README first.

普通构建命令仍默认 dev.3。显式准备前端构建工具，再传入输出中的 `receipt` 路径和
dev.4 版本。准备工具需要构建时网络访问，普通编辑器打开只用随包工具。先按根 README
安装固定构建依赖、准备 HTTP 编译器与 JDBC 驱动。

```sh
python3 scripts/bootstrap.py --target macos-arm64
python3 scripts/provision_frontend_tools.py --target macos-arm64
python3 scripts/package.py --target macos-arm64 --version 0.1.0-dev.4 --output build/dev4/OpenPyCharm.app --frontend-runtime-receipt /absolute/path/from-provision/frontend-tools.json
python3 scripts/installers.py --target macos-arm64 --version 0.1.0-dev.4 --product build/dev4/OpenPyCharm.app
```

Choose a new output directory for each assembly. On Windows use `python`,
`--target windows-x64` and `build/dev4/OpenPyCharm`. A build, installer or launch
alone does not establish full desktop or 1:1 acceptance.

每次组装选择新的输出目录。Windows 使用 `python`、`--target windows-x64` 和
`build/dev4/OpenPyCharm`。仅构建、生成安装器或启动成功不等于完整桌面或 1:1 验收。

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
