"""The deterministic safety rules for AI messaging. These are plain code, never prompts: a model can be talked
into things, code cannot. Everything here fails closed (when in doubt, a human decides)."""

from __future__ import annotations

import re
import unicodedata

from .. import constants as C

INVITE_MAX = C.LINKEDIN_INVITE_MAX_CHARS
DM_MAX = 800
EMAIL_BODY_MAX = 1800
SUBJECT_MAX = 70
INBOUND_MAX = 1500  # a reply this long is a conversation a person should read

# Matched against `_fold(text)`: lower case, accents removed, typographic apostrophes made plain.
# Covered: English, Dutch, German, French and Spanish, common wording only. This will miss other phrasings.
_OPT_OUT_PATTERNS = (
    # English
    r"\bstop (messaging|contacting|emailing|writing|sending|texting|reaching out)\b",
    r"\bplease stop\b(?!\s+(by|in|over|at)\b)",
    r"^\W*(please\W+)?stop(\W+please)?\W*$",
    r"\b(stop it|unsubscribe|remove me|take me off|leave me alone|opt[- ]?out|not interested|no thanks|no thank you)\b",
    r"\b(do not|don'?t) (contact|message|email|write to|text) (me|us)\b",
    r"\b(do not|don'?t) contact\b",
    r"\bno more (messages|emails|mails)\b",
    # Dutch
    r"\b(geen interesse|niet geinteresseerd|stop met|verwijder mij|geen berichten meer|uitschrijven)\b",
    r"\bniet meer (benaderen|mailen|berichten|contacteren)\b",
    # German
    r"\b(abmelden|abbestellen|kein interesse)\b",
    r"\bkeine (weiteren )?(nachrichten|e-?mails|mails|kontaktaufnahmen?)\b",
    r"\b(nicht mehr (kontaktieren|anschreiben|schreiben|melden)|kontaktieren sie mich nicht)\b",
    # French
    r"\b(ne plus me (contacter|ecrire)|ne me (contactez|ecrivez) plus|desinscri\w*|me desabonner|pas interessee?)\b",
    # Spanish
    r"\b(no me (contacten?|contactes|escriban?)|darme de baja|dar de baja|no me interesa|no estoy interesad[oa])\b",
)
# Erasure and other data-rights requests: stop all automation AND hand to a person, who has to act on the data.
_DATA_PATTERNS = (
    r"\b(remove|delete|erase|wipe) (all )?(of )?my (personal )?(data|information|info|details)\b",
    r"\bright to be forgotten\b",
    r"\b(losch\w*|loesch\w*)( sie)?( bitte)? meine (personenbezogenen )?daten\b|\bmeine daten (loschen|loeschen)\b",
    r"\b(supprim\w+|effac\w+) mes (donnees|informations)\b",
    r"\b(borr\w+|elimin\w+|suprim\w+) mis datos\b",
    r"\bverwijder mijn gegevens\b|\bmijn gegevens (wissen|verwijderen)\b",
)
_OPT_OUT = re.compile("|".join(_OPT_OUT_PATTERNS))
_DATA_REQUEST = re.compile("|".join(_DATA_PATTERNS))
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\u00b4": "'", "`": "'"})

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


def _fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.translate(_APOSTROPHES))
    return " ".join("".join(ch for ch in plain if not unicodedata.combining(ch)).casefold().split())


def is_opt_out(text: str) -> bool:
    """True when someone is asking us to stop. Checked before any AI is involved."""
    return bool(_OPT_OUT.search(_fold(text)))


def is_data_request(text: str) -> bool:
    """True when someone asks for their data to be erased. This stops automation and needs a person."""
    return bool(_DATA_REQUEST.search(_fold(text)))


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
