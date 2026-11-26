"""GRR and NRR from the SQL movements, with customer bootstrap intervals and sensitivity runs."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from .config import BOOTSTRAP_REPS, SEED
from .sqldb import build, query, run_checks

# chronological, not alphabetical
ORDER = ("ORDER BY cmp, CASE cohort WHEN '2009-12 or older' THEN 0 WHEN '2010 Jan-Mar' THEN 1 WHEN '2010 Apr-Jun' THEN 2 "
         "WHEN '2010 Jul-Sep' THEN 3 WHEN '2010 Oct-Nov' THEN 4 ELSE 5 END")


def rates(start: float, churn: float, contraction: float, expansion: float) -> tuple[float, float]:
    if start <= 0:
        return float("nan"), float("nan")
    gross = (start - churn - contraction) / start
    return gross, gross + expansion / start


def add_rates(frame: pd.DataFrame) -> pd.DataFrame:
    values = [rates(r.start_pence, r.churn_pence, r.contraction_pence, r.expansion_pence) for r in frame.itertuples()]
    return frame.assign(grr=[v[0] for v in values], nrr=[v[1] for v in values],
                        logo_retention=frame["retained_customers"] / frame["start_customers"])


def waterfall(con: sqlite3.Connection) -> pd.DataFrame:
    return add_rates(query(con, "SELECT * FROM waterfall ORDER BY cmp"))


def cohorts(con: sqlite3.Connection) -> pd.DataFrame:
    return add_rates(query(con, f"SELECT * FROM cohort_retention {ORDER}"))


def base_movements(con: sqlite3.Connection, cmp: str) -> pd.DataFrame:
    frame = query(con, "SELECT * FROM movements WHERE start_pence > 0 ORDER BY cmp, customer_id")
    return frame[frame["cmp"] == cmp].reset_index(drop=True)


def bootstrap_rates(base: pd.DataFrame, reps: int = BOOTSTRAP_REPS, seed: int = SEED) -> dict[str, tuple[float, float]]:
    """95% percentile interval from resampling customers. It reflects concentration, not future periods."""
    values = base[["start_pence", "churn_pence", "contraction_pence", "expansion_pence"]].to_numpy(float)
    rng = np.random.default_rng(seed)
    draws = np.array([rates(*values[rng.integers(0, len(values), len(values))].sum(axis=0)) for _ in range(reps)])
    low, high = np.percentile(draws, [2.5, 97.5], axis=0)
    return {"grr": (float(low[0]), float(high[0])), "nrr": (float(low[1]), float(high[1]))}


def without_top(base: pd.DataFrame, n: int) -> tuple[float, float, float]:
    """GRR and NRR without the n largest base customers, and the share of base revenue those held."""
    ranked = base.sort_values(["start_pence", "customer_id"], ascending=[False, True])
    rest = ranked.iloc[n:]
    sums = rest[["start_pence", "churn_pence", "contraction_pence", "expansion_pence"]].sum()
    share = ranked["start_pence"].head(n).sum() / ranked["start_pence"].sum()
    gross, net = rates(*sums)
    return gross, net, float(share)


def _annual_row(name: str, con: sqlite3.Connection) -> dict[str, object]:
    run_checks(con)
    row = waterfall(con).set_index("cmp").loc["annual"]
    return {"variant": name, "start_gbp": row.start_pence / 100, "grr": row.grr, "nrr": row.nrr}


def sensitivity(raw: pd.DataFrame, con: sqlite3.Connection, **build_args: object) -> pd.DataFrame:
    """How much do the annual figures move when a defensible cleaning choice changes?"""
    rows = [_annual_row("main definition", con)]
    columns = [c for c in raw.columns if c != "sheet_no"]
    variants = {
        "also drop exact duplicate rows within a sheet": (raw.loc[~raw.duplicated(["sheet_no", *columns])], ()),
        "count manual adjustments (code M) as revenue": (raw, ("M",)),
    }
    for name, (frame, codes) in variants.items():
        other = build(frame, extra_codes=codes, **build_args)
        rows.append(_annual_row(name, other))
        other.close()
    base = base_movements(con, "annual")
    for n in (10, 50):
        gross, net, share = without_top(base, n)
        start = base["start_pence"].sum() * (1 - share) / 100
        rows.append({"variant": f"without the {n} largest base customers ({share:.0%} of base)", "start_gbp": start,
                     "grr": gross, "nrr": net})
    return pd.DataFrame(rows)


def monthly_trap(con: sqlite3.Connection) -> pd.DataFrame:
    """What a SaaS-style month-on-month GRR would claim on non-contractual buying (do not use it)."""
    months = query(con, "SELECT customer_id, month, MAX(net_pence, 0) AS pence FROM customer_month "
                        "WHERE month <= (SELECT last_full_month FROM params)")
    table = months.pivot(index="customer_id", columns="month", values="pence").fillna(0)
    rows = []
    for previous, current in zip(table.columns[:-1], table.columns[1:]):
        base = table[table[previous] > 0]
        rows.append({"month": current, "naive_grr": np.minimum(base[previous], base[current]).sum() / base[previous].sum(),
                     "lapsed_share": float((base[current] == 0).mean())})
    return pd.DataFrame(rows)
