# Disposable SQLite example

Create a **new** fixture file from the repository root with Python 3.10+:

```sh
python - <<'PY'
from pathlib import Path
import sqlite3
path = Path('build/database-demo/inventory.sqlite')
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists():
    raise SystemExit('Choose a new fixture file; existing databases are never overwritten')
with sqlite3.connect(path) as connection:
    connection.executescript(Path('fixtures/database/inventory.sql').read_text())
print(path.resolve())
PY
```

In the native **Database** tool window, add SQLite and paste that absolute file
path. Connect, refresh tables, select `products`, and choose **Select rows**.
Review the generated SQL and run it. To try transactions, choose **Begin
transaction**, run `UPDATE products SET quantity = quantity - 1 WHERE sku =
'PY-001';`, then choose **Rollback** and query again.

This fixture uses no network service or credentials. Never point acceptance
checks at a production database. Actual native desktop evidence for this plugin
has not yet been captured.
