import json
from datetime import datetime, timezone

import pytest

from sequencer.store import Store
from sequencer.tests.conftest import build_store, person
from sequencer.web.http import Request
from sequencer.web.routes import dispatch
from sequencer.web.workspace import Workspace
from sequencer.workflow import AddContactError, add_contact

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
GOOD = {
    "name": "Ravi Sample",
    "company": "",
    "title": "",
    "email": "",
    "linkedin_url": "https://www.linkedin.com/in/ravi-sample/",
    "sequence": "Main",
}


def test_a_valid_contact_is_added_with_the_next_row_and_normalised_fields():
    s = build_store(contacts=[person(1), person(2)])
    result = add_contact(s, {**GOOD, "email": "  Ravi@Example.COM "}, NOW)
    assert result.contact.key == "r0003" and result.contact.row == 3
    stored = s.contact("r0003").contact
    assert (stored.email, stored.linkedin_url, stored.first_name, stored.last_name) == (
        "ravi@example.com",
        "https://www.linkedin.com/in/ravi-sample",
        "Ravi",
        "Sample",
    )
    assert s.contact("r0003").status == "Not Started"


def test_the_first_contact_marks_the_list_as_validated_so_the_launch_gate_can_pass():
    s = Store()
    assert s.get_setting("validation_run") is None
    add_contact(s, GOOD, NOW)
    run = s.get_setting("validation_run")
    assert run["manual"] is True and run["kept"] == 1


def test_names_are_split_and_a_single_word_name_is_accepted():
    s = Store()
    one = add_contact(s, {**GOOD, "name": "Madonna"}, NOW).contact
    assert (one.first_name, one.last_name) == ("Madonna", "")
    two = add_contact(s, {**GOOD, "name": "Mary Jane Watson", "linkedin_url": "https://www.linkedin.com/in/mjw-1"}, NOW).contact
    assert (two.first_name, two.last_name) == ("Mary", "Jane Watson")


@pytest.mark.parametrize(
    "fields,reason",
    [
        ({"name": ""}, "missing_name"),
        ({"email": "nope", "linkedin_url": ""}, "invalid_email"),
        ({"email": "", "linkedin_url": ""}, "no_reachable_channel"),
        ({"linkedin_url": "https://www.linkedin.com/company/acme", "email": ""}, "invalid_linkedin_url"),
    ],
)
def test_invalid_contacts_are_refused_with_a_plain_reason_and_nothing_is_stored(fields, reason):
    s = Store()
    with pytest.raises(AddContactError) as err:
        add_contact(s, {**GOOD, **fields}, NOW)
    assert err.value.reason == reason and s.contacts() == []


def test_a_duplicate_of_an_existing_contact_is_refused():
    s = build_store(contacts=[person(1, email="a@acme.example")])
    with pytest.raises(AddContactError) as err:
        add_contact(s, {**GOOD, "email": "A@acme.example", "linkedin_url": ""}, NOW)
    assert err.value.reason == "duplicate" and len(s.contacts()) == 1


def test_a_suppressed_person_is_refused():
    from sequencer.validate import Suppression

    s = Store()
    s.add_suppression(Suppression(emails=frozenset({"no@acme.example"})), "test")
    with pytest.raises(AddContactError) as err:
        add_contact(s, {**GOOD, "email": "no@acme.example"}, NOW)
    assert err.value.reason == "opted_out"


def test_a_sequence_is_required_and_a_live_sequence_cannot_take_new_people():
    s = build_store()
    with pytest.raises(AddContactError, match="sequence"):
        add_contact(s, {**GOOD, "sequence": ""}, NOW)
    from sequencer.engine import launch
    from sequencer.tests.conftest import TUESDAY_10

    launch(s, "Main", TUESDAY_10)
    with pytest.raises(AddContactError, match="live"):
        add_contact(s, {**GOOD, "sequence": "Main"}, NOW)


def test_field_lengths_are_capped():
    with pytest.raises(AddContactError, match="too long"):
        add_contact(Store(), {**GOOD, "company": "x" * 300}, NOW)


def test_risky_emails_are_kept_with_a_note():
    result = add_contact(Store(), {**GOOD, "email": "info@acme.example"}, NOW)
    assert any("risky" in f for f in result.contact.flags)


# ---------------------------------------------------------------- API


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "ws")


def call(ws, body):
    res = dispatch(ws, Request("POST", "/api/contacts/add", {}, json.dumps(body).encode(), {"host": "x"}))
    return res.status, json.loads(res.body)


def test_api_adds_a_contact_and_it_shows_in_the_list(ws):
    status, body = call(ws, GOOD)
    assert status == 200 and body["key"] == "r0001"
    res = dispatch(ws, Request("GET", "/api/contacts", {}, b"", {"host": "x"}))
    assert [c["name"] for c in json.loads(res.body)["contacts"]] == ["Ravi Sample"]


def test_api_reports_why_a_contact_was_refused(ws):
    status, body = call(ws, {**GOOD, "linkedin_url": "https://www.linkedin.com/company/acme"})
    assert (
        status == 422
        and "company page" not in body["error"]
        and "LinkedIn" in body["error"]
        and body["reason"] == "invalid_linkedin_url"
    )


def test_api_rejects_non_string_fields_and_unknown_fields_are_ignored(ws):
    assert call(ws, {**GOOD, "name": 5})[0] == 400
    assert call(ws, {**GOOD, "is_admin": True})[0] == 200


def test_state_lists_sequence_names_that_contacts_use_but_that_are_not_built_yet(ws):
    def post(path, body):
        return dispatch(ws, Request("POST", path, {}, json.dumps(body).encode(), {"host": "x"})).status

    call(ws, {**GOOD, "sequence": "Founders outreach"})
    state = json.loads(dispatch(ws, Request("GET", "/api/state", {}, b"", {"host": "x"})).body)
    assert state["pending_sequences"] == ["Founders outreach"]
    assert post("/api/templates", {"id": "inv", "channel": "linkedin_invite", "body": "Hi {{first_name}}"}) == 200
    assert post("/api/templates", {"id": "dm", "channel": "linkedin_message", "body": "Hi {{first_name}}"}) == 200
    steps = [
        {"channel": "linkedin_invite", "wait_days": 0, "template": "inv"},
        {"channel": "linkedin_message", "wait_days": 1, "template": "dm"},
    ]
    assert post("/api/sequence", {"name": "Founders outreach", "steps": steps}) == 200
    state = json.loads(dispatch(ws, Request("GET", "/api/state", {}, b"", {"host": "x"})).body)
    assert state["pending_sequences"] == []
