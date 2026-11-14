# Standalone JVM lease bridge

This worker-only Java prototype owns the IPv4 loopback listener and nonce used
by the existing Go guardian. It is not an IntelliJ service, ProcessHandler,
plugin, bundled runtime or published IDE capability.

`GuardianLease.open()` creates a new numeric-loopback listener and 32-byte
SecureRandom nonce. `command()` returns literal helper arguments. A worker
starts the helper, then calls `accept()` with a 1–5000 ms total deadline. Only
one peer is accepted; greeting bytes are bounded and compared exactly before
`OK\n`. Authentication failure closes the listener and connection. `close()`
closes the independent lease channel, including while accept is waiting.
Open, accept and close explicitly reject Swing EDT calls. Metadata getters and
argument construction perform no filesystem/process work.

Observed on macOS 27.2 arm64 with the authenticated PC261 JBR 25.0.3, compiled
with `--release 21`: five EDT/nonce/timeout/accept-close boundary controls passed.
The real authenticated Go helper/tiny-child fixtures also passed three chains:
normal lease close removed root/child/grandchild; abrupt death of only the owned
JVM removed that tree; an infinite-output fixture remained undrained until the
JVM had exited and owned targets were gone. The final pipe held 65,536 bytes.
An unrelated owned sentinel survived each chain. This is a real JBR JVM stand-in,
not the IDE. No Node or IDE was started; network traffic was loopback only.

The first harness used `communicate()` immediately after requesting close,
which drained stdout too early to establish that boundary. The accepted final
harness waits for JVM exit and owned cleanup before draining; only its receipt
is committed. The earlier bulk generated stdout was discarded.

Inferred: a future IDE adapter can supply the same lease protocol without
proxying LSP stdin/stdout. Unknown: actual IntelliJ Disposable/ProcessHandler/LSP
integration, asynchronous EDT disposal scheduling, Windows/Linux JVM bridge
execution, exhaustive races, stolen-nonce peers, or process-group escape.
`close()` itself is worker-only; calling it from an EDT callback is not an
implemented integration strategy. A caller must close the lease if process
creation fails and must authenticate the runtime executable separately.

Reproduce with an existing authenticated SDK and the existing Go proof directory:

```sh
python3.10 native/lsp-guardian/jvm/verify_jvm.py \
  --sdk /absolute/authenticated/PC261/PyCharm.app \
  --go-proof /absolute/existing/guardian-results/exact-snapshot-20261114-final \
  --output .tools/guardian-jvm-proof/new-run
```

The driver authenticates Go fixture bytes against their saved receipt and uses
the platform builder's full SDK authentication before compiling/executing Java.
It creates only owned fixture processes and never signals a PID read from a file.

中文：这是独立 JVM 租约桥原型，未接入 IntelliJ、未打包进产品。真实 JBR JVM 与已有
Go helper 的正常关闭、仅终止自有 JVM、stdout 不读取时的清理链路，以及五项线程/
握手边界控制通过。最终 stdout 测试先等 JVM 和目标进程退出，再读取 64 KiB 管道
数据；没有把首版过早排空管道的结果算作该边界通过。Windows/Linux JVM 桥、实际
IDE 生命周期接线和完整异常清理仍待验收，不能据此称产品已实现该功能。
