# 0.1.0-dev.2 release verification / 发行验收

**Recorded CI and installed Mac checks passed. / 本页记录的 CI 与 Mac 安装版检查通过。**

Published as a prerelease on 2026-11-14. The [publication receipt](v0.1.0-dev.2-published.json)
verifies all four server asset digests, the release tag, and public README/GIF bytes.

已于 2026-11-14 发布预览版。[发布收据](v0.1.0-dev.2-published.json)记录四项发行资产的
服务器摘要、版本标签及公开 README/GIF 字节核对结果。

This document tracks one exact candidate. Earlier successful checks are retained
as historical evidence, not transferred to the final installed candidate.

本页跟踪一个明确候选。较早候选的成功检查保留为历史证据，不直接计入最终安装版
的验收结果。

| Identity / 来源 | Value / 值 |
| --- | --- |
| Version / 版本 | `0.1.0-dev.2` |
| Production source / 生产来源 | `d5fc10d19e295d02707598832fabee20d8d01bee` |
| Native CI / 原生 CI | [43522231765](https://github.com/shubolab/openpycharm/actions/runs/43522231765) |
| Upstream / 上游 | Open-source PyCharm `2026.1.4`, build `PC-261.26222.68` |
| Upstream source / 上游源码 | `456919a9624bae72ac12efafc35d2b916cb0c5c5` |
| Release / 发行 | [v0.1.0-dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2) |

## Installer receipts / 安装包收据

Both native CI jobs succeeded, including the macOS actual cold Markdown gate.
The exact artifacts were downloaded and authenticated against installer,
provenance and source-input receipts. Each product's 85 source inputs matched
the candidate source; Windows checkout line-ending conversions are recorded in
its download receipt. The Mac app was installed from the mounted CI image.

双平台原生 CI 已成功，包括 macOS 真实冷 Markdown 检查。明确的 artifact 已下载，
并与安装包、来源及源码输入收据核对；两产品各 85 项源码输入均匹配候选来源，Windows
检出换行转换在下载收据中单列。Mac 应用从挂载的 CI 镜像安装。

| Asset / 资产 | Bytes / 字节 | SHA-256 |
| --- | --- | --- |
| `OpenPyCharm-0.1.0-dev.2-macos-arm64.dmg` | 681,276,890 | `900281937ed35dc7858d58e4a90468242eb4addc8276331cc9aecf43c42064c5` |
| `OpenPyCharm-0.1.0-dev.2-windows-x64-setup.exe` | 596,918,304 | `8fd215445988f91ffe8c88af6e3e837071d47fd08476f9b3d23e290d457e6e18` |

Release assets and server metadata are on the [release page](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2).
Download receipts are retained under
`.tools/ci/dev2-d5fc10d/{macos-arm64,windows-x64}-download.json` in the release
workspace. Artifact IDs are `14084262350` (Mac) and `14084531145` (Windows).

校验和、来源发行资产及服务器元数据见[发行页](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2)。发行工作区在
`.tools/ci/dev2-d5fc10d/{macos-arm64,windows-x64}-download.json` 保留下载收据；
artifact ID 分别为 Mac `14084262350`、Windows `14084531145`。

| Product identity / 产品来源 | macOS arm64 | Windows x64 |
| --- | --- | --- |
| Manifest SHA-256 / 清单摘要 | `14302665cab50370b2f455c9bcd8ccbc063b0ea5de81866469c619fe45d43c9a` | `70e7a2d42bcd805b69a9e45410827286576ccccafb46d853af5abbe6e5f8404c` |
| Tree SHA-256 / 产品树摘要 | `21c996890ba9bb96c095361cabdd58ffa7dcc7722bc0a2a38efad33e1cbb121e` | `bea057e29ab0942779e9b8cc525be3eab96bf9ff4678e632be8f5ee38714c0cb` |

macOS uses an ad-hoc signature and is not notarized. The Windows EXE is unsigned.
These limitations remain for dev.2.

macOS 使用临时签名、未经公证；Windows EXE 未签名。dev.2 保留这些限制。

## Current evidence boundary / 当前证据边界

CI and final installed Mac desktop observations are recorded separately below.
The desktop checks used the exact downloaded DMG, source and product tree above.
The post-workflow tree/signature/log and capture receipts also passed.

下表将 CI 与最终 Mac 安装版桌面观察分开记录。桌面检查使用上表明确的 DMG、来源与
产品树。产品树、签名、日志后检及最终 GIF 收据也已通过。

| Check / 检查 | State for this candidate / 当前候选状态 |
| --- | --- |
| Repository controls, fixtures, native source replay and plugin builds / 仓库控制、示例、原生源码回放与插件构建 | Both native CI jobs passed / 双平台原生 CI 通过 |
| Mac CI actual cold Markdown panel / Mac CI 真实冷 Markdown panel | Passed / 通过 |
| Windows native install/start/uninstall / Windows 原生安装、启动与卸载 | Native CI passed / 原生 CI 通过 |
| Packaged HTTP/framework API, generated real venvs and servers / 安装产品 HTTP/框架 API、生成项目真实 venv 与服务 | Both native CI jobs passed / 双平台原生 CI 通过 |
| Final installed Mac Python Run / 最终 Mac 安装版 Python 运行 | Passed, expected totals and exit 0 / 通过，预期金额及退出码 0 |
| Final installed Mac unittest tree / 最终 Mac 安装版 unittest 结果树 | Passed, 9 methods / 20 items / 通过，9 个方法 / 20 项 |
| Final installed Mac FastAPI create/debug/evaluate/resume/stop/reopen / 最终 Mac 安装版 FastAPI 创建、断点、求值、继续、停止与重开 | Passed / 通过 |
| Final installed Mac HTTP current/batch/Unicode/Save/cancel / 最终 Mac 安装版 HTTP 单条、批量、Unicode、保存与停止 | Passed, including exact saved binary bytes / 通过，包含保存后二进制字节核对 |
| Final installed Mac cold README restoration / 最终 Mac 安装版 README 冷恢复 | Actual FastAPI README restored in native preview / 真实 FastAPI README 在原生预览恢复 |
| Installed product immutability, strict signature and bounded session log / 安装产品不变性、严格签名及有界会话日志 | Unchanged tree, signature passed, 0 errors / 产品树未变、签名通过、0 条错误 |
| New installed-version GIF and capture manifest / 新安装版本 GIF 与拍摄清单 | Actual dev.2 installed-app screenshots assembled and bound to manifest / dev.2 真实安装版截屏已组装并绑定清单 |
| Windows interactive Python/HTTP/framework desktop / Windows 交互式 Python、HTTP 与框架桌面 | Unverified / 未验收 |

The archived Mac CI Markdown receipt records both `HttpConfigurable` and
`ProxyMigrationService` uncreated before the first actual
`MarkdownJCEFHtmlPanel`, then created afterwards. The native browser rendered its
nonce and Chinese text; the owned application exited 0. That bounded CI log has
0 errors and 4 retained warnings. Source-derived Holder controls passed 68 checks;
the original SDK and unsafe-publication negative controls failed as expected.

Mac CI Markdown 收据记录首次实际创建 `MarkdownJCEFHtmlPanel` 前，HTTP 设置与代理
迁移服务均未创建，之后两者已创建；真实浏览器渲染随机标记和中文，本次应用退出 0。
有界 CI 日志含 0 条错误、4 条保留警告。源码派生 Holder 控制通过 68 项；原始 SDK 与
不安全发布负对照均按预期失败。

## Final installed Mac observations / 最终 Mac 安装版观察

System: **macOS 27.2 arm64**, Python **3.14.0**, installed
`~/Applications/OpenPyCharm.app`. These are actual desktop observations reported
by the release owner, after the application's normal startup and project trust.

系统为 **macOS 27.2 arm64**，Python **3.14.0**，应用安装于
`~/Applications/OpenPyCharm.app`。以下是发行负责人在应用正常启动及项目信任流程后
完成的真实桌面观察。

- **Python Run/Test:** `hello-python` printed `34.00`, `2.04`, `36.04` and exited 0.
  Native unittest showed 9 test methods / 20 items, all passing.
- **FastAPI:** native New Project created `FastAPI 新建` with a fresh Python 3.14
  venv and explicitly selected dependency installation. Native Debug started
  Uvicorn on `127.0.0.1:8000`; the request hit `app.py:8`, evaluation showed
  `app.title` as `'FastAPI'`, and Continue returned HTTP 200 with the clean response
  `{"framework":"fastapi","message":"Hello from FastAPI!"}`. Native Stop exited
  0. Save, close project and reopen retained the `OpenPyCharmFastAPI` configuration.
- **HTTP:** the current health request returned 200; Run All completed three
  requests with 200 responses. The echo preserved Chinese and 🚀. Native Save
  produced exactly 16 binary bytes `00` through `0f`, SHA-256
  `be45cb2605bf36bebde684841a28f0fd43c69850a3dce5fedba69928ee3a8991`. A slow request
  showed Sending / 1 running; Stop All changed this to 0 running / 1 cancelled,
  with `HTTP request cancelled` visible.
- **README restoration:** startup restored an existing FastAPI README in the
  native Markdown preview. This is separate from CI's cold panel/DOM check.

Python 运行输出金额正确且退出 0，原生测试树全部通过；全新 FastAPI 项目实际完成
venv、选择安装、请求断点、求值、继续、正常响应及停止，重开后配置保留。HTTP 单条、
批量、中文/emoji、原生保存和停止均完成，保存后的 16 字节与摘要匹配预期。README
启动恢复是独立的桌面观察，没有用 CI panel/DOM 检查替代。

## Post-workflow and capture receipts / 工作流后检与拍摄收据

The installed tree remained
`21c996890ba9bb96c095361cabdd58ffa7dcc7722bc0a2a38efad33e1cbb121e` and strict
ad-hoc signature verification passed after the desktop workflows. The bounded
250,949-byte session log has 0 errors and 20 retained warnings, SHA-256
`4576ada5bc68fd33a155d885ed97cccc7cf1860bf37775f40e562062c5f85513`.
The owned IDE and HTTP fixture processes exited. The release workspace retains
this receipt as `.tools/ci/dev2-d5fc10d/desktop-final.json`; the release owner
archives the [compact installed-desktop record](dev2-installed-desktop-20261114.json)
with the public evidence.

桌面工作流后，安装产品树仍为上面的 `21c99689…`，严格临时签名校验通过。有界会话
日志为 250,949 字节，0 条错误、20 条保留警告，摘要见上；本次 IDE 和 HTTP 测试服务
进程均已退出。发行工作区在 `.tools/ci/dev2-d5fc10d/desktop-final.json` 保留该收据，
发行负责人另将[安装版精简记录](dev2-installed-desktop-20261114.json)归档为公开证据。

The new GIF is **0.1.0-dev.2**, **macOS 27.2 arm64**, Python **3.14.0**. It is a
sequence assembled from actual native app screenshots: Python Run, unittest,
FastAPI breakpoint evaluation, and HTTP batch/Unicode response. The final frame
is HTTP, despite its retained raw filename `step.png`; no debugger step is
claimed. The four animation frames and four additional native captures were
hash-checked against the release owner's manifest.

新版 GIF 对应 **0.1.0-dev.2**、**macOS 27.2 arm64**、Python **3.14.0**，由真实原生
应用截屏组装，展示 Python 运行、unittest、FastAPI 断点求值和 HTTP 批量/Unicode
响应。最后一帧虽保留原始文件名 `step.png`，实际内容是 HTTP，不声称调试单步。
4 张动画帧和另外 4 张原生截屏均已核对拍摄清单摘要。

- GIF: `docs/demo/v0.1.0-dev.2/openpycharm-native.gif`, 588,934 bytes, SHA-256
  `4e8265f7c5118a990a2a24abbd5cd9c1da2a7ad434cd179f5f3ac3b967369c6e`.
- Manifest: `docs/demo/v0.1.0-dev.2/capture.json`, binding the installed DMG,
  production source, CI run, version, OS, Python and each raw capture.

Both READMEs reference this versioned GIF. No earlier demo was selected as dev.2
evidence. Publication and downloadable assets are tracked on the release page;
Windows interactive desktop acceptance is still open.

两个 README 均引用这份版本固定的 GIF，没有将旧演示作为 dev.2 证据。公开发行资产
及发布元数据见发行页；Windows 交互式桌面验收继续保持未完成。

## What dev.2 adds / dev.2 新增范围

The independent HTTP plugin provides `.http` editing, current-request and batch
execution, native Services responses, original-byte Save, and cancellation. The
independent framework plugin provides Django/Flask/FastAPI native configuration
types and New Project generators. It reuses PythonCore's selected SDK, native
Run/Debug runners, working directory and environment. Dependency installation is
off by default and explicit when requested. Generated examples return an ordinary
framework name and greeting, with no internal probe fields.

独立 HTTP 插件提供 `.http` 编辑、当前请求与批量执行、原生 Services 响应、原始字节
保存及取消。独立框架插件提供 Django/Flask/FastAPI 原生配置类型和 New Project
生成器，复用 PythonCore 所选 SDK、原生运行/调试 runner、工作目录与环境变量。
依赖安装默认关闭，仅在显式选择后执行。生成示例返回普通框架名称与问候，不含内部
探针字段。

The JCEF fix replays pinned public source and changes singleton construction in
`JBCefApp$Holder`. It does not disable Markdown/JCEF, proxy support or service
authentication, suppress log errors, or delete user caches. Its bounded controls
and exception/cancellation limits are described in the
[source-replay note](jcef-startup.md). CI exercised a cold Markdown panel, and the
final installed desktop separately restored a README preview.

JCEF 修复回放固定公开源码，调整 `JBCefApp$Holder` 的单例构造，不禁用 Markdown/
JCEF、代理和服务认证，不屏蔽错误日志，也不删除用户缓存。有界控制和异常/取消边界
见[源码回放说明](jcef-startup.md)。CI 检查了冷 Markdown panel，最终安装版另行完成
README 预览恢复。

## Historical observations / 历史观察

- [HTTP desktop candidate](http-desktop-20261114.json), source `6f9ae45`: actual
  Mac current request, three-request batch, Chinese/emoji echo, raw 16-byte Save
  and Stop All. This was a development app, not the final dev.2 installer.
- [Framework desktop candidate](framework-desktop-20261114.json), source `80cea80`:
  actual FastAPI Create/venv/dependency opt-in/Run. Its old internal response
  marker was subsequently removed; it is not evidence of the cleaned template.
- [Rejected installed candidate](dev2-26da-desktop-checkpoint.json), source
  `26da493`: Python Run/unittest and clean-template FastAPI native Debug worked,
  but restored Markdown logged the JCEF service-in-class-initializer SEVERE.
  That candidate was rejected. Its successful workflows and captures do not
  accept the repaired candidate.
- [Template cleanup controls](framework-template-cleanup-20261114.json) distinguish
  production Hello examples from instrumented test fixtures.

上述记录分别来自明确的旧候选：HTTP 开发版、仍含旧响应标记的框架开发版、以及因
Markdown SEVERE 被拒绝的 `26da493` 安装版。它们不能替代修复后安装包的验收；生成
模板清理检查也不等于最终桌面行为通过。

## Limits / 限制

Framework project generation and native Run/Debug are not complete framework
semantics or full PyCharm parity. Django/Flask desktop workflows, template/ORM
intelligence and broader navigation remain pending. HTTP environment files,
OAuth and broader credential workflows are not implemented by this slice.
Notebook and database tools are not included in dev.2. Windows desktop acceptance
and full 1:1 parity remain open.

框架项目生成和原生运行/调试不等于完整框架语义或 PyCharm 全量对齐。Django/Flask
桌面流程、模板/ORM 智能分析及更广导航仍待实现或验收。本次 HTTP 未实现环境文件、
OAuth 和更广凭据流程。dev.2 不包含 Notebook 和数据库工具。Windows 桌面验收与
完整 1:1 对齐仍未完成。

Local IDE use remains independent of IDE accounts, billing, subscriptions, trials
and upgrade promotions. Git/GitHub/private-repository and user-selected service
authentication are preserved. Reference installations remain read-only;
upstream open-source and third-party notices are retained.

本地 IDE 使用继续独立于 IDE 账号、计费、订阅、试用和升级推广；保留 Git、GitHub、
私有仓库及用户选择的服务认证。对照安装保持只读，保留上游开源及第三方声明。
