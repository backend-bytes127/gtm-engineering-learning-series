import hashlib
import hmac

import pytest

from hub.signing import GENERIC, SLACK, sign, signed_headers, verify

SECRET = "unit-test-key-0123456789"
NOW = 1_800_000_000


def test_signature_matches_an_independent_construction():
    expected = hmac.new(SECRET.encode(), b'v0:1800000000:{"a":1}', hashlib.sha256).hexdigest()
    assert sign(SLACK, SECRET, NOW, b'{"a":1}') == f"v0={expected}"


@pytest.mark.parametrize("scheme", [GENERIC, SLACK])
def test_round_trip_and_header_case(scheme):
    headers = {k.title(): v for k, v in signed_headers(scheme, SECRET, NOW, b"body").items()}
    assert verify(scheme, SECRET, headers, b"body", NOW).ok


@pytest.mark.parametrize("age,ok", [(0, True), (300, True), (301, False), (-300, True), (-301, False)])
def test_freshness_window_edges(age, ok):
    headers = signed_headers(GENERIC, SECRET, NOW - age, b"x")
    result = verify(GENERIC, SECRET, headers, b"x", NOW)
    assert (result.ok, result.reason) == (ok, "ok" if ok else "stale_timestamp")


@pytest.mark.parametrize(
    "headers,reason",
    [
        ({}, "missing_headers"),
        ({"x-gtm-timestamp": "1800000000"}, "missing_headers"),
        ({"x-gtm-timestamp": "1800000000.5", "x-gtm-signature": "v1=a"}, "bad_timestamp"),
        ({"x-gtm-timestamp": "-1", "x-gtm-signature": "v1=a"}, "bad_timestamp"),
        ({"x-gtm-timestamp": "1800000000", "x-gtm-signature": "v1=é"}, "bad_signature"),
    ],
)
def test_malformed_headers(headers, reason):
    assert verify(GENERIC, SECRET, headers, b"x", NOW).reason == reason


def test_changed_body_wrong_key_and_wrong_scheme_fail():
    headers = signed_headers(GENERIC, SECRET, NOW, b"x")
    assert verify(GENERIC, SECRET, headers, b"x ", NOW).reason == "bad_signature"
    assert verify(GENERIC, SECRET + "z", headers, b"x", NOW).reason == "bad_signature"
    as_slack = {"x-slack-request-timestamp": str(NOW), "x-slack-signature": headers["x-gtm-signature"]}
    assert verify(SLACK, SECRET, as_slack, b"x", NOW).reason == "bad_signature"


@pytest.mark.parametrize("secret", ["", "short", None])
def test_fails_closed_without_a_real_secret(secret):
    headers = signed_headers(GENERIC, SECRET, NOW, b"x")
    assert verify(GENERIC, secret, headers, b"x", NOW).reason == "not_configured"
