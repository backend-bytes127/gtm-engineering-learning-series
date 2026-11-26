"""Hand-made rows in the Criteo column layout. No real Criteo rows appear in this repository."""
import numpy as np
import pandas as pd
import pytest

from attribution.criteo import COLUMNS, audit, click_journeys, group_campaigns, load, validate
from attribution.criteo_run import run_frame
from attribution.journeys import DAY, prepare

D = int(DAY)


def row(day, uid, campaign, click=1, conv_day=None, conv_id=-1):
    converted = int(conv_day is not None)
    return (int(day * D), uid, campaign, converted, int(conv_day * D) if converted else -1, conv_id, click)


def hand_frame():
    rows = [
        row(1, 1, 10, conv_day=3, conv_id=100),  # conversion on day 3: too early for a 5-day lookback
        row(6, 2, 10, conv_day=9, conv_id=200),
        row(8, 2, 10, conv_day=9, conv_id=200),
        row(7, 2, 10, click=0),  # same user and campaign, not clicked, marked not converted
        row(9, 3, 20, conv_day=10, conv_id=300),
        row(10, 4, 10),
        row(11, 4, 20),
        row(2, 4, 20),  # older than the lookback at the end of the data
        row(12, 5, 30, conv_day=40, conv_id=500),  # converts after the data ends
        row(12, 6, 30),
    ]
    return pd.DataFrame(rows, columns=COLUMNS).sort_values("timestamp", ignore_index=True)


def test_audit_reports_the_disqualifying_facts():
    facts = audit(hand_frame())
    assert facts["converted_rows_without_a_click"] == 0
    assert facts["same_user_campaign_unclicked_rows_within_30d_before_conversion_marked_0"] == 1
    assert facts["conversion_paths_with_more_than_one_campaign"] == 0
    assert facts["conversions_after_the_last_observed_impression"] == 1
    assert facts["conversions"] == 4


def test_click_journeys_keep_only_fully_observed_conversions():
    touches, journeys = click_journeys(hand_frame(), lookback_days=5)
    assert journeys["converted"].sum() == 2
    prepared = prepare(touches, journeys, 5)
    assert prepared.n_conversions == 2
    assert (~prepared.touches["converted"]).sum() == 3  # users 4 (two clicks) and 6


def test_campaign_grouping_pools_the_tail():
    touches, journeys = click_journeys(hand_frame(), lookback_days=5)
    grouped = group_campaigns(touches, journeys, top=1)
    assert set(grouped["channel"]) == {"campaign_A", "other"}
    with pytest.raises(ValueError):
        group_campaigns(touches, journeys, top=20)


@pytest.mark.parametrize("days", [0, 100])
def test_lookback_guards(days):
    with pytest.raises(ValueError):
        click_journeys(hand_frame(), days)


@pytest.mark.parametrize(
    "bad", [lambda f: f.drop(columns="click"), lambda f: f.assign(click=2), lambda f: f.assign(conversion=1)]
)
def test_validation(bad):
    with pytest.raises(ValueError):
        validate(bad(hand_frame()))


def test_load_roundtrip_and_missing_file(tmp_path):
    path = tmp_path / "x.tsv.gz"
    hand_frame().to_csv(path, sep="\t", index=False)
    assert len(load(path)) == len(hand_frame())
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "missing.gz")


def synthetic_frame(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for uid in range(600):
        campaign = int(rng.integers(1, 15))
        buys = rng.random() < 0.3
        end = float(rng.uniform(1, 30))
        for _ in range(int(rng.integers(1, 4))):
            rows.append(row(max(0, end - rng.uniform(0.01, 2)), uid, campaign, conv_day=end if buys else None, conv_id=uid if buys else -1))
    rows.append(row(30.5, 10_000, 1))
    return pd.DataFrame(rows, columns=COLUMNS)


def test_end_to_end_on_made_up_rows_and_report(tmp_path):
    from attribution import report_criteo

    result = run_frame(synthetic_frame(), n_boot=10, lookbacks=(3, 7), primary=7)
    assert result.multi_campaign_paths == 0
    assert result.all_campaign_distance.to_numpy().max() == pytest.approx(0, abs=1e-5)
    text = report_criteo.build(result, tmp_path, 10)
    assert "CC BY-NC-SA 4.0" in text
    assert (tmp_path / "criteo_shares.png").stat().st_size > 0


@pytest.mark.parametrize(("unclicked", "multi", "gap", "expected"), [
    (0, 0, 0.0, ("Every row marked converted is a clicked row", "No conversion path contains two campaigns")),
    (3, 5, 0.2, ("3 rows marked converted have no click", "5 conversions have more than one campaign")),
])
def test_narrative_follows_the_computed_audit(unclicked, multi, gap, expected):
    from attribution import report_criteo

    audit_values = {"converted_rows_without_a_click": unclicked, "conversion_paths_with_more_than_one_campaign": multi,
                    "conversions_after_the_last_observed_impression": 0}
    text = report_criteo.consequences(audit_values) + report_criteo.conclusions(gap)
    assert all(phrase in text for phrase in expected)
    assert ("makes no difference" in text) == (gap == 0)
