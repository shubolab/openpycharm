# Independent SQL completion increment

Scope: native table, schema and column suggestions from the already-connected
project database. No IDE, CUA, network database server or user database was used
for these checks. This source increment is separate from the responsive-layout
fix and does not claim native popup/insert acceptance or a delivered release.

The implementation registers `SqlCompletionContributor` for `OpenPyCharmSQL`.
Connect and **Refresh tables** collect an immutable metadata snapshot on the
existing owned JDBC worker. Completion reads a project-memory key and that
snapshot; it never calls the service container, JDBC, PasswordSafe, filesystem
or network, and never schedules a refresh. The console now uses the public
`LanguageTextField` in-memory PSI document path so the native completion action
can identify its SQL language.

Snapshots are bounded to 128 tables, 64 columns per table and 4096 columns in
total. Collection checks a three-second budget between driver calls and rows;
individual calls still depend on driver/network timeouts. Completion reads at
most 128 KiB/12000 tokens and returns at most 200 candidates. Snapshots expire
after five minutes and remain empty until another explicit connect/refresh.

Connection changes, disconnect and common DDL invalidate the cache. Generation
tokens reject a late refresh from an older connection or refresh operation.
Commit/rollback also invalidates metadata captured after transaction-local DDL,
so a rolled-back table cannot remain in suggestions. Lookup preparation and
insertion recheck the snapshot identity; stale insertions restore the original
identifier text. Existing owned-connection, cancellation-ticket and query
deadline paths remain in place.

Observed:

- Compilation against authenticated OSS PyCharm 2026.1.4 / PC-261.26222.68 and
  actual IntelliJ archive-reader verification passed.
- The existing 80 real SQLite/JVM controls passed, including transactions,
  explicit cancellation, stale cancellation tickets and the 15-second deadline.
- 75 completion assertions passed across actual disposable SQLite metadata,
  executable completed SQL, native prefix matching, quoted/Unicode identifiers,
  aliases, duplicate names, context bounds, disconnect/reconnect, expiration,
  late refresh rejection, DDL rollback and project-memory-only lookup on EDT.
  Schema-qualified namespace controls use immutable synthetic namespaces over
  real SQLite column metadata; no PostgreSQL/MySQL server was contacted.
- Repository discovery passed 112 tests with six existing notebook-kernel
  dependency-gated skips; all database checks ran. The Python example passed
  nine tests from its fixture directory.

Exact source/driver/JAR and test-source digests are in
[verification.json](verification.json).

For root's native UI gate, use only an owned disposable database:

1. Connect it once, then invoke the IDE's normal **Basic Completion** action in
   both a physical `.sql` file and the embedded Database SQL console.
2. Complete `FROM pro`, then `SELECT p.na FROM products p`; inspect the popup
   and selected insertion. Identifiers should be quoted without duplicate dots.
3. Add a disposable table/column containing a space, Unicode or embedded quote,
   click **Refresh tables**, and complete inside an unfinished quoted name.
   Accepting a candidate must replace its remaining suffix/closing quote once.
4. Try a joined duplicate `id` column: proposals must distinguish qualified
   aliases. Strings/comments must not receive database candidates.
5. Disconnect and invoke completion again. Connect another disposable endpoint:
   the previous endpoint's tables must not appear.
6. Create a table inside a managed transaction, refresh, roll back, then refresh
   again. The rolled-back table must disappear. Existing query cancellation and
   close/rollback controls remain separate acceptance checks.

Unknown: native extension registration/popup/keyboard/quote replacement in the
real IDE, physical display behavior, Windows runtime, server metadata latency,
and vendor-specific SQL semantics. CTEs, subqueries, full dialect name
resolution, semantic inspections and completion from unconnected databases
are intentionally outside this bounded implementation. External schema
changes require explicit Refresh tables.
