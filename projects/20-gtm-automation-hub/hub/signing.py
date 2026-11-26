"""HMAC signing and verification for the hub's own webhooks and for Slack's request signature.

Both schemes sign ``version:timestamp:raw_body`` with HMAC-SHA256. The raw bytes matter: parsing
JSON and serialising it again can change spacing or key order and break the signature.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass

TOLERANCE_SECONDS = 300
MIN_SECRET_LENGTH = 16
_TIMESTAMP = re.compile(r"[0-9]{1,12}")


@dataclass(frozen=True)
class Scheme:
    version: str
    timestamp_header: str
    signature_header: str


GENERIC = Scheme("v1", "x-gtm-timestamp", "x-gtm-signature")
SLACK = Scheme("v0", "x-slack-request-timestamp", "x-slack-signature")


@dataclass(frozen=True)
class Verification:
    ok: bool
    reason: str  # ok, not_configured, missing_headers, bad_timestamp, stale_timestamp, bad_signature


def sign(scheme: Scheme, secret: str, timestamp: int | str, body: bytes) -> str:
    base = f"{scheme.version}:{timestamp}:".encode() + body
    return f"{scheme.version}=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def signed_headers(scheme: Scheme, secret: str, timestamp: int, body: bytes) -> dict[str, str]:
    return {scheme.timestamp_header: str(timestamp), scheme.signature_header: sign(scheme, secret, timestamp, body)}


def verify(
    scheme: Scheme, secret: str, headers: Mapping[str, str], body: bytes, now: float, tolerance: int = TOLERANCE_SECONDS
) -> Verification:
    """Fail closed: a missing or short secret rejects everything."""
    if len(secret or "") < MIN_SECRET_LENGTH:
        return Verification(False, "not_configured")
    lowered = {key.lower(): value for key, value in headers.items()}
    timestamp = lowered.get(scheme.timestamp_header, "")
    signature = lowered.get(scheme.signature_header, "")
    if not timestamp or not signature:
        return Verification(False, "missing_headers")
    if not _TIMESTAMP.fullmatch(timestamp):
        return Verification(False, "bad_timestamp")
    if abs(now - int(timestamp)) > tolerance:
        return Verification(False, "stale_timestamp")
    expected = sign(scheme, secret, timestamp, body)
    if not hmac.compare_digest(expected.encode(), signature.encode("utf-8", "replace")):
        return Verification(False, "bad_signature")
    return Verification(True, "ok")
