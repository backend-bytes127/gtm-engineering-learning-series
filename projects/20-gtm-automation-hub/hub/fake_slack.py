"""A local stand-in for Slack. It records what would have been posted and can be told to fail.

``python -m hub.fake_slack --port 8787`` prints one line per message. It listens on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class Recorder:
    """Thread-safe record of attempts. ``fail_next`` makes that many following posts return HTTP 500."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: tuple[dict[str, Any], ...] = ()
        self._fail_next = 0

    def reset(self, fail_next: int = 0) -> None:
        with self._lock:
            self._entries, self._fail_next = (), fail_next

    def post(self, path: str, message: Any) -> int:
        with self._lock:
            status = 500 if self._fail_next > 0 else 200
            self._fail_next = max(0, self._fail_next - 1)
            self._entries = (*self._entries, {"path": path, "message": message, "status": status})
            return status

    def entries(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return self._entries


def make_server(recorder: Recorder, port: int = 0, echo: bool = False) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - name fixed by http.server
            length = int(self.headers.get("content-length") or 0)
            try:
                message = json.loads(self.rfile.read(min(length, 100_000)).decode("utf-8"))
            except ValueError:
                self._finish(400, b"invalid_payload")
                return
            status = recorder.post(self.path, message)
            if echo:
                print(f"{status} {self.path} {json.dumps(message, ensure_ascii=False)}", flush=True)
            self._finish(status, b"ok" if status == 200 else b"error")

        def _finish(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            """Silence the default access log."""

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local fake Slack endpoint")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    server = make_server(Recorder(), args.port, echo=True)
    print(f"fake Slack listening on 127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":  # pragma: no cover
    main()
