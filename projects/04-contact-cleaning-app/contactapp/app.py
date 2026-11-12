"""The API: routes, the safety checks around them, and the in-memory state of one working session."""
from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import crm_plan, intake, service
from .http import ApiError, Request, Response, ok
from .hubspot import CrmError, HubSpotClient, Transport, push
from .sessions import TTL_SECONDS, Visitor, VisitorStore
from .state import Session

STATIC = Path(__file__).resolve().parent / "static"
MAX_ROWS_SHOWN = 2000
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class Config:
    allowed_hosts: tuple[str, ...] | None  # None on a public deployment: the Host header cannot be pinned
    hosted: bool = False
    crm_token: str = ""
    expected_portal: str = ""
    allow_push: bool = False
    transport: Transport | None = None


def _need_result(session: Session) -> service.RunResult:
    if session.result is None:
        raise ApiError(409, "Upload and process the files first.")
    return session.result


def _client(cfg: Config) -> HubSpotClient:
    kwargs = {"transport": cfg.transport} if cfg.transport else {}
    return HubSpotClient(cfg.crm_token, **kwargs)


def _verified_client(cfg: Config) -> tuple[HubSpotClient, str]:
    """A client for the right portal, or an error. A mismatch with the expected portal id refuses to continue."""
    client = _client(cfg)
    portal = client.portal_id()
    if cfg.expected_portal and portal != cfg.expected_portal:
        raise ApiError(409, "The token belongs to a different HubSpot account than the one this app was set up for.")
    return client, portal


def state(cfg: Config, session: Session) -> dict:
    res = session.result
    return {
        "slots": [{"key": s.key, "label": s.label, "sheets": list(s.sheets)} for s in intake.SLOTS],
        "has_result": res is not None,
        "summary": res.summary if res else None,
        "crm": {"configured": bool(cfg.crm_token), "push_enabled": cfg.allow_push},
        "hosted": cfg.hosted,
        "ttl_minutes": TTL_SECONDS // 60,
    }


def process(cfg: Config, session: Session, req: Request) -> Response:
    files = req.files()
    template = files.pop("template", None)
    try:
        session.set(service.run_files(files, template))
    except intake.IntakeError as exc:
        raise ApiError(422, "Some files cannot be used.", problems=exc.problems) from exc
    return ok({"summary": session.result.summary})  # type: ignore[union-attr]


def result(cfg: Config, session: Session, req: Request) -> Response:
    res = _need_result(session)
    shown = res.rows[:MAX_ROWS_SHOWN]
    return ok({"summary": res.summary, "rows": shown, "removed": res.removed, "truncated": len(res.rows) > len(shown)})


def download(session: Session, which: str) -> Response:
    res = _need_result(session)
    data, name = (res.final_xlsx, "Final_Contact_List.xlsx") if which == "final" else (res.audit_xlsx, "Cleaning_Audit.xlsx")
    return Response(200, data, XLSX, (("Content-Disposition", f'attachment; filename="{name}"'),))


def crm_plan_view(cfg: Config, session: Session, req: Request) -> Response:
    _need_result(session)
    return ok(crm_plan.preview(session.plan))  # type: ignore[arg-type]


def crm_test(cfg: Config, session: Session, req: Request) -> Response:
    if not cfg.crm_token:
        raise ApiError(409, "No HubSpot token is configured. Start the app with --crm-env-file.")
    try:
        _, portal = _verified_client(cfg)
    except CrmError as exc:
        raise ApiError(502, str(exc)) from exc
    return ok({"portal_id": portal, "matches_expected": (not cfg.expected_portal) or portal == cfg.expected_portal})


