"""UTM, click-id and referrer normalisation into a fixed list of channels.

Rules run in a stated order. Anything tagged that no rule understands becomes "unmapped";
it is never quietly counted as direct.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

OWN_DOMAIN = "shop.example"

SOURCE_ALIASES = {
    "fb": "facebook", "facebook.com": "facebook", "meta": "facebook", "ig": "instagram", "li": "linkedin",
    "linkedin.com": "linkedin", "lnkd": "linkedin", "t.co": "twitter", "x": "twitter", "adwords": "google",
    "google-ads": "google", "googleads": "google", "bing-ads": "bing", "newsletter": "email",
}
SOCIAL = {"facebook", "instagram", "linkedin", "twitter", "tiktok", "reddit", "youtube"}
SEARCH = {"google", "bing", "duckduckgo", "yahoo", "ecosia"}
PAID_MEDIA = {"cpc", "ppc", "paid", "paidsearch", "paidsocial", "paid_social", "cpm", "sem"}
DISPLAY_MEDIA = {"display", "banner", "cpm", "programmatic"}
EMAIL_MEDIA = {"email", "e_mail", "mail", "newsletter"}
RETARGETING = re.compile(r"(?<![a-z])(retargeting|retarget|remarketing|rtg|rmkt)(?![a-z])")
NONBRAND = re.compile(r"(?<![a-z])(non[ _-]?brand(ed)?|nb|generic)(?![a-z])")
BRAND = re.compile(r"(?<![a-z])(brand|branded|brnd)(?![a-z])")


@dataclass(frozen=True)
class Normalised:
    channel: str
    rule: str


def _clean(value: str) -> str:
    return re.sub(r"[\s-]+", "_", value.strip().lower())


def _host(url: str) -> str:
    host = (urlsplit(url if "//" in url else f"//{url}").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def parse_params(url: str) -> dict[str, str]:
    """Query parameters with lower-cased keys; the first value wins and blanks are dropped."""
    query = parse_qs(urlsplit(url).query, keep_blank_values=False)
    result: dict[str, str] = {}
    for key, values in query.items():
        result.setdefault(key.lower(), values[0].strip())
    return {k: v for k, v in result.items() if v}


def _campaign_kind(campaign: str) -> str | None:
    """'nonbrand' is tested first because it contains the word 'brand'."""
    if NONBRAND.search(campaign):
        return "nonbrand"
    if BRAND.search(campaign):
        return "brand"
    return None


def _search_channel(campaign: str, rule: str) -> Normalised:
    kind = _campaign_kind(campaign)
    if kind is None:
        return Normalised("paid_search_unclassified", rule)
    return Normalised(f"{kind}_search", rule)


def _from_utm(source: str, medium: str, campaign: str) -> Normalised:
    medium_key = medium.replace("_", "")
    if medium in EMAIL_MEDIA or source == "email":
        return Normalised("email", "email_tag")
    if "webinar" in (source, medium):
        return Normalised("webinar", "webinar_tag")
    # After e-mail on purpose: a "remarketing" e-mail is still e-mail, not a retargeting ad.
    if RETARGETING.search(campaign) or RETARGETING.search(medium):
        return Normalised("retargeting", "retargeting_name")
    paid = medium in PAID_MEDIA or medium_key in PAID_MEDIA
    if source in SOCIAL:
        social_paid = paid or medium in DISPLAY_MEDIA
        return Normalised("paid_social" if social_paid else "organic_social", "social_source")
    if medium in DISPLAY_MEDIA:
        return Normalised("display", "display_medium")
    if source in SEARCH and paid:
        return _search_channel(campaign, "paid_search_tag")
    if source in SEARCH and medium == "organic":
        return Normalised("organic_search", "organic_search_tag")
    if medium == "referral":
        return Normalised("referral", "referral_tag")
    return Normalised("unmapped", "unknown_utm")


def _from_referrer(referrer: str) -> Normalised:
    host = _host(referrer)
    if not host:
        return Normalised("unmapped", "unreadable_referrer")
    if host == OWN_DOMAIN or host.endswith("." + OWN_DOMAIN):
        return Normalised("direct", "self_referral")
    label = SOURCE_ALIASES.get(host, host.split(".")[-2] if "." in host else host)
    if label in SEARCH:
        return Normalised("organic_search", "search_referrer")
    if label in SOCIAL:
        return Normalised("organic_social", "social_referrer")
    return Normalised("referral", "other_referrer")


def normalise_channel(landing_url: str, referrer: str = "") -> Normalised:
    if not isinstance(landing_url, str) or not isinstance(referrer, str):
        raise TypeError("landing_url and referrer must be strings")
    params = parse_params(landing_url)
    source = _clean(params.get("utm_source", ""))
    source = SOURCE_ALIASES.get(source.replace("_", "-"), source)
    medium = _clean(params.get("utm_medium", ""))
    campaign = params.get("utm_campaign", "").lower()
    if source or medium:
        return _from_utm(source, medium, campaign)
    if "gclid" in params or "msclkid" in params:
        return _search_channel(campaign, "click_id_only")
    if any(k.startswith("utm_") for k in params):
        return Normalised("unmapped", "incomplete_utm")
    if referrer.strip():
        return _from_referrer(referrer.strip())
    # fbclid is appended to unpaid links too, so on its own it is not evidence of an ad.
    if "fbclid" in params:
        return Normalised("organic_social", "fbclid_only")
    return Normalised("direct", "no_signal")


def normalise_pairs(urls: list[str], referrers: list[str]) -> list[str]:
    """Normalise many rows, parsing each distinct (url, referrer) pair once."""
    cache: dict[tuple[str, str], str] = {}
    result = []
    for pair in zip(urls, referrers):
        if pair not in cache:
            cache[pair] = normalise_channel(*pair).channel
        result.append(cache[pair])
    return result
