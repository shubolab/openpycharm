# 0.1.0-dev.2 verification draft / 验收草稿

**Status: pending final acceptance; not release-ready. / 状态：最终验收待完成，不可据此发版。**

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
| Published release / 已发布版本 | dev.2 pending; [dev.1 remains published](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.1) |

## Installer receipts / 安装包收据

Both native CI jobs succeeded, including the macOS actual cold Markdown gate.
The release owner is downloading and checking the exact installer and provenance
artifacts. Their hashes are pending here; no earlier candidate checksum is used.

双平台原生 CI 已成功，包括 macOS 真实冷 Markdown 检查。发行负责人正在下载并核对
明确的安装包与来源收据；本页摘要待补充，不使用较早候选的校验和。

| Asset / 资产 | SHA-256 | Status / 状态 |
| --- | --- | --- |
| `OpenPyCharm-0.1.0-dev.2-macos-arm64.dmg` | Pending / 待确认 | Final downloaded and mounted-image receipt pending / 最终下载与挂载收据待确认 |
| `OpenPyCharm-0.1.0-dev.2-windows-x64-setup.exe` | Pending / 待确认 | Final downloaded installer receipt pending / 最终下载收据待确认 |
| `SHA256SUMS.txt` and provenance / 校验和与来源收据 | Pending / 待确认 | Publish with exact assets after acceptance / 验收后随明确资产发布 |

macOS uses an ad-hoc signature and is not notarized. The Windows EXE is unsigned.
These limitations remain for dev.2.

macOS 使用临时签名、未经公证；Windows EXE 未签名。dev.2 保留这些限制。

## Current evidence boundary / 当前证据边界

The CI success below is confirmed by the release owner. Final downloaded
receipts will supply the precise counts and hashes; no final GUI pass is implied.

下表 CI 成功已由发行负责人确认。实际下载收据将补充精确数量与摘要，不代表最终
图形界面验收通过。

| Check / 检查 | State for this candidate / 当前候选状态 |
| --- | --- |
| Repository controls, fixtures, native source replay and plugin builds / 仓库控制、示例、原生源码回放与插件构建 | Native CI passed; artifact receipts pending / 原生 CI 通过，artifact 收据待归档 |
| Mac CI actual cold Markdown panel / Mac CI 真实冷 Markdown panel | Passed; final artifact receipt pending / 通过，最终 artifact 收据待归档 |
| Windows native install/start/uninstall / Windows 原生安装、启动与卸载 | Native CI passed; downloaded receipts pending / 原生 CI 通过，下载收据待归档 |
| Packaged HTTP/framework API, generated real venvs and servers / 安装产品 HTTP/框架 API、生成项目真实 venv 与服务 | Native CI passed; final receipts pending / 原生 CI 通过，最终收据待归档 |
| Final installed Mac Python Run / 最终 Mac 安装版 Python 运行 | Pending / 待验收 |
| Final installed Mac unittest tree / 最终 Mac 安装版 unittest 结果树 | Pending / 待验收 |
| Final installed Mac FastAPI create/debug/evaluate/resume/stop / 最终 Mac 安装版 FastAPI 创建、断点、求值、继续与停止 | Pending / 待验收 |
| Final installed Mac HTTP current/batch/Unicode/binary/cancel / 最终 Mac 安装版 HTTP 单条、批量、Unicode、二进制与停止 | Pending / 待验收 |
| Final installed Mac cold README restoration / 最终 Mac 安装版 README 冷恢复 | Pending; a panel/API check alone is insufficient / 待验收，panel/API 检查不能代替此项 |
| Installed product immutability, strict signature and bounded session log / 安装产品不变性、严格签名及有界会话日志 | Pending after desktop workflows / 待桌面工作流完成后确认 |
| New installed-version GIF and capture manifest / 新安装版本 GIF 与拍摄清单 | Pending; no old recording selected / 待录制，未选择旧版录屏 |
| Windows interactive Python/HTTP/framework desktop / Windows 交互式 Python、HTTP 与框架桌面 | Unverified / 未验收 |

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
[source-replay note](jcef-startup.md). A cold Markdown panel proves that path;
restoring an installed README remains a separate desktop gate.

JCEF 修复回放固定公开源码，调整 `JBCefApp$Holder` 的单例构造，不禁用 Markdown/
JCEF、代理和服务认证，不屏蔽错误日志，也不删除用户缓存。有界控制和异常/取消边界
见[源码回放说明](jcef-startup.md)。冷 Markdown panel 证明确切路径，已安装 README
恢复仍须单独桌面验收。

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
