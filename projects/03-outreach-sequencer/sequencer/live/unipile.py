"""Unipile (LinkedIn) adapter. Request shapes follow Unipile's v2 API as already verified live in outbound-os.

Everything that touches the network goes through one injectable `transport`, so the tests run offline. The API key
is sent only as a request header and is scrubbed from any error text, so it cannot leak into a log or the browser.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlencode

from .. import constants as C
from ..models import Contact, SendResult, Step

BASE_URL = "https://api.unipile.com/v2"
LINKEDIN_INBOX = "CLASSIC_PRIMARY"
TIMEOUT_SECONDS = 20
SIGNATURE_TOLERANCE = 300
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, str]]


class UnipileError(Exception):
    def __init__(self, status: int, kind: str, detail: str):
        super().__init__(f"Unipile error ({status} {kind}): {detail}"[:300])
        self.status, self.kind, self.detail = status, kind, detail


class LinkedInLimit(UnipileError): ...


class LinkedInDuplicate(UnipileError): ...


class LinkedInUnreachable(UnipileError): ...


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (fixed https base URL)
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        return 599, json.dumps({"type": "network", "detail": f"could not reach Unipile ({type(exc).__name__})"})


def linkedin_identifier(value: str) -> str:
    match = re.search(r"linkedin\.com/in/([^/?#]+)", value, re.I)
    from urllib.parse import unquote

    return unquote(match.group(1) if match else value.strip()).rstrip("/")


@dataclass(frozen=True)
class Profile:
    provider_id: str
    public_identifier: str
    first_name: str
    last_name: str
    is_connected: bool
    is_self: bool


def _classify(status: int, kind: str, detail: str) -> UnipileError:
    text = f"{kind} {detail}".lower()
    if status == 429 or re.search(r"too_many_requests|limit|restrict|temporarily|checkpoint", text):
        return LinkedInLimit(status, kind, detail)
    if re.search(r"already|pending|cannot_resend", text):
        return LinkedInDuplicate(status, kind, detail)
    if status == 404 or re.search(r"not_found|invalid_recipient|unreachable|blocked", text):
        return LinkedInUnreachable(status, kind, detail)
    return UnipileError(status, kind, detail)


class UnipileClient:
    def __init__(self, api_key: str, account_id: str, transport: Transport = urllib_transport, base_url: str = BASE_URL):
        if not api_key or not account_id:
            raise ValueError("A Unipile API key and account id are both required")
        self._key, self.account_id, self._transport, self._base = api_key, account_id, transport, base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"X-API-KEY": self._key, "accept": "application/json"}
        data = None
        if body is not None:
            headers["content-type"] = "application/json"
            data = json.dumps(body).encode()
        status, text = self._transport(method, f"{self._base}{path}", headers, data)
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if status >= 400:
            detail = str(payload.get("detail") or payload.get("title") or text[:200]).replace(self._key, "***")
            raise _classify(status, str(payload.get("type", "")), detail)
        return payload

    def _a(self, tail: str) -> str:
        return f"/{quote(self.account_id, safe='')}{tail}"

    def get_profile(self, identifier: str) -> Profile | None:
        try:
            raw = self._request("GET", self._a(f"/users/{quote(linkedin_identifier(identifier), safe='')}"))
        except LinkedInUnreachable:
            return None
        if not isinstance(raw.get("id"), str) or not raw["id"]:
            return None
        specifics = raw.get("specifics") if isinstance(raw.get("specifics"), dict) else {}
        distance = str(specifics.get("network_distance", "")).upper()
        return Profile(
            raw["id"],
            str(raw.get("public_identifier", "")),
            str(raw.get("first_name", "")),
            str(raw.get("last_name", "")),
            distance == "FIRST_DEGREE",
            distance == "SELF",
        )

    def send_invite(self, provider_id: str, message: str) -> None:
        body = {"user_id": provider_id, **({"message": message[: C.LINKEDIN_INVITE_MAX_CHARS]} if message else {})}
        self._request("POST", self._a("/users/me/relation-requests"), body)

    def start_chat(self, provider_id: str, text: str) -> dict:
        return self._request("POST", self._a(f"/inboxes/{LINKEDIN_INBOX}/chats/send"), {"text": text, "users_ids": [provider_id]})

    def send_chat_message(self, chat_id: str, text: str) -> dict:
        """Reply inside an existing LinkedIn chat."""
        return self._request("POST", self._a(f"/chats/{quote(chat_id, safe='')}/messages/send"), {"text": text})

    def list_relation_ids(self, limit: int = 100) -> set[str]:
        raw = self._request("GET", self._a(f"/users/me/relations?{urlencode({'limit': min(limit, 100)})}"))
        items = raw.get("data") if isinstance(raw.get("data"), list) else []
        ids = {i["user"]["id"] for i in items if isinstance(i, dict) and isinstance(i.get("user"), dict) and i["user"].get("id")}
        return {str(x) for x in ids}


class UnipileProvider:
    """Sends LinkedIn invites and DMs. Anything it cannot or should not do is reported back as a skip or a retry."""

    name = "unipile"

    def __init__(self, client: UnipileClient, remember: Callable[[str, str], None] | None = None):
        self._client, self._remember, self._profiles = client, remember, {}

    def _profile(self, contact: Contact) -> Profile | None:
        if contact.key not in self._profiles:
            self._profiles[contact.key] = self._client.get_profile(contact.linkedin_url)
            found = self._profiles[contact.key]
            if found and self._remember:
                self._remember(contact.key, found.provider_id)
        return self._profiles[contact.key]

    def send(self, contact: Contact, step: Step, subject: str, body: str, now: datetime) -> SendResult:
        if step.channel == C.EMAIL:
            return SendResult(False, skip_reason="channel_not_enabled")
        try:
            profile = self._profile(contact)
            if profile is None:
                return SendResult(False, skip_reason="linkedin_unreachable")
            if profile.is_self:
                return SendResult(False, skip_reason="is_self")
            if step.channel == C.LINKEDIN_INVITE:
                if profile.is_connected:
                    return SendResult(False, skip_reason="already_connected")
                self._client.send_invite(profile.provider_id, body)
            else:
                self._client.start_chat(profile.provider_id, body)
            return SendResult(True, provider_id=f"unipile:{profile.provider_id}:{step.position}")
        except LinkedInLimit as exc:
            return SendResult(False, error=str(exc), retry_later=True)
        except LinkedInDuplicate:
            return SendResult(False, skip_reason="invite_already_pending")
        except LinkedInUnreachable:
            return SendResult(False, skip_reason="linkedin_unreachable")
        except UnipileError as exc:
            return SendResult(False, error=str(exc))


# ---------------------------------------------------------------- webhooks


@dataclass(frozen=True)
class InboundEvent:
    kind: str
    provider_id: str
    text: str
    message_id: str
    chat_id: str = ""


def verify_signature(raw_body: str, header: str | None, secret: str | None, now: float | None = None) -> bool:
    """`unipile-signature: t=<unix>,v0=<hex>` where v0 = HMAC-SHA256(secret, "<t>.<raw body>"). Constant-time, 5-minute window."""
    if not secret or not header:
        return False
    stamp, candidates = None, []
    for part in header.split(","):
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if key == "t" and value.isdigit():
            stamp = int(value)
        elif key == "v0" and re.fullmatch(r"[0-9a-fA-F]+", value):
            candidates.append(value.lower())
    if stamp is None or not candidates or abs((now if now is not None else time.time()) - stamp) > SIGNATURE_TOLERANCE:
        return False
    expected = hmac.new(secret.encode(), f"{stamp}.{raw_body}".encode(), hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(c, expected) for c in candidates)


def parse_webhook(envelope: object, account_id: str) -> InboundEvent | None:
    """Only a `message.new` written by someone else, on our own account, becomes a reply event."""
    if not isinstance(envelope, dict) or envelope.get("type") != "message.new" or envelope.get("account_id") != account_id:
        return None
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or payload.get("is_sender") in (True, 1):
        return None
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    who = str(payload.get("sender_id") or sender.get("id") or "")
    message_id = str(payload.get("id") or "")
    if not who or not message_id:
        return None
    return InboundEvent("reply", who, str(payload.get("text") or ""), message_id, str(payload.get("chat_id") or ""))
