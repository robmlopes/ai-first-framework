"""SQLite adapter implementing the DbWrite port (balances stored as TEXT to keep Decimal exact)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from domain.transfer import Account
from ports.db import DbWrite


class SqliteDb:
    """Satisfies ports.db.DbWrite; `get` is an adapter-only helper for reads and tests."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute("CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, balance TEXT NOT NULL)")

    def save(self, account: Account) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO accounts (id, balance) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET balance = excluded.balance",
                (account.id, str(account.balance)),
            )

    def get(self, account_id: str) -> Account | None:
        row = self._conn.execute("SELECT balance FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return None if row is None else Account(account_id, Decimal(row[0]))

    def close(self) -> None:
        self._conn.close()


def as_db_write(db: SqliteDb) -> DbWrite:
    """Typed conformance check: mypy fails here if SqliteDb stops satisfying the DbWrite port."""
    return db
