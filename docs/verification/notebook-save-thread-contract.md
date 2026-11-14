# Notebook native save gate

The captured dev.3 preflight froze during Notebook **Save**. Both retained thread dumps place the Notebook save worker inside a caller-owned `WriteIntentReadAction`, waiting for `FileDocumentManagerImpl`'s ordinary synchronous EDT `beforeAnyDocumentSaving` callback. The EDT remained runnable in its write-intent event queue. This establishes the save lock cycle; it does not establish a separate Undo/reload cause.

The fix enters saving on an unlocked worker. It lets the fixed platform implementation own its internal write action and transfer the callbacks that run inside that action. It also moves the whole parent-document reload entry to the EDT, because background saving can deliver document notifications. Parsing, merge preparation and serialization remain on workers; generation/stamp checks still reject stale results. The accepted dirty-state, exact-number merge and independent kernel-disposal code is unchanged.

This depends on the pinned platform implementation at [`456919a9624bae72ac12efafc35d2b916cb0c5c5`](https://github.com/JetBrains/intellij-community/tree/456919a9624bae72ac12efafc35d2b916cb0c5c5). It is not a general public API guarantee: the pinned `FileDocumentManager` API still documents EDT/write-intent use, whereas the same platform's official background save caller uses its IO dispatcher without an outer read/write-intent/write lock.

Primary source points:

- [`FileDocumentManagerImpl.java`](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/platform-impl/src/com/intellij/openapi/fileEditor/impl/FileDocumentManagerImpl.java#L340): initial synchronous bridge before the internal write action; ordinary bridge at lines 1104–1105; transferred in-write-action bridge at lines 1074–1080.
- [`SaveAndSyncHandlerImpl.kt`](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/configuration-store-impl/src/SaveAndSyncHandlerImpl.kt#L316): official background save entry on IO, without an outer action.
- [`FileDocumentManager.java`](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/core-api/src/com/intellij/openapi/fileEditor/FileDocumentManager.java#L106): public documentation/annotation caveat.
- [`TransactionGuardImpl.java`](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/core-impl/src/com/intellij/openapi/application/impl/TransactionGuardImpl.java#L136): write-action assertion returns immediately off EDT. `ModalityState.any()` is not used to bypass write safety.

The JVM save control checks worker/EDT callback topology, rejects unsafe/rejected worker entry, and writes/reopens a real UTF-8 notebook. It explicitly reports `actualIdeSaveEngineExercised: false`. Persistence and exact-number merge regression controls also pass. The native probe compiles against the authenticated SDK and binds its report to the **actual selected product's** bundled Notebook JAR digest; compilation alone is not native save acceptance.

Prepare only (Python 3.11 or later; no IDE launch):

```sh
python3.11 scripts/notebook_save_probe.py --sdk /absolute/authenticated/PyCharm.app \
  --workspace .tools/new-owned-save-compile --prepare-only
```

Run only in the root-controlled native acceptance window, using a newly assembled fixed product:

```sh
python3.11 scripts/notebook_save_probe.py --sdk /absolute/authenticated/PyCharm.app \
  --app /absolute/fixed/OpenPyCharm.app --workspace .tools/new-owned-save-native --run --timeout 180
```

The workspace must be new and below this checkout's `.tools`. The gate creates an owned project and isolated config/system/plugins/log paths. Ordinary project trust remains active. It does not execute notebook code or modify the SDK/reference installation. Existing fixture outputs are explicitly test data, not kernel execution evidence.

The actual-platform gate opens `NotebookFileEditor`, edits Unicode Python, invokes the native undo manager, merges pending cell edits with independent JSON metadata, clicks the real Notebook Save button twice, verifies persisted bytes/large-integer metadata/unknown MIME data, closes and reopens the editor, and measures EDT heartbeats. Timeout or cleanup failure retains the exact owned PID, logs, captured document/cell contents and thread evidence. Only the launcher and descendants created by this invocation are cleanup candidates. Windows uses the existing suspended-launcher/owned-job control; Windows native behavior still needs its own actual run.

Observed headless/compile evidence is retained under the savefix worktree's `.tools/savefix-build.json`, `.tools/save-native-compile-final-3/prepared.json` and `.tools/savefix-repository-tests.log`. Native gate results, normal-modal callbacks, disposal during saving and the reported Shift+Enter shortcut failure remain separate acceptance items. The shortcut is not changed by this save fix.

中文：此次修复针对两份原生线程转储明确证明的保存锁等待：调用者在后台持有 WIRA，同时等待普通 EDT 回调。改为无外层锁的后台保存，遵循当前固定版本实际使用的后台入口；不能把它写成跨版本通用 API 保证。文档变更回调先整体切回 EDT，再捕获/更新可变编辑器状态。已有 dirty、三方合并、大数精确比较和独立内核清理保持不变。

无界面测试及原生探针编译均不能替代真实桌面保存验收。探针要求主流程显式 `--run`，检查原生撤销、待保存 cell 与外部 JSON 合并、两次保存、EDT 心跳、文件字节和重新打开。普通项目信任不被绕过，不运行夹具内 Python。失败保留线程及精确自有进程证据，Windows 仍需实际运行。快捷键缺口不在本小修中宣称已解决。
