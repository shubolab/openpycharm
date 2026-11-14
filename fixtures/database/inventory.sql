-- Disposable example only. Apply to a new owned SQLite file.
CREATE TABLE products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0)
);
INSERT INTO products VALUES
    ('PY-001', 'Python workbook', 12, 3900),
    ('PY-002', '数据分析练习册', 8, 4900),
    ('PY-003', 'Native IDE notebook', 20, 1500);

-- In the editor, place the caret on one statement and choose Run SQL Statement.
SELECT sku, name, quantity, price_cents / 100.0 AS price
FROM products ORDER BY sku;
