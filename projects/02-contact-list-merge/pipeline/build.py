"""Resolve one clean output row (plus an audit trail) from each cluster of records."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from . import normalize as N
from .cluster import Prepared
from .loaders import Rec

COLUMNS = ("Company Name", "Website", "HQ Location", "Company Size", "Contact Person Name",
           "First Name", "Last Name", "Designation/Job Title", "LinkedIn URL", "Mobile No.", "Email ID")
_MIN = datetime.min
_STRUCTURED = {"LinkedIn Lead Gen Form": 0, "ZoomInfo": 1, "Apollo": 2, "LinkedIn Scraped": 3,
               "Event Delegate": 4, "Event Booth Scan": 5, "Google Ads": 6}


@dataclass(frozen=True)
class Person:
    row: dict
    flags: tuple[str, ...]
    refs: tuple[str, ...]


def _when(p: Prepared) -> datetime:
    return p.rec.date or _MIN


def _most_common(values: list[str]) -> str:
    return Counter(values).most_common(1)[0][0] if values else ""


# --------------------------------------------------------------------------- company facts
def company_facts(company: str, all_preps: list[Prepared]) -> dict:
    """Rule 4: ZoomInfo first, then Apollo, then everything else."""
    at = [p for p in all_preps if p.company_c == company]
    facts = {"Company Name": company, "Website": "", "HQ Location": "", "Company Size": ""}
    for source in ("ZoomInfo", "Apollo"):
        rows = [p.rec for p in at if p.rec.source == source]
        if not facts["Website"]:
            facts["Website"] = _most_common([N.root_domain(r.co_website) for r in rows if r.co_website])
        if not facts["HQ Location"]:
            facts["HQ Location"] = _hq(_most_common([r.co_city for r in rows if r.co_city]),
                                       _most_common([r.co_country for r in rows if r.co_country]))
        if not facts["Company Size"]:
            facts["Company Size"] = _most_common(
                [N.size_bucket(r.co_size_raw) for r in rows if N.size_bucket(r.co_size_raw)])
    if not facts["Company Size"]:
        facts["Company Size"] = _most_common(
            [N.size_bucket(p.rec.co_size_raw) for p in at if N.size_bucket(p.rec.co_size_raw)])
    if not facts["HQ Location"]:
        facts["HQ Location"] = _most_common(
            [_hq(*N.city_country(p.rec.co_loc_raw)) for p in at if N.city_country(p.rec.co_loc_raw)[0]])
    return facts


def _hq(city: str, country: str) -> str:
    canon_city, canon_country = N.city_country(city)
    city = canon_city or city
    country = country or canon_country
    return f"{city}, {country}" if city and country else ""


# --------------------------------------------------------------------------- person facts
def _current(cluster: list[Prepared]) -> tuple[str, str]:
    """Rule 3: most recent dated source wins for employer, then for title at that employer."""
    dated = sorted((p for p in cluster if p.company_c), key=_when, reverse=True)
    company = dated[0].company_c
    titled = [p for p in dated if p.company_c == company and p.title_c]
    return company, (titled[0].title_c if titled else "")


def _name(cluster: list[Prepared]) -> tuple[str, str, str]:
    slugs = {p.rec.slug for p in cluster} - {""}
    cands = [(p.rec.full, _STRUCTURED[p.rec.source]) for p in cluster if p.rec.full]
    if slugs:
        target = N.letters(N.slug_to_name(next(iter(slugs))))
        matched = [c for c in cands if N.letters(c[0]) == target]
        cands = matched or cands
    counts = Counter(c[0] for c in cands)
    best = max(counts, key=lambda n: (counts[n], -min(r for c, r in cands if c == n)))
    for p in cluster:  # prefer a structured first/last pair that reproduces the chosen name
        if p.rec.first and p.rec.last and N.letters(p.rec.first + p.rec.last) == N.letters(best):
            return best, p.rec.first, p.rec.last
    first, _, last = best.partition(" ")
    return best, first, last


def _email(cluster: list[Prepared], domain: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    score: dict[str, tuple] = {}
    for p in cluster:
        for email, status in p.emails:
            dom = email.split("@")[1]
            rank = (dom == domain, not N.is_personal_domain(email))
            old = score.get(email, (rank, 0, _MIN, status))
            merged = "ok" if "ok" in (old[3], status) else "repaired"  # clean in any source = no repair needed
            score[email] = (rank, old[1] + 1, max(old[2], _when(p)), merged)
    if not score:
        return "", ["no valid email in any source"]
    best = max(score, key=lambda e: score[e][:3])
    rank, _, _, status = score[best]
    if status == "repaired":
        flags.append(f"email typo repaired to {best} (domain confirmed from ZoomInfo/Apollo)")
    if not rank[1]:
        flags.append("personal email used: no work email in any source")
    elif not rank[0]:
        flags.append("work email is on a previous employer's domain: no current-employer email found")
    return best, flags


def _mobile(cluster: list[Prepared]) -> tuple[str, list[str]]:
    seen: dict[str, list[tuple[str, str]]] = {}
    for p in cluster:
        for number, kind in p.phones:
            seen.setdefault(number, []).append((kind, p.rec.source))
    usable: dict[str, tuple] = {}
    flags: list[str] = []
    for number, hits in seen.items():
        kinds = [k for k, _ in hits]
        if set(kinds) == {"apollo_direct"}:
            flags.append(f"{number} only in Apollo 'Work Direct Phone' (uncorroborated): excluded as a direct line")
            continue
        usable[number] = ("mobile" in kinds, len(hits))
    if not usable:
        return "", flags or ["no mobile number in any source"]
    return max(usable, key=lambda n: usable[n]), flags


def build_person(cluster: list[Prepared], all_preps: list[Prepared]) -> Person:
    company, title = _current(cluster)
    facts = company_facts(company, all_preps)
    name, first, last = _name(cluster)
    slugs = sorted({p.rec.slug for p in cluster} - {""})
    email, flags = _email(cluster, facts["Website"])
    mobile, mflags = _mobile(cluster)
    if len({p.company_c for p in cluster if p.company_c}) > 1:
        flags.append("employer changed across sources: latest dated source used ("
                     + " / ".join(sorted({p.company_c for p in cluster if p.company_c})) + ")")
    if len(slugs) == 0:
        flags.append("no public LinkedIn slug in any source (Sales Navigator / ACwAA ids only)")
    row = {**facts, "Contact Person Name": name, "First Name": first, "Last Name": last,
           "Designation/Job Title": title, "LinkedIn URL": N.linkedin_url(slugs[0]) if slugs else "",
           "Mobile No.": mobile, "Email ID": email}
    refs = tuple(f"{p.rec.source}: {p.rec.ref}" for p in cluster)
    return Person(row, tuple(flags + mflags), refs)


def build_all(clusters: list[list[Prepared]], all_preps: list[Prepared]) -> tuple[list[Person], list[tuple]]:
    people, dropped = [], []
    for cluster in clusters:
        if not any(p.company_c for p in cluster):
            dropped.append(cluster)
            continue
        people.append(build_person(cluster, all_preps))
    people.sort(key=lambda p: (p.row["Company Name"], p.row["Last Name"], p.row["First Name"]))
    return people, dropped


__all__ = ["COLUMNS", "Person", "build_all", "build_person", "company_facts", "Rec"]
