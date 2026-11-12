"""The deterministic safety rules for AI messaging. These are plain code, never prompts: a model can be talked
into things, code cannot. Everything here fails closed (when in doubt, a human decides)."""

from __future__ import annotations

import re

from .. import constants as C

INVITE_MAX = C.LINKEDIN_INVITE_MAX_CHARS
DM_MAX = 800
EMAIL_BODY_MAX = 1800
SUBJECT_MAX = 70
INBOUND_MAX = 1500  # a reply this long is a conversation a person should read

_OPT_OUT = re.compile(
    r"\b(stop (messaging|contacting|emailing|writing|sending)|stop it|unsubscribe|remove me|take me off|"
    r"do not contact|don'?t contact|not interested|no thanks|no thank you|leave me alone|opt[- ]?out|"
    r"geen interesse|niet ge[iï]nteresseerd|stop met|verwijder mij)\b"
    r"|^\W*stop\W*$",
    re.I,
)
_HUMAN_ONLY = re.compile(
    r"\b(pric(e|es|ing)|quote|cost of|contract|legal|lawyer|attorney|gdpr|complain\w*|scam|spam|harass\w*|"
    r"report (you|this)|sue|invoice|refund)\b",
    re.I,
)
_URL = re.compile(r"(https?://|www\.)", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(\+\d[\d\s().-]{6,}\d)|(\b\d{8,}\b)")
_PLACEHOLDER = re.compile(r"\{\{|\}\}|\{[a-z_]+\}", re.I)
_LEAK = re.compile(r"as an ai\b|language model|system prompt|my instructions|i am an ai|i'm an ai", re.I)


def is_opt_out(text: str) -> bool:
    """True when someone is asking us to stop. Checked before any AI is involved."""
    return bool(_OPT_OUT.search(text))


def needs_human(text: str) -> bool:
    """True for replies a person should answer: money, legal, complaints, or anything too long to skim."""
    return len(text) > INBOUND_MAX or bool(_HUMAN_ONLY.search(text))


def check_output(channel: str, subject: str, text: str, limit: int | None = None) -> list[str]:
    """Problems with a message before it may be sent. An empty list means it is safe to send."""
    found: list[str] = []
    body = text.strip()
    if not body:
        return ["message is empty"]
    cap = limit or {C.LINKEDIN_INVITE: INVITE_MAX, C.LINKEDIN_MESSAGE: DM_MAX, C.EMAIL: EMAIL_BODY_MAX}.get(channel, DM_MAX)
    if len(body) > cap:
        found.append(f"message is too long ({len(body)} characters, limit {cap})")
    if _URL.search(body):
        found.append("message contains a link")
    if _EMAIL.search(body):
        found.append("message contains an email address")
    if _PHONE.search(body):
        found.append("message contains a phone number")
    if _PLACEHOLDER.search(body) or _PLACEHOLDER.search(subject):
        found.append("message contains an unfilled placeholder")
    if _LEAK.search(body):
        found.append("message talks about its own instructions")
    if channel == C.EMAIL and (not subject.strip() or len(subject) > SUBJECT_MAX):
        found.append(f"email needs a subject of at most {SUBJECT_MAX} characters")
    return found
