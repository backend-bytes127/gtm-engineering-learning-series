"""API handlers for configuration: templates, sequences, rules, sender, preview, launch gate, sample and reset."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .. import constants as C
from ..engine import DRAFT_CHECK, EngineError, draft_problems, get_sender, launch, launch_checklist
from ..models import Contact, Issue, Sender, Template
from ..rules import RulesError, parse_rules
from ..sequence import SequenceError, parse_sequence, sequence_errors
from ..store import Store, to_iso
from ..templates import CONTACT_VARS, KNOWN_VARS, SENDER_VARS, approval_hash, check_draft, lint_template, render, variables_in
from ..workflow import ApprovalError, approve_templates, import_and_validate, load_config
from .http import ApiError, Request, Response, ok
from .workspace import Workspace, first_window_start

ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_CONTACT = Contact(
    row=0, name="Alex Example", first_name="Alex", last_name="Example", company="Example Co", title="Head of Sales"
)
PLACEHOLDER_SENDER = Sender("Your Name", "Your Company", "Your postal address")


def _issues(items: list[Issue]) -> list[dict]:
    return [asdict(i) for i in items]


def _template_row(s: Store, t: Template) -> dict:
    return {
        "id": t.id,
        "channel": t.channel,
        "subject": t.subject,
        "body": t.body,
        "approved": s.approved_hash(t.id) == approval_hash(t),
        "issues": _issues(lint_template(t)),
    }


def _sequence_row(s: Store, name: str, templates: dict[str, Template]) -> dict:
    seq = s.sequence(name)
    return {
        "name": name,
        "live": s.is_live(name),
        "errors": sequence_errors(seq, templates),
        "contacts": sum(1 for c in s.contacts(sequence=name)),
        "steps": [{"channel": x.channel, "wait_days": x.wait_days, "template": x.template} for x in seq.steps],
    }


def get_config(ws: Workspace, req: Request) -> Response:
    with ws.store() as s:
        templates, rules, sender = s.templates(), s.get_rules(), get_sender(s)
        return ok(
            {
                "templates": [_template_row(s, t) for t in sorted(templates.values(), key=lambda t: t.id)],
                "sequences": [_sequence_row(s, n, templates) for n in s.sequence_names()],
                "rules": rules.to_dict() if rules else None,
                "sender": asdict(sender) if sender else None,
                "variables": {"contact": list(CONTACT_VARS), "sender": list(SENDER_VARS), "all": list(KNOWN_VARS)},
                "limits": {
                    "email": C.HARD_CAP_EMAIL_PER_DAY,
                    "invites": C.HARD_CAP_INVITES_PER_DAY,
                    "messages": C.HARD_CAP_MESSAGES_PER_DAY,
                    "invite_chars": C.LINKEDIN_INVITE_MAX_CHARS,
                    "max_steps": C.MAX_STEPS,
                    "max_wait": C.MAX_WAIT_DAYS,
                },
                "channels": list(C.CHANNELS),
                "stop_kinds": list(C.STOP_RULE_KINDS),
            }
        )


def _template_from(body: dict) -> Template:
    tid = str(body.get("id", "")).strip()
    if not tid or len(tid) > 60 or not all(ch.isalnum() or ch in "_-" for ch in tid):
        raise ApiError(422, "A template id uses letters, numbers, _ and - only (for example intro_email)")
    return Template(tid, str(body.get("channel", "")), str(body.get("body", "")), str(body.get("subject", "")))


def _in_live_sequence(s: Store, template_id: str) -> bool:
    return any(s.is_live(n) and any(x.template == template_id for x in s.sequence(n).steps) for n in s.sequence_names())


def lint(ws: Workspace, req: Request) -> Response:
    """Stateless check of a draft as it is being typed. Also reports the worst-case invite length."""
    t = _template_from({"id": "draft", **req.json()})
    return ok({"issues": _issues(lint_template(t)), "variables": variables_in(t.body) + variables_in(t.subject)})


def save_template(ws: Workspace, req: Request) -> Response:
    t = _template_from(req.json())
    with ws.store() as s:
        if _in_live_sequence(s, t.id):
            raise ApiError(409, "This template is used by a live sequence and cannot be edited now")
        s.save_templates({t.id: t})
        return ok(_template_row(s, t))


def delete_template(ws: Workspace, req: Request) -> Response:
    tid = str(req.json().get("id", ""))
    with ws.store() as s:
        users = [n for n in s.sequence_names() if any(x.template == tid for x in s.sequence(n).steps)]
        if users:
            raise ApiError(409, f"Used by: {', '.join(users)}. Remove it from the sequence first.")
        s.delete_template(tid)
    return ok({"deleted": tid})


def approve(ws: Workspace, req: Request) -> Response:
    ids = req.json().get("ids") or None
    with ws.store() as s:
        try:
            approved = approve_templates(s, ids, datetime.now(timezone.utc))
        except ApprovalError as exc:
            raise ApiError(422, str(exc)) from exc
    return ok({"approved": approved})


def preview(ws: Workspace, req: Request) -> Response:
    body = req.json()
    t = _template_from({"id": "draft", **body})
    with ws.store() as s:
        key = str(body.get("contact", ""))
        tracked = s.contact(key) if key else None
        contact = tracked.contact if tracked else (s.contacts()[0].contact if s.contacts() else PLACEHOLDER_CONTACT)
        sender = get_sender(s) or PLACEHOLDER_SENDER
    out, subject = render(t.body, contact, sender), render(t.subject, contact, sender)
    return ok(
        {
            "subject": subject.text,
            "body": out.text,
            "missing": list(dict.fromkeys(out.missing + subject.missing)),
            "fallbacks": list(dict.fromkeys(out.fallbacks + subject.fallbacks)),
            "chars": len(out.text),
            "contact": {"key": contact.key, "name": contact.name},
            "issues": _issues(check_draft(t, contact, sender)),
        }
    )


def _sequence_from(body: dict):
    try:
        return parse_sequence(body)
    except SequenceError as exc:
        raise ApiError(422, str(exc)) from exc


def check_sequence(ws: Workspace, req: Request) -> Response:
    seq = _sequence_from(req.json())
    with ws.store() as s:
        return ok({"errors": sequence_errors(seq, s.templates())})


def save_sequence(ws: Workspace, req: Request) -> Response:
    seq = _sequence_from(req.json())
    with ws.store() as s:
        if s.is_live(seq.name):
            raise ApiError(409, "This sequence is live and cannot be edited. Reset the results to change it.")
        errors = sequence_errors(seq, s.templates())
        if errors:
            raise ApiError(422, "The sequence has problems", errors=errors)
        s.save_sequence(seq)
        return ok(_sequence_row(s, seq.name, s.templates()))


def save_rules(ws: Workspace, req: Request) -> Response:
    try:
        rules = parse_rules(req.json())
    except RulesError as exc:
        raise ApiError(422, str(exc)) from exc
    with ws.store() as s:
        s.set_setting("rules", rules.to_dict())
    return ok(rules.to_dict())


def save_sender(ws: Workspace, req: Request) -> Response:
    body = req.json()
    name, address = str(body.get("name", "")).strip(), str(body.get("postal_address", "")).strip()
    if not name or not address:
        raise ApiError(422, "A sender name and a postal address are required (every email carries them)")
    sender = Sender(name[:120], str(body.get("company", "")).strip()[:120], address[:300])
    with ws.store() as s:
        s.set_setting("sender", asdict(sender))
    return ok(asdict(sender))


def check_launch(ws: Workspace, req: Request) -> Response:
    name = req.query.get("sequence", "")
    with ws.store() as s:
        checklist = launch_checklist(s, name)
        sender = get_sender(s)
        held = draft_problems(s, name, sender) if sender and s.sequence(name) else {}
        others_ok = all(ok_ for label, ok_, _ in checklist.items if label != DRAFT_CHECK)
        return ok(
            {
                "items": [{"label": a, "ok": b, "detail": c} for a, b, c in checklist.items],
                "ready": checklist.ready,
                "live": s.is_live(name),
                "incomplete": [{"key": k, "problems": v} for k, v in sorted(held.items())],
                "can_hold": others_ok and bool(held),
            }
        )


def do_launch(ws: Workspace, req: Request) -> Response:
    body = req.json()
    name = str(body.get("sequence", ""))
    with ws.store() as s:
        rules = s.get_rules()
        now = first_window_start(rules) if rules else datetime.now(timezone.utc)
        try:
            result = launch(s, name, now, hold_incomplete=bool(body.get("hold_incomplete")))
        except EngineError as exc:
            raise ApiError(409, str(exc)) from exc
        s.set_setting("clock_start", to_iso(now))
    return ok({"launched": result.launched, "held": list(result.held), "starts_at": to_iso(now)})


def load_sample(ws: Workspace, req: Request) -> Response:
    ws.wipe()
    supp = (ROOT / "config" / "suppression.csv").read_text(encoding="utf-8")
    with ws.store() as s:
        load_config(s, ROOT / "config")
        import_and_validate(
            s,
            ROOT / "sample-data" / "contacts.csv",
            default_sequence="Outbound Intro",
            suppression_path=ROOT / "config" / "suppression.csv",
            now=datetime.now(timezone.utc),
        )
        s.set_setting("suppression_text", "\n".join(ln for ln in supp.splitlines() if ln.strip().lower() != "value"))
        s.set_setting("import_source", "sample contacts.csv")
    return ok({"loaded": True})


def reset(ws: Workspace, req: Request) -> Response:
    scope = req.json().get("scope")
    if scope == "all":
        ws.wipe()
    elif scope == "run":
        with ws.store() as s:
            s.reset_run()
    else:
        raise ApiError(400, "scope must be 'run' or 'all'")
    return ok({"reset": scope})
