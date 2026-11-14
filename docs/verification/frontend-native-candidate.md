# Public native LSP process candidate

The frozen M0 already registered `LspIntegrationProvider` with a `ProjectWideLspClientDescriptor`, normal `com.intellij.modules.lsp` dependency and explicit JS/TS language IDs. This candidate keeps that connection and its default-off owned-fixture boundary. It adds the public `startServerProcess` hook with an SDK `OSProcessHandler`, plus testable transport and release controls. No Ultimate alias, proprietary JS/TS implementation, new editor surface, product packaging or automatic dependency acquisition is introduced.

The fixed public [descriptor API](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp/src/api/LspClientDescriptor.kt) exposes the process hook and preserves CRLF framing. The pinned [connector shutdown path](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/src/impl/connector/Lsp4jServerConnector.kt#L116) writes the shutdown request before waiting on its response future. A response timeout therefore does not itself bound a blocked OS write. The candidate gives stdin one bounded FIFO owner, at most eight queued writes of at most 8 MiB, and a two-second write deadline. A write timeout makes that transport terminal and independently schedules cleanup; cleanup never acquires the writer's pipe lock. An interrupted request thread cannot truncate an accepted shared document notification.

Authentication, process creation and transport writes reject the Swing EDT. Dispose schedules work and returns. The exact handler is registered with the normal project disposable; completed handlers remove themselves from that tree. Startup rechecks normal project trust after cache authentication. The public native client manager remains responsible for document synchronization, request routing and its ordinary client/root lifecycle.

The native hook signals the spawned main process and observed descendants only while PID and start time still match. A missing main identity fails closed using the newly created Process object. Reused/unverifiable child identities are not signalled. Incomplete identity evidence or more than 128 tracked live processes cannot report complete cleanup. **The native hook does not install a dedicated POSIX session or Windows Job. Descendants that reparent between observations after an unexpected parent crash remain unverified.** The preserved protocol CLI has a separate, stronger session/job ownership boundary; its result is not relabelled as native-hook proof. The headless control's outer JVM watchdog also owns a separate test session/job, not the IDE's group.

Observed on macOS against the authenticated PC261 SDK and existing Node24.22.3 / TLS6.1.0 / TypeScript6.0.3 bytes:

- The actual public SDK process handler and LSP4J stdio delivered TS/JS completions from unsaved text, including emoji. TLS omitted optional `serverInfo`; its real TypeScript version notification reported `6.0.3`, source `user-setting`.
- Four real request futures were cancelled. The following shared document change reached the server, and a completion exposed its newly added property.
- SIGSTOP of the exact owned Node plus a full input pipe caused write failure after 2006ms. Independent cleanup ended after1030ms with the three observed owned identities gone, no writer/stream-closer thread alive, and unchanged pinned tools. Native SDK disposable-parent release returned on EDT after12ms; a fresh replacement process also closed cleanly.
- Pure controls reject EDT writes, preserve FIFO/interrupt state, reject reused PIDs, handle executor refusal independently, and avoid claiming unverifiable children clean.
- An offline audit of actual SDK boot JARs, module alias, canonical EP, project-service XML, candidate descriptor and implementation-class closure passed. This is static registration evidence, not service startup.
- All104 repository tests and20 focused frontend tests passed. The original M0 files, tools lock and legal closure are byte-identical; its original real protocol and full-pipe shutdown controls also passed.

Reproduce with the already authenticated offline cache and an explicitly prepared fixture:

```sh
python3.11 scripts/build_frontend_plugin.py --sdk /absolute/authenticated/PC-SDK --test \
  --worker-fixture /absolute/owned/fixture --process-fixture /absolute/owned/fixture \
  > .tools/frontend-native-build.json
python3.11 scripts/frontend_native_api_audit.py --sdk /absolute/authenticated/PC-SDK \
  --build-report .tools/frontend-native-build.json
```

The ordinary builder `--test` does not start Node. `--process-fixture` explicitly starts the pinned owned local server, not an IDE or network service. Existing M0 archives were copied read-only into the new worktree's cache, reauthenticated and extracted using `--offline`; all21 dependency legal sets remain present. No npm/install script or runtime download was invoked. Child analysis credentials/cache isolation follows the unchanged M0 policy and does not modify Git/npm/service authentication outside that child.

A native project scaffold and activation data are prepared under this worktree's `.tools`; the exact path is in the JSON receipt. Opening it must still use ordinary project trust, isolated IDE paths, the exact candidate JAR and explicit M0 activation properties. This agent did not open it. Native module/EP/service startup, `LspClientManager` document/version ordering, completion/diagnostic/navigation UI, project close/restart, Windows behavior and distribution remain separate gates. Existing native editors/TextMate may provide syntax; this LSP slice is not complete JavaScript/TypeScript PSI or refactoring. HTML/CSS, embedded languages/templates, frameworks and browser DAP remain outside this candidate.

中文：本候选继续沿用公开原生 LSP EP、正常项目 trust 和默认关闭的自有夹具边界。新增公开 SDK 进程适配器、有界输入及独立释放；不会以响应 future 的超时替代真实管道写入期限。鉴权、进程启动、写入与等待不进入 EDT。真实 headless SDK/Node/TLS 控制和静态注册闭合已通过，完整锁与第三方法律保留，原 M0 有界关闭不变。

本代理没有启动 IDE，不把公开 SDK 进程控制冒充原生 IDE 客户端/编辑界面验收，也未证明 Windows 或意外父进程崩溃后的重归属子进程发现。默认关闭、未打入生产包；不能据此宣称完整前端或 PyCharm 1:1 对齐。
