"""Slack button clicks: parse the form body, check the action, and guard the reply URL."""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from urllib.parse import parse_qs

from hub.messages import APPROVE, DISMISS

DECISIONS = {APPROVE: "approved", DISMISS: "dismissed"}
SLACK_PREFIX = "https://hooks.slack.com/"


class InteractionError(ValueError):
    """The request is signed but is not a button click this app understands."""


@dataclass(frozen=True)
class Click:
    key: str
    decision: str
    user_id: str
    response_url: str


def parse_click(body: bytes) -> Click:
    try:
        payload = json.loads(parse_qs(body.decode())["payload"][0])
        action = payload["actions"][0]
        click = Click(action["value"], DECISIONS[action["action_id"]], payload["user"]["id"], payload.get("response_url", ""))
        kind = payload["type"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise InteractionError("unsupported interaction") from error
    fields = (click.key, click.user_id, click.response_url)
    if kind != "block_actions" or not all(isinstance(value, str) for value in fields):
        raise InteractionError("unsupported interaction")
    if not (click.user_id.isascii() and click.user_id.isalnum()):
        raise InteractionError("unsupported interaction")
    return click


def reply_url_allowed(url: str, prefix: str = SLACK_PREFIX) -> bool:
    """The reply URL arrives inside the request. Only post to the expected host (the prefix must end with a slash)."""
    return prefix.endswith("/") and url.startswith(prefix)


def user_allowed(user_id: str, approvers: Collection[str]) -> bool:
    """An empty allow-list means anyone who can see the message may decide."""
    return not approvers or user_id in approvers
