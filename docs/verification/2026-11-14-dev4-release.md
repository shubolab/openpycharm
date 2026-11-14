# 0.1.0-dev.4 preview verification / 预览版发行验收

Full PyCharm 1:1 parity remains incomplete. This record covers the bundled
frontend preview, native product gates, installer transport and bounded desktop
observations. Published on 2026-11-15 (Asia/Shanghai); the [publication receipt](v0.1.0-dev.4-published.json) records all four server digests and anonymous public transport checks.

完整 1:1 尚未完成。本页记录前端预览版、原生产品门、安装器传输和有界桌面观察；
公开发行日期为 2026-11-15（Asia/Shanghai），附件摘要及匿名下载核对见发行收据。

| Identity / 来源 | Value / 值 |
| --- | --- |
| Production source | `63921a4a931e19996b05ea4de4df12d27ff021bf` |
| Native CI | [43608150941](https://github.com/shubolab/openpycharm/actions/runs/43608150941), both jobs successful |
| Upstream | OSS PyCharm 2026.1.4 / `PC-261.26222.68` |
| Release | [v0.1.0-dev.4](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.4) |
| Receipts | [CI](frontend-dev4-ci-20261114.json), [artifacts](frontend-dev4-artifacts-20261114.json), [installed CI DMG](frontend-dev4-ci-installed-20261114.json), [desktop](frontend-dev4-installed-20261114.json) |

## Observed / 已观察

Both complete artifact ZIPs match GitHub's recorded size and SHA-256. Every ZIP
entry passed path, duplicate, type and CRC controls. All 171 production inputs
match the source: Mac has 171 exact files; Windows has 138 exact files and 33
recorded exact LF-to-CRLF conversions. No source path was omitted.

两个完整 ZIP 均匹配 GitHub 的大小与 SHA-256，全部条目通过路径、重复、类型与 CRC
检查。171 项生产输入全部核对：Mac 171 项逐字节相同；Windows 138 项相同、33 项
精确换行转换逐路径记录，没有笼统排除文件。

| Installer / 安装包 | Bytes / 字节 | SHA-256 |
| --- | ---: | --- |
| `OpenPyCharm-0.1.0-dev.4-macos-arm64.dmg` | 745666387 | `5b07b72026108082a56da34cad2be600f56b04d99850c8a7e25176cf49eaaa76` |
| `OpenPyCharm-0.1.0-dev.4-windows-x64-setup.exe` | 646318653 | `fa1dcf5e36e1a1f5e41e3859c6ee158101f148b75f4e4126dcc90d54621e8aa2` |

Mac artifact ZIP: 693250632 bytes, SHA-256
`840ad6505d0736df48ca04911922c7bfb74c1936af300984010f0f6dfef5691a`.
Windows artifact ZIP: 647582321 bytes, SHA-256
`6c5e73822667a892bd9823456721aed55ad670d5b97ca2ef6a93973ce08f56cd`.
These ZIP digests differ from the standalone installer digests above.

| Gate / 检查 | Recorded result / 结果 |
| --- | --- |
| Local repository controls | 177 passed, zero skips, authenticated SDK and selected real Notebook Python |
| CI repository controls | Mac 177 run/175 pass/2 pre-SDK skips; Windows 177 run/171 pass/6 explicit skips |
| Additional frontend SDK controls | Both platforms: 4 passed, including 68 worker/settings/filesystem controls and real 191-file runtime authentication |
| Python fixture | 9 methods passed on both platforms |
| Existing native product gates | HTTP, framework generation/real venv servers, Notebook JVM/local kernel/edit/undo/merge/save/reopen, startup passed on both; Mac cold Markdown passed |
| Installers | Mac mounted/copied tree and strict signature; Windows silent install/file identity/native startup/uninstall passed |
| Downloaded CI Mac app | Read-only mount, actual copy-install, native startup and post-startup unchanged tree/strict signature passed; tree `234acb5ede9ebfe39bbae3b464f6b9dfa89a7dfe38bed77bffee48c0a44eb7b9` |
| Product contents | 5 plugins; frontend contains 193 files, including 191 pinned runtime files and corresponding 21 notice sets; 17 product classes, no M0 provider classes |

The initial run `43607720413` stopped in repository controls. Repairs isolated
synthetic overlay fixtures from missing shallow-clone history and made a HOME
assertion use native path separators. A separate Windows JVM helper fix uses a
UTF-8 argument file for long classpaths. The successful run above includes those
fixes. They do not alter the product's 171 production inputs.

## Actual native desktop / 实际原生桌面

The local DMG was copied and run on **macOS 27.2 arm64**, Python **3.14.0**, with
isolated IDE paths and ordinary trust for only the owned fixture projects.

- Edited Python Run printed `34.00/2.04/36.04`, exit 0. Native unittest reported
  9 methods/20 items passed. Debug reached the calculator breakpoint, displayed
  native evaluation `Decimal('2.0400')`, stepped with F8 and resumed with F9 to exit 0.
- Python PSI completion accepted `quote.total`. Cross-file Rename changed class,
  exports, imports, calls and tests; tests passed. Native Undo restored the class
  and the test run passed again; restored source files were compared bytewise.
- Bundled TypeScript started by default in a normally trusted project. Member
  completion inserted `quote.total`; the Problems pane showed the real string/
  number type error; Cmd+B navigated to `quote.ts:1:17`.
- JavaScript completion accepted `receipt.installedNative_9631` from unsaved text
  containing Chinese and emoji. The identifier was absent on disk before acceptance.
- Normal project close removed all three observed owned Node processes. Normal
  Quit ended the owned IDE/debug processes; the signed app tree stayed unchanged.
  The earlier external-product-plugin window also verified project settings
  disable/re-enable and new owned process IDs.

本机 DMG 的真实键鼠流程覆盖上述 Python 编辑/运行/测试/调试/补全/跨文件重构与撤销，
以及 JS/TS 补全、诊断、定义跳转和未保存文本同步。普通项目关闭后自有进程退出，
未使用强制结束来计作成功。安装版树与严格签名在工作流后保持一致。

These desktop captures belong to the local DMG source `88387c3`, hash
`8b849bc6db67e929c8dff25ed32f79b0bb1d420c89487b6d85c0e34c8545dd64`.
The CI app from `63921a4` has **identical 171 production inputs and all five JARs**;
that equality and its separate copy-install/startup checks are observed. Complete
keyboard-and-mouse replay on the CI DMG was not performed. This distinction is
retained in the [six-frame GIF manifest](../demo/v0.1.0-dev.4/capture.json).
The local desktop log contains 0 ERROR/SEVERE and retained warnings; exact counts
and hashes are in its receipt. It is not described as warning-free.

拍摄来自本机 DMG，来源与 CI 安装器分别记录。CI 应用的 171 项生产输入和五个 JAR
逐字节一致，复制安装、启动、产品树与签名另验；没有把字节一致称为在 CI DMG 上
重复了全部键鼠流程。日志警告数量与摘要保留在明细收据中。

## Inferred and unknown / 推断与未知

The matching production inputs/JARs support sharing the local desktop functional
observations with this preview's code. They do not prove every platform, project,
workflow or performance scenario. Windows physical UI, native pending-request
cancellation/backpressure, unexpected owner-crash/reparenting cleanup, HTML/CSS,
full frontend PSI/refactorings/debugging, remote/container features and full 1:1
parity remain open. The standalone guardian prototype is stored separately and
is not shipped. Historical dev.3 Notebook/SQLite desktop evidence remains tied
to dev.3; the dev.4 CI/API checks are recorded separately.

相同源码与 JAR 支持对本预览版代码复用有界功能观察，不证明所有平台和场景。
Windows 实体桌面、异常进程清理、完整前端语义、HTML/CSS、远程/容器与完整 1:1
仍未完成。guardian 原型单独保存，不随产品发布；历史桌面结果保留其原版本归属。

## Canonical local installation / 本机正式安装位置

The verified CI app is now installed at `~/Applications/OpenPyCharm.app`,
with a retained dev.3 app under the repository's `build/retained-installed/dev3-before-dev4`.
Its isolated native startup, final tree, strict signature and exited owned process
were checked again. [Installation receipt](frontend-dev4-canonical-installed-20261115.json).

本机 OpenPyCharm 已更新为上述 CI dev.4，保留 dev.3 回退副本；独立启动、最终产品树、
严格签名及自有进程退出再次通过。该升级没有修改对照 PyCharm 或用户配置。
