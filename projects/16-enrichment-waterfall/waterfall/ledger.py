"""The call ledger. One row per (provider, contact): it is the cache, the spend record and the retry guard."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .models import Answer

RESERVED, DONE, UNKNOWN = "reserved", "done", "unknown"
SCHEMA = """CREATE TABLE IF NOT EXISTS calls (
  provider TEXT NOT NULL, contact TEXT NOT NULL, state TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', micros INTEGER NOT NULL,
  PRIMARY KEY (provider, contact))"""


class CapReached(Exception):
    """Making this call could take spend over the cap, so it is not made."""


@dataclass(frozen=True)
class Row:
    state: str
    answer: Answer
    micros: int


class Ledger:
    def __init__(self, path: str = ":memory:"):
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.execute(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def get(self, provider: str, contact: str) -> Row | None:
        row = self._db.execute(
            "SELECT state, status, email, micros FROM calls WHERE provider=? AND contact=?", (provider, contact)
        ).fetchone()
        return Row(row[0], Answer(row[1], row[2]), row[3]) if row else None

    def committed(self) -> int:
        """Money spent plus money that might be: settled, unknown and still-reserved rows."""
        return self._db.execute("SELECT COALESCE(SUM(micros), 0) FROM calls").fetchone()[0]

    def reserve(self, provider: str, contact: str, price: int, cap: int | None) -> None:
        """Set aside the full price BEFORE calling. The check and the insert happen in one write transaction."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if cap is not None and self.committed() + price > cap:
                raise CapReached(f"cap of {cap} micros would be exceeded")
            self._db.execute("INSERT INTO calls(provider, contact, state, micros) VALUES (?,?,?,?)", (provider, contact, RESERVED, price))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def settle(self, provider: str, contact: str, state: str, answer: Answer, micros: int) -> None:
        self._db.execute(
            "UPDATE calls SET state=?, status=?, email=?, micros=? WHERE provider=? AND contact=?",
            (state, answer.status, answer.email, micros, provider, contact),
        )

    def release(self, provider: str, contact: str) -> None:
        """Only for calls known not to have been billed."""
        self._db.execute("DELETE FROM calls WHERE provider=? AND contact=?", (provider, contact))

    def count(self, state: str) -> int:
        return self._db.execute("SELECT COUNT(*) FROM calls WHERE state=?", (state,)).fetchone()[0]
