# Next-only frontend integration plan

Base: `913e59b` (reviewed dev.3 release documentation; installer production source `9a243e6`). The accepted M0/native frontend slice is integrated on `codex_frontend_integration_next`. All145 existing production inputs, the original four plugins, product version and both root READMEs remain byte-identical. Sixteen frontend inputs are recorded separately; the normal strict source inventory now covers all161, without exclusions. The ordinary product assembler still packages exactly the original four plugins.

The new entry point creates a **separate default-off plugin ZIP/overlay**, not an IDE installer:

```sh
python3.11 scripts/prepare_frontend_candidate.py \
  --sdk /absolute/authenticated/PC-SDK --output .tools/new-frontend-candidate \
  --verify-determinism --test
```

It rejects changed/removed dev.3 inputs, unrelated new source, edited release READMEs, changed compiled JAR bytes and reused output paths. Two fresh forced compiles must produce identical JARs and payloads. It never provisions tools, invokes Node, installs a plugin, edits an app, starts an IDE or publishes. Its ZIP contains only the independent frontend plugin JAR. Node/TLS/TS pins, complete expected runtime/legal manifests and all packaged notices match the accepted candidate; runtime binaries are not redistributed here.

Observed: all four original plugins compiled and passed their existing headless/backend controls. Notebook remains `88224892…`, Database `499b6849…`; HTTP and Framework hashes are in the JSON receipt. Repository tests:144 passed,6 existing real-kernel checks skipped. Frontend boundary tests:25 passed. Current frontend compile/FIFO/identity/EDT controls and static SDK boot/module/EP/service closure passed. No Node or IDE was run during this integration.

Root's next native window:

1. Use a new owned profile and the candidate's external plugin directory, preserving the signed app/SDK. First leave activation off: opening JS/TS must not launch Node.
2. Explicitly prepare the already authenticated Node24.22.3 / TLS6.1.0 / TypeScript6.0.3 cache and all21 corresponding legal sets **offline** under this worktree's compiled cache parent. Generate an owned M0 fixture/nonce and normal module content root. No editor-open download or installation is allowed.
3. Keep the ordinary project-trust flow. Enable only the exact M0 fixture/nonce/receipt/hash properties after preparation. Verify actual module/EP/service startup, selected TypeScript path, native unsaved TS/JS completion, diagnostics/navigation, emoji/CRLF changes and cancellation/stale-response behavior.
4. Exercise restart and project close with pending work; verify only owned PID/start-time identities are cleanup targets. Unknown identity must not be treated as exit. Unexpected parent-crash reparenting and Windows native lifetime still require their own evidence.

The candidate deliberately retains compiled owned fixture/cache paths; it is not yet a general relocatable frontend distribution. Only three classes differ from the accepted `c127…` JAR because those absolute path constants changed; all other class and resource bytes match. Keep actual IDE service/document UI and Windows acceptance separate from compile/headless controls. Do not add this candidate to dev.3 or change the published demo. Root owns the next version, native evidence, installers and release decision.

中文：这是913基线上的 next-only 源码和独立 Frontend ZIP 候选，不改 dev.3 版本、根 README、四插件默认装配或145项既有生产输入。新增16项单列，全161项继续严格绑定。默认关闭，不自动下载、安装或执行 Node；本轮未启动 IDE。下一轮由主流程在普通 trust 和隔离 profile 内显式准备缓存、启动验证服务/文档界面及生命周期；Windows 和意外重归属未验证，不能据此宣布完整前端或1:1完成。

A later actual native M0 window loaded exact `c127087d…` into installed dev.3; see
[desktop evidence](frontend-native-desktop-20261114.json). It confirms that bounded
fixture candidate, not the retargeted `2ae4…` overlay or a general product frontend.
