"""The local web server (standard library only). Binds to 127.0.0.1: this is a single-user local tool."""

from __future__ import annotations

import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from ..live.scheduler import Scheduler
from .auth import Auth
from .http import Request
from .routes import dispatch
from .workspace import Workspace

MAX_BODY = 11 * 1024 * 1024


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def auth_from_env(env: dict[str, str], host: str) -> Auth | None:
    """Local use may run open; anything reachable from outside must have a password. Fails closed."""
    password, secret = env.get("APP_PASSWORD", ""), env.get("SESSION_SECRET", "")
    if not password and host not in LOOPBACK:
        raise SystemExit("Refusing to listen on a public address without a login. Set APP_PASSWORD and SESSION_SECRET.")
    if not password:
        return None
    if not secret:
        raise SystemExit("SESSION_SECRET is required when APP_PASSWORD is set.")
    try:
        return Auth(password, secret)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def make_handler(ws: Workspace, auth: Auth | None = None):
    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            parts = urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self.send_error(413)
                return
            body = self.rfile.read(length) if length else b""
            headers = {k.lower(): v for k, v in self.headers.items()}
            res = dispatch(ws, Request(self.command, parts.path, dict(parse_qsl(parts.query)), body, headers), auth=auth)
            self.send_response(res.status)
            self.send_header("Content-Type", res.content_type)
            self.send_header("Content-Length", str(len(res.body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src https://fonts.gstatic.com; img-src 'self' data:",
            )
            for k, v in res.headers:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(res.body)

        do_GET = do_POST = do_HEAD = _serve

        def log_message(self, fmt: str, *args) -> None:  # quiet: one line per API write is enough
            if self.command != "GET":
                super().log_message(fmt, *args)

    return Handler


def serve(root: Path, port: int = 8765, open_browser: bool = True, host: str = "127.0.0.1") -> None:
    import os

    auth = auth_from_env(dict(os.environ), host)
    ws = Workspace(Path(root))
    try:
        ws.store().close()  # fail at startup, with a clear message, if the data folder cannot be written
    except Exception as exc:
        raise SystemExit(f"Cannot write to the data folder {ws.root}: {exc}") from exc
    server = ThreadingHTTPServer((host, port), make_handler(ws, auth))
    scheduler = Scheduler(ws)
    scheduler.start()
    url = f"http://{host}:{server.server_port}/"
    print(f"Outreach Sequencer running at {url}  (Ctrl+C to stop)\nData is kept in {ws.root}")
    print("Login is " + ("required" if auth else "off (local use only)"))
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        scheduler.stop()
        server.server_close()
