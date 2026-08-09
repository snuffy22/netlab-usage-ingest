from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import app


class FakeStatement:
    def __init__(self, db: FakeD1, sql: str):
        self.db = db
        self.sql = sql
        self.parameters: tuple[Any, ...] = ()

    def bind(self, *parameters: Any) -> FakeStatement:
        self.parameters = parameters
        return self

    async def run(self) -> object:
        self.db.connection.execute(self.sql, self.parameters)
        self.db.connection.commit()
        return object()

    async def first(self, column: str | None = None) -> Any:
        row = self.db.connection.execute(self.sql, self.parameters).fetchone()
        if row is None:
            return None
        if column is None:
            return dict(row)
        return row[column]


class FakeD1:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(':memory:', check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        migration = Path('migrations/0001_initial.sql').read_text()
        self.connection.executescript(migration)

    def prepare(self, sql: str) -> FakeStatement:
        return FakeStatement(self, sql)

    async def batch(self, statements: list[FakeStatement]) -> list[object]:
        try:
            self.connection.execute('BEGIN')
            for statement in statements:
                self.connection.execute(statement.sql, statement.parameters)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return [object() for _ in statements]


class FakeLimiter:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    async def limit(self, _value: object) -> SimpleNamespace:
        return SimpleNamespace(success=self.allowed)


@pytest.fixture
def db() -> FakeD1:
    return FakeD1()


@pytest.fixture
def env(db: FakeD1) -> SimpleNamespace:
    return SimpleNamespace(
        DB=db,
        MAX_BODY_BYTES='65536',
        BATCH_RETENTION_DAYS='30',
        SUBMISSION_LIMITER=FakeLimiter(),
    )


@pytest.fixture
def client(env: SimpleNamespace) -> TestClient:
    app.state.env = env
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    del app.state.env
