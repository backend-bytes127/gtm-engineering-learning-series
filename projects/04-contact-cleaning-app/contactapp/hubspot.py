"""A small HubSpot client (standard library only) and the push that applies a CrmPlan.

The transport is injectable so every call can be tested without a network. Contacts and companies are upserted in
batches of 100, then read back by their match key to learn their ids, then associated.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from .crm_plan import CrmPlan

BASE = "https://api.hubapi.com"
BATCH = 100
Transport = Callable[[str, str, Mapping[str, str], bytes | None], tuple[int, dict]]


class CrmError(Exception):
    """A HubSpot call failed. The message is safe to show: it never contains the token."""


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method=method, headers=dict(headers))  # noqa: S310 (fixed https host)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310
            raw = res.read()
            return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"message": "non-JSON error body"}
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CrmError(f"Could not reach HubSpot: {exc.__class__.__name__}") from exc


def _chunks(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class HubSpotClient:
    def __init__(self, token: str, transport: Transport = urllib_transport, sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise CrmError("No HubSpot token is configured.")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._transport, self._sleep = transport, sleep

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        for attempt in range(4):
            status, data = self._transport(method, BASE + path, self._headers, body)
            if status in (429, 500, 502, 503, 504) and attempt < 3:
                self._sleep(min(2 ** attempt, 8))
                continue
            if status >= 400:
                raise CrmError(f"HubSpot returned {status} for {method} {path}: {str(data.get('message', ''))[:200]}")
            return data
        raise CrmError("HubSpot kept failing after retries")  # pragma: no cover (loop always returns or raises)

    def portal_id(self) -> str:
        return str(self._call("GET", "/account-info/v3/details").get("portalId", ""))

    def ensure_company_property(self, name: str) -> None:
        """Create a custom text property on companies if it is missing (an existing one is left alone)."""
        payload = {"name": name, "label": "GTM company size", "type": "string", "fieldType": "text", "groupName": "companyinformation"}
        status, data = self._transport("POST", BASE + "/crm/v3/properties/companies", self._headers, json.dumps(payload).encode())
        if status == 409 or status < 300:
            return
        raise CrmError(f"Could not create the {name} property ({status}): {str(data.get('message', ''))[:200]}")

    def upsert(self, kind: str, key: str, items: list[Mapping[str, str]]) -> None:
        for chunk in _chunks(items, BATCH):
            inputs = [{"idProperty": key, "id": it[key], "properties": dict(it)} for it in chunk]
            self._call("POST", f"/crm/v3/objects/{kind}/batch/upsert", {"inputs": inputs})

    def ids(self, kind: str, key: str, values: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for chunk in _chunks(values, BATCH):
            data = self._call("POST", f"/crm/v3/objects/{kind}/batch/read",
                              {"idProperty": key, "properties": [key], "inputs": [{"id": v} for v in chunk]})
            for r in data.get("results", []):
                found[str(r.get("properties", {}).get(key, "")).lower()] = str(r["id"])
        return found

    def associate(self, pairs: list[tuple[str, str]]) -> None:
        for chunk in _chunks(pairs, BATCH):
            inputs = [{"from": {"id": c}, "to": {"id": co}} for c, co in chunk]
            self._call("POST", "/crm/v4/associations/contacts/companies/batch/associate/default", {"inputs": inputs})


@dataclass(frozen=True)
class PushReport:
    contacts_sent: int = 0
    companies_sent: int = 0
    associations_made: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors


def push(plan: CrmPlan, client: HubSpotClient) -> PushReport:
    """Apply the plan. Stops at the first failing stage and reports what was done before it, never hiding a partial result."""
    sent_companies = sent_contacts = made = 0
    try:
        for prop in plan.custom_properties:
            client.ensure_company_property(prop)
        client.upsert("companies", "domain", [dict(c.properties) for c in plan.companies])
        sent_companies = len(plan.companies)
        client.upsert("contacts", "email", [dict(c.properties) for c in plan.contacts])
        sent_contacts = len(plan.contacts)
        company_ids = client.ids("companies", "domain", [c.domain for c in plan.companies])
        contact_ids = client.ids("contacts", "email", [c.email for c in plan.contacts])
        pairs = [(contact_ids[c.email], company_ids[c.company_domain]) for c in plan.contacts
                 if c.company_domain in company_ids and c.email in contact_ids]
        client.associate(pairs)
        made = len(pairs)
    except CrmError as exc:
        return PushReport(sent_contacts, sent_companies, made, (str(exc),))
    return PushReport(sent_contacts, sent_companies, made)
