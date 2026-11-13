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

Build against the read-only authenticated SDK with the already cached pinned
Kotlin compiler. Python 3.10+ is required; no Gradle/compiler download occurs:

```sh
python3 scripts/build_http_plugin.py --sdk /absolute/path/to/PyCharm.app --test
```

The result is `build/http-client/plugin`, with `build.json` and
`protocol-tests.json`. A relocated compiler cache can be selected with
`--compiler-cache`. Missing or altered compiler artifacts fail closed; the
compiler pin lists the required filenames and hashes.

For an isolated development launch, add this plugin directory to `plugin.path`
using an owned temporary VM-options file. Multiple plugin paths are comma
separated. Do not modify the reference installation or its configuration.

The loopback tests send real HTTP requests and check wire bytes, headers/error
statuses, redirect/cookie policy, streaming limits, socket cancellation and the
whole-body deadline. Compilation and protocol checks do not establish that the
native toolbar, Services selection, stop controls and save dialog have passed
desktop acceptance in OpenPyCharm. Those checks remain separate release gates.

For desktop acceptance, start `python3 plugins/http-client/examples/server.py`,
open `examples/demo.http` in the native IDE, run the current request and Run All,
inspect the JSON/binary Services results and save the binary response. Use
`examples/stop.http` to check cancellation against the real streaming server.
The fixture listens only on loopback and makes no external service requests.
`scripts/prepare_http_acceptance.py --app /absolute/path/to/OpenPyCharm.app`
prepares a disposable copy and isolated profile and prints exact argv/environment
without launching either process. Its native command always supplies that
explicit project directory; no home-directory welcome project is requested.
