import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sequencer import constants as C
from sequencer.live import scheduler
from sequencer.tests.test_unipile import ACCOUNT, FakeTransport, profile
from sequencer.web import routes_live
from sequencer.web.auth import Auth
from sequencer.web.http import Request
from sequencer.web.routes import dispatch
from sequencer.web.server import auth_from_env
from sequencer.web.workspace import Workspace

ROOT = Path(__file__).resolve().parents[2]
WEBHOOK_SECRET = "whsec_unit_test"
LI_STEPS = [
    {"channel": "linkedin_invite", "wait_days": 0, "template": "connect_invite"},
    {"channel": "linkedin_message", "wait_days": 2, "template": "thanks_dm"},
]
ROUTES = {
    ("GET", f"/{ACCOUNT}/users/person-1"): (200, profile("SECOND_DEGREE", "prov_1")),
    ("GET", f"/{ACCOUNT}/users/mira-castellan-1a01"): (200, profile("SECOND_DEGREE", "prov_mira")),
    ("GET", f"/{ACCOUNT}/users/jonas-wekesa-1a02"): (200, profile("FIRST_DEGREE", "prov_jonas")),
    ("POST", f"/{ACCOUNT}/users/me/relation-requests"): (200, {}),
    ("POST", f"/{ACCOUNT}/inboxes/CLASSIC_PRIMARY/chats/send"): (200, {}),
    ("GET", f"/{ACCOUNT}/users/me/relations"): (200, {"data": []}),
}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("UNIPILE_API_KEY", "k-secret")
    monkeypatch.setenv("UNIPILE_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setenv("UNIPILE_WEBHOOK_SECRET", WEBHOOK_SECRET)


@pytest.fixture
def transport(monkeypatch):
    t = FakeTransport(dict(ROUTES))
    monkeypatch.setattr(routes_live, "TRANSPORT", t)
    return t


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "ws")


def call(ws, method, path, body=None, raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    res = dispatch(ws, Request(method, path, {}, data, {"host": "x", **(headers or {})}))
    return res.status, json.loads(res.body)


def launched(ws):
    assert call(ws, "POST", "/api/sample")[0] == 200
    assert call(ws, "POST", "/api/sequence", {"name": "LinkedIn test", "steps": LI_STEPS})[0] == 200
    call(ws, "POST", "/api/templates/approve", {})
    with ws.store() as s:
        for t in s.contacts():
            s._db.execute("UPDATE contacts SET sequence = 'LinkedIn test' WHERE key = ?", (t.contact.key,))
        s._db.commit()
    status, body = call(ws, "POST", "/api/launch", {"sequence": "LinkedIn test", "hold_incomplete": True})
    assert status == 200, body


def test_status_reports_whether_live_sending_is_configured(ws, monkeypatch):
    for key in ("UNIPILE_API_KEY", "UNIPILE_ACCOUNT_ID", "UNIPILE_WEBHOOK_SECRET"):
        monkeypatch.delenv(key, raising=False)
    _, st = call(ws, "GET", "/api/live")
    assert st["configured"] is False and st["enabled"] is False and st["caps"] == {"invites": 3, "messages": 5}
    monkeypatch.setenv("UNIPILE_API_KEY", "k")
    monkeypatch.setenv("UNIPILE_ACCOUNT_ID", "a")
    assert call(ws, "GET", "/api/live")[1]["configured"] is True


def test_the_api_never_returns_the_key(ws, env, transport):
    assert "k-secret" not in json.dumps(call(ws, "GET", "/api/live")[1])


def test_start_is_refused_without_configuration_or_confirmation(ws, monkeypatch):
    for key in ("UNIPILE_API_KEY", "UNIPILE_ACCOUNT_ID"):
        monkeypatch.delenv(key, raising=False)
    launched(ws)
    assert call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})[0] == 409
    monkeypatch.setenv("UNIPILE_API_KEY", "k")
    monkeypatch.setenv("UNIPILE_ACCOUNT_ID", ACCOUNT)
    assert call(ws, "POST", "/api/live/start", {"contacts": ["r0001"]})[0] == 400
    assert call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": "yes"})[0] == 400
    assert call(ws, "POST", "/api/live/start", {"contacts": "r0001", "confirm": True})[0] == 400


