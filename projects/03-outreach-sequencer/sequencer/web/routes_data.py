"""API handlers for the list: state, upload, import and validate, contacts, tracking, report."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from .. import constants as C
from ..engine import get_sender, record_event
from ..importer import FIELDS, read_preview, suggest_mapping
from ..live.runner import get_live
from ..provider import SimulatedProvider
from ..report import build_report, metrics_dict, summary_lines, write_xlsx
from ..simulate import run_simulation
from ..store import Store, from_iso, to_iso
from ..templates import approval_hash
from ..workflow import AddContactError, add_contact, import_and_validate
from .http import ApiError, Request, Response, ok
from .workspace import Workspace, first_window_start

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _is_simulated(store: Store) -> bool:
    mode = store.get_setting("mode")
    return isinstance(mode, dict) and mode.get("provider") == "simulated"


def get_state(ws: Workspace, req: Request) -> Response:
    with ws.store() as s:
        contacts, templates, names = s.contacts(), s.templates(), s.sequence_names()
        used = {t.template for n in names for t in s.sequence(n).steps}
        approved = bool(used) and all(t in templates and s.approved_hash(t) == approval_hash(templates[t]) for t in used)
        counts = {status: 0 for status in C.STATUSES}
        for c in contacts:
            counts[c.status] += 1
        validation = s.get_setting("validation_run")
        live = [n for n in names if s.is_live(n)]
        ran = s.get_setting("mode") is not None
        done = {
            "import": validation is not None,
            "validate": validation is not None,
            "sequence": bool(names),
            "messages": approved,
            "rules": s.get_rules() is not None and get_sender(s) is not None,
            "launch": bool(live),
            "report": ran,
        }
        return ok(
            {
                "validation": validation,
                "import_source": s.get_setting("import_source"),
                "counts": counts,
                "total": len(contacts),
                "sequences": names,
                "live": live,
                "ran": ran,
                "simulated": _is_simulated(s),
                "done": done,
                "removed": len(s.removed()),
                "live_sending": bool(get_live(s).get("enabled")),
                "pending_sequences": sorted({c.contact.sequence for c in contacts if c.contact.sequence} - set(names)),
            }
        )


def upload(ws: Workspace, req: Request) -> Response:
    name = req.headers.get("x-filename", "")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("csv", "xlsx"):
        raise ApiError(400, "Upload a CSV or XLSX file")
    if not req.body or len(req.body) > MAX_UPLOAD_BYTES:
        raise ApiError(400, "The file is empty or larger than 10 MB")
    ws.uploads.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    path = ws.uploads / f"{upload_id}.{ext}"
    path.write_bytes(req.body)
    try:
        headers, rows, total = read_preview(path)
    except Exception as exc:  # unreadable or corrupt file: report it, do not keep it
        path.unlink(missing_ok=True)
        raise ApiError(400, f"That file could not be read ({type(exc).__name__}). Is it a valid {ext.upper()}?") from exc
    return ok(
        {
            "upload_id": upload_id,
            "filename": name,
            "headers": headers,
            "rows": rows,
            "total": total,
            "suggested": suggest_mapping(headers),
            "fields": list(FIELDS),
        }
    )


def run_import(ws: Workspace, req: Request) -> Response:
    body = req.json()
    path = ws.upload_path(str(body.get("upload_id", "")))
    if path is None:
        raise ApiError(400, "Upload the file again; this upload was not found")
    mapping = body.get("mapping", {})
    if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
        raise ApiError(400, "mapping must be an object of field to column header")
    supp_text = str(body.get("suppression_text", ""))
    supp_path = ws.uploads / f"{uuid.uuid4().hex}.supp.csv"
    supp_path.write_text("value\n" + supp_text, encoding="utf-8")
    now = datetime.now().astimezone()
    with ws.store() as s:
        s.reset_list()
        summary = import_and_validate(
            s,
            path,
            mapping={k: v for k, v in mapping.items() if v},
            default_sequence=str(body.get("default_sequence", "")).strip(),
            suppression_path=supp_path,
            now=now,
        )
        s.set_setting("suppression_text", supp_text)
        s.set_setting("import_source", str(body.get("filename", path.name)))
    supp_path.unlink(missing_ok=True)
    return ok(
        {
            "read": summary.read,
            "kept": len(summary.report.valid),
            "removed": len(summary.report.removed),
            "unmapped": list(summary.unmapped),
        }
    )


def get_validation(ws: Workspace, req: Request) -> Response:
    with ws.store() as s:
        kept = [
            {
                "key": t.contact.key,
                "row": t.contact.row,
                "name": t.contact.name,
                "company": t.contact.company,
                "email": t.contact.email,
                "linkedin": t.contact.linkedin_url,
                "flags": list(t.contact.flags),
            }
            for t in s.contacts()
        ]
        removed = [
            {
                "row": r.contact.row,
                "name": r.contact.name,
                "email": r.contact.email,
                "linkedin": r.contact.linkedin_url,
                "reason": r.reason,
                "detail": r.detail,
            }
            for r in s.removed()
        ]
        return ok(
            {
                "kept": kept,
                "removed": removed,
                "suppression_text": s.get_setting("suppression_text") or "",
                "validation": s.get_setting("validation_run"),
            }
        )


def _row(t, sent: dict[str, int]) -> dict:
    c = t.contact
    return {
        "key": c.key,
        "name": c.name,
        "company": c.company,
        "title": c.title,
        "email": c.email,
        "linkedin": c.linkedin_url,
        "sequence": c.sequence,
        "status": t.status,
        "stop_reason": t.stop_reason,
        "next_step": t.next_step,
        "next_due": to_iso(t.next_due) if t.next_due else None,
        "flags": list(c.flags),
        "sent": sent.get(c.key, 0),
    }


def list_contacts(ws: Workspace, req: Request) -> Response:
    with ws.store() as s:
        sent: dict[str, int] = {}
        for t in s.touches():
            if t.status == C.SENT:
                sent[t.contact_key] = sent.get(t.contact_key, 0) + 1
        return ok({"contacts": [_row(t, sent) for t in s.contacts()]})


def get_contact(ws: Workspace, req: Request, key: str) -> Response:
    with ws.store() as s:
        tracked = s.contact(key)
        if tracked is None:
            raise ApiError(404, f"No contact {key}")
        events = s.events(key)
        touches = [
            {
                "id": t.id,
                "step": t.step,
                "channel": t.channel,
                "status": t.status,
                "reason": t.reason,
                "subject": t.subject,
                "body": t.body,
                "at": to_iso(t.at),
                "events": [e.kind for e in events if e.touch_id == t.id],
            }
            for t in s.touches(key)
        ]
        sent = sum(1 for t in touches if t["status"] == C.SENT)
        return ok(
            {
                "contact": _row(tracked, {key: sent}),
                "touches": touches,
                "events": [{"kind": e.kind, "at": to_iso(e.at), "detail": e.detail} for e in events],
            }
        )


def run_sim(ws: Workspace, req: Request) -> Response:
    body = req.json()
    days, seed = body.get("days", 60), body.get("seed", 7)
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (days, seed)) or not 1 <= days <= 120:
        raise ApiError(400, "days must be a whole number from 1 to 120, and seed a whole number")
    with ws.store() as s:
        if not any(s.is_live(n) for n in s.sequence_names()):
            raise ApiError(409, "Launch a sequence first")
        if s.get_setting("mode") is not None:
            raise ApiError(409, "The simulation has already run. Reset the results to run it again.")
        start = from_iso(s.get_setting("clock_start")) or first_window_start(s.get_rules())
        summary = run_simulation(s, SimulatedProvider(seed=seed), start, days)
        s.set_setting("clock_now", to_iso(start + timedelta(hours=summary.hours)))
    return ok(
        {
            "touches_sent": summary.touches_sent,
            "events": summary.events,
            "finished_early": summary.finished_early,
            "days": summary.hours // 24,
        }
    )


def post_event(ws: Workspace, req: Request) -> Response:
    body = req.json()
    key, kind = str(body.get("contact", "")), str(body.get("kind", ""))
    with ws.store() as s:
        now = from_iso(s.get_setting("clock_now"))
        if now is None:
            raise ApiError(409, "Run the sequence before recording events")
        if kind not in C.EVENT_KINDS:
            raise ApiError(400, f"Unknown event '{kind}'")
        fresh = record_event(s, key, kind, now, detail=str(body.get("detail", ""))[:200])
        t = s.contact(key)
        return ok({"recorded": fresh, "status": t.status, "stop_reason": t.stop_reason})


def get_report(ws: Workspace, req: Request) -> Response:
    with ws.store() as s:
        r, simulated = build_report(s), _is_simulated(s)
        return ok(
            {
                "simulated": simulated,
                "summary": summary_lines(r, simulated),
                "metrics": metrics_dict(r),
                "stats": {"held": r.contacts_held},
            }
        )


def download_report(ws: Workspace, req: Request) -> Response:
    import tempfile
    from pathlib import Path

    with ws.store() as s, tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Sequence_Report.xlsx"
        write_xlsx(s, build_report(s), path, _is_simulated(s))
        data = path.read_bytes()
    return Response(
        200,
        data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        (("Content-Disposition", 'attachment; filename="Sequence_Report.xlsx"'),),
    )


def add_one(ws: Workspace, req: Request) -> Response:
    body = req.json()
    fields = {k: body.get(k, "") for k in ("name", "company", "title", "email", "linkedin_url", "sequence")}
    if not all(isinstance(v, str) for v in fields.values()):
        raise ApiError(400, "Every field must be text")
    with ws.store() as s:
        try:
            result = add_contact(s, fields, datetime.now().astimezone())
        except AddContactError as exc:
            return ok({"error": str(exc), "reason": exc.reason}, 422)
        return ok({"key": result.contact.key, "name": result.contact.name, "flags": list(result.contact.flags)})
