from __future__ import annotations

import asyncio
import sqlite3

from local_d1 import LocalD1
from migrations import apply_local_migrations


def test_local_migrations_are_idempotent(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001.sql").write_text(
        "CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL);",
        encoding="utf-8",
    )
    db_path = tmp_path / "db.sqlite3"

    assert apply_local_migrations(db_path, migrations) == ["0001.sql"]
    assert apply_local_migrations(db_path, migrations) == []

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT name FROM d1_migrations").fetchall() == [("0001.sql",)]


def test_local_d1_first_run_and_atomic_batch(tmp_path):
    db = LocalD1(tmp_path / "db.sqlite3")
    asyncio.run(db.prepare("CREATE TABLE x (id INTEGER PRIMARY KEY, value TEXT UNIQUE)").run())
    result = asyncio.run(db.prepare("INSERT INTO x(value) VALUES (?)").bind("one").run())
    assert result.success
    assert asyncio.run(db.prepare("SELECT value FROM x WHERE id = 1").first("value")) == "one"

    statements = [
        db.prepare("INSERT INTO x(value) VALUES (?)").bind("two"),
        db.prepare("INSERT INTO x(value) VALUES (?)").bind("three"),
    ]
    asyncio.run(db.batch(statements))
    assert asyncio.run(db.prepare("SELECT COUNT(*) AS count FROM x").first("count")) == 3

    failing = [
        db.prepare("INSERT INTO x(value) VALUES (?)").bind("four"),
        db.prepare("INSERT INTO x(value) VALUES (?)").bind("one"),
    ]
    try:
        asyncio.run(db.batch(failing))
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("batch should have failed")
    assert asyncio.run(db.prepare("SELECT COUNT(*) AS count FROM x").first("count")) == 3
