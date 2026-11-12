import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import pytest

from sequencer import constants as C
from sequencer.ai import runtime
from sequencer.live import scheduler
from sequencer.tests.test_ai_flow import FakeSDK, send
from sequencer.tests.test_unipile import ACCOUNT
from sequencer.tests.test_web_live import WEBHOOK_SECRET, call, env, launched, transport, ws  # noqa: F401  (fixtures)
from sequencer.web.auth import Auth
from sequencer.web.http import Request
from sequencer.web.routes import dispatch

MON_10 = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)  # Monday, inside 09-17 London


@pytest.fixture(autouse=True)
def chat_reply_route(transport):
    """The fake Unipile also needs to accept 'reply inside an existing chat'."""
    transport.routes[("POST", f"/{ACCOUNT}/chats/")] = (200, {})


@pytest.fixture
def sdk(monkeypatch):
    fake = FakeSDK()
    monkeypatch.setattr(runtime, "SDK_OVERRIDE", fake)
    return fake


def settings(ws, mode, **kw):
    body = {"mode": mode, "max_auto_replies": 3, "reply_delay_minutes": 0, "disclose": True, **kw}
    return call(ws, "POST", "/api/ai/settings", body)


def started(ws, transport):
    launched(ws)
    assert call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})[0] == 200
    scheduler.step(ws, MON_10, transport)  # sends the invite


def signed(body: str):
    ts = int(time.time())
    return {
        "unipile-signature": f"t={ts},v0={hmac.new(WEBHOOK_SECRET.encode(), f'{ts}.{body}'.encode(), hashlib.sha256).hexdigest()}"
    }


def webhook(ws, text, mid="m1", chat="chat-1"):
    body = json.dumps(
        {
            "type": "message.new",
            "account_id": ACCOUNT,
            "payload": {"id": mid, "chat_id": chat, "is_sender": False, "sender_id": "prov_mira", "text": text},
        }
    )
    return call(ws, "POST", "/api/webhooks/unipile", raw=body.encode(), headers=signed(body))


# ------------------------------------------------------------------ settings


