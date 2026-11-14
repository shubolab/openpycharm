# Actual-platform Database completion gate

This is a test-only native plugin and an explicit launcher. Preparation defaults
to compilation only; it does not start an IDE. It binds to the selected product's
actual receipted Database JAR, not a separately rebuilt or replacement plugin.
The existing application, project and profile are not modified.

The passive first/last completion observers add no candidates, create no Lookup,
and inject no cache. They record actual callback order, parameters/caret/offsets,
PSI language and file type, project/editor/document identities, actual service
and immutable metadata snapshot, contributor list and native prefix. Collection
is restricted to the owned test editors and bounded per case; report I/O runs
on the worker. Probe exceptions are recorded rather than changing the provider
pipeline; normal platform cancellation is preserved.

The probe creates a new owned project and SQLite fixture, uses the production
profile service and actual **Connect** button, then invokes the actual
`CodeCompletion` action through the real editor component's data context. It
checks a native `LookupImpl` popup and selects the typed production item using
`LookupImpl.finishLookup`, rather than patching completed text directly. Six
required table/alias/quoted cases cover both the physical SQL editor and the
embedded PSI console. One direct-handler case is diagnostic only and cannot
make an otherwise failed action gate pass. Keyboard/menu interaction is not
claimed by this API probe.

Root's initial native finding was no Lookup/insert after real Connect/Refresh.
Pinned owning-source and actual SDK-bytecode inspection confirm that completion
copy `START_OFFSET` and the original editor caret are distinct coordinates. The
production provider changes that start and later analyzes original document
text with `parameters.getOffset`; this is a concrete coordinate-contract risk.
It does not yet prove the entire no-Lookup cause. Syntax highlighting also does
not prove the PSI language selected for completion, so the probe records both.
See [owning-source-audit.json](owning-source-audit.json) for primary URLs, exact
SDK class hashes and observed/inferred boundaries.

Compile/preparation only (new workspace required):

```sh
python3.13 scripts/database_completion_probe.py \
  --sdk /Users/wangshubo/develop/openpycharm/.tools/platform/pycharm-2026.1.4-macos-arm64/PyCharm.app \
  --app /Users/wangshubo/develop/openpycharm/build/dev3-savefix/OpenPyCharm.app \
  --workspace .tools/prepared-completion-new
```

Only root may run this after its exclusive desktop phase is ready; choose
another new workspace instead of reusing an existing IDE profile:

```sh
python3.13 scripts/database_completion_probe.py \
  --sdk /Users/wangshubo/develop/openpycharm/.tools/platform/pycharm-2026.1.4-macos-arm64/PyCharm.app \
  --app /Users/wangshubo/develop/openpycharm/build/dev3-savefix/OpenPyCharm.app \
  --workspace .tools/native-completion-run-new --run --timeout 240
```

The ordinary project-trust flow is preserved. The report and launch/timeout
evidence remain under the new workspace. Cleanup targets only the process/job
created by that invocation. No existing project, native session or user database
is selected. Profile creation through the public service is setup, not new-profile
dialog acceptance; Connect and completion use their actual production UI/API
paths.

Observed here: authenticated SDK compilation and real IntelliJ/JDK archive-reader
comparison, plus evidence-validation controls that reject missing console cases,
handler-only results, injected candidates/cache, wrong JAR/invocation, fake Lookup
classes, mismatched inserted text and unshown popups. Unknown: actual callback
values, native Lookup/insert, source-vs-console behavior and Windows runtime.
No native application was launched during preparation, no native completion
success is claimed, and no author fix is bundled with this probe.
