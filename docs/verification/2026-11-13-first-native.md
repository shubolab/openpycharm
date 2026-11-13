# First native product verification

Product candidate: OpenPyCharm `0.1.0-dev.1`; upstream PC `261.26222.68`
(2026.1.4). Host: macOS Apple silicon. This record is a development checkpoint,
not full parity acceptance or a published release.

The [published preview record](2026-11-14-preview-release.md) supersedes this
checkpoint. Older generated binaries were retired after publication; their
manifests, hashes and logs were retained locally. See the exact
[retention ledger](artifact-retention-20261114.json) before interpreting the
historical build paths below as existing binaries.

## Passed observations

- Official OSS archive authenticated; PC identity, PythonCore present, Pythonid
  absent, complete cached SDK tree revalidated.
- 20 repository boundary/regression controls passed. Fixture command-line run
  and 9 unittest methods passed.
- Independent app ad-hoc signature verified, original icon/name shown, native
  project safety prompt and workbench opened without an IDE account.
- Isolated launcher profile appeared in actual JVM arguments and config/log
  paths. Native Python, Git and Terminal plugins loaded.
- Baseline desktop created a Python 3.14.0 venv using the native interpreter
  dialog; main.py printed the expected `34.00 / 2.04 / 36.04` values and exited0.
- Baseline native unittest runner used `_jb_unittest_runner.py`; 9 test methods
  plus subtests appeared as 20 passing items in the native test tree.
- Baseline Debug stopped at calculator.py:20, showed lines/self/subtotal, and
  evaluated `subtotal * self.tax_rate` as `Decimal('2.0400')`. Resume completed
  with the expected output and exit0.
- Final candidate includes the two source-replayed platform fixes and embedded
  promotion-descriptor fix; native main.py run passed again.
- A new isolated system-cache control on the same final candidate/Python SDK
  restored the native unittest tree: all 20 items (9 methods plus subtests)
  passed. Final-candidate Debug again stopped at calculator.py:20, evaluated
  `Decimal('2.0400')`, stepped to line21, and resumed to exit0. Its log contained
  no ERROR/SEVERE during these workflows; warnings remain recorded.
- macOS DMG image verified, mounted contents and copied app match the sealed
  product tree; drag-to-Applications link and signatures passed.
- Fresh isolated automated startup observation loaded Python/Git/Terminal,
  verified identity and paths, and had no ERROR/SEVERE in its bounded interval.
  It did not bypass project trust or prove project workflows.

DMG SHA-256:
`13e60240ba409d8b242d0f8c10d7e3c0f7f46489bc3cafc5773f4815082412e8`.
The candidate precedes the later runtime-smoke source addition; its build
manifest binds the source inputs it actually used. Release sealing must bind the
final source state separately.

## Open findings

- The longer baseline session logged a Python IdempotenceChecker error during
  the first SDK index: unittest.subTest returned cached empty resolution then a
  function. Index invalidation is a candidate explanation, not a proven cause.
- Moving from the baseline app path to the final path while reusing its system
  cache produced 9 type warnings and generic script execution for a test file.
  The log reported 1310 old typeshed paths in the project index filter. SDK
  paths, content root and test registrations were checked and retained. A fresh
  cache control recovered native detection, and a later diagnostic run on the
  original profile also resolved the TestCase and selected the native test
  producer. Root cause remains unknown; the original generic execution is
  preserved as a real failure rather than attributed solely to old filter paths.
- Upstream Configuration Script reports a service override warning. It has not
  been suppressed, and the experimental configuration feature is retained.
- Windows installer build/startup/native workflows and complete editor,
  refactoring, localization and broader parity remain open.

## Evidence locations

Compact source-repair records: `build/repair-smoke/report.json` and
`behavior.json`. Local-policy graph control: `.tools/local-product-verification.json`.
Installer evidence: `build/installers/provenance/0.1.0-dev.1-macos-arm64`.
Baseline/final relocation logs: `.state/development/log/idea.log`.
Bounded fresh-start receipt: `build/runtime-smoke-agent/startup.json`.
The [Run capture](../demo/run.png) is a real native screenshot of the final
candidate, not a mockup. The [README GIF](../demo/README.md) combines the real Run,
test-tree, breakpoint and Step Over captures with version/system/hash metadata.
