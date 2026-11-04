"""Group records that describe the same real person."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from . import normalize as N
from .loaders import Rec


@dataclass(frozen=True)
class Prepared:
    rec: Rec
    company_c: str
    title_c: str
    emails: tuple[tuple[str, str], ...]  # (email, status ok|repaired)
    phones: tuple[tuple[str, str], ...]  # (E.164, kind)
    country: str
    city: str


@dataclass(frozen=True)
class Link:
    kind: str
    a: str
    b: str
    note: str


def company_universe(recs: list[Rec]) -> tuple[tuple[str, ...], dict[str, str], frozenset[str]]:
    """Canonical names (ZoomInfo first, then Apollo) -> HQ country; known website domains."""
    names: dict[str, str] = {}
    domains: set[str] = set()
    for source in ("ZoomInfo", "Apollo"):
        for r in (x for x in recs if x.source == source):
            names.setdefault(r.company.strip(), r.co_country)
            domains.add(N.root_domain(r.co_website))
    return tuple(names), names, frozenset(d for d in domains if d)


def prepare(recs: list[Rec]) -> list[Prepared]:
    canon, hq_country, domains = company_universe(recs)
    out = []
    for r in recs:
        company_c = N.match_company(r.company, canon)
        city, loc_country = N.city_country(r.person_loc)
        country = r.country or loc_country or hq_country.get(company_c, "")
        emails = []
        for raw in r.emails:
            for cand in N.split_emails(raw):
                status, fixed = N.classify_email(cand, domains)
                if status in ("ok", "repaired"):
                    emails.append((fixed, status))
        phones = []
        for raw, kind in r.phones:
            e164, _ = N.parse_mobile(raw, country)
            if e164:
                phones.append((e164, kind))
        out.append(Prepared(r, company_c, N.canonical_title(r.title), tuple(emails),
                            tuple(phones), country, city))
    return out


class _Groups:
    """Union-find over record indices; refuses merges that would join two different LinkedIn identities."""

    def __init__(self, preps: list[Prepared]) -> None:
        self.parent = list(range(len(preps)))
        self.slugs = [{p.rec.slug} - {""} for p in preps]
        self.acwaa = [{p.rec.acwaa} - {""} for p in preps]
        self.refused: list[tuple[int, int, str]] = []

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int, why: str) -> bool:
        ri, rj = self.find(i), self.find(j)
        if ri == rj:
            return True
        if (self.slugs[ri] and self.slugs[rj] and not self.slugs[ri] & self.slugs[rj]) or (
                self.acwaa[ri] and self.acwaa[rj] and not self.acwaa[ri] & self.acwaa[rj]):
            self.refused.append((i, j, why))
            return False
        self.parent[rj] = ri
        self.slugs[ri] |= self.slugs[rj]
        self.acwaa[ri] |= self.acwaa[rj]
        return True


def _strong_keys(p: Prepared) -> list[str]:
    keys = [f"email:{e}" for e, _ in p.emails]
    keys += [f"phone:{ph}" for ph, _ in p.phones]
    if p.rec.slug:
        keys.append(f"slug:{p.rec.slug}")
    if p.rec.acwaa:
        keys.append(f"acwaa:{p.rec.acwaa}")
    return keys


def _same_name(a: Prepared, b: Prepared) -> bool:
    ka, kb = N.name_key(a.rec.first or a.rec.full.split(" ")[0], _last(a)), N.name_key(
        b.rec.first or b.rec.full.split(" ")[0], _last(b))
    return ka == kb


def _last(p: Prepared) -> str:
    if p.rec.last and p.rec.first:
        # structured: take the family name relative to the given first name
        return p.rec.full[len(p.rec.first):].strip() if p.rec.full.startswith(p.rec.first) else p.rec.last
    parts = p.rec.full.split(" ", 1)
    return parts[1] if len(parts) > 1 else ""


def build_clusters(preps: list[Prepared]) -> tuple[list[list[Prepared]], list[Link]]:
    groups = _Groups(preps)
    links: list[Link] = []
    seen: dict[str, int] = {}
    for i, p in enumerate(preps):                      # 1. strong keys
        for key in _strong_keys(p):
            if key in seen:
                groups.union(seen[key], i, key)
            else:
                seen[key] = i
    for i, j in combinations(range(len(preps)), 2):    # 2. name + company + compatible title
        a, b = preps[i], preps[j]
        if groups.find(i) == groups.find(j) or not a.company_c or a.company_c != b.company_c:
            continue
        if _same_name(a, b) and (not a.title_c or not b.title_c or a.title_c == b.title_c):
            if groups.union(i, j, "name+company+title"):
                links.append(Link("name+company+title", a.rec.ref, b.rec.ref,
                                  f"{a.rec.full} @ {a.company_c} ({a.title_c or b.title_c})"))
    for i, j in combinations(range(len(preps)), 2):    # 3. job changers: same name, same city, new employer
        a, b = preps[i], preps[j]
        if groups.find(i) == groups.find(j) or not a.company_c or not b.company_c:
            continue
        if a.company_c != b.company_c and a.city and a.city == b.city and _same_name(a, b):
            if groups.union(i, j, "job-change"):
                links.append(Link("job-change (verify)", a.rec.ref, b.rec.ref,
                                  f"{a.rec.full}: {a.company_c} / {b.company_c}, both in {a.city}"))
    buckets: dict[int, list[Prepared]] = {}
    for i, p in enumerate(preps):
        buckets.setdefault(groups.find(i), []).append(p)
    for i, j, why in groups.refused:
        links.append(Link("REFUSED merge", preps[i].rec.ref, preps[j].rec.ref,
                          f"{why}: different LinkedIn identities"))
    return list(buckets.values()), links
