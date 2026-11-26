import numpy as np
import pandas as pd
import pytest

from pql import ingest, tracking_plan
from pql.cohort import build_cohort, buyer_timing, funnel_population, time_split
from pql.config import MINUTE_MS
from pql.features import FEATURES, LeakageError, build_features
from pql.milestones import funnel, milestone_table, reached
from tests.fixtures import SMALL, cohort_events, frame, row


def _padded(rows: list[tuple]) -> pd.DataFrame:
    """Add enough good rows that a few bad ones stay under the quarantine limit."""
    return frame(rows + [row(1000 + i, i) for i in range(1000)])


def test_valid_feed_passes_and_exact_duplicates_are_counted():
    result = tracking_plan.validate(frame([row(1, 0), row(1, 0), row(1, 1, "transaction", transaction=9)]))
    assert result.violations == {"exact_duplicate": 1}
    assert len(result.clean) == 2 and result.rows_quarantined == 1


@pytest.mark.parametrize(
    "bad, rule",
    [
        (row(1, 0, "purchase"), "unknown_event"),
        (row(1, 0, "transaction"), "transaction_without_transactionid"),
        (row(1, 0, "view", transaction=3), "view_with_transactionid"),
        (row(-4, 0), "below_min_visitorid"),
        (row(1, 0, item=np.nan), "missing_itemid"),
        (row(1, 0, item="abc"), "bad_type_itemid"),
        (row(1, 0, item=1.5), "bad_type_itemid"),
        (row(1, 0, day=900), "timestamp_out_of_window"),
    ],
)
def test_each_broken_row_is_quarantined_with_its_rule(bad, rule):
    result = tracking_plan.validate(_padded([bad]))
    assert result.violations[rule] == 1
    assert len(result.clean) == 1000


def test_too_many_bad_rows_stop_the_run():
    with pytest.raises(tracking_plan.SchemaError, match="break the tracking plan"):
        tracking_plan.validate(frame([row(1, 0, "oops"), row(2, 0)]))


def test_a_missing_column_stops_the_run():
    with pytest.raises(tracking_plan.SchemaError, match="itemid"):
        tracking_plan.validate(frame([row(1, 0)]).drop(columns="itemid"))


def test_checksum_is_enforced(tmp_path):
    (tmp_path / "a.csv").write_text("x\n1\n")
    good = {"a.csv": ingest.sha256_of(tmp_path / "a.csv")}
    assert len(ingest.read_csv(ingest.verify_file(tmp_path, "a.csv", good))) == 1
    with pytest.raises(ingest.DataError, match="checksum mismatch"):
        ingest.verify_file(tmp_path, "a.csv", {"a.csv": "0" * 64})
    with pytest.raises(ingest.DataError, match="fetch_data"):
        ingest.verify_file(tmp_path, "b.csv", {"b.csv": "0" * 64})


def _cohort():
    events = tracking_plan.validate(cohort_events()).clean
    return events, build_cohort(events, SMALL)


def test_every_eligibility_rule_and_the_label():
    _, cohort = _cohort()
    assert sorted(cohort.visitors.index) == [2, 5, 6]
    assert cohort.visitors["label"].to_dict() == {2: 1, 5: 0, 6: 0}
    assert cohort.counts["excluded_burn_in"] == 1
    assert cohort.counts["excluded_bought_before_cutoff"] == 1
    assert cohort.counts["excluded_automation_like"] == 1
    assert cohort.counts["excluded_label_window_incomplete"] == 2


def test_features_count_only_events_up_to_the_cutoff():
    _, cohort = _cohort()
    features = build_features(cohort.window, cohort.visitors, SMALL)
    assert list(features.columns) == list(FEATURES)
    assert features.loc[5, "views"] == 2 and features.loc[5, "cart_adds"] == 0
    assert features.loc[5, "repeat_views"] == 1 and features.loc[5, "idle_minutes_at_cutoff"] == 0
    assert features.loc[2, "minutes_to_first_cart"] == 5
    assert features.loc[5, "minutes_to_first_cart"] == SMALL.cutoff_minutes


def test_changing_the_future_cannot_change_a_feature():
    events, cohort = _cohort()
    before = build_features(cohort.window, cohort.visitors, SMALL)
    extra = tracking_plan.validate(frame([row(5, 50, "addtocart", item=3), row(2, 60, item=4)])).clean
    changed = build_cohort(pd.concat([events, extra]), SMALL)
    pd.testing.assert_frame_equal(before, build_features(changed.window, changed.visitors, SMALL))


def test_feature_builder_refuses_a_future_event():
    events, cohort = _cohort()
    with pytest.raises(LeakageError):
        build_features(events[events["visitorid"].isin(cohort.visitors.index)], cohort.visitors, SMALL)


def test_split_keeps_an_embargo_so_earlier_labels_are_known():
    day = 86_400_000
    base = pd.Timestamp("2015-06-01").value // 1_000_000
    first = pd.Series([base - 9 * day, base - 3 * day, base + day, base + 20 * day])
    visitors = pd.DataFrame({"first_ts": first, "cutoff_ts": first + 30 * MINUTE_MS})
    split = time_split(visitors, "2015-06-01", "2015-06-20", SMALL)
    assert list(split["train"]) == [0]  # visitor 1's label is not known on 1 June
    assert list(split["validation"]) == [2] and list(split["test"]) == [3]
    with pytest.raises(ValueError):
        time_split(visitors, "2015-06-20", "2015-06-01", SMALL)


def test_buyer_timing_is_cumulative():
    events, _ = _cohort()
    shares = [r["share_already_bought"] for r in buyer_timing(events, (5, 30, 60, 20_000), SMALL)]
    assert shares == sorted(shares) and shares[-1] == 1.0


def test_milestones_report_reach_and_lift():
    _, cohort = _cohort()
    features = build_features(cohort.window, cohort.visitors, SMALL)
    table = {r["milestone"]: r for r in milestone_table(features, cohort.visitors["label"])}
    assert table["M4_added_to_cart"]["buy_rate_reached"] == 1.0
    assert table["M4_added_to_cart"]["share_of_later_buyers"] == 1.0
    assert table["M3_explored_5_items"]["reach"] == 0.0
    assert reached(features).shape == (3, 5)


def test_funnel_is_ordered_and_includes_fast_buyers():
    events = tracking_plan.validate(
        frame(
            [row(1, 0), row(1, 2, "addtocart"), row(1, 3, "transaction", transaction=1), row(2, 0), row(2, 1, "transaction", transaction=2)]
        )
    ).clean
    first = events.groupby("visitorid")["timestamp"].min()
    steps = {r["step"]: r["visitors"] for r in funnel(events, first.index, first, SMALL.horizon_ms)}
    assert steps == {"viewed": 2, "added_to_cart": 1, "purchased": 1, "purchased_without_that_path": 1}


def test_funnel_population_drops_burn_in_and_incomplete_horizons():
    events = tracking_plan.validate(cohort_events()).clean
    first = funnel_population(events, "2015-06-01", SMALL)
    assert 1 not in first.index and 3 in first.index and 7 not in first.index
