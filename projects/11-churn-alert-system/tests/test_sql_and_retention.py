from __future__ import annotations

import math

import pandas as pd
import pytest
from conftest import ONE_COMPARISON

from churnalert import data, retention, sqldb
from churnalert.config import Comparison


@pytest.fixture
def con(raw):
    connection = sqldb.build(raw, comparisons=ONE_COMPARISON, last_full_month="2011-05")
    yield connection
    connection.close()


def test_every_source_row_gets_one_bucket(con):
    counts = dict(sqldb.query(con, "SELECT bucket, COUNT(*) AS n FROM lines GROUP BY bucket").itertuples(index=False))
    assert counts == {"analysed": 11, "overlap_duplicate": 1, "no_customer_id": 1, "non_merchandise_code": 2, "zero_value": 1}


def test_waterfall_matches_hand_calculation(con):
    row = retention.waterfall(con).iloc[0]
    expected = {"start": 700, "new": 80, "reactivation": 40, "expansion": 50, "contraction": 150, "churn": 400, "end": 320}
    assert {k: row[f"{k}_pence"] / 100 for k in expected} == expected
    assert row.grr == pytest.approx(150 / 700)
    assert row.nrr == pytest.approx(200 / 700)
    assert row.logo_retention == pytest.approx(2 / 4)


def test_new_revenue_never_enters_retention(con):
    cohorts = retention.cohorts(con)
    assert cohorts["start_pence"].sum() == 70_000
    assert cohorts["expansion_pence"].sum() == 5_000


def test_all_checks_balance_including_the_zero_floor(con):
    checks = sqldb.run_checks(con)
    assert checks["ok"].all()
    floor = checks[checks["name"] == "window net + floor adjustment = waterfall end: c"].iloc[0]
    assert floor.lhs == floor.rhs == 32_000


def test_one_penny_of_drift_stops_the_run(con):
    con.execute("UPDATE movements SET churn_pence = churn_pence + 1 WHERE customer_id = 3")
    with pytest.raises(sqldb.ReconciliationError, match="rolls forward"):
        sqldb.run_checks(con)


def test_extra_codes_count_as_revenue(raw):
    other = sqldb.build(raw, comparisons=ONE_COMPARISON, last_full_month="2011-05", extra_codes=("M",))
    assert retention.waterfall(other).iloc[0].end_pence == 33_200


def test_analysed_lines_flag_sales(con):
    lines = sqldb.analysed_lines(con)
    assert lines.loc[lines["invoice"].str.startswith("C"), "is_sale"].sum() == 0
    assert pd.api.types.is_datetime64_any_dtype(lines["ts"])


def test_rates_and_empty_base():
    assert retention.rates(100, 20, 10, 40) == pytest.approx((0.7, 1.1))
    assert math.isnan(retention.rates(0, 0, 0, 0)[0])


def test_bootstrap_and_top_customer_removal(con):
    base = retention.base_movements(con, "c")
    interval = retention.bootstrap_rates(base, reps=50)
    assert 0 <= interval["grr"][0] <= interval["grr"][1] <= 1
    gross, net, share = retention.without_top(base, 1)  # removes customer 3, who churned 300 of 700
    assert (gross, net, share) == pytest.approx((150 / 400, 200 / 400, 300 / 700))


def test_monthly_trap_is_a_share(con):
    assert retention.monthly_trap(con)["naive_grr"].between(0, 1).all()


def test_sensitivity_lists_each_variant(raw):
    annual = (Comparison("annual", "x", "2010-03-01", "2010-06-01", "2011-03-01", "2011-06-01"),)
    args = {"comparisons": annual, "last_full_month": "2011-05"}
    table = retention.sensitivity(raw, sqldb.build(raw, **args), **args)
    assert len(table) == 5
    assert table.iloc[0].nrr == pytest.approx(200 / 700)


def test_cohort_triangle_month_zero(con):
    triangle = sqldb.query(con, "SELECT * FROM cohort_month WHERE month_index = 0")
    assert (triangle["buyers"] == triangle["cohort_size"]).all()


def test_normalise_holds_money_as_pence(raw):
    assert raw["pence"].dtype == "int64"
    assert raw.loc[raw["invoice"] == "C205", "pence"].item() == -3000
    assert raw.loc[raw["invoice"] == "207", "stock_code"].item() == "POST"


def test_normalise_rejects_bad_input(sheets):
    with pytest.raises(ValueError, match="lacks columns"):
        data.normalise([sheets[0].drop(columns="Price")])
    broken = sheets[0].assign(Price=None)
    with pytest.raises(ValueError, match="empty"):
        data.normalise([broken])


def test_load_reads_workbook_then_cache(tmp_path, sheets):
    with pytest.raises(FileNotFoundError, match="fetch_data"):
        data.load(tmp_path / "missing.xlsx")
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        for i, sheet in enumerate(sheets):
            sheet.to_excel(writer, sheet_name=f"s{i}", index=False)
    cache = tmp_path / "lines.parquet"
    first = data.load(path, cache)
    assert cache.exists()
    assert data.load(path, cache)["pence"].sum() == first["pence"].sum()
