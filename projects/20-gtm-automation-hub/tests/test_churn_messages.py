import json
from datetime import date
from pathlib import Path

import pytest

from hub.churn import QUEUE_COLUMNS, QueueError, as_of_from_name, by_reason, parse_queue, to_pence
from hub.messages import churn_digest, escape, pounds, pql_alert, signal_alert, three_decimals
from hub.scenarios import SAMPLES, sample

HEADER = ",".join(QUEUE_COLUMNS) + "\n"
ROW = "{rank},{id},0.5,10,{amount},{reason},why,{action},not sent\n"


def queue(*rows):
    return HEADER + "".join(ROW.format(rank=r, id=i, amount=a, reason=why, action="Call") for r, i, a, why in rows)


def test_parse_sorts_by_rank_and_groups_by_reason():
    accounts = parse_queue(queue((2, "b", "10.50", "B"), (1, "a", "1.25", "A"), (3, "c", "2", "B")))
    assert [a.customer_id for a in accounts] == ["a", "b", "c"]
    assert by_reason(accounts) == [("B", 2, 1250), ("A", 1, 125)]


@pytest.mark.parametrize(
    "text",
    [
        "a,b\n1,2\n",
        HEADER,
        "",
        queue((1, "a", "-1", "A")),
        queue((1, "a", "nan", "A")),
        queue((1, "a", "1_000", "A")),
        queue(("x", "a", "1", "A")),
        queue((1, "", "1", "A")),
    ],
)
def test_bad_queues_are_refused(text):
    with pytest.raises(QueueError):
        parse_queue(text)


def test_file_name_gives_the_date():
    assert as_of_from_name("alert_queue_2011-12-10.csv") == "2011-12-10"
    with pytest.raises(QueueError):
        as_of_from_name("queue.csv")


def test_money_rounds_half_up():
    assert (to_pence("0.125"), pounds(150), pounds(149), pounds(123456789)) == (13, "£2", "£1", "£1,234,568")
    assert three_decimals(0.0625) == "0.063"


def test_digest_shows_top_five_and_flags_a_stale_queue():
    text = (SAMPLES / "inbox" / "alert_queue_2026-11-23.csv").read_text(encoding="utf-8")
    accounts = parse_queue(text)
    fresh = churn_digest(accounts, "2026-11-23", date(2026, 12, 1))
    stale = churn_digest(accounts, "2026-11-23", date(2026, 12, 2))
    assert len(stale["blocks"]) == len(fresh["blocks"]) + 1 and "9 days old" in json.dumps(stale)
    assert fresh["blocks"][3]["text"]["text"].count("\n") == 5
    assert "not a forecast" in json.dumps(fresh)


def test_slack_control_characters_are_escaped_everywhere():
    assert escape("<!channel> & <@U1>") == "&lt;!channel&gt; &amp; &lt;@U1&gt;"
    event = {**sample("signal.synthetic.json"), "source": "<!here>"}
    assert "<!here>" not in json.dumps(signal_alert(event))
    lead = {**sample("pql_lead.synthetic.json"), "action": "<!channel>"}
    assert "<!channel>" not in json.dumps(pql_alert(lead))


def test_pql_buttons_carry_the_idempotency_key():
    buttons = pql_alert(sample("pql_lead.synthetic.json"))["blocks"][2]["elements"]
    assert [(b["action_id"], b["value"]) for b in buttons] == [
        ("pql_approve", "syn-visitor-001:demo-v1"),
        ("pql_dismiss", "syn-visitor-001:demo-v1"),
    ]


def test_columns_match_the_earlier_project_if_it_is_present():
    source = Path(__file__).resolve().parents[2] / "11-churn-alert-system" / "churnalert" / "queue.py"
    if not source.exists():
        pytest.skip("project 11 is not in this checkout")
    text = source.read_text(encoding="utf-8")
    assert all(f'"{column}"' in text for column in QUEUE_COLUMNS)
