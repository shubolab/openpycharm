# OpenPyCharm native HTTP client

This independent plugin adapts the repository owner's existing opengoland HTTP
implementation. It uses the native IntelliJ editor, Run process controls and
Services response tree. Source provenance is retained in `upstream.json` and
`NOTICE`; no Go engine, LSP integration or browser surface is required.

| Workflow | Implemented scope |
| --- | --- |
| Edit `.http` | Native syntax highlighting, comments and request-line gutter actions |
| Execute | Current caret request or every `###` block sequentially; editor toolbar and context menu |
| Syntax | Absolute HTTP(S) URLs; GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS; headers and UTF-8 text bodies |
| Variables | File declarations `@name = value`, including forward references, and `{{name}}` expansion; duplicate references/cycles fail explicitly |
| Results | Native Services batches and individual requests; status, timing, headers, safe read-only response editors and bounded JSON formatting |
| Controls | Run Again, Stop All, native Run Stop, cancellation on project disposal; original raw response save through the native save dialog |
| Transport | 30-second whole-exchange deadline; redirects displayed without automatic following; standard JVM TLS validation; no shared cookies/authentication state |
| Bounds | 2M UTF-16 units per editor snapshot; 1 MiB UTF-8 request body; 200 headers / 64 KiB total headers; 1 MiB streamed response; 16 MiB project response cache; 20 retained finished batches |
| Not yet implemented | Environment JSON files, OS environment lookup, dynamic variables, request/response JavaScript, file uploads/multipart construction, cookie jar, OAuth/helper authentication, automatic redirects, WebSocket/gRPC, IDE HTTP history |

An explicit `Authorization` or `Cookie` header can be supplied by the developer.
URL credentials and executable/file-body syntax are rejected. HTML responses
remain plain native-editor text; they are never evaluated or loaded in a WebView.
`Content-Length` and `Transfer-Encoding` belong to the transport and cannot be
set manually, regardless of letter case.

Python 3.10+ is required. Provision the seven pinned compiler artifacts explicitly
from Maven Central into this checkout's `.tools/kotlin`, then build offline
against the read-only authenticated SDK. No Gradle installation is used:

```sh
python3 scripts/provision_http_compiler.py
python3 scripts/build_http_plugin.py --sdk /absolute/path/to/PyCharm.app --test
```

The result is `build/http-client/plugin`, with `build.json` and
`protocol-tests.json`. A relocated compiler cache can be selected with
`--compiler-cache`. Missing or altered compiler artifacts fail closed; the
compiler pin lists primary download URLs, exact sizes and hashes. Interrupted,
oversized or altered responses are never promoted into the compiler cache.

`scripts/package.py` includes the compiled JAR under
`Contents/third-party-plugins/openpycharm-http/lib` on macOS, or
`third-party-plugins/openpycharm-http/lib` in the Windows product root. The pinned
platform discovers this home-relative directory directly, including after app
relocation; production packaging does not set an absolute `plugin.path`. The
product manifest binds the plugin version, JAR digest, build identity and source
inventory before helper-directory sealing and macOS signing.

CI provisions the cache and runs `--test` with the target SDK's native JVM on
both operating systems. A Mac-host classpath check against the Windows SDK may
use `--host-sdk /absolute/path/to/macOS/PyCharm.app`; its report explicitly marks
`nativeTargetRuntime: false` and does not establish Windows runtime acceptance.

For an isolated standalone development launch, add this plugin directory to `plugin.path`
using an owned temporary VM-options file. Multiple plugin paths are comma
separated. Do not modify the reference installation or its configuration.

The loopback tests send real HTTP requests and check wire bytes, headers/error
statuses, redirect/cookie policy, streaming limits, socket cancellation and the
whole-body deadline. Compilation and protocol checks do not establish that the
native toolbar, Services selection, stop controls and save dialog have passed
desktop acceptance in OpenPyCharm. Those checks remain separate release gates.
The headless SDK controls also restart the HTTP lexer at every token and restore
saved lexer positions; these verify the incremental-lexer contract rather than
claiming a desktop editing session.

For desktop acceptance, start `python3 plugins/http-client/examples/server.py`,
open `examples/demo.http` in the native IDE, run the current request and Run All,
inspect the JSON/binary Services results and save the binary response. Use
`examples/stop.http` to check cancellation against the real streaming server.
The fixture listens only on loopback and makes no external service requests.
`scripts/prepare_http_acceptance.py --app /absolute/path/to/OpenPyCharm.app`
prepares a disposable copy and isolated profile and prints exact argv/environment
without launching either process. Its native command always supplies that
explicit project directory; no home-directory welcome project is requested.

For read-only native registration evidence, use `scripts/native_probe.py --mode
http --app ... --sdk ... --project /owned/copied/http-fixture --test-file
/owned/copied/http-fixture/demo.http --profile /owned/isolated/profile --report
/owned/evidence.json`. The probe checks the actual bundled descriptor/version/
JAR path and digest, native file type/in-memory PSI/highlighter, three registered
actions and Services contributor. Its application listener uses the default
project for in-memory HTTP PSI and does not wait for project trust. It does not
invoke those actions, inspect the untrusted project's execution settings or bypass normal
project trust. Repeat against a relocated copy to verify home-relative loading.
