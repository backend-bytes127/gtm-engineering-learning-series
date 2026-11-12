import json

from contactapp.tests.conftest import HOST
from contactapp.tests.test_hubspot import Fake


def body(res):
    return json.loads(res.body)


def test_foreign_host_is_refused(make_client):
    assert make_client().call("GET", "/api/state", host="evil.example").status == 403


def test_post_without_the_page_token_is_refused(make_client):
    assert make_client().call("POST", "/api/sample", token=False).status == 403


def test_page_serves_with_a_per_visitor_token(make_client):
    c = make_client()
    res = c.open_page()
    assert res.status == 200 and c.token.encode() in res.body and b"__PAGE_TOKEN__" not in res.body


def test_static_path_traversal_is_blocked(make_client):
    assert make_client().call("GET", "/static/../app.py").status == 404


def test_results_need_a_run_first(make_client):
    c = make_client()
    assert c.call("GET", "/api/result").status == 409 and c.call("GET", "/api/crm/plan").status == 409


def test_upload_then_result_download_and_plan(make_client, sample_files):
    c = make_client()
    assert body(c.upload(sample_files))["summary"]["people"] == 12
    assert len(body(c.call("GET", "/api/result"))["rows"]) == 12
    dl = c.call("GET", "/api/download/final.xlsx")
    assert dl.status == 200 and dl.body.startswith(b"PK") and b"Final_Contact_List" in dict(dl.headers)["Content-Disposition"].encode()
    assert body(c.call("GET", "/api/crm/plan"))["contacts"] == 12


def test_bad_upload_returns_the_problems_per_file(make_client, sample_files):
    res = make_client().upload({**sample_files, "02": b"junk"})
    assert res.status == 422 and "02" in body(res)["problems"]


def test_sample_button(make_client):
    c = make_client()
    assert body(c.call("POST", "/api/sample"))["summary"]["people"] == 12


def test_push_is_off_by_default(make_client):
    c = make_client(crm_token="tok")
    c.call("POST", "/api/sample")
    assert c.call("POST", "/api/crm/push", b'{"confirm_contacts": 12}').status == 403


def test_push_needs_the_contact_count_typed_back(make_client):
    c = make_client(crm_token="tok", allow_push=True, transport=Fake())
    c.call("POST", "/api/sample")
    res = c.call("POST", "/api/crm/push", b'{"confirm_contacts": 5}')
    assert res.status == 400 and body(res)["expected"] == 12


def test_confirmed_push_reports_counts(make_client):
    fake = Fake()
    c = make_client(crm_token="tok", allow_push=True, expected_portal="123", transport=fake)
    c.call("POST", "/api/sample")
    res = body(c.call("POST", "/api/crm/push", b'{"confirm_contacts": 12}'))
    assert res["ok"] and (res["contacts"], res["companies"], res["associations"]) == (12, 5, 12)


def test_wrong_portal_blocks_the_push_before_any_write(make_client):
    fake = Fake()
    c = make_client(crm_token="tok", allow_push=True, expected_portal="999", transport=fake)
    c.call("POST", "/api/sample")
    res = c.call("POST", "/api/crm/push", b'{"confirm_contacts": 12}')
    assert res.status == 409 and not [x for x in fake.calls if x[0] == "POST"]


def test_connection_test(make_client):
    c = make_client(crm_token="tok", transport=Fake())
    assert body(c.call("POST", "/api/crm/test"))["portal_id"] == "123"
    assert make_client().call("POST", "/api/crm/test").status == 409


def test_state_never_exposes_the_token(make_client):
    res = make_client(crm_token="super-secret-token").call("GET", "/api/state")
    assert b"super-secret-token" not in res.body and body(res)["crm"] == {"configured": True, "push_enabled": False}


def test_host_constant_matches():
    assert HOST == "127.0.0.1:9"
