"""Step 4: message templates with personalisation variables, a linter, and per-contact draft checks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from . import constants as C
from .models import Contact, Issue, Sender, Template

# Contact-derived variables count as personalisation. Sender variables do not.
CONTACT_VARS = ("first_name", "last_name", "name", "company", "title")
SENDER_VARS = ("sender_name", "sender_company", "unsubscribe_line")
KNOWN_VARS = CONTACT_VARS + SENDER_VARS

_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\|([^{}]*))?\}\}")
SPAM_PHRASES = (
    "act now",
    "100%",
    "risk free",
    "risk-free",
    "guarantee",
    "free ",
    "winner",
    "click here",
    "limited time",
    "no obligation",
)
MAX_EMAIL_WORDS = 150
MAX_SUBJECT_CHARS = 70
MAX_DM_CHARS = 700


@dataclass(frozen=True)
class Rendered:
    text: str
    missing: tuple[str, ...] = ()  # variables with no value and no fallback
    fallbacks: tuple[str, ...] = ()  # variables filled from their fallback


def variables_in(text: str) -> list[str]:
    seen: list[str] = []
    for m in _VAR.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def _unsubscribe_line(sender: Sender) -> str:
    return (
        f'If you would rather not hear from me, reply "unsubscribe" and I will not contact you again. '
        f"{sender.name}, {sender.company}, {sender.postal_address}"
    )


def _values(contact: Contact, sender: Sender) -> dict[str, str]:
    return {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "name": contact.name,
        "company": contact.company,
        "title": contact.title,
        "sender_name": sender.name,
        "sender_company": sender.company,
        "unsubscribe_line": _unsubscribe_line(sender),
    }


def render(text: str, contact: Contact, sender: Sender) -> Rendered:
    """Substitute variables in a single pass, so a value that itself contains `{{x}}` is never re-evaluated."""
    values = _values(contact, sender)
    missing: list[str] = []
    fallbacks: list[str] = []

    def sub(m: re.Match) -> str:
        name, fallback = m.group(1), m.group(2)
        value = values.get(name, "").strip()
        if value:
            return value
        if fallback is not None and fallback.strip():
            if name not in fallbacks:
                fallbacks.append(name)
            return fallback.strip()
        if name not in missing:
            missing.append(name)
        return ""

    return Rendered(_VAR.sub(sub, text), tuple(missing), tuple(fallbacks))


def lint_template(t: Template) -> list[Issue]:
    """Contact-independent checks. Errors block approval; warnings are advice."""
    issues: list[Issue] = []

    def add(severity: str, code: str, message: str) -> None:
        issues.append(Issue(severity, code, message))

    if t.channel not in C.CHANNELS:
        add("error", "bad_channel", f"channel must be one of {', '.join(C.CHANNELS)}")
    if not t.body.strip():
        add("error", "empty_body", "the message body is empty")
    used = variables_in(t.body) + variables_in(t.subject)
    for name in used:
        if name not in KNOWN_VARS:
            add("error", "unknown_variable", f"{{{{{name}}}}} is not a known variable (use {', '.join(KNOWN_VARS)})")
    if not any(v in CONTACT_VARS for v in used):
        add(
            "error",
            "no_personalisation",
            f"uses no contact variable ({', '.join(CONTACT_VARS)}), so every recipient gets identical text",
        )

    if t.channel == C.EMAIL:
        if not t.subject.strip():
            add("error", "missing_subject", "an email needs a subject")
        elif len(t.subject) > MAX_SUBJECT_CHARS:
            add(
                "warning",
                "long_subject",
                f"subject is {len(t.subject)} characters; over {MAX_SUBJECT_CHARS} gets cut off on phones",
            )
        if "unsubscribe_line" not in variables_in(t.body):
            add("error", "missing_unsubscribe", "an email must include {{unsubscribe_line}} (opt-out and sender address)")
        words = len(re.sub(r"\{\{[^}]*\}\}", "x", t.body).split())
        if words > MAX_EMAIL_WORDS:
            add("warning", "long_email", f"{words} words; cold emails under {MAX_EMAIL_WORDS} get read")
    if t.channel == C.LINKEDIN_INVITE:
        worst = _worst_case_length(t.body)
        if worst > C.LINKEDIN_INVITE_MAX_CHARS:
            add("error", "invite_too_long", f"invite can reach {worst} characters; LinkedIn allows {C.LINKEDIN_INVITE_MAX_CHARS}")
    if t.channel == C.LINKEDIN_MESSAGE and len(t.body) > MAX_DM_CHARS:
        add("warning", "long_dm", f"{len(t.body)} characters; short DMs get answered")

    lowered = f"{t.subject} {t.body}".lower()
    hits = [p.strip() for p in SPAM_PHRASES if p in lowered]
    if hits:
        add("warning", "spam_words", f"spam-filter phrases: {', '.join(hits)}")
    letters = re.sub(r"[^A-Za-z]", "", re.sub(r"\{\{[^}]*\}\}", "", t.subject + t.body))
    if "!!" in t.body or "!!" in t.subject or (len(letters) > 20 and sum(ch.isupper() for ch in letters) / len(letters) > 0.35):
        add("warning", "shouting", "too many exclamation marks or capital letters")
    if len(re.findall(r"https?://", t.body)) > 1:
        add("warning", "many_links", "more than one link hurts deliverability")
    return issues


_WORST_CASE = {
    "first_name": 20,
    "last_name": 25,
    "name": 40,
    "company": 40,
    "title": 50,
    "sender_name": 30,
    "sender_company": 40,
    "unsubscribe_line": 0,
}


def _worst_case_length(body: str) -> int:
    """Length if every variable took a generous maximum value; fallbacks count at their own length when longer."""

    def sub(m: re.Match) -> str:
        return "x" * max(_WORST_CASE.get(m.group(1), 0), len(m.group(2) or ""))

    return len(_VAR.sub(sub, body))


def check_draft(t: Template, contact: Contact, sender: Sender) -> list[Issue]:
    """Per-contact check of the message that would actually go out. Any error means this draft must not be sent."""
    issues: list[Issue] = []
    body = render(t.body, contact, sender)
    subject = render(t.subject, contact, sender)
    missing = tuple(dict.fromkeys(body.missing + subject.missing))
    if missing:
        issues.append(Issue("error", "missing_data", f"{contact.key} ({contact.name}) has no value for: {', '.join(missing)}"))
    if t.channel == C.LINKEDIN_INVITE and len(body.text) > C.LINKEDIN_INVITE_MAX_CHARS:
        issues.append(Issue("error", "invite_too_long", f"{contact.key}: invite is {len(body.text)} characters after filling in"))
    return issues


def approval_hash(t: Template) -> str:
    """Fingerprint of what will be sent. Approval is bound to it, so editing an approved template un-approves it."""
    return hashlib.sha256(f"{t.channel}\x00{t.subject}\x00{t.body}".encode()).hexdigest()
