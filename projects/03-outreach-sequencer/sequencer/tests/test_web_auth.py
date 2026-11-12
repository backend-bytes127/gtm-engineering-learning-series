import json
import time

import pytest

from sequencer.web.auth import Auth, parse_cookies
from sequencer.web.http import Request
from sequencer.web.routes import dispatch
from sequencer.web.workspace import Workspace

PASSWORD = "correct horse battery staple"


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "ws")


@pytest.fixture
def auth():
    clock = {"now": 1_000_000.0}
    a = Auth(PASSWORD, "s" * 40, now=lambda: clock["now"])
    a.clock = clock
    return a


def call(ws, auth, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else b""
    res = dispatch(ws, Request(method, path, {}, data, {"host": "app.example", **(headers or {})}), auth=auth)
    kind = res.content_type.startswith("application/json")
    return res, (json.loads(res.body) if kind else res.body)


def login(ws, auth, password=PASSWORD, headers=None):
    res, body = call(ws, auth, "POST", "/api/login", {"password": password}, headers)
    cookie = dict(res.headers).get("Set-Cookie", "")
    return res, body, cookie.split(";")[0] if cookie else ""


def test_parse_cookies():
    assert parse_cookies("a=1; seq_session=abc.def; b=x=y") == {"a": "1", "seq_session": "abc.def", "b": "x=y"}
    assert parse_cookies("") == {}


def test_everything_but_the_login_page_is_locked_without_a_session(ws, auth):
    for path in ("/api/state", "/api/contacts", "/api/config", "/api/report.xlsx", "/api/contacts/r0001"):
        assert call(ws, auth, "GET", path)[0].status == 401, path
    assert call(ws, auth, "POST", "/api/reset", {"scope": "all"})[0].status == 401
    assert call(ws, auth, "POST", "/api/sample")[0].status == 401


def test_the_root_shows_the_login_page_and_other_static_files_are_locked(ws, auth):
    res, body = call(ws, auth, "GET", "/")
    assert res.status == 200 and b"password" in body.lower()
    assert call(ws, auth, "GET", "/js/app.js")[0].status == 401
    assert call(ws, auth, "GET", "/app.css")[0].status == 200  # the login page needs its stylesheet


def test_wrong_password_is_refused_and_sets_no_cookie(ws, auth):
    res, body, cookie = login(ws, auth, "nope")
    assert res.status == 401 and cookie == "" and "incorrect" in body["error"].lower()


def test_login_sets_a_hardened_cookie_that_unlocks_the_app(ws, auth):
    res, _, cookie = login(ws, auth, headers={"x-forwarded-proto": "https"})
    attrs = dict(res.headers)["Set-Cookie"]
    assert res.status == 200 and "HttpOnly" in attrs and "SameSite=Strict" in attrs and "Secure" in attrs and "Max-Age=" in attrs
    assert call(ws, auth, "GET", "/api/state", headers={"cookie": cookie})[0].status == 200
    assert call(ws, auth, "GET", "/js/app.js", headers={"cookie": cookie})[0].status == 200


def test_cookie_is_not_marked_secure_on_plain_http_so_local_use_still_works(ws, auth):
    res, _, _ = login(ws, auth)
    assert "Secure" not in dict(res.headers)["Set-Cookie"]


def test_tampered_or_forged_cookies_are_rejected(ws, auth):
    _, _, cookie = login(ws, auth)
    name, value = cookie.split("=", 1)
    expiry, sig = value.split(".")
    for forged in (f"{name}={expiry}.{'0' * len(sig)}", f"{name}={int(expiry) + 99999}.{sig}", f"{name}=garbage", f"{name}="):
        assert call(ws, auth, "GET", "/api/state", headers={"cookie": forged})[0].status == 401


def test_sessions_expire(ws, auth):
    _, _, cookie = login(ws, auth)
    auth.clock["now"] += 13 * 3600
    assert call(ws, auth, "GET", "/api/state", headers={"cookie": cookie})[0].status == 401


def test_a_cookie_signed_with_another_secret_is_rejected(ws, auth):
    _, _, cookie = login(ws, auth)
    other = Auth(PASSWORD, "different-secret-" * 3, now=lambda: auth.clock["now"])
    assert call(ws, other, "GET", "/api/state", headers={"cookie": cookie})[0].status == 401


def test_logout_clears_the_cookie(ws, auth):
    res, _ = call(ws, auth, "POST", "/api/logout")
    assert res.status == 200 and "Max-Age=0" in dict(res.headers)["Set-Cookie"]


def test_repeated_wrong_passwords_lock_login_even_for_the_right_one(ws, auth):
    for _ in range(5):
        assert login(ws, auth, "bad")[0].status == 401
    res, body, _ = login(ws, auth, PASSWORD)
    assert res.status == 429 and "wait" in body["error"].lower()
    auth.clock["now"] += 61
    assert login(ws, auth, PASSWORD)[0].status == 200


def test_login_validates_its_input(ws, auth):
    for body in ({}, {"password": 5}, {"password": ""}):
        assert call(ws, auth, "POST", "/api/login", body)[0].status in (400, 401)


def test_health_check_is_open_and_reveals_nothing(ws, auth):
    res, body = call(ws, auth, "GET", "/healthz")
    assert res.status == 200 and body == {"ok": True}


def test_cross_origin_login_attempts_are_refused(ws, auth):
    res, _ = call(ws, auth, "POST", "/api/login", {"password": PASSWORD}, {"origin": "https://evil.example"})
    assert res.status == 403


def test_without_auth_configured_nothing_changes_for_local_use(ws):
    res = dispatch(ws, Request("GET", "/api/state", {}, b"", {"host": "127.0.0.1:1"}))
    assert res.status == 200


def test_auth_refuses_weak_configuration():
    with pytest.raises(ValueError, match="at least 12"):
        Auth("short", "s" * 40)
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        Auth(PASSWORD, "tiny")


def test_real_clock_is_used_by_default():
    a = Auth(PASSWORD, "s" * 40)
    token = a.issue()
    assert a.valid(token) and abs(a.expiry_of(token) - (time.time() + a.ttl)) < 5
