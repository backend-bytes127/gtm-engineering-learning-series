"""API for live sending: status, preflight, start, stop, and the signed Unipile webhook."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..ai.replies import handle_inbound
from ..ai.runtime import ai_env, make_ai
from ..engine import get_sender
from ..live.config import live_settings
from ..live.runner import HARD_MAX_CONTACTS, LiveError, apply_webhook, get_live, start_live, stop_live
from ..live.unipile import Transport, UnipileClient, UnipileError, urllib_transport, verify_signature
from .http import ApiError, Request, Response, ok
from .workspace import Workspace

TRANSPORT: Transport = urllib_transport  # tests replace this with a fake


def make_client() -> UnipileClient:
    cfg = live_settings()
    if not cfg.configured:
        raise ApiError(409, "Live sending is not set up. Add UNIPILE_API_KEY and UNIPILE_ACCOUNT_ID to the app's environment.")
    return UnipileClient(cfg.api_key, cfg.account_id, transport=TRANSPORT)


def get_status(ws: Workspace, req: Request) -> Response:
    cfg = live_settings()
    with ws.store() as s:
        live = get_live(s)
        chosen = [
            {
                "key": k,
                "name": (s.contact(k).contact.name if s.contact(k) else k),
                "status": s.contact(k).status if s.contact(k) else "",
            }
            for k in live.get("contacts", [])
        ]
        return ok(
            {
                "configured": cfg.configured,
                "webhook_secret_set": bool(cfg.webhook_secret),
                "enabled": bool(live.get("enabled")),
                "started": bool(live.get("contacts")),
                "contacts": chosen,
                "status": s.get_setting("live_status"),
                "caps": {"invites": cfg.max_invites, "messages": cfg.max_messages},
                "max_contacts": HARD_MAX_CONTACTS,
                "simulated": (s.get_setting("mode") or {}).get("provider") == "simulated",
            }
        )


def _keys(req: Request) -> list[str]:
    keys = req.json().get("contacts")
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        raise ApiError(400, "contacts must be a list of contact keys")
    return keys


def preflight(ws: Workspace, req: Request) -> Response:
    """Read-only: look each chosen person up on LinkedIn and say what a send would do. Sends nothing."""
    keys = _keys(req)
    if len(keys) > HARD_MAX_CONTACTS:
        raise ApiError(400, f"Choose at most {HARD_MAX_CONTACTS} contacts")
    client = make_client()
    out = []
    with ws.store() as s:
        for key in keys:
            tracked = s.contact(key)
            if tracked is None:
                raise ApiError(404, f"No contact {key}")
            c = tracked.contact
            if not c.linkedin_url:
                out.append({"key": key, "name": c.name, "result": "no_linkedin", "note": "No LinkedIn URL on file"})
                continue
            try:
                p = client.get_profile(c.linkedin_url)
            except UnipileError as exc:
                raise ApiError(502, f"LinkedIn lookup failed for {c.name}: {exc.detail[:120]}") from exc
            if p is None:
                out.append({"key": key, "name": c.name, "result": "not_found", "note": "Profile not found. Check the URL."})
            elif p.is_self:
                out.append({"key": key, "name": c.name, "result": "self", "note": "This is your own profile"})
            else:
                out.append(
                    {
                        "key": key,
                        "name": c.name,
                        "result": "connected" if p.is_connected else "not_connected",
                        "note": "Already connected: the invite is skipped and the message goes straight out"
                        if p.is_connected
                        else "Not connected: an invite goes first, the message after they accept",
                    }
                )
    return ok({"contacts": out})


def start(ws: Workspace, req: Request) -> Response:
    body = req.json()
    if body.get("confirm") is not True:
        raise ApiError(400, "Confirm that you want to send real messages")
    make_client()  # fails clearly when live sending is not configured
    keys = _keys(req)
    with ws.store() as s:
        try:
            start_live(s, keys, datetime.now(timezone.utc))
        except LiveError as exc:
            raise ApiError(409, str(exc)) from exc
    return ok({"started": True, "contacts": keys})


def stop(ws: Workspace, req: Request) -> Response:
    with ws.store() as s:
        stop_live(s)
    return ok({"enabled": False})


def webhook(ws: Workspace, req: Request) -> Response:
    """Public endpoint: nothing is read until the HMAC signature over the raw body checks out."""
    cfg = live_settings()
    raw = req.body.decode("utf-8", "replace")
    if not verify_signature(raw, req.headers.get("unipile-signature"), cfg.webhook_secret):
        raise ApiError(401, "Invalid signature")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(400, "Not valid JSON") from exc
    with ws.store() as s:
        sender = get_sender(s)

        def on_inbound(key: str, text: str, chat_id: str, at: datetime) -> None:
            if sender is not None:
                handle_inbound(s, make_ai(), ai_env().daily_call_cap, sender, key, text, at)

        apply_webhook(s, envelope, cfg.account_id, datetime.now(timezone.utc), on_inbound=on_inbound)
    return ok({"ok": True})
