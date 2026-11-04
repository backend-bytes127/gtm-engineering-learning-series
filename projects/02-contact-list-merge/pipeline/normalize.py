"""Pure field normalizers: each takes raw input and returns a new cleaned value."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from . import constants as C

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF‍️]+"
)
_PARENS = re.compile(r"\([^)]*\)")


def is_blank(value: object) -> bool:
    return value is None or (isinstance(value, float) and value != value) or str(value).strip() == ""


def strip_emoji(text: str) -> str:
    return _EMOJI.sub("", text)


# --------------------------------------------------------------------------- names
def _cap_token(token: str) -> str:
    return "'".join(part[:1].upper() + part[1:].lower() for part in token.split("'"))


def clean_name(raw: object) -> str:
    """Proper-cased name without salutations, credentials, pronouns, emoji."""
    if is_blank(raw):
        return ""
    text = _PARENS.sub(" ", strip_emoji(str(raw)))
    parts = [p.strip() for p in text.split(",") if p.strip()]
    parts = [p for p in parts if p.lower().strip(".") not in C.CREDENTIALS]
    if len(parts) == 2:  # "Last, First"
        parts = [parts[1], parts[0]]
    tokens = " ".join(parts).split()
    while tokens and tokens[0].lower().strip(".") in C.SALUTATIONS and len(tokens) > 1:
        tokens = tokens[1:]
    return " ".join(_cap_token(t) for t in tokens)


def slug_to_name(slug: str) -> str:
    """Letters-only name embedded in a LinkedIn slug (id suffix removed)."""
    base = re.sub(r"-[0-9a-f]{8}$", "", slug.lower())
    base = re.sub(r"\d+$", "", base)
    return base.replace("-", " ").strip()


def letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def alias_first(first: str) -> str:
    low = first.lower()
    return C.FIRST_NAME_ALIASES.get(low, low)


def name_key(first: str, last: str) -> str:
    return f"{alias_first(first.split()[0]) if first else ''}|{letters(last)}"


# --------------------------------------------------------------------------- titles
def canonical_title(raw: object) -> str:
    if is_blank(raw):
        return ""
    text = strip_emoji(str(raw)).split("|")[0].lower().replace(".", "")
    tokens: list[str] = []
    for tok in re.findall(r"[a-z]+", text):
        if tok in C.TITLE_DROP_TOKENS:
            continue
        tokens.extend(C.TOKEN_EXPANSIONS.get(tok, [tok]))
    if not tokens:
        return ""
    words = " ".join
    if "chief" in tokens:
        func = next((t for t in tokens if t in {"executive", "technology", "revenue",
                                                 "marketing", "operating", "financial"}), "")
        return f"Chief {func.title()} Officer".replace("  ", " ")
    func_tokens = [t for t in tokens if t not in {"vice", "president", "director", "head",
                                                   "manager", "senior", "lead"}]
    func = words(func_tokens).title()
    if "vice" in tokens:
        return f"Vice President of {func}".strip()
    if "director" in tokens:
        return f"Director of {func}".strip()
    if "head" in tokens:
        return f"Head of {func}".strip()
    if "manager" in tokens:
        prefix = "Senior " if "senior" in tokens else ""
        return f"{prefix}{func} Manager".replace("  ", " ").strip()
    if "lead" in tokens:
        return f"{func} Lead".strip()
    return words(tokens).title()


# --------------------------------------------------------------------------- email
def _domain_ok(domain: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}", domain))


def split_emails(raw: object) -> list[str]:
    if is_blank(raw):
        return []
    text = str(raw).lower().replace("mailto:", "")
    out = []
    for part in re.split(r"[;,\s]+(?=\S+@)|;", text):
        item = re.sub(r"\s+", "", part).replace("@@", "@")
        if item:
            out.append(item)
    return out


def classify_email(email: str, known_domains: frozenset[str]) -> tuple[str, str]:
    """Return (status, repaired_email). status: ok|repaired|generic|invalid."""
    if email in C.PLACEHOLDER_EMAILS or email.count("@") != 1:
        return "invalid", ""
    local, domain = email.split("@")
    if domain in C.TEST_EMAIL_DOMAINS or domain.endswith(C.INVALID_EMAIL_DOMAIN_SUFFIXES):
        return "invalid", ""
    if local in C.GENERIC_MAILBOXES:
        return "generic", ""
    if domain in known_domains:
        return "ok", email
    # typo repair only when the corrected domain is a confirmed company domain
    candidates = [re.sub(r"\.con$", ".com", domain)]
    candidates += [d for d in known_domains if d.startswith(domain + ".")]
    for cand in candidates:
        if cand != domain and cand in known_domains:
            return "repaired", f"{local}@{cand}"
    return ("ok", email) if _domain_ok(domain) else ("invalid", "")


def is_personal_domain(email: str) -> bool:
    return email.split("@")[-1] in C.PERSONAL_EMAIL_DOMAINS


# --------------------------------------------------------------------------- phone
_PHONE_RULES = {
    "IN": (r"\+91[6-9]\d{9}", "91", 12), "US": (r"\+1\d{10}", "1", 11),
    "GB": (r"\+447\d{9}", "44", 12), "AE": (r"\+9715\d{8}", "971", 12),
    "SG": (r"\+65[89]\d{7}", "65", 10),
}


def _all_fake(digits: str) -> bool:
    return len(set(digits)) == 1 or digits in {"1234567890", "0123456789", "9876543210"}


def _valid(e164: str) -> bool:
    return any(re.fullmatch(rule[0], e164) for rule in _PHONE_RULES.values())


def parse_mobile(raw: object, country: str = "") -> tuple[str | None, str]:
    """Return (E.164 or None, reason). Rejects landlines, placeholders, truncated floats."""
    if is_blank(raw):
        return None, "empty"
    text = str(raw).strip().lstrip("'")
    if text.lower() in C.PLACEHOLDER_PHONES:
        return None, "placeholder"
    if re.fullmatch(r"\d\.\d+E\+\d+", text, re.I):
        return None, "scientific-notation (digits lost)"
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    if re.match(r"^0\d{2,4}-\d{6,8}$", text):
        return None, "landline (STD code)"
    text = re.sub(r"\([^)\d]*[A-Za-z][^)]*\)", "", text)  # "(WhatsApp)", not "(415)"
    digits = re.sub(r"\D", "", text)
    if not digits or _all_fake(digits[-10:]):
        return None, "fake/placeholder number"
    if text.startswith("+"):
        cand = "+" + digits
    elif digits.startswith("00"):
        cand = "+" + digits[2:]
    else:
        cand = _national(digits, C.COUNTRY_ISO.get(country, ""))
    return (cand, "ok") if cand and _valid(cand) else (None, f"unrecognised format ({text})")


def _national(digits: str, iso: str) -> str:
    for rule_iso, (_, prefix, length) in _PHONE_RULES.items():
        if len(digits) == length and digits.startswith(prefix) and rule_iso != "US":
            return "+" + digits
    if len(digits) == 11 and digits.startswith("1") and iso == "US":
        return "+" + digits
    if iso == "IN":
        digits = digits[1:] if len(digits) == 11 and digits.startswith("0") else digits
        return "+91" + digits if len(digits) == 10 else ""
    if iso == "US":
        return "+1" + digits if len(digits) == 10 else ""
    if iso == "SG":
        return "+65" + digits if len(digits) == 8 else ""
    if iso == "AE":
        digits = digits[1:] if digits.startswith("0") else digits
        return "+971" + digits if len(digits) == 9 else ""
    return ""


def phone_from_notes(notes: object) -> str:
    match = re.search(r"Mob\s+(\d{7,12})", str(notes or ""))
    return match.group(1) if match else ""


# --------------------------------------------------------------------------- linkedin
def linkedin_slug(raw: object) -> str:
    """Public slug, or '' for Sales Navigator links, ACwAA ids and non-profile URLs."""
    if is_blank(raw):
        return ""
    text = str(raw).strip()
    match = re.search(r"linkedin\.com/in/([^/?#,\s]+)", text, re.I)
    if not match:
        return ""
    slug = match.group(1).lower()
    return "" if slug.startswith("acwa") else slug


def linkedin_acwaa(raw: object) -> str:
    match = re.search(r"/in/(ACwA[^/?#,\s]+)|/lead/(ACwA[^,/?#\s]+)", str(raw or ""))
    return (match.group(1) or match.group(2)).lower() if match else ""


def linkedin_url(slug: str) -> str:
    return f"https://www.linkedin.com/in/{slug}" if slug else ""


# --------------------------------------------------------------------------- company
def _strip_legal(name: str) -> str:
    text = strip_emoji(name).strip().lower()
    for _ in range(2):
        for suffix in sorted(C.LEGAL_SUFFIXES, key=len, reverse=True):
            if text.endswith(" " + suffix):
                text = text[: -len(suffix)].strip(" ,.")
    return re.sub(r"\s+", " ", text)


def match_company(raw: object, canonical: tuple[str, ...]) -> str:
    """Map a raw company string onto a canonical name (typos, suffixes, short forms)."""
    if is_blank(raw):
        return ""
    cleaned = _strip_legal(str(raw))
    by_norm = {_strip_legal(c): c for c in canonical}
    if cleaned in by_norm:
        return by_norm[cleaned]
    prefixed = [c for n, c in by_norm.items() if n.startswith(cleaned + " ")]
    if len(prefixed) == 1:
        return prefixed[0]
    squashed = cleaned.replace(" ", "")
    best, score = "", 0.0
    for norm, canon in by_norm.items():
        ratio = SequenceMatcher(None, squashed, norm.replace(" ", "")).ratio()
        if ratio > score:
            best, score = canon, ratio
    return best if score >= 0.86 else ""


def root_domain(raw: object) -> str:
    if is_blank(raw):
        return ""
    text = re.sub(r"^[a-z]+://", "", str(raw).strip().lower())
    host = re.split(r"[/?#]", text)[0]
    return re.sub(r"^www\.", "", host)


def size_bucket(value: object) -> str:
    """Bucket a number or a 'a-b' / 'a to b' range (upper bound is used for ranges)."""
    if is_blank(value):
        return ""
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", str(value))]
    if not nums:
        return ""  # SMB / Enterprise / Mid-Market are not sizes
    count = nums[0] if len(nums) == 1 else (nums[0] + nums[1]) // 2
    for upper, label in C.SIZE_BUCKETS:
        if count <= upper:
            return label
    return C.SIZE_TOP


# --------------------------------------------------------------------------- location
def city_country(raw: object) -> tuple[str, str]:
    """Best-effort (city, country) from a messy location string; '' when unknown."""
    if is_blank(raw):
        return "", ""
    low = strip_emoji(str(raw)).lower()
    first = low.split(",")[0].strip()
    if first in C.CITY_INFO:
        return C.CITY_INFO[first]
    for key in C.CITY_KEYWORDS:
        if key in low:
            return C.CITY_INFO[key]
    return "", ""


def country_name(raw: object) -> str:
    return C.COUNTRY_ALIASES.get(str(raw or "").strip().lower(), "")