def test_preflight_looks_people_up_and_sends_nothing(ws, env, transport):
    launched(ws)
    status, body = call(ws, "POST", "/api/live/preflight", {"contacts": ["r0001", "r0002"]})
    assert status == 200
    assert [(c["name"], c["result"]) for c in body["contacts"]] == [
        ("Mira Castellan", "not_connected"),
        ("Jonas Wekesa", "connected"),
    ]
    assert all(r["method"] == "GET" for r in transport.requests)


def test_preflight_reports_missing_linkedin_and_unknown_profiles(ws, env, transport):
    launched(ws)
    with ws.store() as s:
        s._db.execute("UPDATE contacts SET linkedin_url = '' WHERE key = 'r0001'")
        s._db.commit()
    transport.routes[("GET", f"/{ACCOUNT}/users/jonas-wekesa-1a02")] = (404, {"type": "not_found", "detail": "x"})
    _, body = call(ws, "POST", "/api/live/preflight", {"contacts": ["r0001", "r0002"]})
    assert [c["result"] for c in body["contacts"]] == ["no_linkedin", "not_found"]
    assert call(ws, "POST", "/api/live/preflight", {"contacts": ["r9999"]})[0] == 404
    assert call(ws, "POST", "/api/live/preflight", {"contacts": [f"r{i:04d}" for i in range(1, 13)]})[0] == 400


def test_preflight_surfaces_a_provider_failure_without_the_key(ws, env, transport):
    launched(ws)
    transport.routes[("GET", f"/{ACCOUNT}/users/mira-castellan-1a01")] = (401, {"detail": "bad credentials k-secret"})
    status, body = call(ws, "POST", "/api/live/preflight", {"contacts": ["r0001"]})
    assert status == 502 and "k-secret" not in json.dumps(body)


def test_start_then_scheduler_sends_only_to_the_chosen_contact_within_caps(ws, env, transport):
    launched(ws)
    assert call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})[0] == 200
    now = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)  # Monday, inside the 9-17 London window
    scheduler.step(ws, now, transport)
    posts = [r for r in transport.requests if r["method"] == "POST"]
    assert len(posts) == 1 and posts[0]["body"]["user_id"] == "prov_mira"
    _, st = call(ws, "GET", "/api/live")
    assert (
        st["enabled"]
        and st["status"]["sent"] == 1
        and st["status"]["error"] == ""
        and st["contacts"][0]["name"] == "Mira Castellan"
    )
    with ws.store() as s:
        assert [t.contact_key for t in s.touches()] == ["r0001"]


def test_stop_halts_the_scheduler(ws, env, transport):
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    assert call(ws, "POST", "/api/live/stop")[1] == {"enabled": False}
    scheduler.step(ws, datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc), transport)
    assert [r for r in transport.requests if r["method"] == "POST"] == []


def test_simulation_is_refused_once_live_has_started(ws, env, transport):
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    assert call(ws, "POST", "/api/run", {"days": 5})[0] == 409


def test_a_scheduler_error_is_recorded_not_raised(ws, env):
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})

    def broken(*a, **k):
        raise OSError("network down")

    scheduler.step(ws, datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc), broken)
    assert "network down" in call(ws, "GET", "/api/live")[1]["status"]["error"]


def test_scheduler_does_nothing_when_unconfigured_or_not_started(ws, monkeypatch):
    monkeypatch.delenv("UNIPILE_API_KEY", raising=False)
    boom = FakeTransport({})
    assert scheduler.step(ws, datetime.now(timezone.utc), boom, None) is None and boom.requests == []


def test_accept_polling_runs_on_a_schedule_not_every_tick(ws, env, transport):
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    t0 = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
    last = scheduler.step(ws, t0, transport)
    n = len([r for r in transport.requests if r["path"].endswith("/relations")])
    last = scheduler.step(ws, t0.replace(minute=5), transport, last)
    assert len([r for r in transport.requests if r["path"].endswith("/relations")]) == n  # only 5 minutes later
    scheduler.step(ws, t0.replace(minute=15), transport, last)
    assert len([r for r in transport.requests if r["path"].endswith("/relations")]) == n + 1


# ---------------------------------------------------------------- webhook


def signed(body: str, secret=WEBHOOK_SECRET):
    ts = int(time.time())
    return {"unipile-signature": f"t={ts},v0={hmac.new(secret.encode(), f'{ts}.{body}'.encode(), hashlib.sha256).hexdigest()}"}