def test_the_default_mode_is_off_and_status_says_whether_the_ai_is_set_up(ws, monkeypatch):
    monkeypatch.setattr(runtime, "SDK_OVERRIDE", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, st = call(ws, "GET", "/api/ai")
    assert (
        st["mode"] == "off"
        and st["configured"] is False
        and st["model"] == "claude-opus-5-5"
        and st["modes"] == ["off", "review", "autonomous"]
    )
    assert "sk-" not in json.dumps(st)


def test_review_and_autonomous_need_an_api_key(ws, monkeypatch):
    monkeypatch.setattr(runtime, "SDK_OVERRIDE", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert settings(ws, "review")[0] == 409 and settings(ws, "off")[0] == 200


def test_autonomous_needs_explicit_confirmation(ws, sdk):
    assert settings(ws, "autonomous")[0] == 400
    assert settings(ws, "autonomous", confirm=True)[0] == 200
    assert call(ws, "GET", "/api/ai")[1]["mode"] == "autonomous"
    assert settings(ws, "review")[0] == 200  # switching to a safer mode never asks


@pytest.mark.parametrize(
    "bad", [dict(mode="turbo"), dict(max_auto_replies=99), dict(reply_delay_minutes="x"), dict(disclose="yes")]
)
def test_bad_settings_are_refused(ws, sdk, bad):
    body = {"mode": "review", "max_auto_replies": 3, "reply_delay_minutes": 0, "disclose": True} | bad
    assert call(ws, "POST", "/api/ai/settings", body)[0] == 400


# ------------------------------------------------------------------ the whole path: reply arrives, AI answers, it is sent


def test_autonomous_end_to_end_a_reply_arrives_and_is_answered_in_the_same_chat(ws, env, transport, sdk):  # noqa: F811
    started(ws, transport)
    settings(ws, "autonomous", confirm=True)
    sdk._texts.append(send("Thanks for getting back to me. I am looking at how teams run outbound."))
    assert webhook(ws, "Sure, what is it about?")[0] == 200
    with ws.store() as s:
        assert s.contact("r0001").status == C.REPLIED
        d = s.drafts(kind="reply")[0]
        assert d.status == "approved" and d.decided_by == "auto" and d.body.endswith("AI assistant")
    scheduler.step(ws, MON_10.replace(minute=30), transport)
    posts = [r for r in transport.requests if r["path"].endswith("/chats/chat-1/messages/send")]
    assert len(posts) == 1 and posts[0]["body"]["text"].startswith("Thanks for getting back")
    with ws.store() as s:
        assert s.drafts(kind="reply")[0].status == "sent"


def test_review_end_to_end_nothing_is_sent_until_a_person_approves(ws, env, transport, sdk):  # noqa: F811
    started(ws, transport)
    settings(ws, "review")
    sdk._texts.append(send("Happy to explain more."))
    webhook(ws, "Sure, what is it about?")
    scheduler.step(ws, MON_10.replace(minute=30), transport)
    assert not [r for r in transport.requests if "chats/" in r["path"]]  # held
    _, box = call(ws, "GET", "/api/inbox")
    assert box["conversations"][0]["attention"] == "draft"
    _, th = call(ws, "GET", "/api/inbox/r0001")
    draft = th["drafts"][0]
    assert (
        call(
            ws,
            "POST",
            "/api/ai/drafts/decide",
            {"id": draft["id"], "action": "approve", "body": "Happy to explain more, edited by me."},
        )[0]
        == 200
    )
    scheduler.step(ws, MON_10.replace(minute=45), transport)
    posts = [r for r in transport.requests if "chats/chat-1" in r["path"]]
    assert posts[0]["body"]["text"] == "Happy to explain more, edited by me."


def test_a_stop_request_by_webhook_stops_the_contact_with_no_ai_call(ws, env, transport, sdk):  # noqa: F811
    started(ws, transport)
    settings(ws, "autonomous", confirm=True)
    assert webhook(ws, "please stop messaging me")[0] == 200
    assert sdk.calls == []
    with ws.store() as s:
        assert s.contact("r0001").status == C.STOPPED and s.drafts() == []


def test_a_pricing_question_lands_in_needs_you_and_the_human_answer_is_validated(ws, env, transport, sdk):  # noqa: F811
    started(ws, transport)
    settings(ws, "autonomous", confirm=True)
    webhook(ws, "What does it cost?")  # 'cost' alone is fine; use a clear trigger below
    webhook(ws, "Send me your pricing please", mid="m2")
    _, box = call(ws, "GET", "/api/inbox")
    assert box["conversations"][0]["attention"] == "needs_you"
    _, th = call(ws, "GET", "/api/inbox/r0001")
    esc = next(d for d in th["drafts"] if d["status"] == "escalated")
    assert call(ws, "POST", "/api/ai/drafts/decide", {"id": esc["id"], "action": "approve", "body": ""})[0] == 422  # empty
    assert (
        call(ws, "POST", "/api/ai/drafts/decide", {"id": esc["id"], "action": "approve", "body": "see https://x.example"})[0]
        == 422
    )  # link
    assert (
        call(
            ws,
            "POST",
            "/api/ai/drafts/decide",
            {"id": esc["id"], "action": "approve", "body": "Happy to share pricing on a short call."},
        )[0]
        == 200
    )


def test_step_drafts_in_review_mode_hold_the_live_send_until_approved(ws, env, transport, sdk):  # noqa: F811
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    settings(ws, "review")
    sdk._texts.append(send("Hi Mira, I would love to connect and compare notes."))
    scheduler.step(ws, MON_10, transport)
    assert not [r for r in transport.requests if r["path"].endswith("/relation-requests")]
    _, st = call(ws, "GET", "/api/live")
    assert st["status"]["held"] == 1
    with ws.store() as s:
        d = s.drafts(kind="step")[0]
    assert d.status == "pending" and d.step == 1
    call(ws, "POST", "/api/ai/drafts/decide", {"id": d.id, "action": "approve"})
    scheduler.step(ws, MON_10.replace(minute=5), transport)
    invites = [r for r in transport.requests if r["path"].endswith("/relation-requests")]
    assert invites and invites[0]["body"]["message"] == "Hi Mira, I would love to connect and compare notes."


def test_rejecting_a_draft_means_that_step_is_never_sent(ws, env, transport, sdk):  # noqa: F811
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    settings(ws, "review")
    sdk._texts.append(send("Hi Mira, let us connect."))
    scheduler.step(ws, MON_10, transport)
    with ws.store() as s:
        d = s.drafts(kind="step")[0]
    assert call(ws, "POST", "/api/ai/drafts/decide", {"id": d.id, "action": "reject"})[0] == 200
    scheduler.step(ws, MON_10.replace(minute=5), transport)
    assert not [r for r in transport.requests if r["path"].endswith("/relation-requests")]
    assert call(ws, "POST", "/api/ai/drafts/decide", {"id": d.id, "action": "approve"})[0] == 409  # already decided


def test_switching_to_off_makes_sending_revert_to_the_templates_immediately(ws, env, transport, sdk):  # noqa: F811
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    settings(ws, "autonomous", confirm=True)
    settings(ws, "off")
    scheduler.step(ws, MON_10, transport)
    assert sdk.calls == []
    invites = [r for r in transport.requests if r["path"].endswith("/relation-requests")]
    assert invites and "Mira" in invites[0]["body"]["message"]


def test_decide_validates_its_input(ws, sdk):
    assert call(ws, "POST", "/api/ai/drafts/decide", {"id": "1", "action": "approve"})[0] == 400
    assert call(ws, "POST", "/api/ai/drafts/decide", {"id": 1, "action": "maybe"})[0] == 400
    assert call(ws, "POST", "/api/ai/drafts/decide", {"id": 999, "action": "approve"})[0] == 404
    assert call(ws, "GET", "/api/inbox/r9999")[0] == 404


def test_every_ai_route_is_locked_behind_the_login(ws):
    auth = Auth("a-long-enough-password", "s" * 40)
    for method, path in (
        ("GET", "/api/ai"),
        ("POST", "/api/ai/settings"),
        ("GET", "/api/inbox"),
        ("GET", "/api/inbox/r0001"),
        ("POST", "/api/ai/drafts/decide"),
    ):
        res = dispatch(ws, Request(method, path, {}, b"{}", {"host": "x"}), auth=auth)
        assert res.status == 401, path


def test_the_state_says_whether_real_sending_is_on_so_the_footer_never_lies(ws, env, transport):  # noqa: F811
    assert call(ws, "GET", "/api/state")[1]["live_sending"] is False
    launched(ws)
    call(ws, "POST", "/api/live/start", {"contacts": ["r0001"], "confirm": True})
    assert call(ws, "GET", "/api/state")[1]["live_sending"] is True
    call(ws, "POST", "/api/live/stop")
    assert call(ws, "GET", "/api/state")[1]["live_sending"] is False
