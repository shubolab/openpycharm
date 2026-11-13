# Broader PyCharm parity: source audit and next implementation

Audit date: 2026-11-14. Reference: installed PY `261.26222.68`; product input:
OSS PC `261.26222.68`, source
`456919a9624bae72ac12efafc35d2b916cb0c5c5`. This is a bounded static audit and
implementation proposal. It does not establish native framework/notebook/database
acceptance. The original full-parity goal remains open.

## Additional promotion-only registrations omitted

The OSS Python descriptor contains four **non-runnable** configuration types:
Django, Flask, FastAPI and dbt. The pinned
[PythonLockedRunConfiguration.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/run/PythonLockedRunConfiguration.kt)
constructs a promotion panel and lock icon; execution and validation throw the
"not runnable in this mode" error. These are not framework implementations.
`local_product.xml_filter` omits only their exact `configurationType`
registrations, in source JAR descriptors and the escaped embedded descriptors in
the bundled-plugin cache. No class is enabled, unlocked or changed.

The shared customization module also registers a unified-distribution welcome
banner and a listener recording migration state. Both live in
[WelcomeToUnifiedWelcomeScreenBanner.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/ide/impl/src/com/intellij/pycharm/community/ide/impl/promo/WelcomeToUnifiedWelcomeScreenBanner.kt).
Their two exact registrations are omitted. The previously excluded
`intellij.pycharm.community.ide.impl.promotion` module already contains the
nonfunctional Django/JavaScript project generators and promotion tool/settings
actions; it is still excluded without removing the real Python project wizard.

The fresh application also opened the upstream What's New tab. Its
[PyCharm content provider](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/ide/impl/src/com/intellij/pycharm/community/ide/impl/whatsnew/PyCharmWhatsNewInVisionContentProvider.kt)
selects `whatsNew/pycharm2026.1.json`, which the OSS artifact ships as embedded
JetBrains web content. The exact
[WhatsNewShowOnStartCheckService](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/whatsNew/src/com/intellij/platform/whatsNew/WhatsNewShowOnStartCheckService.kt)
startup registration is omitted. This removes the unsolicited upstream release
tab while preserving the Help action, native onboarding and feature tours.
Routing the manual What's New action to our own release notes remains open.

Controls: 11 local-product tests pass, covering exact framework omissions,
embedded XML, untouched Python/test configuration types, retained native tours,
Git authentication/feature discovery and numeric-promotion inlay hints, plus
source-SDK/symlink ownership. The original pinned cached/JAR descriptors were
also transformed in memory; all targeted framework/migration registrations were
absent afterward. The compact local control is
`.tools/parity-audit/promo-registration-control.json`. Updated product build and
native checks must run after these descriptor edits.

## What is actually available

REA `inspect_plist` parsed both `Resources/product-info.json` files. Reference
evidence: `ev_cf34583d0a53c7c26890d2af069c6a2936c036b5beb56a6820ead7b40ec45c3d`;
OSS evidence: `ev_070f714ee2eae0cbea08e742db5f9a7342748316bd700c294133868bccda3183`.
The selected `source_path`/artifact-path locations identify each JSON; the REA
session's active subject was the reference Info.plist, not the JSON's hash.
Metadata declares 98 bundled IDs in the installed reference and 31 in the
unmodified OSS input. Presence is static inventory, not executed behavior or a
redistribution entitlement.

| Area | Installed reference declares | Pinned OSS input | Independent route |
| --- | --- | --- | --- |
| Python language, interpreter, Run/Test/Debug | `PythonCore` plus `Pythonid` | `PythonCore`, native PSI/debugger/test runners/SDK wizard | Reuse the OSS integrations already shipped. |
| Django | `com.intellij.python.django`, `Pythonid` | Promotion placeholders; no real Django plugin | Own project generator, real run configuration and Django test orchestration. |
| Flask/FastAPI | Professional Python integration | Non-runnable configuration placeholders | Own native configuration backed by the existing Python runner/debugger. |
| HTTP client | `com.jetbrains.restClient` | No HTTP-client plugin (`org.jetbrains.plugins.rest` is reStructuredText) | Extract opengoland's independent JVM HTTP implementation. |
| Jupyter/notebooks | `com.intellij.notebooks.core`, `intellij.jupyter`, scientific Python alias | No corresponding bundled plugin/alias | Native cell editor plus independent Jupyter kernel bridge. |
| Database tools/SQL | `com.intellij.database`, database/SQL aliases and dialect modules | No DatabaseTools plugin or database/SQL aliases | Own native explorer/query UI with independent drivers and SQL support. |
| Web tooling | JavaScript, debugger, HTML/CSS and framework plugins | Python plus base XML/platform components | Separate language/template/web tooling implementation; Python runtime launch alone does not satisfy this area. |

