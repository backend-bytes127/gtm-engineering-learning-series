"""The local web server (standard library only). Listens on this machine only: the data is personal and the CRM token is real."""
from __future__ import annotations

import webbrowser
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .app import Config, dispatch
from .http import Request
from .sessions import VisitorStore

MAX_BODY = 60 * 1024 * 1024


def make_handler(cfg: Config, store: VisitorStore):
    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self.send_error(413)
                return
            body = self.rfile.read(length) if length else b""
            headers = {k.lower(): v for k, v in self.headers.items()}
            res = dispatch(cfg, store, Request(self.command, self.path.split("?")[0], body, headers))
            self.send_response(res.status)
            self.send_header("Content-Type", res.content_type)
            self.send_header("Content-Length", str(len(res.body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; img-src 'self' data:")
            for k, v in res.headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(res.body)

        do_GET = do_POST = _serve

        def log_message(self, fmt: str, *args) -> None:
            if self.command != "GET":
                super().log_message(fmt, *args)

    return Handler


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def check_exposure(cfg: Config, host: str) -> None:
    """Fail closed: a copy reachable from outside must never hold a CRM token or be able to push."""
    if host not in LOOPBACK and (cfg.crm_token or cfg.allow_push):
        raise SystemExit("Refusing to listen on a public address with a HubSpot token loaded. Run the CRM push locally.")


def serve(cfg: Config, host: str, port: int, open_browser: bool = True) -> None:
    check_exposure(cfg, host)
    public = host not in LOOPBACK
    server = ThreadingHTTPServer((host, port), BaseHTTPRequestHandler)
    bound = server.server_port
    live = replace(cfg, hosted=public, allowed_hosts=None if public else (f"127.0.0.1:{bound}", f"localhost:{bound}"))
    server.RequestHandlerClass = make_handler(live, VisitorStore())
    url = f"http://{host}:{bound}/"
    print(f"Contact Cleaning App running at {url}  (Ctrl+C to stop)")
    print("HubSpot:", "token loaded" if cfg.crm_token else "not configured", "| push", "ON" if cfg.allow_push else "off (preview only)")
    if public:
        print("Public mode: no login, in-memory sessions per visitor, CRM push unavailable.")
    if open_browser and not public:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
