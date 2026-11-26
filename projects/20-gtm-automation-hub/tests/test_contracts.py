import pytest

from hub.contracts import pql_errors, signal_errors
from hub.scenarios import sample

SIGNAL = sample("signal.synthetic.json")
LEAD = sample("pql_lead.synthetic.json")


def test_samples_are_valid():
    assert signal_errors(SIGNAL) == [] and pql_errors(LEAD) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_id", "has space"),
        ("event_id", "a" * 81),
        ("type", "unknown"),
        ("account_domain", "UPPER.example"),
        ("account_domain", "nodot"),
        ("account_domain", "a.example\n"),
        ("occurred_at", "2026-01-12"),
        ("source", "   "),
        ("source", "x" * 41),
    ],
)
def test_bad_signal_fields_are_named(field, value):
    assert signal_errors({**SIGNAL, field: value}) == [field]


@pytest.mark.parametrize(
    "field,value",
    [
        ("tier", "D"),
        ("score", 1.2),
        ("score", True),
        ("score", "0.2"),
        ("score", float("nan")),
        ("action", ""),
        ("decided_at", None),
        ("idempotency_key", "other:key"),
    ],
)
def test_bad_lead_fields_are_named(field, value):
    assert pql_errors({**LEAD, field: value}) == [field]


@pytest.mark.parametrize("value", [None, [], "text", 3])
def test_non_objects(value):
    assert signal_errors(value) == pql_errors(value) == ["not_an_object"]
