import json

import pytest

from contactapp import crm_plan
from contactapp.hubspot import BATCH, CrmError, HubSpotClient, push


class Fake:
    """Records calls and answers like HubSpot would."""

    def __init__(self, fail_on=None, statuses=None):
        self.calls, self.fail_on, self.statuses = [], fail_on, list(statuses or [])

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
    assert paths.index("/crm/v3/objects/companies/batch/upsert") < paths.index("/crm/v3/objects/contacts/batch/upsert") < paths.index(
        "/crm/v4/associations/contacts/companies/batch/associate/default")


def test_upsert_matches_on_email_and_domain_so_reruns_do_not_duplicate():
    fake = Fake()
    push(plan(1), client(fake))
    contacts = next(c for c in fake.calls if c[1] == "/crm/v3/objects/contacts/batch/upsert")[2]["inputs"][0]
    companies = next(c for c in fake.calls if c[1] == "/crm/v3/objects/companies/batch/upsert")[2]["inputs"][0]
    assert contacts["idProperty"] == "email" and companies["idProperty"] == "domain"


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