def crm_push(cfg: Config, session: Session, req: Request) -> Response:
    _need_result(session)
    plan = session.plan
    if not cfg.allow_push:
        raise ApiError(403, "Pushing is switched off. Start the app with --allow-crm-push to enable it.")
    if not cfg.crm_token:
        raise ApiError(409, "No HubSpot token is configured. Start the app with --crm-env-file.")
    if req.json().get("confirm_contacts") != len(plan.contacts):  # type: ignore[union-attr]
        raise ApiError(400, "Type the number of contacts to confirm the push.", expected=len(plan.contacts))  # type: ignore[union-attr]
    try:
        client, portal = _verified_client(cfg)
        report = push(plan, client)  # type: ignore[arg-type]
    except CrmError as exc:
        raise ApiError(502, str(exc)) from exc
    return ok({"portal_id": portal, "ok": report.ok, "contacts": report.contacts_sent, "companies": report.companies_sent,
               "associations": report.associations_made, "errors": list(report.errors)}, 200 if report.ok else 207)


def page(name: str, token: str = "") -> Response:
    path = (STATIC / name).resolve()
    if STATIC not in path.parents or not path.is_file():
        raise ApiError(404, "Not found")
    body = path.read_bytes()
    if name == "index.html":
        body = body.replace(b"__PAGE_TOKEN__", token.encode())
    return Response(200, body, TYPES.get(path.suffix, "application/octet-stream"))


def dispatch(cfg: Config, store: VisitorStore, req: Request) -> Response:
    try:
        return _route(cfg, store, req)
    except ApiError as exc:
        return ok({"error": exc.message, **exc.extra}, exc.status)


def _cookie(req: Request, name: str) -> str:
    for part in req.headers.get("cookie", "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def _start_page(cfg: Config, store: VisitorStore, req: Request) -> Response:
    sid, visitor = store.create()
    secure = cfg.hosted or req.headers.get("x-forwarded-proto") == "https"
    cookie = f"sid={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={TTL_SECONDS}" + ("; Secure" if secure else "")
    res = page("index.html", visitor.token)
    return Response(res.status, res.body, res.content_type, (("Set-Cookie", cookie),))


def _visitor(store: VisitorStore, req: Request) -> Visitor:
    visitor = store.get(_cookie(req, "sid"))
    if visitor is None:
        raise ApiError(401, "Your session has expired. Reload the page to start again.")
    if req.method == "POST" and not secrets.compare_digest(req.headers.get("x-page-token", ""), visitor.token):
        raise ApiError(403, "Missing or wrong page token. Reload the page.")
    return visitor


def _route(cfg: Config, store: VisitorStore, req: Request) -> Response:
    if cfg.allowed_hosts is not None and req.headers.get("host", "") not in cfg.allowed_hosts:
        raise ApiError(403, "Unexpected host")
    if req.method == "GET" and req.path == "/healthz":
        return Response(200, b"ok", "text/plain; charset=utf-8")
    if req.method == "GET" and req.path == "/":
        return _start_page(cfg, store, req)
    if req.method == "GET" and req.path.startswith("/static/"):
        return page(req.path.removeprefix("/static/"))
    if req.method not in ("GET", "POST") or not req.path.startswith("/api/"):
        raise ApiError(404, "Not found")
    session = _visitor(store, req).session
    get: dict[str, Callable[[], Response]] = {
        "/api/state": lambda: ok(state(cfg, session)),
        "/api/result": lambda: result(cfg, session, req),
        "/api/crm/plan": lambda: crm_plan_view(cfg, session, req),
        "/api/download/final.xlsx": lambda: download(session, "final"),
        "/api/download/audit.xlsx": lambda: download(session, "audit"),
    }
    post: dict[str, Callable[[], Response]] = {
        "/api/process": lambda: _limited(store, lambda: process(cfg, session, req)),
        "/api/sample": lambda: _limited(store, lambda: _sample(session)),
        "/api/crm/test": lambda: crm_test(cfg, session, req),
        "/api/crm/push": lambda: crm_push(cfg, session, req),
    }
    handler = (get if req.method == "GET" else post).get(req.path)
    if handler is None:
        raise ApiError(404, "Not found")
    return handler()


def _limited(store: VisitorStore, action: Callable[[], Response]) -> Response:
    if not store.allow_run():
        raise ApiError(429, "Too many runs right now. Wait a minute and try again.")
    return action()


def _sample(session: Session) -> Response:
    session.set(service.run_sample())
    return ok({"summary": session.result.summary})  # type: ignore[union-attr]
