"""Step 2: check every contact and remove records that are invalid, duplicated or opted out.

Email checks here are offline (syntax, disposable and typo domains, role accounts). They tell you an address is
well-formed and plausible, not that the mailbox exists. Confirming a mailbox needs an SMTP-level verifier such
as a paid verification API; plug one in by implementing `EmailVerifier` (the engine never cares which one ran).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from . import constants as C
from .models import Contact, Removed

DISPOSABLE = frozenset(
    {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "yopmail.com", "trashmail.com"}
)
TYPO_DOMAINS = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gmail.con": "gmail.com",
    "gamil.com": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "outlok.com": "outlook.com",
}
ROLE_LOCALS = frozenset({"info", "sales", "admin", "support", "hello", "contact", "office", "team", "hr", "careers", "billing"})
NO_REPLY_LOCALS = frozenset({"noreply", "no-reply", "donotreply", "do-not-reply"})
OPT_OUT_STATUSES = frozenset({"opted out", "opt out", "optout", "unsubscribed", "do not contact", "dnc", "unsub", "suppressed"})

_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_SLUG = re.compile(r"^[A-Za-z0-9_%-]{3,100}$")


@dataclass(frozen=True)
class EmailVerdict:
    status: str  # "valid" | "risky" | "invalid"
    reason: str = ""


class EmailVerifier(Protocol):
    def verify(self, email: str) -> EmailVerdict: ...


class OfflineVerifier:
    def verify(self, email: str) -> EmailVerdict:
        if not email:
            return EmailVerdict("invalid", "empty address")
        if email.count("@") != 1:
            return EmailVerdict("invalid", "address needs exactly one @")
        local, domain = email.split("@")
        if not local:
            return EmailVerdict("invalid", "missing local part")
        if len(local) > 64 or len(email) > 254:
            return EmailVerdict("invalid", "address too long")
        if not _LOCAL.match(local):
            return EmailVerdict("invalid", "bad characters or dots in the local part (space, leading or double dot)")
        if not domain:
            return EmailVerdict("invalid", "missing domain")
        labels = domain.split(".")
        if len(labels) < 2:
            return EmailVerdict("invalid", "domain needs a dot")
        if not all(_LABEL.match(label) for label in labels):
            return EmailVerdict("invalid", "bad domain (empty label, double dot or leading hyphen)")
        if not re.fullmatch(r"[A-Za-z]{2,}", labels[-1]):
            return EmailVerdict("invalid", "bad top-level domain")
        d = domain.lower()
        if d in TYPO_DOMAINS:
            return EmailVerdict("invalid", f"likely typo, did you mean {TYPO_DOMAINS[d]}?")
        if d in DISPOSABLE:
            return EmailVerdict("invalid", "disposable address")
        base = local.lower().split("+")[0]
        if base in NO_REPLY_LOCALS:
            return EmailVerdict("invalid", "no-reply address")
        if base in ROLE_LOCALS:
            return EmailVerdict("risky", "role account")
        return EmailVerdict("valid")


def normalize_linkedin_url(raw: str) -> tuple[str | None, str]:
    """Return (canonical URL, "") when usable, ("", "") for a blank, or (None, reason) when it is not a profile URL."""
    text = raw.strip()
    if not text:
        return "", ""
    parts = urlsplit(text if "//" in text else f"https://{text}")
    host = (parts.hostname or "").lower()
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return None, "not a linkedin.com address"
    segments = [s for s in parts.path.split("/") if s]
    if not segments or segments[0] != "in":
        kind = segments[0] if segments else "empty path"
        return None, f"not a personal profile (/{kind}); use the /in/ URL"
    if len(segments) < 2 or not _SLUG.match(segments[1]):
        return None, "profile name missing or malformed"
    return f"https://www.linkedin.com/in/{segments[1].lower()}", ""


def linkedin_slug(url: str) -> str:
    return url.rsplit("/", 1)[-1].lower() if url else ""


@dataclass(frozen=True)
class Suppression:
    emails: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()
    linkedin: frozenset[str] = frozenset()

    def hit(self, email: str, slug: str) -> str:
        """Why this person is suppressed, or "" if not."""
        domain = email.rsplit("@", 1)[-1] if email else ""
        if email and email in self.emails:
            return f"email {email} is on the suppression list"
        if slug and slug in self.linkedin:
            return f"LinkedIn profile {slug} is on the suppression list"
        for blocked in self.domains:
            if domain == blocked or domain.endswith("." + blocked):
                return f"domain {blocked} is on the suppression list"
        return ""


def load_suppression(path: str | Path) -> Suppression:
    """One entry per line: an e-mail, @domain, or a LinkedIn /in/ URL. `#` starts a comment; a `value` header is ignored."""
    p = Path(path)
    if not p.exists():
        return Suppression()
    emails: set[str] = set()
    domains: set[str] = set()
    slugs: set[str] = set()
    with p.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            value = row[0].strip() if row else ""
            if not value or value.startswith("#") or value.lower() == "value":
                continue
            if value.startswith("@"):
                domains.add(value[1:].lower())
            elif "linkedin.com" in value.lower():
                url, _ = normalize_linkedin_url(value)
                if url:
                    slugs.add(linkedin_slug(url))
            else:
                emails.add(value.lower())
    return Suppression(frozenset(emails), frozenset(domains), frozenset(slugs))


@dataclass(frozen=True)
class ValidationReport:
    valid: tuple[Contact, ...] = ()
    removed: tuple[Removed, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)


def validate_contacts(
    contacts: list[Contact] | tuple[Contact, ...], suppression: Suppression, verifier: EmailVerifier
) -> ValidationReport:
    valid: list[Contact] = []
    removed: list[Removed] = []
    seen_email: dict[str, Contact] = {}
    seen_slug: dict[str, Contact] = {}

    for original in contacts:
        flags = list(original.flags)
        if not original.name.strip():
            removed.append(Removed(original, C.MISSING_NAME, "no name, so nothing can be personalised"))
            continue

        email = original.email.strip().lower()
        verdict = verifier.verify(email) if email else EmailVerdict("invalid", "no e-mail")
        email_reason = verdict.reason if email else ""
        if email and verdict.status == "invalid":
            flags.append(f"email_cleared:invalid ({verdict.reason})")
            email = ""
        elif verdict.status == "risky":
            flags.append(f"email_risky:{verdict.reason}")

        linkedin, li_reason = normalize_linkedin_url(original.linkedin_url)
        if linkedin is None:
            flags.append(f"linkedin_cleared:{li_reason}")
            linkedin = ""
        slug = linkedin_slug(linkedin)

        status = original.source_status.strip().lower()
        why = "status column says " + original.source_status.strip() if status in OPT_OUT_STATUSES else ""
        why = why or suppression.hit(original.email.strip().lower(), slug) or suppression.hit(email, slug)
        if why:
            removed.append(Removed(original, C.OPTED_OUT, why))
            continue

        if not email and not linkedin:
            reason = C.INVALID_EMAIL if email_reason else (C.INVALID_LINKEDIN if original.linkedin_url.strip() else C.NO_CHANNEL)
            detail = email_reason or (li_reason if original.linkedin_url.strip() else "no e-mail and no LinkedIn URL")
            removed.append(Removed(original, reason, detail))
            continue

        twin = seen_email.get(email) if email else None
        twin = twin or (seen_slug.get(slug) if slug else None)
        if twin is not None:
            removed.append(Removed(original, C.DUPLICATE, f"same person as {twin.key} (first occurrence kept)"))
            continue

        kept = replace(original, email=email, linkedin_url=linkedin, flags=tuple(flags))
        valid.append(kept)
        if email:
            seen_email[email] = kept
        if slug:
            seen_slug[slug] = kept
    return ValidationReport(tuple(valid), tuple(removed))
