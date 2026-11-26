"""Hand-made fixtures. No downloaded data and no network."""
from __future__ import annotations

import pandas as pd
import pytest

from churnalert import data
from churnalert.config import Comparison

ONE_COMPARISON = (Comparison("c", "Mar-May 2011 vs Mar-May 2010", "2010-03-01", "2010-06-01", "2011-03-01", "2011-06-01"),)


def source_row(invoice, code, qty, ts, price, customer, country="United Kingdom"):
    return {"Invoice": invoice, "StockCode": code, "Quantity": qty, "InvoiceDate": pd.Timestamp(ts), "Price": price,
            "Customer ID": customer, "Country": country}


@pytest.fixture
def sheets() -> list[pd.DataFrame]:
    """Customers 1-6 are one of each movement. The other rows are one of each exclusion bucket."""
    first = [
        source_row("100", "11111", 1, "2010-01-05", 10.00, 5),  # customer 5: old customer, silent in the base window
        source_row("101", "11111", 1, "2010-03-05", 100.00, 1),
        source_row("102", "11111", 1, "2010-03-06", 200.00, 2),
        source_row("103", "11111", 1, "2010-04-07", 300.00, 3),
        source_row("104", "11111", 1, "2010-05-08", 100.00, 6),
        source_row("105", "22222", 1, "2010-12-02", 7.00, 1),  # also in sheet 2: the overlap
    ]
    second = [
        source_row("105", "22222", 1, "2010-12-02", 7.00, 1),
        source_row("201", "11111", 1, "2011-03-05", 150.00, 1),
        source_row("202", "11111", 1, "2011-03-06", 50.00, 2),
        source_row("203", "11111", 1, "2011-04-01", 80.00, 4),
        source_row("204", "11111", 1, "2011-04-02", 40.00, 5),
        source_row("C205", "11111", -1, "2011-05-02", 30.00, 6),  # only a return: window floored at zero
        source_row("206", "11111", 1, "2011-05-03", 99.00, None),
        source_row("207", "post", 1, "2011-05-04", 5.00, 1),
        source_row("208", "11111", 1, "2011-05-05", 0.00, 1),
        source_row("209", "M", 1, "2011-05-06", 12.00, 2),
    ]
    return [pd.DataFrame(first), pd.DataFrame(second)]


@pytest.fixture
def raw(sheets) -> pd.DataFrame:
    return data.normalise(sheets)


def make_lines(events) -> pd.DataFrame:
    """Analysed-line frame from (customer, date, pence[, stock_code, country]) tuples. Negative pence is a return."""
    rows = []
    for i, event in enumerate(events):
        customer, day, pence, code, country = (*event, "11111", "United Kingdom")[:5] if len(event) == 3 else event
        rows.append({"invoice": f"{'C' if pence < 0 else ''}{i}", "stock_code": code, "qty": -1 if pence < 0 else 1,
                     "ts": pd.Timestamp(day), "pence": pence, "customer_id": customer, "country": country,
                     "is_sale": int(pence > 0)})
    return pd.DataFrame(rows)
