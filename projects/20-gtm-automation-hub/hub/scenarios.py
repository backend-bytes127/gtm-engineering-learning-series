"""One scripted tour of every webhook path. The offline simulation and the n8n run both execute this list."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from hub import signing
from hub.pipeline import MAX_BODY_BYTES, Request, Settings

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
APPROVER = "U0SYNTHETIC1"


@dataclass(frozen=True)
class Step:
    name: str
    route: str  # signal, pql or click
    status: int
    outcome: str
    build: Callable[[int], Request] | None = None
    resend: str | None = None  # send an earlier step's exact bytes and headers again
    fail_next: int = 0  # the fake Slack rejects this many posts
    content_type: str | None = None  # n8n parses bodies labelled JSON itself; see the README


def sample(name: str) -> dict[str, Any]:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def _encode(value: Any) -> bytes:
    return value if isinstance(value, bytes) else json.dumps(value).encode()


class Tour:
    """Request builders. ``offset`` shifts the timestamp so that two signatures of one body differ."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def signed(self, payload: Any, offset: int = 0) -> Callable[[int], Request]:
        def build(now: int) -> Request:
            body = _encode(payload)
            return Request(signing.signed_headers(signing.GENERIC, self.settings.webhook_secret, now + offset, body), body)

        return build

    def click(
        self, key: str, offset: int = 0, action: str = "pql_approve", user: str = APPROVER, reply: str | None = None, kind: str = ""
    ) -> Callable[[int], Request]:
        def build(now: int) -> Request:
            payload = {
                **sample("slack_click.synthetic.json"),
                "type": kind or "block_actions",
                "user": {"id": user},
                "actions": [{"action_id": action, "value": key}],
                "response_url": reply or f"{self.settings.response_url_prefix}reply/{key}",
            }
            body = urlencode({"payload": json.dumps(payload)}).encode()
            return Request(signing.signed_headers(signing.SLACK, self.settings.slack_signing_secret, now + offset, body), body)

        return build


def _tampered(builder: Callable[[int], Request]) -> Callable[[int], Request]:
    def build(now: int) -> Request:
        request = builder(now)
        return Request(request.headers, request.body + b" ")

    return build


def _bare(payload: Any) -> Callable[[int], Request]:
    return lambda now: Request({}, _encode(payload))


def signal_steps(tour: Tour) -> list[Step]:
    first = sample("signal.synthetic.json")
    second = {**first, "event_id": "syn-evt-0002"}
    third = {**first, "event_id": "syn-evt-0003"}
    hostile = {**first, "event_id": "syn-evt-0004", "source": "<!channel> & <b>"}
    s, ok = tour.signed, "delivered"
    return [
        Step("valid signal", "signal", 200, ok, s(first)),
        Step("exact replay", "signal", 409, "replay", resend="valid signal"),
        Step("same event, new signature", "signal", 200, "duplicate", s(first, -30)),
        Step("body changed after signing", "signal", 401, "bad_signature", _tampered(s(second))),
        Step("timestamp 10 minutes old", "signal", 401, "stale_timestamp", s(second, -600)),
        Step("timestamp 10 minutes ahead", "signal", 401, "stale_timestamp", s(second, 600)),
        Step("unsigned", "signal", 401, "missing_headers", _bare(second)),
        Step("signed, not JSON", "signal", 422, "invalid_json", s(b"{not json"), content_type="text/plain"),
        Step("signed, NaN is not JSON", "signal", 422, "invalid_json", s(b'{"score": NaN}'), content_type="text/plain"),
        Step("signed, wrong fields", "signal", 422, "invalid_schema", s({**second, "type": "other", "account_domain": "no spaces"})),
        Step("body over the size limit", "signal", 413, "too_large", s({"pad": "x" * MAX_BODY_BYTES})),
        Step("Slack down for all three tries", "signal", 502, "delivery_failed", s(second), fail_next=3),
        Step("sender retries after the failure", "signal", 200, ok, s(second, -60)),
        Step("Slack fails once, retry works", "signal", 200, ok, s(third), fail_next=1),
        Step("mention injection is escaped", "signal", 200, ok, s(hostile)),
    ]


def pql_steps(tour: Tour) -> list[Step]:
    lead = sample("pql_lead.synthetic.json")

    def other(number: int, **changes: Any) -> dict[str, Any]:
        visitor = f"syn-visitor-{number:03d}"
        return {**lead, "visitor_key": visitor, "idempotency_key": f"{visitor}:{lead['score_version']}", **changes}

    key1, key2, key3, key4 = (other(n)["idempotency_key"] for n in (1, 2, 3, 4))
    s, c = tour.signed, tour.click
    return [
        Step("tier A lead is sent for review", "pql", 200, "pending", s(lead)),
        Step("same lead again", "pql", 200, "duplicate", s(lead, -30)),
        Step("tier B lead is not sent", "pql", 200, "not_routed", s(other(9, tier="B_nudge"))),
        Step("idempotency key does not match", "pql", 422, "invalid_schema", s({**lead, "idempotency_key": "x:y"})),
        Step("click with a forged signature", "click", 401, "bad_signature", _tampered(c(key1))),
        Step("click by a user not on the list", "click", 200, "not_allowed", c(key1, -1, user="U0SOMEONEELSE")),
        Step("approve", "click", 200, "approved", c(key1)),
        Step("click replayed", "click", 409, "replay", resend="approve"),
        Step("second click on a decided lead", "click", 200, "already_decided", c(key1, -2, action="pql_dismiss")),
        Step("second lead", "pql", 200, "pending", s(other(2))),
        Step("dismiss", "click", 200, "dismissed", c(key2, action="pql_dismiss")),
        Step("click for a lead never sent", "click", 200, "unknown_lead", c("constructor")),
        Step("not a button click", "click", 200, "unsupported_interaction", c(key1, -3, kind="view_submission")),
        Step("third lead", "pql", 200, "pending", s(other(3))),
        Step("reply URL on another host", "click", 200, "approved", c(key3, reply="https://hooks.slack.com.evil.example/x")),
        Step("lead while Slack is down", "pql", 502, "delivery_failed", s(other(4)), fail_next=3),
        Step("no click possible on an unsent lead", "click", 200, "unknown_lead", c(key4)),
    ]


def all_steps(settings: Settings) -> list[Step]:
    tour = Tour(settings)
    return [*signal_steps(tour), *pql_steps(tour)]
