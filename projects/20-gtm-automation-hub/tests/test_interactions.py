import json
from urllib.parse import urlencode

import pytest

from hub.interactions import InteractionError, parse_click, reply_url_allowed, user_allowed
from hub.scenarios import sample

CLICK = sample("slack_click.synthetic.json")


def encode(payload):
    return urlencode({"payload": json.dumps(payload)}).encode()


def test_parse_a_click():
    click = parse_click(encode(CLICK))
    assert (click.key, click.decision, click.user_id) == ("syn-visitor-001:demo-v1", "approved", "U0SYNTHETIC1")


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"payload=not-json",
        b"\xff",
        encode([]),
        encode("text"),
        encode({**CLICK, "type": "view_submission"}),
        encode({**CLICK, "actions": []}),
        encode({**CLICK, "actions": [{"action_id": "other", "value": "k"}]}),
        encode({**CLICK, "actions": [{"action_id": ["x"], "value": "k"}]}),
        encode({**CLICK, "actions": [{"action_id": "pql_approve", "value": 4}]}),
        encode({**CLICK, "user": {"id": "<!channel>"}}),
        encode({**CLICK, "user": "U1"}),
    ],
)
def test_anything_else_is_refused(body):
    with pytest.raises(InteractionError):
        parse_click(body)


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://hooks.slack.com/actions/T/1/x", True),
        ("https://hooks.slack.com.evil.example/x", False),
        ("http://hooks.slack.com/x", False),
        ("https://hooks.slack.com@evil.example/x", False),
        ("", False),
    ],
)
def test_reply_url_guard(url, ok):
    assert reply_url_allowed(url) is ok


def test_a_prefix_without_a_slash_allows_nothing():
    assert not reply_url_allowed("https://hooks.slack.com.evil.example", "https://hooks.slack.com")


def test_allow_list():
    assert user_allowed("U1", ()) and user_allowed("U1", ("U1",)) and not user_allowed("U2", ("U1",))
