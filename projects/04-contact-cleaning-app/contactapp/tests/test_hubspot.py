import json

import pytest

from contactapp import crm_plan
from contactapp.hubspot import BATCH, CrmError, HubSpotClient, push


class Fake:
    """Records calls and answers like HubSpot would."""

    def __init__(self, fail_on=None, statuses=None, existing=None, partial_on=None):
        self.calls, self.fail_on, self.statuses = [], fail_on, list(statuses or [])
        self.existing, self.partial_on = existing or {}, partial_on

    def __call__(self, method, url, headers, body):
        path = url.removeprefix("https://api.hubapi.com")
        payload = json.loads(body) if body else None
        self.calls.append((method, path, payload, headers))
        if self.statuses:
            return self.statuses.pop(0), {"message": "boom"}
        if self.fail_on and self.fail_on in path:
            return 400, {"message": "bad request"}
        if path.endswith("/batch/read"):
            key = payload["idProperty"]
            return 200, {"results": [{"id": str(i), "properties": {key: x["id"].upper()}} for i, x in enumerate(payload["inputs"], 1)]}
        if path == "/account-info/v3/details":
            return 200, {"portalId": 123}
        if self.partial_on and self.partial_on in path:
            return 207, {"numErrors": len(payload["inputs"]), "errors": [{"message": "invalid property"}], "results": []}
        if path.endswith("/companies/search"):
            wanted = payload["filterGroups"][0]["filters"][0]["values"]
            return 200, {"results": [{"id": i, "properties": {"domain": d}} for d in wanted for i in self.existing.get(d, [])]}
        if path.endswith("/companies/batch/upsert"):
            return 400, {"message": "domain is not a unique property"}  # what the real API is expected to do
        if path.endswith(("/batch/upsert", "/batch/create", "/batch/update")):
            return 200, {"results": [{"id": str(i), "properties": x["properties"]} for i, x in enumerate(payload["inputs"], 1)]}
        return 200, {}


def plan(n=2):
    rows = [{"Email ID": f"p{i}@acme.com", "Website": "acme.com", "Company Name": "Acme", "First Name": "P"} for i in range(n)]
    return crm_plan.build_plan(rows)


def client(fake):
    return HubSpotClient("tok", transport=fake, sleep=lambda s: None)


def test_push_runs_the_stages_in_order_and_associates():
    fake = Fake()
    report = push(plan(), client(fake))
    paths = [c[1] for c in fake.calls]
    assert report.ok and (report.contacts_sent, report.companies_sent, report.associations_made) == (2, 1, 2)
    order = ["companies/search", "companies/batch/create", "contacts/batch/upsert", "batch/associate/default"]
    positions = [next(i for i, p in enumerate(paths) if p.endswith(end)) for end in order]
    assert positions == sorted(positions)


def test_contacts_upsert_on_email_and_companies_are_never_upserted_on_domain():
    fake = Fake()
    push(plan(1), client(fake))
    contacts = next(c for c in fake.calls if c[1] == "/crm/v3/objects/contacts/batch/upsert")[2]["inputs"][0]
    assert contacts["idProperty"] == "email"
    assert not [c for c in fake.calls if c[1].endswith("/companies/batch/upsert")]


def test_an_existing_company_is_updated_not_created_again():
    fake = Fake(existing={"acme.com": ["900"]})
    report = push(plan(), client(fake))
    update = next(c for c in fake.calls if c[1].endswith("/companies/batch/update"))[2]["inputs"]
    assert report.ok and update[0]["id"] == "900"
    assert not [c for c in fake.calls if c[1].endswith("/companies/batch/create")]


def test_duplicate_companies_already_in_the_crm_are_reported_and_left_alone():
    fake = Fake(existing={"acme.com": ["900", "901"]})
    report = push(plan(), client(fake))
    assert not report.ok and "2 companies" in report.errors[0]
    assert report.companies_sent == 0 and report.associations_made == 0 and report.contacts_sent == 2


def test_a_partial_failure_with_status_207_is_not_reported_as_success():
    report = push(plan(), client(Fake(partial_on="contacts/batch/upsert")))
    assert not report.ok and report.contacts_sent == 0 and report.companies_sent == 1
    assert "partial failure" in report.errors[0]


def test_retry_after_is_honoured():
    waits, replies = [], iter([(429, {"_retry_after": "7"}), (200, {"portalId": 5})])
    api = HubSpotClient("tok", transport=lambda *a: next(replies), sleep=waits.append)
    assert api.portal_id() == "5" and waits == [7.0]


def test_a_create_is_not_repeated_after_a_server_error():
    seen = []

    def transport(method, url, headers, body):
        seen.append(url)
        return 502, {"message": "bad gateway"}

    with pytest.raises(CrmError):
        HubSpotClient("tok", transport=transport, sleep=lambda s: None).create_companies([{"domain": "acme.com"}])
    assert len(seen) == 1


def test_large_lists_are_batched_by_100():
    fake = Fake()
    push(plan(BATCH + 1), client(fake))
    upserts = [c for c in fake.calls if c[1] == "/crm/v3/objects/contacts/batch/upsert"]
    assert [len(u[2]["inputs"]) for u in upserts] == [BATCH, 1]


def test_a_failure_stops_the_push_and_reports_what_was_done():
    report = push(plan(), client(Fake(fail_on="contacts/batch/upsert")))
    assert not report.ok and report.companies_sent == 1 and report.contacts_sent == 0 and "400" in report.errors[0]


def test_existing_custom_property_is_not_an_error():
    fake = Fake(statuses=[409])
    assert push(plan(), client(fake)).ok


def test_throttling_is_retried_then_succeeds():
    fake = Fake(statuses=[429, 503])
    assert client(fake).portal_id() == "123"


def test_the_token_is_sent_but_never_appears_in_errors():
    fake = Fake(fail_on="account-info")
    with pytest.raises(CrmError) as err:
        client(fake).portal_id()
    assert "tok" not in str(err.value) and fake.calls[0][3]["Authorization"] == "Bearer tok"


def test_empty_token_is_refused():
    with pytest.raises(CrmError):
        HubSpotClient("")
