"""Turns a simulated outcome into raw, messy landing events, as a web analytics export would look."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .journeys import DAY
from .world import CHANNELS, Outcome

HORIZON_DAYS = 30
# (earliest day, latest day) for each channel: prospecting is early, intent capture is late.
TIMING = {
    "paid_social": (0, 18),
    "display": (0, 24),
    "nonbrand_search": (1, 20),
    "webinar": (4, 20),
    "retargeting": (10, 27),
    "email": (8, 27),
    "brand_search": (18, 29),
    "direct": (16, 29),
}
BASE = "https://www.shop.example/"
# Several spellings per channel; the normaliser has to bring them back together.
VARIANTS: dict[str, list[tuple[str, str]]] = {
    "paid_social": [
        ("utm_source=facebook&utm_medium=paid_social&utm_campaign=prospecting", ""),
        ("utm_source=FB&utm_medium=CPC&utm_campaign=Prospecting_Q3", ""),
        ("UTM_Source=LinkedIn&utm_medium=paid-social&utm_campaign=abm", "https://www.linkedin.com/"),
    ],
    "display": [
        ("utm_source=google&utm_medium=display&utm_campaign=reach", ""),
        ("utm_source=dsp&utm_medium=Banner&utm_campaign=reach", "https://news.example/"),
    ],
    "nonbrand_search": [
        ("utm_source=google&utm_medium=cpc&utm_campaign=nonbrand_category", "https://www.google.com/"),
        ("utm_source=bing&utm_medium=PPC&utm_campaign=Non-Brand%20Tools", ""),
        ("gclid=abc123&utm_campaign=generic_terms", ""),
    ],
    "webinar": [("utm_source=webinar&utm_medium=event", ""), ("utm_source=partner&utm_medium=Webinar", "")],
    "retargeting": [
        ("utm_source=google&utm_medium=display&utm_campaign=remarketing_30d", ""),
        ("utm_source=meta&utm_medium=paid_social&utm_campaign=rtg-visitors", ""),
    ],
    "email": [("utm_source=newsletter&utm_medium=email", ""), ("utm_source=crm&utm_medium=E-mail&utm_campaign=nurture", "")],
    "brand_search": [
        ("utm_source=google&utm_medium=cpc&utm_campaign=brand_exact", "https://www.google.com/"),
        ("gclid=xyz789&utm_campaign=Brand-Search", ""),
    ],
    "direct": [("", ""), ("", "https://shop.example/pricing")],
}


def emit(outcome: Outcome, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Raw events (journey_id, ts, landing_url, referrer, planted_channel) and the journeys table.

    About 30% of buyers also get e-mail or direct visits after buying; a pipeline that forgets
    the point-in-time rule will credit them.
    """
    rng = np.random.default_rng(seed)
    n = len(outcome.converted)
    conversion_ts = (HORIZON_DAYS + rng.random(n)) * DAY
    frames = []
    for channel in CHANNELS:
        users = np.flatnonzero(outcome.exposed[channel])
        repeats = 1 + rng.binomial(1, 0.25, len(users))
        users = np.repeat(users, repeats)
        low, high = TIMING[channel]
        ts = rng.uniform(low, high + 1, len(users)) * DAY
        frames.append(_rows(channel, users, ts, rng))
    for channel in ("email", "direct"):
        buyers = np.flatnonzero(outcome.converted & (rng.random(n) < 0.3))
        later = conversion_ts[buyers] + rng.uniform(0.01, 5, len(buyers)) * DAY
        frames.append(_rows(channel, buyers, later, rng))
    events = pd.concat(frames, ignore_index=True).sort_values(["journey_id", "ts"], kind="mergesort").reset_index(drop=True)
    ids = np.unique(events["journey_id"].to_numpy())
    # Buyers with no touch at all stay in the table: they are real conversions nobody can credit.
    ids = np.union1d(ids, np.flatnonzero(outcome.converted))
    converted = outcome.converted[ids]
    end = np.where(converted, conversion_ts[ids], (HORIZON_DAYS + 1) * DAY)
    return events, pd.DataFrame({"journey_id": ids, "converted": converted, "end_ts": end})


def _rows(channel: str, users: np.ndarray, ts: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    options = VARIANTS[channel]
    pick = rng.integers(0, len(options), len(users))
    urls = np.array([BASE + (f"?{query}" if query else "") for query, _ in options], dtype=object)
    referrers = np.array([referrer for _, referrer in options], dtype=object)
    return pd.DataFrame(
        {"journey_id": users, "ts": ts, "landing_url": urls[pick], "referrer": referrers[pick], "planted_channel": channel}
    )
