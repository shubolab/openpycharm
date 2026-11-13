# Native Database plugin

Independent Apache-2.0 implementation using the pinned OSS IntelliJ Platform,
native editors/PSI, Swing and JDBC. It contains no proprietary Database Tools
implementation or WebView.

The **Database** tool window supports manually added SQLite, PostgreSQL and
MySQL data sources (MySQL uses MariaDB Connector/J), connect/disconnect,
table/view and column metadata, quoted SELECT generation, SQL result previews,
affected-row counts, query cancellation and explicit transactions. The SQL
console uses a native IntelliJ editor. `.sql` files have independent token/PSI
support and an editor popup **Run SQL Statement** action. Execution uses the
selection, or the statement containing the caret; scripts are not run implicitly.
SQL with ambiguous backslash quoting is rejected; use standard doubled quotes.
Use the transaction buttons for Begin/Commit/Rollback. Direct transaction and
session-control commands are rejected to keep JDBC and the UI state consistent.
Normal database-specific implicit-commit rules still apply to DDL.

Profiles persist in the isolated project's workspace file. Passwords are only
stored via IntelliJ PasswordSafe, whose memory/keychain policy remains under
the user's control. Keys include canonical project path, generated endpoint,
user, profile ID and TLS mode. Editing these values requires credentials for
the new scope. Project opening never connects or runs a query. Unknown driver
names and metadata survive state round trips and remain disconnected.

Connections are serialized on an owned background worker. Query cancellation
uses a separate worker, with a 15-second cancellation deadline, 5-second connect
timeout, and network read timeout. SQLite native busy timeout is bounded too.
Previews are capped at 500 rows, 100 columns, 4096 characters per cell and 2 MiB
of displayed character data; binary values show at most 64 bytes. JDBC drivers
may buffer server payloads internally, so these are presentation limits rather
than a guarantee on total driver allocation or database server execution time.
Cancel requests depend on the driver's protocol support. Pending manual
transactions are rolled back when disconnecting or closing the project.

PostgreSQL/MySQL connections verify TLS certificates and hostnames by default.
The profile dialog permits an explicit opt-out for a local test server. There
are no arbitrary JDBC URLs/properties, embedded credentials, local-infile or
multi-query options. Separate driver JARs, licenses and matching MariaDB source
are distributed according to [NOTICE](NOTICE) and [drivers.lock.json](drivers.lock.json).

Build with Python 3.10+ and the authenticated SDK. Provisioning is a separate
explicit action; the builder never downloads dependencies:

```sh
python scripts/provision_database_drivers.py
python scripts/build_database_plugin.py --sdk .tools/platform/pycharm-2026.1.4-macos-arm64/PyCharm.app --version 0.1.0-dev.3 --test
python -m unittest discover -s tests -v
```

The builder reports a plugin directory containing `lib/database.jar`, the three
unmodified JDBC JARs, and `legal/mariadb-java-client-3.5.11-sources.jar`. Keep the
entire directory together when packaging. [Disposable fixture](../../fixtures/database/README.md).

Observed: compilation against the authenticated macOS ARM64 SDK, real IntelliJ
archive-reader verification, real temporary SQLite execution/transactions/
metadata/cancel/deadline/close checks, native state serialization, credential
scope isolation, SQL lexer restart checks, and offline cache controls.

Inferred from public driver APIs: PostgreSQL/MySQL connectivity. The bundled
drivers load and recognize generated URLs; no server was contacted by these
checks. Unknown: native desktop interaction/registration, real server TLS/auth,
network cancellation, Windows runtime, large/complex schemas and full 1:1
compatibility. Schema completion, vendor semantic inspections, migrations,
SSH tunnels, editable result cells and export are not implemented in this slice.
No release, installer or README GIF is claimed for this source-only increment.
