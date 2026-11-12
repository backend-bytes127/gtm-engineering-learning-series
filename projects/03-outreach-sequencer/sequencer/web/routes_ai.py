"""API for the AI assistant: settings, the review queue, and conversations."""

from __future__ import annotations

from datetime import datetime, timezone

from .. import constants as C
from ..ai.guard import DM_MAX, EMAIL_BODY_MAX, INVITE_MAX, check_output
from ..ai.runtime import MODES, ai_env, get_ai_mode, set_ai_mode
from ..ai.steps import calls_left
from ..live.runner import get_live
from ..store import Store, to_iso
from .http import ApiError, Request, Response, ok
from .workspace import Workspace

LIMITS = {C.LINKEDIN_INVITE: INVITE_MAX, C.LINKEDIN_MESSAGE: DM_MAX, C.EMAIL: EMAIL_BODY_MAX}
ATTENTION = ("pending", "escalated")


def _draft(d) -> dict:
    return {
        "id": d.id,
        "kind": d.kind,
        "step": d.step,
        "channel": d.channel,
        "subject": d.subject,
        "body": d.body,
        "status": d.status,
        "reason": d.reason,
        "decided_by": d.decided_by,
        "created_at": to_iso(d.created_at),
    }


def get_ai(ws: Workspace, req: Request) -> Response:
    env = ai_env()
    with ws.store() as s:
        mode = get_ai_mode(s)
        rules = s.get_rules()
        waiting = s.drafts(status="pending") + s.drafts(status="escalated")
        left = calls_left(s, env.daily_call_cap, datetime.now(timezone.utc), rules.timezone if rules else "UTC")
        return ok(
            {
                "configured": env.configured,
                "model": env.model,
                "mode": mode.mode,
                "max_auto_replies": mode.max_auto_replies,
                "reply_delay_minutes": mode.reply_delay_minutes,
                "disclose": mode.disclose,
                "modes": list(MODES),
                "daily_call_cap": env.daily_call_cap,
                "calls_left": max(left, 0),
                "waiting": len(waiting),
                "live_running": bool(get_live(s).get("enabled")),
            }
        )


def save_settings(ws: Workspace, req: Request) -> Response:
    body = req.json()
    mode = body.get("mode")
    if mode not in MODES:
        raise ApiError(400, f"mode must be one of {', '.join(MODES)}")
    ints = {k: body.get(k) for k in ("max_auto_replies", "reply_delay_minutes")}
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in ints.values()) or not isinstance(
        body.get("disclose"), bool
    ):
        raise ApiError(400, "max_auto_replies and reply_delay_minutes must be whole numbers and disclose true or false")
    if mode != "off" and not ai_env().configured:
        raise ApiError(409, "The AI needs an API key. Add ANTHROPIC_API_KEY to the app's environment first.")
    if mode == "autonomous" and body.get("confirm") is not True:
        raise ApiError(400, "Confirm that the AI may send messages without your approval")
    with ws.store() as s:
        try:
            saved = set_ai_mode(
                s, mode, ints["max_auto_replies"], ints["reply_delay_minutes"], body["disclose"], datetime.now(timezone.utc)
            )
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        return ok({"mode": saved.mode})


def _last_text(s: Store, key: str) -> tuple[str, datetime | None]:
    items = [(m.at, m.text) for m in s.inbound(key)] + [(t.at, t.body) for t in s.touches(key) if t.status == C.SENT and t.body]
    if not items:
        return "", None
    at, text = max(items, key=lambda i: i[0])
    return text, at


def inbox(ws: Workspace, req: Request) -> Response:
    with ws.store() as s:
        waiting = {}
        for d in s.drafts(status="pending") + s.drafts(status="escalated"):
            waiting[d.contact_key] = (
                "needs_you" if d.status == "escalated" or waiting.get(d.contact_key) == "needs_you" else "draft"
            )
        rows = []
        for t in s.contacts():
            text, at = _last_text(s, t.contact.key)
            if at is None and t.contact.key not in waiting:
                continue
            rows.append(
                {
                    "key": t.contact.key,
                    "name": t.contact.name,
                    "company": t.contact.company,
                    "status": t.status,
                    "attention": waiting.get(t.contact.key, ""),
                    "last_text": text[:120],
                    "last_at": to_iso(at) if at else "",
                    "replied": bool(s.inbound(t.contact.key)),
                }
            )
        rows.sort(
            key=lambda r: (
                {"needs_you": 0, "draft": 1, "": 2}[r["attention"]],
                r["last_at"] and -datetime.fromisoformat(r["last_at"].replace("Z", "+00:00")).timestamp(),
            )
        )
        return ok({"conversations": rows})


def thread(ws: Workspace, req: Request, key: str) -> Response:
    with ws.store() as s:
        tracked = s.contact(key)
        if tracked is None:
            raise ApiError(404, f"No contact {key}")
        c = tracked.contact
        messages = [{"dir": "in", "text": m.text, "at": to_iso(m.at), "kind": "reply"} for m in s.inbound(key)]
        for t in s.touches(key):
            if t.status == C.SENT and t.body:
                messages.append(
                    {
                        "dir": "out",
                        "text": t.body,
                        "at": to_iso(t.at),
                        "kind": "ai_reply" if t.template_id == "ai_reply" else "step",
                        "channel": t.channel,
                        "subject": t.subject,
                    }
                )
            elif t.status == C.SKIPPED:
                messages.append(
                    {
                        "dir": "note",
                        "text": f"Step {t.step} skipped: {t.reason.replace('_', ' ')}",
                        "at": to_iso(t.at),
                        "kind": "note",
                    }
                )
        messages.sort(key=lambda m: m["at"])
        drafts = [_draft(d) for d in s.drafts(contact_key=key) if d.status in ATTENTION or d.status == "approved"]
        return ok(
            {
                "contact": {
                    "key": key,
                    "name": c.name,
                    "company": c.company,
                    "title": c.title,
                    "linkedin": c.linkedin_url,
                    "status": tracked.status,
                    "stop_reason": tracked.stop_reason,
                },
                "messages": messages,
                "drafts": drafts,
            }
        )


def decide(ws: Workspace, req: Request) -> Response:
    """A person approves (optionally after editing) or rejects a draft. Approving sends it on the next tick."""
    body = req.json()
    draft_id, action = body.get("id"), body.get("action")
    if not isinstance(draft_id, int) or isinstance(draft_id, bool) or action not in ("approve", "reject"):
        raise ApiError(400, "id must be a whole number and action 'approve' or 'reject'")
    now = datetime.now(timezone.utc)
    with ws.store() as s:
        d = s.draft(draft_id)
        if d is None:
            raise ApiError(404, "No such draft")
        if d.status not in ATTENTION:
            raise ApiError(409, f"This draft is already {d.status}")
        if action == "reject":
            s.update_draft(draft_id, status="rejected", decided_by="human", decided_at=now)
            return ok({"status": "rejected"})
        text = body.get("body", d.body)
        if not isinstance(text, str):
            raise ApiError(400, "body must be text")
        problems = check_output(
            d.channel,
            body.get("subject", d.subject) if isinstance(body.get("subject", d.subject), str) else "",
            text,
            LIMITS.get(d.channel),
        )
        if problems:
            raise ApiError(422, "This can't be sent: " + "; ".join(problems))
        subject = body.get("subject", d.subject)
        s.update_draft(
            draft_id,
            status="approved",
            body=text.strip(),
            subject=subject if isinstance(subject, str) else d.subject,
            decided_by="human",
            decided_at=now,
            send_after=now,
        )
        return ok({"status": "approved"})
