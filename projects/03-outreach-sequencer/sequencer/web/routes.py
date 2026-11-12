"""Route table and dispatcher: Request in, Response out. No sockets, so tests call `dispatch` directly."""

from __future__ import annotations

import logging
import mimetypes
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from ..engine import EngineError
from ..importer import MappingError
from ..rules import RulesError
from ..sequence import SequenceError
from ..workflow import ApprovalError
from . import routes_ai as ai
from . import routes_config as cfg
from . import routes_data as data
from . import routes_live as live
from .auth import Auth
from .http import ApiError, Request, Response, ok
from .workspace import Workspace

log = logging.getLogger("sequencer.web")
STATIC = Path(__file__).resolve().parent / "static"
Handler = Callable[[Workspace, Request], Response]

ROUTES: dict[tuple[str, str], Handler] = {
    ("GET", "/api/state"): data.get_state,
    ("POST", "/api/upload"): data.upload,
    ("POST", "/api/import"): data.run_import,
    ("POST", "/api/contacts/add"): data.add_one,
    ("GET", "/api/validation"): data.get_validation,
    ("GET", "/api/contacts"): data.list_contacts,
    ("POST", "/api/run"): data.run_sim,
    ("POST", "/api/event"): data.post_event,
    ("GET", "/api/report"): data.get_report,
    ("GET", "/api/report.xlsx"): data.download_report,
    ("GET", "/api/config"): cfg.get_config,
    ("POST", "/api/lint"): cfg.lint,
    ("POST", "/api/templates"): cfg.save_template,
    ("POST", "/api/templates/delete"): cfg.delete_template,
    ("POST", "/api/templates/approve"): cfg.approve,
    ("POST", "/api/preview"): cfg.preview,
    ("POST", "/api/sequence/check"): cfg.check_sequence,
    ("POST", "/api/sequence"): cfg.save_sequence,
    ("POST", "/api/rules"): cfg.save_rules,
    ("POST", "/api/sender"): cfg.save_sender,
    ("GET", "/api/launch/check"): cfg.check_launch,
    ("POST", "/api/launch"): cfg.do_launch,
    ("POST", "/api/sample"): cfg.load_sample,
    ("POST", "/api/reset"): cfg.reset,
    ("GET", "/api/live"): live.get_status,
    ("POST", "/api/live/preflight"): live.preflight,
    ("POST", "/api/live/start"): live.start,
    ("POST", "/api/live/stop"): live.stop,
    ("POST", "/api/webhooks/unipile"): live.webhook,
    ("GET", "/api/ai"): ai.get_ai,
    ("POST", "/api/ai/settings"): ai.save_settings,
    ("GET", "/api/inbox"): ai.inbox,
    ("POST", "/api/ai/drafts/decide"): ai.decide,
}
CONTACT_PATH = re.compile(r"^/api/contacts/(r\d{4,})$")
THREAD_PATH = re.compile(r"^/api/inbox/(r\d{4,})$")
CLIENT_ERRORS = (MappingError, SequenceError, RulesError, EngineError, ApprovalError)


def _error(err: ApiError) -> Response:
    return ok({"error": err.message, **err.extra}, err.status)


def _static(path: str) -> Response:
    rel = "index.html" if path in ("", "/") else path.lstrip("/")
    target = (STATIC / rel).resolve()
    if STATIC.resolve() not in target.parents or not target.is_file():
        return ok({"error": "Not found"}, 404)
    ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
        ctype += "; charset=utf-8"
    return Response(200, target.read_bytes(), ctype, (("Cache-Control", "no-store"),))


def same_origin(req: Request) -> bool:
    """Reject cross-site writes: a web page on another origin must not be able to drive this local tool."""
    origin = req.headers.get("origin")
    return origin is None or urlsplit(origin).netloc == req.headers.get("host", "")


PUBLIC_STATIC = ("/login.html", "/app.css", "/js/login.js")
WEBHOOK_PATH = "/api/webhooks/unipile"


def _secure(req: Request) -> bool:
    return req.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


def _login(auth: Auth, req: Request) -> Response:
    if auth.locked():
        raise ApiError(429, "Too many wrong passwords. Wait a minute and try again.")
    password = req.json().get("password")
    if not isinstance(password, str) or not password:
        raise ApiError(400, "Enter the password")
    if not auth.check_password(password):
        raise ApiError(401, "That password is incorrect")
    res = ok({"ok": True})
    return Response(res.status, res.body, res.content_type, (auth.cookie_header(auth.issue(), _secure(req)),))


def _gate(auth: Auth, req: Request) -> Response | None:
    """The response to send instead of serving the request, or None when it may proceed."""
    if req.path == "/healthz":
        return ok({"ok": True})
    if req.path == "/api/login" and req.method == "POST":
        return _login(auth, req)
    if req.path == "/api/logout" and req.method == "POST":
        res = ok({"ok": True})
        return Response(res.status, res.body, res.content_type, (auth.clear_header(_secure(req)),))
    if req.path == WEBHOOK_PATH and req.method == "POST":
        return None  # public by design: the handler rejects anything without a valid signature
    if auth.authenticated(req.headers):
        return None
    if req.method in ("GET", "HEAD") and not req.path.startswith("/api/"):
        if req.path in PUBLIC_STATIC:
            return None
        return _static("/login.html") if req.path in ("", "/") else ok({"error": "Sign in first"}, 401)
    raise ApiError(401, "Sign in first")


def dispatch(ws: Workspace, req: Request, auth: Auth | None = None) -> Response:
    try:
        if req.method not in ("GET", "HEAD") and not same_origin(req):
            raise ApiError(403, "Cross-origin requests are not allowed")
        if auth is not None:
            gated = _gate(auth, req)
            if gated is not None:
                return gated
        elif req.path == "/healthz":
            return ok({"ok": True})
        if not req.path.startswith("/api/"):
            return _static(req.path) if req.method in ("GET", "HEAD") else ok({"error": "Not found"}, 404)
        match = CONTACT_PATH.match(req.path)
        if match and req.method == "GET":
            return data.get_contact(ws, req, match.group(1))
        thread_match = THREAD_PATH.match(req.path)
        if thread_match and req.method == "GET":
            return ai.thread(ws, req, thread_match.group(1))
        handler = ROUTES.get((req.method, req.path))
        if handler is None:
            raise ApiError(404, "Not found")
        return handler(ws, req)
    except ApiError as err:
        return _error(err)
    except CLIENT_ERRORS as exc:
        return ok({"error": str(exc)}, 422)
    except Exception:
        log.exception("unhandled error on %s %s", req.method, req.path)
        return ok({"error": "Something went wrong on the server. Details are in the terminal."}, 500)
