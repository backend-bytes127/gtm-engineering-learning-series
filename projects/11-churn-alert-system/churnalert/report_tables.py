"""Small formatting helpers for the report."""
from __future__ import annotations

import pandas as pd


def pct(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{100 * value:.1f}%"


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}£{abs(value):,.0f}"


def markdown_table(frame: pd.DataFrame) -> str:
    head = "| " + " | ".join(str(c) for c in frame.columns) + " |"
    rule = "|" + "---|" * len(frame.columns)
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join([head, rule, *body])


def retention_rows(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return frame[keys].assign(base_customers=frame["start_customers"].astype(int),
                              base_revenue=(frame["start_pence"] / 100).map(money),
                              logo_retention=frame["logo_retention"].map(pct), GRR=frame["grr"].map(pct),
                              NRR=frame["nrr"].map(pct))


def backtest_rows(table: pd.DataFrame) -> pd.DataFrame:
    shares = ["precision", "recall", "value_captured", "ev_precision", "ev_value_captured"]
    plain = ["auc", "brier", "log_loss"]
    out = table[["model"]].copy()
    for column in plain:
        out[column] = table[column].map(lambda v: f"{v:.3f}")
    for column in ["mean_predicted", "observed", *shares]:
        out[column] = table[column].map(pct)
    return out
