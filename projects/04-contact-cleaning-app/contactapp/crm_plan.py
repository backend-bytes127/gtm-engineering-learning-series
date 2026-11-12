"""Turn the consolidated list into a CRM update plan. Pure: no network, so it is safe to show before anything is sent.

Rules that protect existing CRM data:
- a contact is matched on e-mail and a company on its domain, so re-running never creates duplicates;
- blank fields are left out of the payload, so a blank in our list can never erase a value already in the CRM;
- a row with no e-mail cannot be matched safely, so it is listed as skipped for a person to handle.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

CONTACT_PROPS = {
    "First Name": "firstname",
    "Last Name": "lastname",
    "Designation/Job Title": "jobtitle",
    "Mobile No.": "mobilephone",
    "LinkedIn URL": "hs_linkedin_url",
}
SIZE_PROPERTY = "gtm_company_size"  # a bucket like "51-200"; HubSpot's own field is a number, so this is a custom text property
CUSTOM_COMPANY_PROPERTIES = (SIZE_PROPERTY,)


@dataclass(frozen=True)
class ContactOp:
    email: str
    properties: Mapping[str, str]
    company_domain: str


@dataclass(frozen=True)
class CompanyOp:
    domain: str
    properties: Mapping[str, str]


@dataclass(frozen=True)
class Skipped:
    name: str
    company: str
    reason: str


@dataclass(frozen=True)
class CrmPlan:
    contacts: tuple[ContactOp, ...]
    companies: tuple[CompanyOp, ...]
    skipped: tuple[Skipped, ...]
    custom_properties: tuple[str, ...] = CUSTOM_COMPANY_PROPERTIES

    @property
    def associations(self) -> int:
        return sum(1 for c in self.contacts if c.company_domain)


def _clean(values: Mapping[str, str]) -> dict[str, str]:
    return {k: v.strip() for k, v in values.items() if v and v.strip()}


def _split_location(hq: str) -> tuple[str, str]:
    city, _, country = (hq or "").partition(",")
    return city.strip(), country.strip()


def _company_props(row: Mapping[str, str], domain: str) -> dict[str, str]:
    city, country = _split_location(row.get("HQ Location", ""))
    return _clean(
        {
            "name": row.get("Company Name", ""),
            "domain": domain,
            "city": city,
            "country": country,
            SIZE_PROPERTY: row.get("Company Size", ""),
        }
    )


def build_plan(rows: Iterable[Mapping[str, str]]) -> CrmPlan:
    contacts: dict[str, ContactOp] = {}
    companies: dict[str, CompanyOp] = {}
    skipped: list[Skipped] = []
    for row in rows:
        email = (row.get("Email ID") or "").strip().lower()
        name, company = row.get("Contact Person Name", ""), row.get("Company Name", "")
        if not email:
            skipped.append(Skipped(name, company, "no e-mail address, so it cannot be matched safely in the CRM"))
            continue
        if email in contacts:
            skipped.append(Skipped(name, company, f"same e-mail as an earlier row ({email})"))
            continue
        domain = (row.get("Website") or "").strip().lower()
        props = _clean({"email": email, **{crm: row.get(col, "") for col, crm in CONTACT_PROPS.items()}})
        contacts[email] = ContactOp(email, props, domain)
        if domain and domain not in companies:
            companies[domain] = CompanyOp(domain, _company_props(row, domain))
    return CrmPlan(tuple(contacts.values()), tuple(companies.values()), tuple(skipped))


def preview(plan: CrmPlan, limit: int = 50) -> dict:
    """A JSON-ready view of the plan for the screen."""
    return {
        "contacts": len(plan.contacts),
        "companies": len(plan.companies),
        "associations": plan.associations,
        "custom_properties": list(plan.custom_properties),
        "skipped": [{"name": s.name, "company": s.company, "reason": s.reason} for s in plan.skipped],
        "sample_contacts": [{"email": c.email, "company": c.company_domain, **c.properties} for c in plan.contacts[:limit]],
        "sample_companies": [dict(c.properties) for c in plan.companies[:limit]],
    }
