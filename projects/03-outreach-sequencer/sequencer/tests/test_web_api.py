import json
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import pytest

from sequencer.rules import parse_rules
from sequencer.web.http import Request
from sequencer.web.routes import dispatch
from sequencer.web.workspace import Workspace, first_window_start

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CSV = (ROOT / "sample-data" / "contacts.csv").read_bytes()


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "ws")


def call(ws, method, path, body=None, query=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    res = dispatch(ws, Request(method, path, query or {}, data, {"host": "127.0.0.1:1", **(headers or {})}))
    parsed = json.loads(res.body) if res.content_type.startswith("application/json") else res.body
    return res.status, parsed


def sample(ws):
    assert call(ws, "POST", "/api/sample")[0] == 200


def ready(ws):
    sample(ws)
    assert call(ws, "POST", "/api/templates/approve", {})[0] == 200


# ---------------------------------------------------------------- state and sample


def test_empty_state(ws):
    _, s = call(ws, "GET", "/api/state")
    assert s["total"] == 0 and not any(s["done"].values()) and s["sequences"] == []


def test_load_sample_populates_everything(ws):
    sample(ws)
    _, s = call(ws, "GET", "/api/state")
    assert (s["total"], s["removed"]) == (26, 10)
    assert s["done"] == {
        "import": True,
        "validate": True,
        "sequence": True,
        "messages": False,
        "rules": True,
        "launch": False,
        "report": False,
    }
    _, cfg = call(ws, "GET", "/api/config")
    assert len(cfg["templates"]) == 5 and cfg["sequences"][0]["name"] == "Outbound Intro" and cfg["rules"]["email_per_day"] == 15


def test_loading_the_sample_twice_does_not_stack_data(ws):
    sample(ws)
    sample(ws)
    assert call(ws, "GET", "/api/state")[1]["total"] == 26


# ---------------------------------------------------------------- upload and import


def upload(ws, content=SAMPLE_CSV, name="list.csv"):
    return call(ws, "POST", "/api/upload", raw=content, headers={"x-filename": name})


def test_upload_returns_preview_and_suggested_mapping(ws):
    status, u = upload(ws)
    assert status == 200 and u["total"] == 36 and len(u["rows"]) == 5
    assert u["suggested"]["email"] == "Work Email" and u["suggested"]["linkedin_url"] == "LinkedIn Profile"


@pytest.mark.parametrize("name,content", [("x.txt", b"a"), ("x.csv", b""), ("noext", b"a")])
def test_upload_rejects_bad_files(ws, name, content):
    assert upload(ws, content, name)[0] == 400


def test_upload_rejects_a_corrupt_xlsx_and_leaves_nothing_behind(ws):
    status, body = upload(ws, b"this is not a zip", "bad.xlsx")
    assert status == 400 and "could not be read" in body["error"]
    assert not list(ws.uploads.glob("*"))


def test_import_validates_and_reports_counts(ws):
    _, u = upload(ws)
    status, r = call(
        ws,
        "POST",
        "/api/import",
        {
            "upload_id": u["upload_id"],
            "mapping": u["suggested"],
            "default_sequence": "Outbound Intro",
            "suppression_text": "@blocked-demo.example\ndo.not.contact@harbor-demo.example",
        },
    )
    assert status == 200 and r["read"] == 36 and r["kept"] + r["removed"] == 36
    _, v = call(ws, "GET", "/api/validation")
    assert {x["reason"] for x in v["removed"]} >= {"invalid_email", "duplicate", "opted_out"}
    assert any("email_cleared" in f for k in v["kept"] for f in k["flags"])


def test_importing_again_replaces_the_list(ws):
    _, u = upload(ws)
    body = {"upload_id": u["upload_id"], "mapping": u["suggested"]}
    call(ws, "POST", "/api/import", body)
    call(ws, "POST", "/api/import", body)
    assert call(ws, "GET", "/api/state")[1]["total"] + call(ws, "GET", "/api/state")[1]["removed"] == 36


def test_import_errors_are_plain_messages(ws):
    _, u = upload(ws, b"Company,Title\nAcme,CTO\n", "c.csv")
    status, body = call(ws, "POST", "/api/import", {"upload_id": u["upload_id"], "mapping": {}})
    assert status == 422 and "name" in body["error"]
    assert call(ws, "POST", "/api/import", {"upload_id": "../../etc/passwd", "mapping": {}})[0] == 400
    assert call(ws, "POST", "/api/import", {"upload_id": u["upload_id"], "mapping": {"name": 3}})[0] == 400


# ---------------------------------------------------------------- templates, sequences, rules


def test_lint_endpoint_flags_problems_while_typing(ws):
    _, r = call(ws, "POST", "/api/lint", {"channel": "email", "subject": "Hi", "body": "No variables here"})
    codes = {i["code"] for i in r["issues"]}
    assert {"no_personalisation", "missing_unsubscribe"} <= codes


def test_save_template_then_edit_unapproves(ws):
    ready(ws)
    _, cfg = call(ws, "GET", "/api/config")
    assert all(t["approved"] for t in cfg["templates"])
    t = next(t for t in cfg["templates"] if t["id"] == "connect_invite")
    call(ws, "POST", "/api/templates", {**t, "body": t["body"] + " Cheers."})
    _, cfg = call(ws, "GET", "/api/config")
    assert not next(x for x in cfg["templates"] if x["id"] == "connect_invite")["approved"]


@pytest.mark.parametrize("bad_id", ["", "has space", "../x", "a" * 61])
def test_template_ids_are_restricted(ws, bad_id):
    assert call(ws, "POST", "/api/templates", {"id": bad_id, "channel": "email", "body": "x"})[0] == 422


def test_approval_refuses_templates_with_errors(ws):
    sample(ws)
    call(ws, "POST", "/api/templates", {"id": "bad", "channel": "linkedin_message", "body": "No variable at all"})
    status, body = call(ws, "POST", "/api/templates/approve", {})
    assert status == 422 and "bad" in body["error"]


def test_cannot_delete_a_template_in_use_but_can_delete_an_unused_one(ws):
    sample(ws)
    assert call(ws, "POST", "/api/templates/delete", {"id": "intro_email"})[0] == 409
    call(ws, "POST", "/api/templates", {"id": "spare", "channel": "linkedin_message", "body": "Hi {{first_name}}"})
    assert call(ws, "POST", "/api/templates/delete", {"id": "spare"})[0] == 200


def test_preview_fills_in_a_real_contact_and_reports_missing_data(ws):
    sample(ws)
    _, cfg = call(ws, "GET", "/api/config")
    t = next(t for t in cfg["templates"] if t["id"] == "intro_email")
    _, p = call(ws, "POST", "/api/preview", {"channel": "email", "subject": t["subject"], "body": t["body"], "contact": "r0001"})
    assert (
        p["missing"] == [] and "Mira" in p["body"] and "Northwind Demo Co" in p["body"] and p["subject"] == "Idea for Harbor Demo"
    )
    _, p = call(ws, "POST", "/api/preview", {"channel": "email", "subject": t["subject"], "body": t["body"], "contact": "r0006"})
    assert p["missing"] == ["company"] and p["issues"][0]["code"] == "missing_data"


def test_preview_works_before_anything_is_imported(ws):
    _, p = call(ws, "POST", "/api/preview", {"channel": "linkedin_message", "body": "Hi {{first_name}}"})
    assert p["body"] == "Hi Alex"


def test_sequence_check_and_save(ws):
    sample(ws)
    steps = [{"channel": "linkedin_message", "wait_days": 0, "template": "thanks_dm"}]
    _, c = call(ws, "POST", "/api/sequence/check", {"name": "Bad", "steps": steps})
    assert any("invite" in e for e in c["errors"])
    status, body = call(ws, "POST", "/api/sequence", {"name": "Bad", "steps": steps})
    assert status == 422 and body["errors"]
    good = [{"channel": "email", "wait_days": 0, "template": "intro_email"}]
    assert call(ws, "POST", "/api/sequence", {"name": "Short", "steps": good})[0] == 200
    assert call(ws, "POST", "/api/sequence", {"name": "", "steps": good})[0] == 422


def test_rules_and_sender_are_validated(ws):
    sample(ws)
    status, body = call(
        ws,
        "POST",
        "/api/rules",
        {
            "timezone": "UTC",
            "email_per_day": 999,
            "linkedin_invites_per_day": 5,
            "linkedin_messages_per_day": 5,
            "start_hour": 9,
            "end_hour": 17,
            "active_days": [1],
        },
    )
    assert status == 422 and "email_per_day" in body["error"]
    assert call(ws, "POST", "/api/sender", {"name": "A", "postal_address": ""})[0] == 422
    assert call(ws, "POST", "/api/sender", {"name": "A", "company": "B", "postal_address": "1 St"})[0] == 200


# ---------------------------------------------------------------- launch, run, track, report


def test_launch_gate_blocks_then_hold_incomplete_launches(ws):
    sample(ws)
    _, chk = call(ws, "GET", "/api/launch/check", query={"sequence": "Outbound Intro"})
    assert not chk["ready"] and not chk["can_hold"]  # templates are not approved yet
    status, body = call(ws, "POST", "/api/launch", {"sequence": "Outbound Intro"})
    assert status == 409 and "Every template approved" in body["error"]
    call(ws, "POST", "/api/templates/approve", {})
    _, chk = call(ws, "GET", "/api/launch/check", query={"sequence": "Outbound Intro"})
    assert not chk["ready"] and chk["can_hold"] and chk["incomplete"][0]["key"] == "r0006"
    assert call(ws, "POST", "/api/launch", {"sequence": "Outbound Intro"})[0] == 409
    status, body = call(ws, "POST", "/api/launch", {"sequence": "Outbound Intro", "hold_incomplete": True})
    assert status == 200 and body["launched"] == 25 and body["held"] == ["r0006"]
    assert call(ws, "POST", "/api/launch", {"sequence": "Outbound Intro"})[0] == 409  # already live


def test_launch_start_is_the_next_window_open(ws):
    rules = parse_rules(json.loads((ROOT / "config" / "rules.json").read_text()))
    saturday = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    start = first_window_start(rules, saturday)
    assert (start.isoweekday(), start.hour) == (1, 9)  # Monday 09:00 London (= 09:00 UTC in November)
    assert first_window_start(rules, datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)).day == 10  # same day, before opening
    inside = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    assert first_window_start(rules, inside) == inside  # the window is open right now: start now, not tomorrow
    after_close = datetime(2026, 11, 10, 18, 30, tzinfo=timezone.utc)
    assert first_window_start(rules, after_close).day == 11  # closed for the day: next opening
    assert first_window_start(rules, datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)).isoweekday() == 1  # weekend: Monday


