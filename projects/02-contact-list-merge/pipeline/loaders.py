"""Read the six source files into a common Rec shape; log every row removed as invalid."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

from . import normalize as N

IST = timedelta(hours=5, minutes=30)
EVENT_END = datetime(2026, 9, 19)  # delegate list has no per-row date; summit ran 18-19 Sep


@dataclass(frozen=True)
class Rec:
    source: str
    ref: str
    date: datetime | None
    first: str = ""
    last: str = ""
    full: str = ""
    emails: tuple[str, ...] = ()
    phones: tuple[tuple[str, str], ...] = ()  # (raw, kind) kind: mobile|self|apollo_direct
    company: str = ""
    title: str = ""
    slug: str = ""
    acwaa: str = ""
    person_loc: str = ""
    country: str = ""
    co_size_raw: str = ""
    co_website: str = ""
    co_city: str = ""
    co_country: str = ""
    co_loc_raw: str = ""


@dataclass(frozen=True)
class Removed:
    source: str
    ref: str
    name: str
    company: str
    reason: str


def _rows(path: Path, sheet: str, header_row: int = 0) -> list[dict]:
    ws = openpyxl.load_workbook(path, data_only=True)[sheet]
    rows = list(ws.iter_rows(values_only=True))
    head = rows[header_row]
    return [
        {**{h: v for h, v in zip(head, r, strict=False)}, "_row": i + header_row + 2}
        for i, r in enumerate(rows[header_row + 1:])
        if any(not N.is_blank(v) for v in r)
    ]


def _s(value: object) -> str:
    return "" if N.is_blank(value) else str(value).strip()


def invalid_reason(name: str, company: str, title: str, email: str) -> str:
    text = f"{name} {company} {title} {email}".lower()
    if re.search(r"\b(test|asdf|qa)\b|\.invalid", text):
        return "test/spam lead"
    if re.search(r"looking for job|job seek|\bstudent\b|\bfreelanc", text):
        return "job seeker / freelancer"
    if name.strip().lower() == "linkedin member":
        return "hidden LinkedIn Member"
    # A blank company is NOT rejected here: it may be enriched from another source.
    # Clusters that end up with no company anywhere are dropped after merging.
    if company.strip().lower() in {"self", "none", "n/a", "-"}:
        return "no company"
    return ""


def _gads(path: Path) -> list[Rec]:
    out = []
    for r in _rows(path / "01_GoogleAds_LeadForm_Export.xlsx", "leads"):
        when = datetime.strptime(_s(r["Time submitted"]).replace(" IST", ""), "%Y-%m-%d %H:%M:%S") - IST
        full = N.clean_name(r["Full name"])
        out.append(Rec(
            "Google Ads", f"leads!{r['_row']}", when, full=full,
            emails=(_s(r["Work email"]),), phones=((_s(r["Phone number"]), "self"),),
            company=_s(r["Company name"]), title=_s(r["Job title"]),
            person_loc=_s(r["City"]), co_size_raw=_s(r["How many employees does your company have?"]),
        ) if str(r["Is test"]).upper() != "TRUE" else Rec("Google Ads", f"leads!{r['_row']}", when,
                                                          full=full, company=_s(r["Company name"]),
                                                          title="TEST", emails=(_s(r["Work email"]),)))
    return out


def _event(path: Path) -> list[Rec]:
    f = path / "02_Event_Delegates_and_Scans.xlsx"
    out = []
    for r in _rows(f, "Delegate List", header_row=4):
        if not isinstance(r["S.No"], int):
            continue
        out.append(Rec(
            "Event Delegate", f"Delegate List!{r['_row']}", EVENT_END, full=N.clean_name(r["Name of Delegate"]),
            emails=(_s(r["Email ID"]),), phones=((_s(r["Contact No"]), "self"),),
            company=_s(r["Organisation"]), title=_s(r["Designation"]),
            person_loc=_s(r["City"]), co_size_raw=_s(r["Emp Strength"]),
        ))
    for r in _rows(f, "Booth Scans"):
        when = datetime.strptime(_s(r["Scan Time"]), "%d/%m/%Y %H:%M") - IST
        phones = [(_s(r["Phone"]), "self")]
        note_phone = N.phone_from_notes(r["Notes"])
        if note_phone:
            phones.append((note_phone, "self"))
        out.append(Rec(
            "Event Booth Scan", f"Booth Scans!{r['_row']}", when, full=N.clean_name(r["Full Name"]),
            emails=(_s(r["Email"]),), phones=tuple(phones), company=_s(r["Company"]),
            title=_s(r["Job Title"]),
        ))
    return out


def _linkedin_form(path: Path) -> list[Rec]:
    out = []
    for r in _rows(path / "03_LinkedIn_LeadGenForm_Export.xlsx", "leads"):
        when = datetime.strptime(_s(r["Submitted At"]), "%m/%d/%Y, %I:%M %p")
        first, last = N.clean_name(r["First Name"]), N.clean_name(r["Last Name"])
        out.append(Rec(
            "LinkedIn Lead Gen Form", f"leads!{r['_row']}", when, first=first, last=last,
            full=f"{first} {last}".strip(), emails=(_s(r["Email Address"]),),
            phones=((_s(r["Phone Number"]), "self"),), company=_s(r["Company Name"]),
            title=_s(r["Job Title"]), slug=N.linkedin_slug(r["LinkedIn Profile"]),
            person_loc=_s(r["City"]), country=N.country_name(r["Country"]),
            co_size_raw=_s(r["Company Size"]),
        ))
    return out


def _scraped(path: Path) -> list[Rec]:
    out = []
    for r in _rows(path / "04_LinkedIn_Scraped_SalesNav.xlsx", "result"):
        when = datetime.strptime(_s(r["timestamp"]).replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S")
        links = " ".join(_s(r[k]) for k in ("defaultProfileUrl", "linkedInProfileUrl", "profileUrl"))
        slug = N.linkedin_slug(r["defaultProfileUrl"]) or N.linkedin_slug(r["linkedInProfileUrl"])
        out.append(Rec(
            "LinkedIn Scraped", f"result!{r['_row']}", when,
            first=N.clean_name(r["firstName"]), last=N.clean_name(r["lastName"]),
            full=N.clean_name(r["fullName"]), company=_s(r["companyName"]), title=_s(r["title"]),
            slug=slug, acwaa=N.linkedin_acwaa(links), person_loc=_s(r["location"]),
            co_loc_raw=_s(r["companyLocation"]),
        ))
    return out


def _apollo(path: Path) -> list[Rec]:
    out = []
    for r in _rows(path / "05_ThirdParty_Apollo_Export.xlsx", "apollo-contacts-export"):
        verified = _s(r["Primary Email Last Verified At"])
        when = datetime.fromisoformat(verified).replace(tzinfo=None) if verified else None
        first, last = N.clean_name(r["First Name"]), N.clean_name(r["Last Name"])
        out.append(Rec(
            "Apollo", f"apollo-contacts-export!{r['_row']}", when, first=first, last=last,
            full=f"{first} {last}", emails=(_s(r["Email"]),),
            phones=((_s(r["Mobile Phone"]), "mobile"), (_s(r["Work Direct Phone"]), "apollo_direct")),
            company=_s(r["Company"]), title=_s(r["Title"]), slug=N.linkedin_slug(r["Person Linkedin Url"]),
            person_loc=_s(r["City"]), country=N.country_name(r["Country"]),
            co_size_raw=_s(r["# Employees"]), co_website=_s(r["Website"]),
            co_city=_s(r["Company City"]), co_country=N.country_name(r["Company Country"]),
        ))
    return out


def _zoominfo(path: Path) -> list[Rec]:
    out = []
    for r in _rows(path / "06_ThirdParty_ZoomInfo_Export.xlsx", "ZoomInfo Contacts"):
        first, last = N.clean_name(r["First Name"]), N.clean_name(r["Last Name"])
        out.append(Rec(  # ZoomInfo has no populated date fields -> date None
            "ZoomInfo", f"ZoomInfo Contacts!{r['_row']}", None, first=first, last=last,
            full=f"{first} {last}", emails=(_s(r["Email Address"]),),
            phones=((_s(r["Mobile phone"]), "mobile"),),  # "Direct Phone Number" deliberately not read
            company=_s(r["Company Name"]), title=_s(r["Job Title"]),
            slug=N.linkedin_slug(r["LinkedIn Contact Profile URL"]),
            person_loc=_s(r["Person City"]), country=N.country_name(r["Country"]),
            co_size_raw=_s(r["Employees"]), co_website=_s(r["Website"]),
            co_city=_s(r["Company City"]), co_country=N.country_name(r["Company Country"]),
        ))
    return out


LOADERS: tuple[Callable[[Path], list[Rec]], ...] = (
    _gads, _event, _linkedin_form, _scraped, _apollo, _zoominfo)


def load_all(folder: Path) -> tuple[list[Rec], list[Removed]]:
    kept: list[Rec] = []
    removed: list[Removed] = []
    for loader in LOADERS:
        for rec in loader(folder):
            reason = invalid_reason(rec.full, rec.company, rec.title, " ".join(rec.emails))
            if reason:
                removed.append(Removed(rec.source, rec.ref, rec.full, rec.company, reason))
            else:
                kept.append(rec)
    return kept, removed
