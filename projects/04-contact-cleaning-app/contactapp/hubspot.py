"""A small HubSpot client (standard library only) and the push that applies a CrmPlan.

The transport is injectable so every call can be tested without a network. Contacts are upserted on e-mail, which
HubSpot treats as unique. A company's domain is not a unique property, so it cannot be an upsert key: companies are
searched by domain first, then updated or created. Everything goes in batches of 100 and is then associated.

Not yet run against a live HubSpot account. HubSpot's search index can lag a few seconds behind a create, so running
the same push again immediately could create a company twice.
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
SEARCH_PAGE = 200
MAX_WAIT_SECONDS = 60
SAFE_TO_REPEAT = (429, 500, 502, 503, 504)
THROTTLED_ONLY = (429,)  # for creates: after a 5xx we cannot know whether the records were made
Transport = Callable[[str, str, Mapping[str, str], bytes | None], tuple[int, dict]]


class CrmError(Exception):
    """A HubSpot call failed. The message is safe to show: it never contains the token."""

    def __init__(self, message: str, results: tuple = ()):
        super().__init__(message)
        self.results = tuple(results)  # records HubSpot did return when only part of a batch succeeded


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method=method, headers=dict(headers))  # noqa: S310 (fixed https host)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310
            raw = res.read()
            return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"message": "non-JSON error body"}
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        return exc.code, {**data, "_retry_after": retry_after} if retry_after else data
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CrmError(f"Could not reach HubSpot: {exc.__class__.__name__}") from exc


def _wait_seconds(data: Mapping, attempt: int) -> float:
    backoff = min(2**attempt, 8)
    try:
        asked = float(data.get("_retry_after") or 0)
    except ValueError:
        asked = 0
    return min(max(asked, backoff), MAX_WAIT_SECONDS)


def _chunks(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class HubSpotClient:
    def __init__(self, token: str, transport: Transport = urllib_transport, sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise CrmError("No HubSpot token is configured.")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._transport, self._sleep = transport, sleep

    def _call(self, method: str, path: str, payload: dict | None = None, retry_on: tuple[int, ...] = SAFE_TO_REPEAT) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        for attempt in range(4):
            status, data = self._transport(method, BASE + path, self._headers, body)
            if status in retry_on and attempt < 3:
                self._sleep(_wait_seconds(data, attempt))
                continue
            if status >= 400:
                raise CrmError(f"HubSpot returned {status} for {method} {path}: {str(data.get('message', ''))[:200]}")
            if status == 207 or data.get("numErrors"):
                errors = data.get("errors") or [{}]
                raise CrmError(
                    f"HubSpot reported a partial failure for {path} ({data.get('numErrors', len(errors))} error(s)): "
                    f"{str(errors[0].get('message', ''))[:200]}",
                    tuple(data.get("results", [])),
                )
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

    def _batches(self, path: str, inputs: list[dict], retry_on: tuple[int, ...] = SAFE_TO_REPEAT) -> list[dict]:
        """Send in batches and return every record HubSpot returned. A failure carries what had succeeded so far."""
        done: list[dict] = []
        for chunk in _chunks(inputs, BATCH):
            try:
                done += self._call("POST", path, {"inputs": chunk}, retry_on).get("results", [])
            except CrmError as exc:
                raise CrmError(str(exc), (*done, *exc.results)) from exc
        return done

    def upsert(self, kind: str, key: str, items: list[Mapping[str, str]]) -> list[dict]:
        """Batch upsert on a property HubSpot treats as unique (e-mail for contacts)."""
        inputs = [{"idProperty": key, "id": it[key], "properties": dict(it)} for it in items]
        return self._batches(f"/crm/v3/objects/{kind}/batch/upsert", inputs)

    def companies_by_domain(self, domains: list[str]) -> dict[str, list[str]]:
        """Existing company ids for each domain. More than one id means the CRM already holds duplicates."""
        found: dict[str, list[str]] = {}
        for chunk in _chunks(domains, BATCH):
            query = {
                "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "IN", "values": chunk}]}],
                "properties": ["domain"],
                "limit": SEARCH_PAGE,
            }
            after = None
            while True:
                data = self._call("POST", "/crm/v3/objects/companies/search", {**query, **({"after": after} if after else {})})
                for r in data.get("results", []):
                    found.setdefault(str(r.get("properties", {}).get("domain", "")).lower(), []).append(str(r["id"]))
                after = data.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
        return found

    def update_companies(self, updates: list[tuple[str, Mapping[str, str]]]) -> list[dict]:
        return self._batches("/crm/v3/objects/companies/batch/update", [{"id": i, "properties": dict(p)} for i, p in updates])

    def create_companies(self, items: list[Mapping[str, str]]) -> list[dict]:
        return self._batches("/crm/v3/objects/companies/batch/create", [{"properties": dict(p)} for p in items], THROTTLED_ONLY)

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
    problems: list[str] = []
    stage = "setup"
    try:
        for prop in plan.custom_properties:
            client.ensure_company_property(prop)
        stage = "companies"
        existing = client.companies_by_domain([c.domain for c in plan.companies])
        company_ids = {d: ids[0] for d, ids in existing.items() if len(ids) == 1}
        ambiguous = {d for d, ids in existing.items() if len(ids) > 1}
        problems += [
            f"{d}: HubSpot already has {len(existing[d])} companies with this domain, so none was changed" for d in sorted(ambiguous)
        ]
        updates = [(company_ids[c.domain], c.properties) for c in plan.companies if c.domain in company_ids]
        sent_companies += len(client.update_companies(updates))
        new = [c.properties for c in plan.companies if c.domain not in existing]
        created = client.create_companies(new)
        sent_companies += len(created)
        company_ids.update({str(r.get("properties", {}).get("domain", "")).lower(): str(r["id"]) for r in created})
        stage = "contacts"
        sent_contacts = len(client.upsert("contacts", "email", [dict(c.properties) for c in plan.contacts]))
        stage = "associations"
        contact_ids = client.ids("contacts", "email", [c.email for c in plan.contacts])
        pairs = [(contact_ids[c.email], company_ids[c.company_domain]) for c in plan.contacts
                 if c.company_domain in company_ids and c.email in contact_ids]
        client.associate(pairs)
        made = len(pairs)
    except CrmError as exc:
        if stage == "companies":
            sent_companies += len(exc.results)
        elif stage == "contacts":
            sent_contacts = len(exc.results)
        return PushReport(sent_contacts, sent_companies, made, (*problems, str(exc)))
    return PushReport(sent_contacts, sent_companies, made, tuple(problems))
