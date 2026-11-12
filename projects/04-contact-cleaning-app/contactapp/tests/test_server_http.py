"""Real sockets: the handler, headers and the multipart reader as a browser would use them."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from contactapp.app import Config
from contactapp.http import ApiError, Request
from contactapp.server import make_handler
from contactapp.sessions import VisitorStore
from contactapp.tests.conftest import multipart


@pytest.fixture
def live():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Config(allowed_hosts=None), VisitorStore()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def start(base):
    """Load the page like a browser: returns the cookie and page token."""
    _, headers, body = fetch(base + "/")
    return headers["Set-Cookie"].split(";")[0], body.split(b'name="page-token" content="')[1].split(b'"')[0].decode()


def fetch(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_security_headers_and_page(live):
    base = live
    status, headers, body = fetch(base + "/")
    assert status == 200 and headers["X-Content-Type-Options"] == "nosniff" and "default-src 'self'" in headers["Content-Security-Policy"]
    assert b"Contact Cleaning App" in body


def test_full_flow_over_http(live, sample_files):
    base = live
    cookie, token = start(base)
    body, ctype = multipart(sample_files)
    status, _, out = fetch(base + "/api/process", body, {"content-type": ctype, "x-page-token": token, "cookie": cookie})
    assert status == 200 and json.loads(out)["summary"]["people"] == 12
    status, headers, data = fetch(base + "/api/download/audit.xlsx", headers={"cookie": cookie})
    assert status == 200 and data.startswith(b"PK") and "Cleaning_Audit" in headers["Content-Disposition"]


def test_post_without_token_over_http(live):
    base = live
    cookie, _ = start(base)
    assert fetch(base + "/api/sample", b"{}", {"cookie": cookie})[0] == 403


def test_request_helpers_reject_bad_input():
    with pytest.raises(ApiError):
        Request("POST", "/x", b"{nope").json()
    with pytest.raises(ApiError):
        Request("POST", "/x", b"[1]").json()
    with pytest.raises(ApiError):
        Request("POST", "/x", b"", {"content-type": "text/plain"}).files()