def reply_body(provider_id):
    return json.dumps(
        {
            "type": "message.new",
            "account_id": ACCOUNT,
            "payload": {"id": "m1", "chat_id": "c", "is_sender": False, "sender_id": provider_id, "text": "yes"},
        }
    )


def test_webhook_rejects_missing_or_wrong_signatures_and_changes_nothing(ws, env, transport):
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    scheduler.step(ws, datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc), transport)
    body = reply_body("prov_mira")
    assert call(ws, "POST", "/api/webhooks/unipile", raw=body.encode())[0] == 401
    assert call(ws, "POST", "/api/webhooks/unipile", raw=body.encode(), headers=signed(body, "wrong"))[0] == 401
    assert call(ws, "POST", "/api/contacts")[0] == 404
    with ws.store() as s:
        assert s.contact("r0001").status == C.IN_SEQUENCE


def test_a_signed_reply_marks_the_contact_replied(ws, env, transport):
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    scheduler.step(ws, datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc), transport)
    body = reply_body("prov_mira")
    assert call(ws, "POST", "/api/webhooks/unipile", raw=body.encode(), headers=signed(body)) == (200, {"ok": True})
    with ws.store() as s:
        assert s.contact("r0001").status == C.REPLIED


def test_the_webhook_is_refused_when_no_secret_is_configured(ws, monkeypatch):
    monkeypatch.delenv("UNIPILE_WEBHOOK_SECRET", raising=False)
    body = reply_body("x")
    assert call(ws, "POST", "/api/webhooks/unipile", raw=body.encode(), headers=signed(body, ""))[0] == 401


def test_the_webhook_is_reachable_without_a_login_but_nothing_else_is(ws, env):
    auth = Auth("a-long-enough-password", "s" * 40)
    body = reply_body("x")
    res = dispatch(ws, Request("POST", "/api/webhooks/unipile", {}, body.encode(), {"host": "x", **signed(body)}), auth=auth)
    assert res.status == 200
    assert dispatch(ws, Request("GET", "/api/live", {}, b"", {"host": "x"}), auth=auth).status == 401
    assert dispatch(ws, Request("POST", "/api/live/start", {}, b"{}", {"host": "x"}), auth=auth).status == 401


# ---------------------------------------------------------------- server configuration fails closed


def test_exposed_servers_require_a_password_and_a_secret():
    with pytest.raises(SystemExit, match="APP_PASSWORD"):
        auth_from_env({}, "0.0.0.0")
    with pytest.raises(SystemExit, match="SESSION_SECRET"):
        auth_from_env({"APP_PASSWORD": "a-long-enough-password"}, "0.0.0.0")
    assert isinstance(auth_from_env({"APP_PASSWORD": "a-long-enough-password", "SESSION_SECRET": "s" * 40}, "0.0.0.0"), Auth)


def test_local_use_needs_no_password_but_uses_one_if_given():
    assert auth_from_env({}, "127.0.0.1") is None
    assert isinstance(auth_from_env({"APP_PASSWORD": "a-long-enough-password", "SESSION_SECRET": "s" * 40}, "127.0.0.1"), Auth)


def test_a_too_short_password_is_a_clear_startup_error():
    with pytest.raises(SystemExit, match="at least 12"):
        auth_from_env({"APP_PASSWORD": "short", "SESSION_SECRET": "s" * 40}, "0.0.0.0")


def test_the_scheduler_loop_survives_a_crashing_iteration(ws, monkeypatch):
    calls = {"n": 0}

    def explode(*a, **k):
        calls["n"] += 1
        raise RuntimeError("disk gone")

    monkeypatch.setattr(scheduler, "step", explode)
    monkeypatch.setattr(scheduler, "TICK_SECONDS", 0.01)
    sch = scheduler.Scheduler(ws)
    sch.start()
    time.sleep(0.15)
    sch.stop()
    sch.join(timeout=2)
    assert calls["n"] >= 2 and not sch.is_alive()


def test_serve_refuses_an_unwritable_data_folder(tmp_path, monkeypatch):
    from sequencer.web.server import serve

    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("APP_PASSWORD", "a-long-enough-password")
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    with pytest.raises(SystemExit, match="Cannot write to the data folder"):
        serve(blocker / "data", port=0, open_browser=False)