def launched(ws):
    ready(ws)
    assert call(ws, "POST", "/api/launch", {"sequence": "Outbound Intro", "hold_incomplete": True})[0] == 200


def test_run_requires_launch_and_only_runs_once(ws):
    ready(ws)
    assert call(ws, "POST", "/api/run", {"days": 30})[0] == 409
    launched(ws)
    assert call(ws, "POST", "/api/run", {"days": 0})[0] == 400
    status, r = call(ws, "POST", "/api/run", {"days": 60, "seed": 7})
    assert status == 200 and r["touches_sent"] > 50
    assert call(ws, "POST", "/api/run", {"days": 60})[0] == 409
    _, s = call(ws, "GET", "/api/state")
    assert s["ran"] and s["simulated"] and s["counts"]["In Sequence"] == 0


def test_the_api_run_matches_the_cli_demo_numbers(ws):
    launched(ws)
    call(ws, "POST", "/api/run", {"days": 60, "seed": 7})
    _, rep = call(ws, "GET", "/api/report")
    golden = json.loads((ROOT / "expected-output" / "metrics.json").read_text())
    assert rep["metrics"]["by_step"] == golden["by_step"] and rep["metrics"]["statuses"] == golden["statuses"]


def test_contacts_detail_and_manual_events(ws):
    launched(ws)
    assert call(ws, "POST", "/api/event", {"contact": "r0001", "kind": "replied"})[0] == 409  # nothing has run yet
    call(ws, "POST", "/api/run", {"days": 1})
    status, d = call(ws, "GET", "/api/contacts/r0001")
    assert status == 200 and d["touches"][0]["channel"] == "email" and d["contact"]["name"] == "Mira Castellan"
    status, e = call(ws, "POST", "/api/event", {"contact": "r0001", "kind": "replied"})
    assert status == 200 and e["status"] == "Replied"
    assert call(ws, "POST", "/api/event", {"contact": "r0001", "kind": "vibes"})[0] == 400
    assert call(ws, "GET", "/api/contacts/r9999")[0] == 404
    _, lst = call(ws, "GET", "/api/contacts")
    assert next(c for c in lst["contacts"] if c["key"] == "r0001")["status"] == "Replied"


