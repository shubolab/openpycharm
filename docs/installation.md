# Installation / 安装说明

## Release status / 发行状态

Preview installers: [v0.1.0-dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2).
Download the macOS Apple silicon DMG or Windows x64 EXE together with
`SHA256SUMS.txt`. Installed macOS desktop and post-workflow checks passed, and
the README includes the actual installed-version GIF.
See [dev.2 verification](verification/2026-11-14-dev2-release.md).

预览版安装包：[v0.1.0-dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2)。
请同时下载 macOS Apple silicon DMG 或 Windows x64 EXE 与 `SHA256SUMS.txt`。
macOS 安装版桌面和工作流后检通过，README 已包含实际安装版 GIF，见
[dev.2 验收记录](verification/2026-11-14-dev2-release.md)。

## Verify a download / 核对下载

On macOS, replace the filename with your downloaded DMG:

在 macOS 中，将文件名替换为你实际下载的 DMG：

```sh
shasum -a 256 OpenPyCharm-VERSION-macos-arm64.dmg
```

On Windows PowerShell / Windows PowerShell：

```powershell
Get-FileHash .\OpenPyCharm-VERSION-windows-x64-setup.exe -Algorithm SHA256
```

Compare the complete SHA-256 with that release's `SHA256SUMS.txt`. Do not use a
checksum from a different version or an earlier candidate.

将完整 SHA-256 与同一版本的 `SHA256SUMS.txt` 对照。不要使用其他版本或较早候选
安装包的摘要。

## macOS Apple silicon

Mount `OpenPyCharm-VERSION-macos-arm64.dmg`, then drag **OpenPyCharm.app** to
**Applications** or `~/Applications`. Launch that installed copy. The application
includes its Java runtime. It is ad-hoc signed and **not notarized**; this preview
does not have an Apple Developer ID signature.

打开 `OpenPyCharm-VERSION-macos-arm64.dmg`，将 **OpenPyCharm.app** 拖到
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

Run `OpenPyCharm-VERSION-windows-x64-setup.exe`. The installer installs per user,
does not require an administrator, and offers an optional `.py` association.
The EXE is **unsigned**. Silent install/startup/uninstall checks on a native
Windows runner do not establish interactive Python or HTTP desktop acceptance;
those workflows remain unverified on Windows.

运行 `OpenPyCharm-VERSION-windows-x64-setup.exe`。安装器按当前用户安装，不需要管理员
权限，并提供可选的 `.py` 文件关联。EXE **未签名**。原生 Windows CI 中的静默安装、
启动与卸载检查不等于交互式 Python 或 HTTP 桌面验收；Windows 桌面工作流仍未验证。

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
separate. In dev.2, Django/Flask/FastAPI generators use this native
interpreter/venv flow. Installing their pinned example dependencies is optional
and off by default; it uses the selected Python environment and network access.

通过原生项目设置选择本机 Python 解释器或创建虚拟环境。应用内置 Java，但 Python
项目解释器需要另行选择。dev.2 预览版的 Django/Flask/FastAPI 生成器沿用原生解释器/
venv 流程。示例依赖安装可选、默认关闭；开启后使用所选 Python 环境并需要网络。

Framework examples and their Run/Debug configurations are a bounded starting
point. They do not imply complete framework, template or ORM intelligence.
Notebook and database tools are not included in dev.2.

框架示例及其运行/调试配置仅覆盖当前实现范围，不代表完整框架、模板或 ORM 智能
支持。dev.2 不包含 Notebook 和数据库工具。

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
