import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pytest

from sequencer import constants as C
from sequencer.live.unipile import (
    BASE_URL,
    UnipileClient,
    UnipileError,
    UnipileProvider,
    linkedin_identifier,
    parse_webhook,
    verify_signature,
)
from sequencer.models import Step
from sequencer.tests.conftest import person

NOW = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
ACCOUNT = "acc_1"


class FakeTransport:
    """Records every request and answers from a table of (method, path-prefix) -> (status, json)."""

    def __init__(self, routes=None):
        self.routes, self.requests = routes or {}, []

    def __call__(self, method, url, headers, body):
        path = urlsplit(url).path.removeprefix(urlsplit(BASE_URL).path)
        self.requests.append(
            {
                "method": method,
                "path": path,
                "query": urlsplit(url).query,
                "headers": headers,
                "body": json.loads(body) if body else None,
            }
        )
        for (m, prefix), (status, payload) in self.routes.items():
            if m == method and path.startswith(prefix):
                return status, json.dumps(payload)
        return 404, json.dumps({"type": "not_found", "detail": "no route"})


def profile(distance="SECOND_DEGREE", pid="prov_ravi"):
    return {
        "id": pid,
        "public_identifier": "ravi-sample",
        "first_name": "Ravi",
        "last_name": "Sample",
        "specifics": {"network_distance": distance},
    }


def provider(routes, remember=None):
    t = FakeTransport(routes)
    return UnipileProvider(UnipileClient("KEY", ACCOUNT, transport=t), remember=remember), t


def ravi(**kw):
    return person(1, name="Ravi Sample", first_name="Ravi", linkedin_url="https://www.linkedin.com/in/ravi-sample", **kw)


INVITE = Step(1, C.LINKEDIN_INVITE, 0, "inv")
DM = Step(2, C.LINKEDIN_MESSAGE, 0, "dm")
MAIL = Step(3, C.EMAIL, 0, "e1")


def test_identifier_is_taken_from_a_url_or_a_bare_slug():
    assert linkedin_identifier("https://www.linkedin.com/in/ravi-sample/") == "ravi-sample"
    assert linkedin_identifier("linkedin.com/in/Ravi%2DSample?x=1") == "Ravi-Sample"
    assert linkedin_identifier("  ravi-sample ") == "ravi-sample"


def test_requests_carry_the_key_and_the_account_in_the_path_and_never_log_it():
    t = FakeTransport({("GET", f"/{ACCOUNT}/users/ravi-sample"): (200, profile())})
    prof = UnipileClient("SECRET-KEY", ACCOUNT, transport=t).get_profile("https://www.linkedin.com/in/ravi-sample")
    assert (prof.provider_id, prof.is_connected, prof.first_name) == ("prov_ravi", False, "Ravi")
    assert t.requests[0]["headers"]["X-API-KEY"] == "SECRET-KEY"


def test_first_degree_means_connected_and_self_is_detected():
    assert (
        UnipileClient("k", ACCOUNT, transport=FakeTransport({("GET", "/"): (200, profile("FIRST_DEGREE"))}))
        .get_profile("x")
        .is_connected
    )
    assert UnipileClient("k", ACCOUNT, transport=FakeTransport({("GET", "/"): (200, profile("SELF"))})).get_profile("x").is_self


def test_unknown_profiles_return_none_and_other_errors_raise():
    assert (
        UnipileClient(
            "k", ACCOUNT, transport=FakeTransport({("GET", "/"): (404, {"type": "not_found", "detail": "x"})})
        ).get_profile("x")
        is None
    )
    with pytest.raises(UnipileError) as err:
        UnipileClient("k", ACCOUNT, transport=FakeTransport({("GET", "/"): (500, {"detail": "boom"})})).get_profile("x")
    assert err.value.status == 500


def test_error_text_never_contains_the_api_key():
    t = FakeTransport({("GET", "/"): (401, {"detail": "bad key SECRET-KEY"})})
    with pytest.raises(UnipileError) as err:
        UnipileClient("SECRET-KEY", ACCOUNT, transport=t).get_profile("x")
    assert "SECRET-KEY" not in str(err.value)


def test_invite_is_sent_with_the_message_truncated_to_300():
    p, t = provider(
        {
            ("GET", f"/{ACCOUNT}/users/ravi-sample"): (200, profile()),
            ("POST", f"/{ACCOUNT}/users/me/relation-requests"): (200, {}),
        }
    )
    res = p.send(ravi(), INVITE, "", "x" * 400, NOW)
    sent = t.requests[-1]
    assert res.ok and sent["body"] == {"user_id": "prov_ravi", "message": "x" * 300}


def test_already_connected_skips_the_invite_without_calling_the_invite_endpoint():
    p, t = provider({("GET", f"/{ACCOUNT}/users/ravi-sample"): (200, profile("FIRST_DEGREE"))})
    res = p.send(ravi(), INVITE, "", "hi", NOW)
    assert (res.ok, res.skip_reason) == (False, "already_connected")
    assert all(r["method"] == "GET" for r in t.requests)


def test_dm_goes_through_the_chat_endpoint_to_the_provider_id():
    p, t = provider(
        {
            ("GET", f"/{ACCOUNT}/users/ravi-sample"): (200, profile("FIRST_DEGREE")),
            ("POST", f"/{ACCOUNT}/inboxes/CLASSIC_PRIMARY/chats/send"): (200, {"chat_id": "chat_9"}),
        }
    )
    res = p.send(ravi(), DM, "", "hello Ravi", NOW)
    assert res.ok and t.requests[-1]["body"] == {"text": "hello Ravi", "users_ids": ["prov_ravi"]}


