# LSP lifetime guardian prototype

This standalone helper is an engineering prototype. It is not registered in an
OpenPyCharm plugin, included in the IDE assembler, installed, or released.

The IDE adapter would own an IPv4 loopback listening socket and a random
32-byte nonce. The helper connects, sends `OPC-LSP-LEASE/1 <nonce>\n`, and waits
for `OK\n` before starting the absolute executable supplied after `--`. Closing
the accepted socket ends the lease. Unexpected lease data also cancels it.
The lease reader is independent of protocol stdin/stdout/stderr, so an unread
language-server pipe cannot prevent lease cancellation. Protocol streams are
inherited directly; the helper does not parse or copy LSP messages.

On macOS/Linux, an outer guardian starts a persistent anchor in a private
session. The anchor occupies its process-group identity until TERM and final
KILL have completed. Control-pipe EOF also starts cleanup when the outer helper
dies. On Windows, `CreateProcess` assigns the target atomically to a private
kill-on-close Job using `PROC_THREAD_ATTRIBUTE_JOB_LIST`; unsupported assignment
fails without a post-spawn fallback. Only duplicated standard-stream handles
are inherited.

Observed on macOS 27.2 arm64: Go unit tests, vet, race controls, and 10 owned
integration cases passed. Cases cover exact binary streams/arguments/status,
root/child/grandchild cleanup, natural launcher exit, abrupt helper death,
kernel death of an IDE stand-in, stdin/stdout backpressure, rejected/closed
handshakes, and unexpected lease data. An unrelated owned sentinel survives
every case. The test stand-in is a Python process, not the real IDE.

Windows amd64 helper, fixture and ABI test binaries cross-compile. **Windows
runtime, Job cleanup, actual IDE integration, and Linux runtime are unverified.**
The POSIX prototype covers descendants that remain in the private process
group. Deliberate process-group/session escape and killing the private anchor
itself are outside this evidence. General crash ownership must not be claimed
for the current frontend product from these standalone results.

## Reproduce offline

Use Python 3.11+ and an existing unmodified Go SDK, its pinned distribution
archive, and an existing module cache. The verifier authenticates the SDK's
exact file closure against the archive before running it, copies the pinned
`golang.org/x/sys v0.38.0` dependency to a private cache, disables downloads,
then writes logs, binaries and a receipt into a new owned directory:

```sh
python3.11 native/lsp-guardian/verify.py \
  --go-root /absolute/unmodified/go \
  --go-archive /absolute/go1.26.10.darwin-arm64.tar.gz \
  --go-archive-sha256 0b5183492292ada170f9b561a834863808dd02edba599e4ad0e89899330020b3 \
  --module-cache /absolute/existing/module-cache \
  --output .tools/guardian-results/new-run
```

The development cache and tool pins were reused read-only from OpenGoLand.
Go and x/sys BSD notices are retained in `licenses/`; Apache-2.0 applies to this
repository's helper and fixtures. `research/` records the pinned platform's
reflection-only API survey; it did not initialize classes or invoke native
Windows APIs.

中文：这是独立的进程生命周期原型，未接入 IDE，也不属于已发布功能。本机通过了
真实子进程、阻塞管道和异常父进程退出的限定测试；Windows 只做交叉编译，未执行。
下一步仍需实现实际 IDE 的租约适配、验证目标进程身份和错误处理，再做真实 macOS
和 Windows 生命周期验收。不能用本原型的通过代替完整前端或 1:1 验收。