def test_report_json_and_xlsx_download(ws):
    launched(ws)
    call(ws, "POST", "/api/run", {"days": 60})
    _, rep = call(ws, "GET", "/api/report")
    assert rep["simulated"] and rep["summary"][0].startswith("**Simulated")
    res = dispatch(ws, Request("GET", "/api/report.xlsx", {}, b"", {"host": "x"}))
    assert res.status == 200 and "attachment" in dict(res.headers)["Content-Disposition"]
    out = ws.root / "dl.xlsx"
    out.write_bytes(res.body)
    assert openpyxl.load_workbook(out).sheetnames[0] == "Summary"


def test_reset_run_keeps_the_list_and_allows_a_rerun(ws):
    launched(ws)
    call(ws, "POST", "/api/run", {"days": 60})
    assert call(ws, "POST", "/api/reset", {"scope": "run"})[0] == 200
    _, s = call(ws, "GET", "/api/state")
    assert s["total"] == 26 and not s["ran"] and s["live"] == []
    assert call(ws, "POST", "/api/reset", {"scope": "nonsense"})[0] == 400
    call(ws, "POST", "/api/reset", {"scope": "all"})
    assert call(ws, "GET", "/api/state")[1]["total"] == 0


def test_live_sequences_and_their_templates_are_locked(ws):
    launched(ws)
    assert (
        call(
            ws,
            "POST",
            "/api/sequence",
            {"name": "Outbound Intro", "steps": [{"channel": "email", "wait_days": 0, "template": "intro_email"}]},
        )[0]
        == 409
    )
    _, cfg = call(ws, "GET", "/api/config")
    t = next(t for t in cfg["templates"] if t["id"] == "intro_email")
    assert call(ws, "POST", "/api/templates", {**t, "body": "Changed {{first_name}} {{unsubscribe_line}}"})[0] == 409


