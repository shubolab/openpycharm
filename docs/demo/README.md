# Native workflow demo

![OpenPyCharm 0.1.0-dev.3 native workflows](v0.1.0-dev.3/openpycharm-native.gif)

Recorded actual installed **0.1.0-dev.3**, based on **PC-261.26222.68 (2026.1.4)**,
**macOS 27.2 arm64**, Python **3.14.0**, on **2026-11-14**.

Six real native screenshots show Python Run, unittest (9 methods/20 items), Debug
with `quote.total=Decimal('36.04')`, actual Notebook PNG/DataFrame outputs, and
SQLite query results with accepted table/alias completion. This is an animated
sequence of captured states. No mock UI is runtime evidence.

The [versioned capture manifest](v0.1.0-dev.3/capture.json) binds all six images,
installer/source/CI, dimensions, durations and the GIF hash.
The [release verification](../verification/2026-11-14-dev3-release.md) records the
exact installed tree, strict signature, workflows, diagnostics and limits.
Windows physical desktop is not inferred from Mac captures or native CI.

Every publishable release updates the README GIF from that installed version and
retains the actual version, OS, workflow and capture manifest. Rebuild this sequence:

```sh
python3 scripts/make-demo.py --directory docs/demo/v0.1.0-dev.3
```

The root GIF/manifest/capture files mirror the current version for the default
recipe. [dev.2](v0.1.0-dev.2/capture.json) and [dev.1](v0.1.0-dev.1/README.md)
remain versioned history.
