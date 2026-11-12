from __future__ import annotations

import pytest

from contactapp import PROJECT_02, intake
from contactapp.app import Config, dispatch
from contactapp.http import Request
from contactapp.sessions import VisitorStore

HOST = "127.0.0.1:9"


@pytest.fixture(scope="session")
def sample_files() -> dict[str, bytes]:
    return {s.key: (PROJECT_02 / "sample-data" / s.filename).read_bytes() for s in intake.SLOTS}


def multipart(files: dict[str, bytes], boundary: str = "XBOUNDARYX") -> tuple[bytes, str]:
    out = b""
    for name, data in files.items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.xlsx"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class Client:
    """Calls dispatch directly, like a browser: it loads the page first, then keeps the cookie and the page token."""

    def __init__(self, cfg: Config, store: VisitorStore | None = None, start: bool = True):
        self.cfg, self.store = cfg, store or VisitorStore()
        self.cookie, self.token = "", ""
        if start:
            self.open_page()

    def open_page(self, host: str = HOST):
        res = dispatch(self.cfg, self.store, Request("GET", "/", b"", {"host": host}))
        set_cookie = dict(res.headers).get("Set-Cookie", "")
        self.cookie = set_cookie.split(";")[0]
        self.token = res.body.split(b'name="page-token" content="')[1].split(b'"')[0].decode() if res.status == 200 else ""
        return res

    def call(self, method, path, body=b"", headers=None, token=True, cookie=True, host=HOST):
        sent = {"x-page-token": self.token} if token else {}
        sent |= {"cookie": self.cookie} if cookie else {}
        h = {"host": host, **sent, **(headers or {})}
        return dispatch(self.cfg, self.store, Request(method, path, body, h))

    def upload(self, files):
        body, ctype = multipart(files)
        return self.call("POST", "/api/process", body, {"content-type": ctype})


@pytest.fixture
def make_client():
    def build(**kw):
        return Client(Config(**{"allowed_hosts": (HOST,), **kw}))

    return build