# ---------------------------------------------------------------- transport and security


def test_cross_origin_writes_are_refused_but_same_origin_and_originless_pass(ws):
    evil = {"origin": "https://evil.example", "host": "127.0.0.1:8765"}
    assert dispatch(ws, Request("POST", "/api/reset", {}, b'{"scope":"all"}', evil)).status == 403
    same = {"origin": "http://127.0.0.1:8765", "host": "127.0.0.1:8765"}
    assert dispatch(ws, Request("POST", "/api/reset", {}, b'{"scope":"run"}', same)).status == 200


def test_static_files_are_served_and_traversal_is_blocked(ws):
    index = dispatch(ws, Request("GET", "/", {}, b"", {}))
    assert index.status == 200 and index.content_type.startswith("text/html") and b"<title>" in index.body
    for path in ("/../routes.py", "/%2e%2e/routes.py", "/..%2f..%2fcli.py", "/nope.js"):
        assert dispatch(ws, Request("GET", path, {}, b"", {})).status == 404


def test_unknown_routes_and_bad_json(ws):
    assert call(ws, "GET", "/api/nothing")[0] == 404
    assert call(ws, "POST", "/api/rules", raw=b"{nope")[0] == 400
    assert call(ws, "POST", "/api/rules", raw=b"[1]")[0] == 400
    assert call(ws, "PUT", "/api/state")[0] == 404


def test_unexpected_errors_do_not_leak_details(ws, monkeypatch):
    import sequencer.web.routes_data as data

    monkeypatch.setattr(data, "get_state", lambda *a: (_ for _ in ()).throw(RuntimeError("secret-detail-that-must-not-leak")))
    from sequencer.web import routes

    monkeypatch.setitem(routes.ROUTES, ("GET", "/api/state"), data.get_state)
    status, body = call(ws, "GET", "/api/state")
    assert status == 500 and "secret-detail" not in json.dumps(body)
