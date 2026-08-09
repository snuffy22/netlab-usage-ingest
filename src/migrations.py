from __future__ import annotations

import sqlite3
from pathlib import Path

from cloudflare_api import CloudflareAPI

TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS d1_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
""".strip()


def migration_files(directory: str | Path) -> list[Path]:
    root = Path(directory)
    files = sorted(path for path in root.glob("*.sql") if path.is_file())
    if not files:
        raise RuntimeError(f"no SQL migrations found in {root}")
    return files


def apply_local_migrations(database_path: str | Path, directory: str | Path) -> list[str]:
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(TRACKING_TABLE_SQL)
        applied = {
            row[0] for row in connection.execute("SELECT name FROM d1_migrations").fetchall()
        }
        newly_applied: list[str] = []
        for path in migration_files(directory):
            if path.name in applied:
                continue
            quoted_name = _sql_string(path.name)
            script = (
                "BEGIN IMMEDIATE;\n"
                + path.read_text(encoding="utf-8")
                + f"\nINSERT INTO d1_migrations(name) VALUES ({quoted_name});\n"
                + "COMMIT;\n"
            )
            try:
                connection.executescript(script)
            except Exception:
                connection.rollback()
                raise
            newly_applied.append(path.name)
        return newly_applied
    finally:
        connection.close()


def apply_remote_migrations(
    api: CloudflareAPI,
    database_id: str,
    directory: str | Path,
) -> list[str]:
    api.query_d1(database_id, TRACKING_TABLE_SQL)
    existing_result = api.query_d1(
        database_id,
        "SELECT name FROM d1_migrations ORDER BY id",
    )
    applied: set[str] = set()
    for query_result in existing_result:
        for row in query_result.get("results", []):
            name = row.get("name")
            if isinstance(name, str):
                applied.add(name)

    newly_applied: list[str] = []
    for path in migration_files(directory):
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8").rstrip()
        # D1's REST query endpoint supports multiple semicolon-delimited statements
        # in one request; append migration bookkeeping to the same batch.
        sql += f"\nINSERT INTO d1_migrations(name) VALUES ({_sql_string(path.name)});"
        api.query_d1(database_id, sql)
        newly_applied.append(path.name)
    return newly_applied


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
