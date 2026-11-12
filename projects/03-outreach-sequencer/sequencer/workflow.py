"""Glue between the steps: import + validate into a store, load config, lint and approve templates."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .importer import import_contacts
from .models import Contact, Issue, Sender
from .rules import parse_rules
from .sequence import SequenceError, load_sequences, load_templates, sequence_errors
from .store import Store
from .templates import approval_hash, lint_template
from .validate import EmailVerifier, OfflineVerifier, ValidationReport, load_suppression, validate_contacts


class ApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class ImportSummary:
    read: int
    unmapped: tuple[str, ...]
    report: ValidationReport


def import_and_validate(
    store: Store,
    contacts_path: str | Path,
    *,
    mapping: dict[str, str] | None = None,
    default_sequence: str = "",
    suppression_path: str | Path | None = None,
    verifier: EmailVerifier | None = None,
    now: datetime,
) -> ImportSummary:
    """Steps 1 and 2. Only validated contacts reach the store; everything removed is kept with its reason."""
    if store.contacts():
        raise ValueError("this database already has contacts; use a new database for a new list")
    imported = import_contacts(contacts_path, mapping, default_sequence)
    if suppression_path:
        store.add_suppression(load_suppression(suppression_path), "suppression file")
    report = validate_contacts(imported.contacts, store.suppression(), verifier or OfflineVerifier())
    store.add_contacts(report.valid)
    store.add_removed(report.removed)
    store.set_setting(
        "validation_run",
        {
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "read": len(imported.contacts),
            "kept": len(report.valid),
            "removed": len(report.removed),
        },
    )
    return ImportSummary(len(imported.contacts), imported.unmapped, report)


def load_config(store: Store, config_dir: str | Path) -> list[str]:
    """Load templates, sequences, sending rules and the sender profile from a config folder. Returns notes for the user."""
    folder = Path(config_dir)
    store.save_templates(load_templates(folder / "templates.json"))
    notes = [f"{len(store.templates())} templates loaded"]
    templates = store.templates()
    for seq in load_sequences(folder / "sequences.json"):
        errs = sequence_errors(seq, templates)
        if errs:
            raise SequenceError(f"sequence '{seq.name}' is not valid: " + "; ".join(errs))
        store.save_sequence(seq)
        notes.append(f"sequence '{seq.name}' loaded ({len(seq.steps)} steps)")
    rules = parse_rules(json.loads((folder / "rules.json").read_text(encoding="utf-8")))
    store.set_setting("rules", rules.to_dict())
    sender = json.loads((folder / "sender.json").read_text(encoding="utf-8"))
    store.set_setting("sender", asdict(Sender(sender["name"], sender.get("company", ""), sender["postal_address"])))
    notes.append(f"sending rules set ({rules.timezone}, {rules.start_hour}:00-{rules.end_hour}:00)")
    return notes


def lint_all(store: Store) -> dict[str, list[Issue]]:
    return {tid: lint_template(t) for tid, t in sorted(store.templates().items())}


def approve_templates(store: Store, ids: list[str] | None, now: datetime) -> list[str]:
    """Approve templates that have no lint errors. All-or-nothing: one failing template approves none."""
    templates = store.templates()
    chosen = ids or sorted(templates)
    unknown = [i for i in chosen if i not in templates]
    if unknown:
        raise ApprovalError(f"unknown template(s): {', '.join(unknown)}")
    failing = {i: [x for x in lint_template(templates[i]) if x.severity == "error"] for i in chosen}
    failing = {i: errs for i, errs in failing.items() if errs}
    if failing:
        detail = "; ".join(f"{i}: " + ", ".join(e.message for e in errs) for i, errs in failing.items())
        raise ApprovalError(f"not approved, fix first: {detail}")
    for i in chosen:
        store.approve_template(i, approval_hash(templates[i]), now)
    return chosen


class AddContactError(ValueError):
    """A hand-entered contact cannot be added. `reason` is a stable code for the UI; the message is plain English."""

    def __init__(self, message: str, reason: str = "invalid"):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class AddResult:
    contact: Contact


FIELD_MAX = 200
_PLAIN_REASON = {
    "missing_name": "A name is needed so the message can be personalised.",
    "invalid_email": "That email address does not look valid ({detail}). Fix it, or add a LinkedIn URL instead.",
    "invalid_linkedin_url": "That LinkedIn URL will not work: {detail}.",
    "no_reachable_channel": "Add an email address or a LinkedIn URL, otherwise there is no way to reach this person.",
    "duplicate": "This person is already in the list ({detail}).",
    "opted_out": "This person is on your do-not-contact list ({detail}).",
}


def add_contact(store: Store, fields: dict[str, str], now: datetime, verifier: EmailVerifier | None = None) -> AddResult:
    """Add one hand-entered contact, with exactly the checks a file import applies. Nothing is stored unless it passes."""
    clean = {k: str(fields.get(k, "")).strip() for k in ("name", "company", "title", "email", "linkedin_url", "sequence")}
    if any(len(v) > FIELD_MAX for v in clean.values()):
        raise AddContactError(f"A field is too long (limit {FIELD_MAX} characters).", "too_long")
    if not clean["sequence"]:
        raise AddContactError("Choose the sequence this person belongs to.", "no_sequence")
    if store.is_live(clean["sequence"]):
        raise AddContactError("That sequence is live, so it cannot take new people. Reset the results first.", "sequence_live")

    existing = [t.contact for t in store.contacts()]
    row = max([c.row for c in existing] + [r.contact.row for r in store.removed()] + [0]) + 1
    parts = clean["name"].split()
    first, last = (parts[0], " ".join(parts[1:])) if parts else ("", "")
    new = Contact(
        row=row,
        name=clean["name"],
        first_name=first,
        last_name=last,
        company=clean["company"],
        title=clean["title"],
        email=clean["email"],
        linkedin_url=clean["linkedin_url"],
        sequence=clean["sequence"],
    )
    report = validate_contacts([*existing, new], store.suppression(), verifier or OfflineVerifier())
    refused = next((r for r in report.removed if r.contact.row == row), None)
    if refused is not None:
        raise AddContactError(
            _PLAIN_REASON.get(refused.reason, "This contact cannot be added.").format(detail=refused.detail), refused.reason
        )
    kept = next(c for c in report.valid if c.row == row)
    store.add_contacts([kept])
    if store.get_setting("validation_run") is None:
        store.set_setting(
            "validation_run", {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "read": 1, "kept": 1, "removed": 0, "manual": True}
        )
    return AddResult(kept)
