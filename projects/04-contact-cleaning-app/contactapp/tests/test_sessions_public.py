import json

import pytest

from contactapp.app import Config, dispatch
from contactapp.http import Request
from contactapp.server import check_exposure
from contactapp.sessions import RUNS_PER_MINUTE, VisitorStore
from contactapp.tests.conftest import Client


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def public(store=None):
    return Client(Config(allowed_hosts=None, hosted=True), store)


def test_visitors_cannot_see_each_others_data():
    store = VisitorStore()
    a, b = public(store), public(store)
    assert a.call("POST", "/api/sample").status == 200
    assert b.call("GET", "/api/result").status == 409  # b has no result of their own
    assert json.loads(a.call("GET", "/api/state").body)["has_result"] is True
    assert json.loads(b.call("GET", "/api/state").body)["has_result"] is False


def test_one_visitors_token_does_not_work_for_another():
    store = VisitorStore()
    a, b = public(store), public(store)
    b.token = a.token
    assert b.call("POST", "/api/sample").status == 403


def test_api_without_a_session_cookie_is_refused():
    assert public().call("GET", "/api/state", cookie=False).status == 401


def test_sessions_expire_after_inactivity():
    clock = Clock()
    c = public(VisitorStore(ttl=60, clock=clock))
    c.call("POST", "/api/sample")
    clock.now = 61
    assert c.call("GET", "/api/result").status == 401


def test_activity_keeps_a_session_alive():
    clock = Clock()
    c = public(VisitorStore(ttl=60, clock=clock))
    for t in (30, 60, 90):
        clock.now = t
        assert c.call("GET", "/api/state").status == 200


def test_oldest_visitor_is_dropped_when_full():
    store = VisitorStore(limit=2)
    first, _second, _third = public(store), public(store), public(store)
    assert first.call("GET", "/api/state").status == 401


def test_runs_are_rate_limited_then_recover():
    clock = Clock()
    c = public(VisitorStore(clock=clock))
    codes = [c.call("POST", "/api/sample").status for _ in range(RUNS_PER_MINUTE + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}
    clock.now = 61
    assert c.call("POST", "/api/sample").status == 200


def test_cookie_is_http_only_strict_and_secure_when_hosted():
    c = public()
    res = dispatch(c.cfg, c.store, Request("GET", "/", b"", {"host": "x"}))
    cookie = dict(res.headers)["Set-Cookie"]
    assert all(flag in cookie for flag in ("HttpOnly", "SameSite=Strict", "Secure"))


def test_hosted_state_says_so_and_has_no_crm():
    state = json.loads(public().call("GET", "/api/state").body)
    assert state["hosted"] is True and state["crm"] == {"configured": False, "push_enabled": False}


def test_a_public_copy_refuses_a_crm_token():
    with pytest.raises(SystemExit):
        check_exposure(Config(allowed_hosts=None, crm_token="t"), "0.0.0.0")
    with pytest.raises(SystemExit):
        check_exposure(Config(allowed_hosts=None, allow_push=True), "0.0.0.0")
    check_exposure(Config(allowed_hosts=None, crm_token="t"), "127.0.0.1")  # local use is fine
    check_exposure(Config(allowed_hosts=None), "0.0.0.0")  # public without a token is fine


def test_health_check_needs_no_session_or_host_match():
    c = Client(Config(allowed_hosts=None), start=False)
    res = c.call("GET", "/healthz", token=False, cookie=False, host="anything.railway.app")
    assert res.status == 200 and res.body == b"ok"
