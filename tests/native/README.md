# Native Python semantic probe

HTTP mode checks the packaged `dev.openpycharm.http` plugin: add `--mode http
--project /owned/copied/http-fixture --test-file
/owned/copied/http-fixture/demo.http`. Its application listener checks the actual
bundled descriptor/version/JAR path and digest, file type, in-memory PSI and
highlighter, three action registrations and Services contributor. It schedules
all work off the EDT and uses the default project; the ordinary Trust Project
dialog can remain unanswered. It never executes requests/actions, grants trust
or verifies desktop Run/Stop/Save behavior. CI retains this evidence separately
from startup and real user workflow acceptance. Repeat with the same isolated
profile against a relocated app to test home-relative plugin discovery.

The Java plugin reads the running native IDE's project/module roots, Python SDK,
PSI classes and resolved superclasses, filename indexes, test detectors and light
run-configuration candidates. It never saves or executes a run configuration.
Ordinary resolution requests can populate IDE caches.

Build the probe against the authenticated SDK and read its complete JAR with the
actual application's IntelliJ archive reader, without launching a window:

```sh
python3 scripts/native_probe.py --app build/product/OpenPyCharm.app --build-only
```

The archive helper uses the actual product JVM and exact copies of its two
reader libraries in an owned temporary directory, with digests verified before
and after copying and recorded in the report. This avoids the standalone JDK
source launcher's classpath limitation at non-BMP application paths; it does
not modify the app or establish that its native launcher supports such paths.

Run against a disposable Python fixture with an isolated profile:

```sh
python3 scripts/native_probe.py --app build/product/OpenPyCharm.app \
  --profile .state/native-python-check --project fixtures/hello-python \
  --report .state/native-python-check/report.json
```

On Windows, pass the installed or assembled `OpenPyCharm` directory to `--app`.
The driver uses the real native launcher and actual product JVM on both systems.
All temporary plugin and VM-options files stay outside the application. It stops
only its native process/session (or Windows job) and records the owned PID and
exit status. Windows launch remains suspended until assigned to the owned job.

An existing profile's `idea.properties` is read without modification and must
already isolate its four configuration/cache/plugin/log paths. A new profile may
require normal **Trust Project** confirmation and Python SDK selection for Python mode. This
probe does not grant trust, change an SDK or create `.idea` project metadata;
prepare those using the ordinary native IDE before a noninteractive regression
run. The default fixture test is `tests/test_calculator.py`; use `--test-file` for
another existing unittest/pytest file.

The Python assessment requires smart-mode PSI evidence, a valid Python SDK, a test file
inside project content and a native Python test configuration candidate. It does
not establish actual Run/Test/Debug execution, context-menu behavior or full 1:1
acceptance. `--build-only` proves archive readability; actual plugin startup is
proved only by an invocation-matched report from the launched IDE.