def test_provider_ids_are_remembered_for_matching_replies_later():
    seen = {}
    p, _ = provider(
        {("GET", f"/{ACCOUNT}/users/ravi-sample"): (200, profile()), ("POST", "/"): (200, {})},
        remember=lambda k, v: seen.update({k: v}),
    )
    p.send(ravi(), INVITE, "", "hi", NOW)
    assert seen == {"r0001": "prov_ravi"}


def test_profile_lookups_are_cached_within_a_provider():
    p, t = provider({("GET", f"/{ACCOUNT}/users/ravi-sample"): (200, profile("FIRST_DEGREE")), ("POST", "/"): (200, {})})
    p.send(ravi(), DM, "", "a", NOW)
    p.send(ravi(), DM, "", "b", NOW)
    assert sum(1 for r in t.requests if r["method"] == "GET") == 1


@pytest.mark.parametrize(
    "status,type_,detail,expected_skip,expected_retry",
    [
        (429, "too_many_requests", "slow down", "", True),
        (403, "checkpoint", "LinkedIn checkpoint", "", True),
        (422, "invalid", "invitation already pending", "invite_already_pending", False),
        (404, "not_found", "not found", "linkedin_unreachable", False),
    ],
)
def test_linkedin_errors_become_the_right_verdict(status, type_, detail, expected_skip, expected_retry):
    p, _ = provider(
        {("GET", f"/{ACCOUNT}/users/ravi-sample"): (200, profile()), ("POST", "/"): (status, {"type": type_, "detail": detail})}
    )
    res = p.send(ravi(), INVITE, "", "hi", NOW)
    assert (res.ok, res.skip_reason, res.retry_later) == (False, expected_skip, expected_retry)


def test_unreachable_profile_and_self_are_skipped():
    p, _ = provider({("GET", "/"): (404, {"type": "not_found", "detail": "x"})})
    assert p.send(ravi(), INVITE, "", "hi", NOW).skip_reason == "linkedin_unreachable"
    p, _ = provider({("GET", "/"): (200, profile("SELF"))})
    assert p.send(ravi(), DM, "", "hi", NOW).skip_reason == "is_self"


def test_email_steps_are_skipped_because_this_provider_only_does_linkedin():
    p, t = provider({})
    assert p.send(ravi(), MAIL, "s", "b", NOW).skip_reason == "channel_not_enabled" and t.requests == []


def test_unexpected_provider_errors_are_failures_not_skips():
    p, _ = provider({("GET", "/"): (500, {"detail": "boom"})})
    res = p.send(ravi(), INVITE, "", "hi", NOW)
    assert not res.ok and not res.skip_reason and not res.retry_later and "500" in res.error


def test_relations_are_listed_for_accept_detection():
    t = FakeTransport(
        {
            ("GET", f"/{ACCOUNT}/users/me/relations"): (
                200,
                {"data": [{"user": {"id": "prov_ravi", "public_identifier": "ravi-sample"}}, {"user": {}}]},
            )
        }
    )
    assert UnipileClient("k", ACCOUNT, transport=t).list_relation_ids(500) == {"prov_ravi"}
    assert "limit=100" in t.requests[0]["query"]


# ---------------------------------------------------------------- webhooks

SECRET = "whsec_test"


def signed(body: str, secret=SECRET, ts=1_700_000_000):
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v0={sig}"


def test_valid_signatures_pass_and_everything_else_fails():
    body = '{"type":"message.new"}'
    ok = signed(body)
    assert verify_signature(body, ok, SECRET, now=1_700_000_100)
    assert not verify_signature(body + " ", ok, SECRET, now=1_700_000_100)  # body tampered
    assert not verify_signature(body, signed(body, "other"), SECRET, now=1_700_000_100)  # wrong secret
    assert not verify_signature(body, ok, SECRET, now=1_700_000_000 + 301)  # replay outside the window
    assert not verify_signature(body, ok, "", now=1_700_000_100)  # no secret configured: always refuse
    assert not verify_signature(body, None, SECRET) and not verify_signature(body, "garbage", SECRET)


def test_message_new_from_someone_else_is_a_reply_event():
    ev = parse_webhook(
        {
            "type": "message.new",
            "account_id": ACCOUNT,
            "payload": {"id": "m1", "chat_id": "c1", "is_sender": False, "sender_id": "prov_ravi", "text": "hey!"},
        },
        ACCOUNT,
    )
    assert (ev.kind, ev.provider_id, ev.text) == ("reply", "prov_ravi", "hey!")


def test_our_own_messages_other_accounts_and_other_events_are_ignored():
    base = {
        "type": "message.new",
        "account_id": ACCOUNT,
        "payload": {"id": "m1", "chat_id": "c1", "is_sender": True, "sender_id": "x"},
    }
    assert parse_webhook(base, ACCOUNT) is None
    assert (
        parse_webhook({**base, "payload": {**base["payload"], "is_sender": False}, "account_id": "someone_else"}, ACCOUNT) is None
    )
    assert parse_webhook({"type": "account.status.ok", "account_id": ACCOUNT, "payload": {}}, ACCOUNT) is None
    assert parse_webhook("not an object", ACCOUNT) is None
    assert parse_webhook({"type": "message.new", "account_id": ACCOUNT, "payload": {"is_sender": False}}, ACCOUNT) is None
