# Independent native notebooks: bounded implementation

This is a new independent plugin, not the proprietary PyCharm notebook implementation. SDK inputs are the authenticated Apache-2.0/open-source PC 261.26222.68 distribution pinned in `product/platform.lock.json`. The optional Jupyter packages are installed separately in the selected Python; no package implementation is vendored. Their exact direct versions, source URLs, wheel hashes and licenses are recorded in `plugins/notebooks/runtime-dependencies.lock.json`.

## Observed

- The actual source compiles with the authenticated native JBR against the pinned IntelliJ/PythonCore APIs. JDK and IntelliJ archive readers agree on all emitted JAR payloads. The builder receipt binds the plugin identity, version, SDK receipts and exact source hashes.
- JVM model checks exercise source edits, execution counts, captured outputs, add/delete, malformed/oversized input and lossless preservation of unknown notebook/cell metadata, Markdown attachments and untouched rich output fields. Newly captured Jupyter `transient` display IDs are excluded from saved nbformat.
- The large-metadata regression admits 2.6 million input characters, edits the source and serializes compact JSON without crossing the admission limit or losing foreign metadata. Immutable snapshots remain unchanged after later edits. A grown notebook remains serializable JSON instead of throwing at save time.
- Deterministic worker tests exercise immediate dirty state, one latest pending snapshot, serialization off the submitting thread, stale/external-generation rejection and dirty state retained on serialization failure.
- Both pending snapshots and prepared UI results have one latest slot. Rejected worker submissions keep dirty state and permit the next submission to retry. External merge suspension retains pending edits; explicit discard is a separate operation.
- Three-way merge tests preserve a pending notebook source edit alongside external notebook/cell metadata edits, including 2.6 million foreign metadata characters. Overlapping values, missing/null distinctions and incompatible cell identity/order changes produce precise conflicts and retain local values. The UI must resolve those conflicts explicitly rather than silently dropping edits.
- Eight bridge tests execute actual local ipykernels with the exact selected Python and cwd, stateful results, stdout/stderr, display data, traceback, no-stdin error, interrupt, busy restart/reset, bounded requests/output and normal/EOF/SIGTERM/broken-pipe cleanup. The unrelated test process survives. See `notebook-kernel-20261114.json`.
- The real compiled Java `NotebookKernelSession` extracts the embedded bridge and exchanges process-pipe events with the actual selected Python. Real stream/result42, interrupt, restart while busy, namespace reset, repeated close, replacement-kernel PID cleanup and unrelated-process survival pass without starting an IDE. See `notebook-java-session-20261114.json`.
- Disposal regressions use a real non-reading interpreter with an actually blocked pipe write and TERM-ignoring owned parent/child. Independent lifecycle disposal removes both within a bounded deadline without waiting for the command writer; close-during-startup and repeated close also pass on POSIX.
- The repository Python suite passes with the explicit test-owned kernel interpreter enabled; the existing Python fixture has nine passing tests. These are automated checks, not a desktop acceptance result.

## Inferred from compiled source; still needs desktop verification

- `.ipynb` is registered as text and supplied by an asynchronous native `FileEditorProvider`. File loading/parsing is performed before the EDT builder. Cell widgets use IntelliJ editors, PythonCore PSI and native Swing output areas. The ordinary text editor remains available for inspecting JSON.
- Run/Run All/Restart call the platform's actual `TrustedProjects.isTrusted(project)` before creating a session. Opening a file has no execution path. Selection uses the notebook's local module Python SDK, then the local project Python SDK; no global interpreter fallback or remote service is selected.
- Code and Markdown/raw cells are editable. Source/output changes become dirty immediately. A coalesced worker serializes immutable compact snapshots; only the current generation can update the ordinary IntelliJ document. External text changes suspend stale commits without clearing dirty edits, pause cell/kernel edits and are merged using the last committed baseline. Independent changes survive; overlapping changes retain dirty state and expose explicit keep/discard choices. Only the exact current document stamp accepts a merged result. The Save button waits for the prepared document before requesting background saving with write-intent access. Pending state survives tab disposal and is restored on reopen; a project-close handler runs before platform document saving and declines close while edits remain pending. These lifecycle integrations need actual desktop verification.
- Kernel startup, extraction, pipe IO, waits and cleanup run on pooled executors. Cleanup records only the launched bridge's actual descendants and checks PID plus start time before termination. Rebuilt cells dispose their listeners and release native editors.

## Unknown or not implemented

Native editor construction, keyboard editing/completion, Safe Mode clicks, save/undo/reopen, Run All, output scrolling and interrupt/restart buttons have not yet been exercised in a real desktop or installed candidate. No native screenshot/GIF is provided as evidence for this feature. Windows compilation/runtime/cleanup and installers remain unverified.

Rich HTML/image rendering, Markdown preview, widget comms, remote kernels, interactive stdin and notebook debugging are not implemented. Display mappings are session-local and cleared when cell widgets are rebuilt. No full 1:1 PyCharm acceptance, publishable release or installer delivery is implied by these checks.

## Reproduction

Use the repository's supported build Python and an authenticated SDK. The explicit runtime below must be a disposable/test-owned environment with `jupyter_client==8.6.3` and `ipykernel==6.29.5` installed. The probes perform no dependency installation and launch no IDE.

```sh
python3 scripts/build_notebook_plugin.py --sdk /absolute/authenticated/PyCharm.app --version 0.1.0-dev.3 --tests
python3 scripts/notebook_kernel_probe.py --python /absolute/test-venv/bin/python --output /absolute/owned/kernel-report.json
python3 scripts/notebook_session_probe.py --sdk /absolute/authenticated/PyCharm.app --python /absolute/test-venv/bin/python --output /absolute/owned/java-session-report.json
OPENPYCHARM_NOTEBOOK_PYTHON=/absolute/test-venv/bin/python python3 -m unittest discover -s tests -v
python3 -m unittest discover -s fixtures/hello-python -v
```

Public references: [nbformat description](https://nbformat.readthedocs.io/en/stable/format_description.html), [Jupyter client API](https://jupyter-client.readthedocs.io/en/stable/api/jupyter_client.html), [kernel messaging](https://jupyter-client.readthedocs.io/en/stable/messaging.html), [pinned IntelliJ Platform source](https://github.com/JetBrains/intellij-community/tree/456919a9624bae72ac12efafc35d2b916cb0c5c5).
