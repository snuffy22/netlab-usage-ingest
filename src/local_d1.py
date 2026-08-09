from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LocalD1Result:
    success: bool = True
    changes: int = 0
    last_row_id: int | None = None


class LocalD1Statement:
    def __init__(self, db: LocalD1, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._db = db
        self.sql = sql
        self.params = params

    def bind(self, *params: Any) -> LocalD1Statement:
        return LocalD1Statement(self._db, self.sql, tuple(params))

    async def first(self, column: str | None = None) -> Any | None:
        row = self._db._execute_first(self.sql, self.params)
        if row is None:
            return None
        if column is not None:
            return row[column]
        return dict(row)

    async def run(self) -> LocalD1Result:
        return self._db._execute_run(self.sql, self.params)


class LocalD1:
    """Small async-shaped adapter for the subset of D1 used by this service.

    The public methods intentionally mirror the Cloudflare D1 calls used in
    ``src/storage.py``: ``prepare().bind().first()``, ``run()``, and ``batch()``.
    SQLite work is synchronous because local development is single-process and
    these statements are tiny; the async API keeps application code unchanged.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")

    def prepare(self, sql: str) -> LocalD1Statement:
        return LocalD1Statement(self, sql)

    async def batch(self, statements: Iterable[LocalD1Statement]) -> list[LocalD1Result]:
        results: list[LocalD1Result] = []
        cursor = self._connection.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            for statement in statements:
                cursor.execute(statement.sql, statement.params)
                results.append(
                    LocalD1Result(
                        success=True,
                        changes=max(cursor.rowcount, 0),
                        last_row_id=cursor.lastrowid,
                    )
                )
            self._connection.commit()
            return results
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def close(self) -> None:
        self._connection.close()

    def _execute_first(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        cursor = self._connection.execute(sql, params)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def _execute_run(self, sql: str, params: tuple[Any, ...]) -> LocalD1Result:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, params)
            self._connection.commit()
            return LocalD1Result(
                success=True,
                changes=max(cursor.rowcount, 0),
                last_row_id=cursor.lastrowid,
            )
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()
