# Database source increment for the next dev.3 candidate

Scope: an independent native JDBC Database tool window and SQL editor/PSI layer.
No installed reference product was modified, no IDE was launched during these
checks, and no production/user database or network database service was used.

Observed on macOS ARM64 using the authenticated PyCharm OSS 2026.1.4 SDK
(`PC-261.26222.68`):

- Native Java compilation and real IntelliJ archive-reader verification passed.
- 80 real-JVM integration checks passed against owned temporary SQLite files.
  They cover query results/NULL/Unicode/binary previews, update counts, bounded
  rows/cells, table/column metadata, commit/rollback/disconnect rollback,
  cancellation, a real 15-second CPU-query deadline, closure/reopening, SQL
  statement boundaries, native XML serialization, lexer incremental restart,
  and canonical-project/endpoint/user/profile/TLS credential scope isolation.
- The complete repository suite passed 98 tests after packaging integration;
  the existing Python example passed nine tests. The new SQL fixture replay is
  included in the repository suite.
- Explicit JDBC cache provisioning authenticated all four artifacts. Binaries
  are unmodified and SHA-256 pinned; matching MariaDB LGPL source is included.
- Packaging/installer/startup controls verify every declared plugin payload,
  including the separate drivers and matching source. Unit controls reject
  driver mutation, missing source, extra JARs, path traversal and symlinks.

The exact plugin inputs, driver pins, JAR digest and SQLite test-source digest
are in [backend-verification.json](backend-verification.json). The tested native
plugin JAR is `0d92b245578c41198b5d0ae2e163ab4c308cc47123640a15259b9b924961655f`.

Reproduction requires Python 3.10+:

```sh
python scripts/provision_database_drivers.py
python scripts/build_database_plugin.py --sdk .tools/platform/pycharm-2026.1.4-macos-arm64/PyCharm.app --version 0.1.0-dev.3 --test
python -m unittest discover -s tests -v
(cd fixtures/hello-python && python -m unittest discover -s tests -v)
```

Inferred: the bundled PostgreSQL/MariaDB drivers should connect through their
documented JDBC APIs. They load and recognize generated PostgreSQL/MySQL URLs,
and TLS verification is enabled by default; no server was contacted.

Unknown and required before delivering dev.3: actual native tool-window and
SQL-file registration/interaction, PasswordSafe persistence with the configured
provider, real PostgreSQL/MySQL TLS/authentication/cancellation, Windows native
runtime, a complete assembled product/installers, new installed-version native
captures/GIF/manifest, checksums and GitHub Release evidence. No claim of full
1:1 parity or a released/installed dev.3 is made. The root agent retains the
exclusive desktop session for the current dev.2 release.