The complete pinned Python source subtree was inventoried (35,607 entries,
untruncated). The separately retrieved plugins subtree was truncated and is not
used to claim that every unbundled feature lacks public source anywhere. No
proprietary implementation was copied or decompiled for this proposal.

## Small independent Python integration

Use one product-owned plugin depending on `com.intellij.modules.platform` and
`PythonCore`. Compile against the same 261 SDK. The newer Python wizard APIs are
version-specific: their presence does not promise cross-version compatibility.

* Templates: the pinned
  [PyV3ProjectBaseGenerator](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/newProjectWizard/PyV3ProjectBaseGenerator.kt)
  explicitly supports extension through `DirectoryProjectGenerator`. It creates
  the selected SDK/venv before invoking `PyV3ProjectTypeSpecificSettings` and
  runs generation with background progress/cancellation. Use independent
  Django/Flask/FastAPI templates and package requirements; preserve existing
  interpreter and uv/Poetry/Hatch choices. The real Empty Project generator is
  retained.
* Runtime: own `ConfigurationType`/factory/settings editors can create genuine
  [PythonRunConfiguration](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/run/PythonRunConfiguration.java)
  configurations with selected module SDK, working directory, environment,
  script/module mode and arguments. The existing
  [PyDebugRunner](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/debugger/PyDebugRunner.java)
  accepts Python run profiles unless they explicitly deny debugging. Use new
  product-owned IDs; do not fake `Pythonid` or inherit the locked types.
* Django: run `manage.py runserver`, manage commands and shell with
  `DJANGO_SETTINGS_MODULE`; tests need actual Django `DiscoverRunner` lifecycle
  and native test events, not a renamed generic unittest command. A
  single-process debug mode can use `--noreload`; reloader child ownership,
  multiprocess debugging, database setup/teardown, settings navigation, ORM
  inference, templates and Django-specific inspections remain separate gates.
* Flask: module `flask --app <target> run` with explicit host/port/env; FastAPI:
  module `uvicorn <module>:<app>`. Verify server readiness, HTTP responses,
  breakpoint/step/locals, Stop and restart using disposable local fixtures.
  Reloaders, factories, routers/endpoints, remote SDKs and framework-aware
  completion are not covered merely by starting a server.

## Reuse opportunities and larger gaps

**HTTP is the smallest reusable next slice.** Read-only audit of opengoland
tracked HEAD `3b32dc53df49388528203fa9b600b93ea69b8368` found nine `http/*.kt`
files and four `lang/HttpRequest*.kt` files, with no Go engine, LSP4IJ or Terminal
code dependencies. `ServiceViewContributor`, `RunContentExecutor`, `DataSink`
and the required Gson APIs exist in the pinned PyCharm SDK; compilation there
still needs verification. Extract as `dev.openpycharm.http` with neutral
package/action/language/service identifiers and explicit bundled-plugin loading.
Reuse the sibling's 72 HTTP tests, four language/native tests and JDK HttpServer
fixtures. Keep its source attribution and runtime evidence boundaries.

That code already implements unsaved request snapshots, file variables,
sequential batches, per-item errors, Services responses, JSON formatting,
headers, cancellation and exact binary saves. Environment files, scripts and
assertions, dynamic variables, response references, multipart/file bodies,
OAuth, credential storage, durable history, cURL import, WebSocket/gRPC and IDE
proxy integration remain open; this is not full HTTP Client compatibility.

**Notebooks require an actual subsystem.** A first independent editor can use
`FileEditorProvider`, Python-aware native editors and a cell/output model that
round-trips nbformat JSON, with a versioned sidecar speaking to
`jupyter_client`/`ipykernel`. It must own kernel processes and execution IDs,
handle cancellation/restart and bound outputs. Completion across cells,
debugging, rich MIME output, trust, remote authentication, diff/merge and data
viewers are material additional work. A JSON editor or launching Jupyter in a
browser is not notebook parity.

**Database tools have reusable domain logic, not a reusable IDE UI.** The local
OpenNavicat repository is MIT-licensed Python/Qt. `opennavicat/database.py`
contains UI-independent sessions/results, seven driver families, owner-thread
rules and cancellation; `schema.py`, `compare.py`, `transfer.py` and `transport.py`
provide additional independently written domain behavior and fixtures. Its Qt
widgets must not be embedded as an IntelliJ workbench replacement. A native
`ToolWindowFactory`/tree/query editor/result grid can use JDBC plus pinned
drivers, or a private owned Python backend extracted without Qt. Neither route
currently supplies SQL PSI/dialects, schema-aware completion, explain plans,
transactions, data editing conflicts, notebooks/ORM linkage or complete
database acceptance. Preserve database credentials via native credential storage
and test only disposable databases. Do not import real saved connections to
populate a demo.

Prioritize framework Run/Debug and HTTP in independently reviewable slices,
then notebook and database systems. Each needs real reference observations and
cross-platform acceptance; this order does not narrow the full goal.
