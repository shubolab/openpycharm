# 0.1.0-dev.3 release verification / 发行验收

The recorded native CI, installers and final installed Mac workflows passed.
Full PyCharm parity remains incomplete. / 本页记录的原生 CI、安装器与最终 Mac 安装版
工作流通过；完整 PyCharm 对齐尚未完成。

| Identity / 来源 | Value / 值 |
| --- | --- |
| Production source / 生产来源 | `9a243e605c43d86788b0e1b4607ec3bdf11b13d1` |
| Native CI / 原生 CI | [43565932969](https://github.com/shubolab/openpycharm/actions/runs/43565932969) |
| Upstream / 上游 | OSS PyCharm `2026.1.4`, `PC-261.26222.68`, source `456919a9624bae72ac12efafc35d2b916cb0c5c5` |
| Release / 发行 | [v0.1.0-dev.3](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.3) |
| Detailed receipts / 明细收据 | [CI](dev3-ci-20261114.json), [installed Mac](dev3-installed-20261114.json), [GIF](../demo/v0.1.0-dev.3/capture.json) |

## Installers / 安装包

Both artifact ZIPs, their complete paths, source inventories and standalone
installers were verified. The 145 production inputs match the production commit;
Windows has 29 exact, recorded LF-to-CRLF checkout conversions. Both accepted
archive layouts use one consistent root. The actual Mac DMG was mounted read-only,
copied to `~/Applications/OpenPyCharm.app`, and verified before and after use.

两个 artifact ZIP 的完整路径、源码清单与独立安装包均已核对。145 项生产输入匹配
固定来源，Windows 的 29 项准确换行转换单独记录。Mac 从明确的 DMG 只读挂载、安装，
并在工作流前后核对产品树和严格签名。上一安装版保留，对照 PyCharm 未修改。

| Installer / 安装包 | Bytes / 字节 | SHA-256 |
| --- | ---: | --- |
| `OpenPyCharm-0.1.0-dev.3-macos-arm64.dmg` | 701566993 | `c32a15bedc407dcd90fbfe1f99606e40a7b30f077207d28c41c068a2898464a6` |
| `OpenPyCharm-0.1.0-dev.3-windows-x64-setup.exe` | 611628694 | `27fb3f71c9e4e425125ff73acba510347dc5e7e0639988eed87412087da11dd8` |

| Product identity / 产品来源 | macOS arm64 | Windows x64 |
| --- | --- | --- |
| Artifact ID | `14102297519` | `14102856659` |
| ZIP SHA-256 | `854dedd78fa0fb10579200b875663757ac533e2a4a0340caca8df2d7c4323408` | `faa1413f38c576eb6cd3909aef8d0b9ef741a5424e6444ba0c8cba1de404a990` |
| Manifest SHA-256 | `871516408f54dd54874c7bbca716a0279baa2d7e33e4589d5acc5fbdf7fadd58` | `b5871a045fb7dff6fc05be8bfa9ae73c382d3b077a7aef3bcbaab75a7d66f1bc` |
| Product tree SHA-256 | `7485d3022a1a8fd113cb8a5c485473dd6cd69f16f4d346a6b250cbd0505a2205` | `3b97d05f213dfbd3ef432e2547ce1d7ca1bc3ad5c2dbb974b4d1c3734da81579` |

The Mac app is ad-hoc signed and not notarized; the Windows installer is unsigned.
The release also provides `SHA256SUMS.txt` and a compact provenance ZIP.

## Native CI and installed desktop / 原生 CI 与安装版桌面

| Check / 检查 | Observed result / 观察结果 |
| --- | --- |
| Repository controls | Mac 125 passed; Windows 125 run, 122 passed, 3 POSIX-only skips; each platform's 9 Python example methods passed |
| Actual JVM/local kernel | Both passed with fresh pinned kernel dependencies; no substitution of fake kernel messages |
| Notebook native Save/Undo/merge/reopen | Both passed through the normal IDE new-project lifecycle for generated owned fixtures; `parentTrustedBefore/After=false` (parent remained untrusted); no global trust override |
| HTTP/framework | Both passed native API registration/generation and real generated framework servers; full physical workflows are not inferred from these gates |
| Cold Markdown | Actual Mac CI cold panel/nonce/Chinese rendering passed |
| Windows installer | Native silent install/file identity/startup/uninstall passed; physical interactive desktop remains unverified |
| Final Mac Run/Test/Debug | Run totals `34.00/2.04/36.04`; 9 unittest methods/20 items; two breakpoints, F8, native `quote.total=Decimal('36.04')`, F9; exit 0 |
| Final Mac Notebook | Fresh native-settings Python 3.14 venv; real PNG phase 2, JPEG, DataFrame `99`, static HTML/Markdown; expected ValueError/recovery 42, Interrupt/KeyboardInterrupt, physical Shift+Enter 56/99; save/close/reopen preserved the 10 original sources/metadata and real outputs; reopened kernel stopped |
| Final Mac SQLite | Three Chinese rows; physical Basic + Return inserted `"main"."products"` and `p."name"`; Disconnect completed |
| Post-workflow | Unchanged tree `7485d3…`, strict signature passed; owned app and kernel/debug processes ended |
| Demo | Six fresh actual installed-version screenshots, 1280×820 animated GIF; SHA-256 `66fe947dc2b6ef199d7fba53bb3120298fe572a1bce3a696de62f357795eecf1` |

The installed Notebook fixture began with empty outputs/execution counts. Its
pristine SHA-256 is `6154f2eb0c86713431ba38e597baba7d3efe7ca5dfd8beea804b3803421ee0c8`;
the actual executed/saved file is `20c9597ea507de8b7fe58d907ad2aa28462590e4a701d144ada42aac8201a814`.
Unknown metadata/MIME and the integer `9007199254740993` remained exact.
The initial `fixtureState` metadata describes the prepared control and is
preserved as foreign metadata; the execution evidence is the recorded outputs,
native UI and process receipts.

Notebook 夹具开始时输出和执行次数为空；最终实测文件保留原 10 个单元源码、元数据，
保存真实图像、更新后的表格、错误和恢复输出。未将旧候选的 Restart 桌面观察计作
本安装候选重复完成的动作。所选 Python 中的内核依赖由用户显式安装，IDE 不自动安装。
SQLite 补全缓存五分钟后过期；重连或 **Refresh tables** 刷新后，真实键盘接受补全通过。

## Retained diagnostics / 保留的诊断

The bounded installed session is **2026-11-14 14:54:54–16:14:51**, with **0
ERROR/SEVERE and 141 WARN**, not a warning-free session. Of these, 115 are action
template text diagnostics when enumerating Find Action, 11 theme diagnostics,
9 absent Python search directories, and 6 other retained warnings. These include
debugger accept timeouts/transient hidden-frame diagnostics despite successful
stepping/evaluation/resume, a project-store override and Git state diagnostic.

One 10-second background-write warning occurred during the normal project-open
current/new-window/attach modal. Its dump shows EDT waiting for modal input while
the platform file-refresh flow waits for write intent. No executing Notebook
save stack or cyclic wait was demonstrated; the old project closed and the new
project started normally, followed by successful complete desktop workflows.
The dump hash and uncertainty are recorded in the installed receipt.

有界日志并非无警告：141 条 WARN 原样保留，包括项目打开确认框期间的一次后台写等待
诊断、调试器超时/隐藏帧提示、主题和动作模板诊断等。该 dump 未显示 Notebook 保存
循环死锁，之后完整工作流成功；这也不构成所有未来锁场景均安全的证明。

## Limits and history / 限制与历史

Windows physical desktop, network PostgreSQL/MySQL/MariaDB authentication/TLS,
PasswordSafe provider flows, remote kernels, active Notebook JavaScript/widgets,
Notebook debugging, complete SQL/framework/frontend semantics and full 1:1 parity
remain open. Dev.2 HTTP/FastAPI physical desktop records remain versioned history;
this release's CI checks do not relabel them as repeated installed dev.3 actions.

Earlier failed Notebook read/save/trust startup and SQL insertion candidates are
retained. See [read-access preflight](notebook-rich-native-preflight-20261114.json),
[cell regression](notebook-cell-native-regression-20261114.json),
[normal-project save gate](notebook-owned-project-native-20261114.json),
[SQL insertion](database-completion-native-20261114.json) and
[dev.2 history](2026-11-14-dev2-release.md).

Local IDE use has no IDE account/billing/subscription flow. Git/GitHub/private
repository and user-selected service authentication remain. Reference installs
are read-only; upstream open-source and third-party notices are retained.
