"""Run the SQL layer in SQLite and enforce its reconciliation checks."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import COMPARISONS, LAST_FULL_MONTH, Comparison

SQL_DIR = Path(__file__).with_name("sql")
SCRIPTS = ("01_lines.sql", "02_customers.sql", "03_movements.sql", "04_summary.sql")


class ReconciliationError(RuntimeError):
    """A figure in the SQL layer does not balance exactly."""


def build(raw: pd.DataFrame, path: str = ":memory:", comparisons: tuple[Comparison, ...] = COMPARISONS,
          last_full_month: str = LAST_FULL_MONTH, extra_codes: tuple[str, ...] = ()) -> sqlite3.Connection:
    """Load raw lines and build every table. `extra_codes` treats extra stock codes as revenue (sensitivity)."""
    con = sqlite3.connect(path)
    table = raw.assign(ts=raw["ts"].dt.strftime("%Y-%m-%d %H:%M:%S"))
    table.to_sql("raw_lines", con, index=False, if_exists="replace")
    pd.DataFrame({"last_full_month": [last_full_month]}).to_sql("params", con, index=False, if_exists="replace")
    pd.DataFrame({"stock_code": list(extra_codes)}, dtype=str).to_sql("extra_codes", con, index=False, if_exists="replace")
    windows = pd.DataFrame([vars(c) for c in comparisons]).rename(columns={"key": "cmp"})
    windows.to_sql("windows", con, index=False, if_exists="replace")
    for name in SCRIPTS:
        con.executescript((SQL_DIR / name).read_text(encoding="utf-8"))
    return con


def query(con: sqlite3.Connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, con)


def run_checks(con: sqlite3.Connection) -> pd.DataFrame:
    """Return every check with an `ok` column, and raise if any side differs by even one penny."""
    checks = query(con, (SQL_DIR / "05_checks.sql").read_text(encoding="utf-8"))
    checks = checks.assign(ok=[bool(a == b) for a, b in zip(checks["lhs"], checks["rhs"])])
    failed = checks[~checks["ok"]]
    if len(failed):
        raise ReconciliationError("reconciliation failed:\n" + failed.to_string(index=False))
    return checks


def analysed_lines(con: sqlite3.Connection) -> pd.DataFrame:
    frame = query(con, "SELECT * FROM analysed")
    return frame.assign(ts=pd.to_datetime(frame["ts"]))
