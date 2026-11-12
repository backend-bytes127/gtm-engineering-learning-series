"""One shared password for a single-user deployment. Fails closed: no password configured means no public access.

Sessions are a signed expiry timestamp in an HttpOnly, SameSite=Strict cookie (no server-side session store, so a
redeploy does not log you out, and rotating SESSION_SECRET logs everyone out). Wrong guesses are rate limited.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable

COOKIE = "seq_session"
TTL_SECONDS = 12 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 60
MIN_PASSWORD = 12
MIN_SECRET = 32


def parse_cookies(header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            out[name] = value
    return out


class Auth:
    def __init__(self, password: str, secret: str, now: Callable[[], float] = time.time):
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"APP_PASSWORD must be at least {MIN_PASSWORD} characters")
        if len(secret) < MIN_SECRET:
            raise ValueError(f"SESSION_SECRET must be at least {MIN_SECRET} characters")
        self._password = hashlib.sha256(password.encode()).digest()
        self._secret = secret.encode()
        self._now = now
        self.ttl = TTL_SECONDS
        self._failures: list[float] = []

    # --- tokens
    def _sign(self, expiry: int) -> str:
        return hmac.new(self._secret, str(expiry).encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        expiry = int(self._now()) + self.ttl
        return f"{expiry}.{self._sign(expiry)}"

    def expiry_of(self, token: str) -> int:
        return int(token.split(".", 1)[0])

    def valid(self, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        stamp, _, sig = token.partition(".")
        if not stamp.isdigit():
            return False
        expiry = int(stamp)
        return expiry > self._now() and hmac.compare_digest(sig, self._sign(expiry))

    def authenticated(self, headers: dict[str, str]) -> bool:
        return self.valid(parse_cookies(headers.get("cookie", "")).get(COOKIE))

    # --- login
    def locked(self) -> bool:
        cutoff = self._now() - LOCK_SECONDS
        self._failures = [t for t in self._failures if t > cutoff]
        return len(self._failures) >= MAX_FAILURES

    def check_password(self, candidate: str) -> bool:
        ok = hmac.compare_digest(hashlib.sha256(candidate.encode()).digest(), self._password)
        if not ok:
            self._failures.append(self._now())
        return ok

    def cookie_header(self, token: str, secure: bool) -> tuple[str, str]:
        flags = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={self.ttl}" + ("; Secure" if secure else "")
        return ("Set-Cookie", flags)

    @staticmethod
    def clear_header(secure: bool) -> tuple[str, str]:
        return ("Set-Cookie", f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" + ("; Secure" if secure else ""))
