"""SQLite store: contacts and their status, templates and approvals, sequences, the touch log and events.

Every touch and every event is its own row and is never updated or deleted, so the log is the single place
to see what happened to a contact. All SQL is parameterised.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import constants as C
from .models import Contact, Removed, Sequence, Step, Template
from .rules import SendingRules, parse_rules
from .validate import Suppression, linkedin_slug

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
  key TEXT PRIMARY KEY, row INTEGER NOT NULL, name TEXT NOT NULL,
  first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '',
  company TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '', linkedin_url TEXT NOT NULL DEFAULT '',
  sequence TEXT NOT NULL, flags TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'Not Started', stop_reason TEXT NOT NULL DEFAULT '',
  next_step INTEGER NOT NULL DEFAULT 1, next_due TEXT
);
CREATE TABLE IF NOT EXISTS removed (
  id INTEGER PRIMARY KEY, row INTEGER NOT NULL, name TEXT, email TEXT, linkedin_url TEXT,
  source_status TEXT, reason TEXT NOT NULL, detail TEXT
);
CREATE TABLE IF NOT EXISTS templates (
  id TEXT PRIMARY KEY, channel TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
  approved_hash TEXT, approved_at TEXT
);
CREATE TABLE IF NOT EXISTS sequences (name TEXT PRIMARY KEY, definition TEXT NOT NULL, launched_at TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppression (kind TEXT NOT NULL, value TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY (kind, value));
CREATE TABLE IF NOT EXISTS touches (
  id INTEGER PRIMARY KEY, contact_key TEXT NOT NULL REFERENCES contacts(key), sequence TEXT NOT NULL,
  step INTEGER NOT NULL, channel TEXT NOT NULL, template_id TEXT NOT NULL, status TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '', subject TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL, provider_id TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS one_outcome_per_step ON touches(contact_key, step) WHERE status IN ('sent', 'skipped');
CREATE INDEX IF NOT EXISTS touches_day ON touches(channel, at);
CREATE TABLE IF NOT EXISTS provider_ids (contact_key TEXT PRIMARY KEY REFERENCES contacts(key), provider_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_drafts (
  id INTEGER PRIMARY KEY, contact_key TEXT NOT NULL REFERENCES contacts(key), kind TEXT NOT NULL, step INTEGER,
  channel TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, send_after TEXT,
  decided_at TEXT, decided_by TEXT NOT NULL DEFAULT '', in_reply_to INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS one_step_draft ON ai_drafts(contact_key, step) WHERE kind = 'step';
CREATE TABLE IF NOT EXISTS inbound (
  id INTEGER PRIMARY KEY, contact_key TEXT NOT NULL REFERENCES contacts(key), text TEXT NOT NULL, at TEXT NOT NULL,
  provider_msg_id TEXT NOT NULL UNIQUE, chat_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, contact_key TEXT NOT NULL REFERENCES contacts(key), touch_id INTEGER REFERENCES touches(id),
  kind TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', UNIQUE (contact_key, touch_id, kind)
);
"""


def to_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_iso(text: str | None) -> datetime | None:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if text else None


@dataclass(frozen=True)
class Tracked:
    contact: Contact
    status: str
    stop_reason: str
    next_step: int
    next_due: datetime | None


@dataclass(frozen=True)
class TouchRow:
    id: int
    contact_key: str
    sequence: str
    step: int
    channel: str
    template_id: str
    status: str
    reason: str
    subject: str
    body: str
    at: datetime
    provider_id: str


@dataclass(frozen=True)
class EventRow:
    id: int
    contact_key: str
    touch_id: int | None
    kind: str
    at: datetime
    detail: str


@dataclass(frozen=True)
class DraftRow:
    id: int
    contact_key: str
    kind: str
    step: int | None
    channel: str
    subject: str
    body: str
    status: str
    reason: str
    model: str
    created_at: datetime
    send_after: datetime | None
    decided_at: datetime | None
    decided_by: str
    in_reply_to: int | None


@dataclass(frozen=True)
class InboundRow:
    id: int
    contact_key: str
    text: str
    at: datetime
    provider_msg_id: str
    chat_id: str


def _draft(r: sqlite3.Row) -> DraftRow:
    return DraftRow(
        r["id"],
        r["contact_key"],
        r["kind"],
        r["step"],
        r["channel"],
        r["subject"],
        r["body"],
        r["status"],
        r["reason"],
        r["model"],
        from_iso(r["created_at"]),
        from_iso(r["send_after"]),
        from_iso(r["decided_at"]),
        r["decided_by"],
        r["in_reply_to"],
    )


def _tracked(r: sqlite3.Row) -> Tracked:
    contact = Contact(
        r["row"],
        r["name"],
        r["first_name"],
        r["last_name"],
        r["company"],
        r["title"],
        r["email"],
        r["linkedin_url"],
        r["sequence"],
        "",
        tuple(json.loads(r["flags"])),
    )
    return Tracked(contact, r["status"], r["stop_reason"], r["next_step"], from_iso(r["next_due"]))


def _touch(r: sqlite3.Row) -> TouchRow:
    return TouchRow(
        r["id"],
        r["contact_key"],
        r["sequence"],
        r["step"],
        r["channel"],
        r["template_id"],
        r["status"],
        r["reason"],
        r["subject"],
        r["body"],
        from_iso(r["at"]),
        r["provider_id"],
    )


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        self._backfill_inbound()

    def _backfill_inbound(self) -> None:
        """Replies recorded before conversations were stored exist only as event text. Copy them in once, never twice."""
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO inbound(contact_key, text, at, provider_msg_id, chat_id) "
                "SELECT e.contact_key, e.detail, e.at, 'event:' || e.id, '' FROM events e "
                "WHERE e.kind = 'replied' AND e.detail != '' AND NOT EXISTS "
                "(SELECT 1 FROM inbound i WHERE i.contact_key = e.contact_key AND substr(i.text, 1, 200) = e.detail)"
            )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- settings (rules, sender, validation marker) ---
    def set_setting(self, key: str, value: object) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def get_setting(self, key: str) -> object | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None

    def get_rules(self) -> SendingRules | None:
        raw = self.get_setting("rules")
        return parse_rules(raw) if isinstance(raw, dict) else None

    # --- contacts ---
    def add_contacts(self, contacts: list[Contact] | tuple[Contact, ...]) -> None:
        with self._db:
            for c in contacts:
                self._db.execute(
                    "INSERT INTO contacts(key, row, name, first_name, last_name, company, title, "
                    "email, linkedin_url, sequence, flags) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        c.key,
                        c.row,
                        c.name,
                        c.first_name,
                        c.last_name,
                        c.company,
                        c.title,
                        c.email,
                        c.linkedin_url,
                        c.sequence,
                        json.dumps(list(c.flags)),
                    ),
                )

    def add_removed(self, removed: list[Removed] | tuple[Removed, ...]) -> None:
        with self._db:
            for r in removed:
                c = r.contact
                self._db.execute(
                    "INSERT INTO removed(row, name, email, linkedin_url, source_status, reason, detail) VALUES (?,?,?,?,?,?,?)",
                    (c.row, c.name, c.email, c.linkedin_url, c.source_status, r.reason, r.detail),
                )

    def removed(self) -> list[Removed]:
        rows = self._db.execute("SELECT * FROM removed ORDER BY row").fetchall()
        return [
            Removed(
                Contact(
                    r["row"],
                    r["name"] or "",
                    email=r["email"] or "",
                    linkedin_url=r["linkedin_url"] or "",
                    source_status=r["source_status"] or "",
                ),
                r["reason"],
                r["detail"] or "",
            )
            for r in rows
        ]

    def contacts(self, sequence: str | None = None, status: str | None = None) -> list[Tracked]:
        sql, args = "SELECT * FROM contacts WHERE 1=1", []
        if sequence is not None:
            sql, args = sql + " AND sequence = ?", [*args, sequence]
        if status is not None:
            sql, args = sql + " AND status = ?", [*args, status]
        return [_tracked(r) for r in self._db.execute(sql + " ORDER BY row", args)]

    def contact(self, key: str) -> Tracked | None:
        r = self._db.execute("SELECT * FROM contacts WHERE key = ?", (key,)).fetchone()
        return _tracked(r) if r else None

    def due(self, now: datetime) -> list[Tracked]:
        rows = self._db.execute(
            "SELECT * FROM contacts WHERE status = ? AND next_due IS NOT NULL AND next_due <= ? ORDER BY next_due, row",
            (C.IN_SEQUENCE, to_iso(now)),
        )
        return [_tracked(r) for r in rows]

    def set_state(
        self, key: str, status: str, stop_reason: str = "", next_step: int | None = None, next_due: datetime | None = None
    ) -> None:
        with self._db:
            step = (
                next_step
                if next_step is not None
                else self._db.execute("SELECT next_step FROM contacts WHERE key = ?", (key,)).fetchone()[0]
            )
            self._db.execute(
                "UPDATE contacts SET status = ?, stop_reason = ?, next_step = ?, next_due = ? WHERE key = ?",
                (status, stop_reason, step, to_iso(next_due) if next_due else None, key),
            )

    # --- templates and approvals ---
    def save_templates(self, templates: dict[str, Template]) -> None:
        with self._db:
            for t in templates.values():
                self._db.execute(
                    "INSERT INTO templates(id, channel, subject, body) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "channel = excluded.channel, subject = excluded.subject, body = excluded.body",
                    (t.id, t.channel, t.subject, t.body),
                )

    def templates(self) -> dict[str, Template]:
        return {
            r["id"]: Template(r["id"], r["channel"], r["body"], r["subject"]) for r in self._db.execute("SELECT * FROM templates")
        }

    def approve_template(self, template_id: str, digest: str, at: datetime) -> None:
        with self._db:
            self._db.execute(
                "UPDATE templates SET approved_hash = ?, approved_at = ? WHERE id = ?", (digest, to_iso(at), template_id)
            )

    def delete_template(self, template_id: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM templates WHERE id = ?", (template_id,))

    def approved_hash(self, template_id: str) -> str | None:
        r = self._db.execute("SELECT approved_hash FROM templates WHERE id = ?", (template_id,)).fetchone()
        return r["approved_hash"] if r else None

    # --- sequences ---
    def save_sequence(self, seq: Sequence) -> None:
        definition = json.dumps([{"channel": s.channel, "wait_days": s.wait_days, "template": s.template} for s in seq.steps])
        with self._db:
            self._db.execute(
                "INSERT INTO sequences(name, definition) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET definition = excluded.definition",
                (seq.name, definition),
            )

    def sequence(self, name: str) -> Sequence | None:
        r = self._db.execute("SELECT definition FROM sequences WHERE name = ?", (name,)).fetchone()
        if not r:
            return None
        return Sequence(
            name,
            tuple(Step(i, s["channel"], s["wait_days"], s["template"]) for i, s in enumerate(json.loads(r["definition"]), 1)),
        )

    def sequence_names(self) -> list[str]:
        return [r["name"] for r in self._db.execute("SELECT name FROM sequences ORDER BY name")]

    def mark_live(self, name: str, at: datetime) -> None:
        with self._db:
            self._db.execute("UPDATE sequences SET launched_at = ? WHERE name = ?", (to_iso(at), name))

    def is_live(self, name: str) -> bool:
        r = self._db.execute("SELECT launched_at FROM sequences WHERE name = ?", (name,)).fetchone()
        return bool(r and r["launched_at"])

    # --- provider ids (who a contact is on the sending service, to match replies) ---
    def set_provider_id(self, contact_key: str, provider_id: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO provider_ids(contact_key, provider_id) VALUES (?, ?) "
                "ON CONFLICT(contact_key) DO UPDATE SET provider_id = excluded.provider_id",
                (contact_key, provider_id),
            )

    def contact_key_for_provider_id(self, provider_id: str) -> str | None:
        r = self._db.execute("SELECT contact_key FROM provider_ids WHERE provider_id = ?", (provider_id,)).fetchone()
        return r["contact_key"] if r else None

    def provider_id_for(self, contact_key: str) -> str | None:
        r = self._db.execute("SELECT provider_id FROM provider_ids WHERE contact_key = ?", (contact_key,)).fetchone()
        return r["provider_id"] if r else None

    # --- AI drafts and inbound messages ---
    DRAFT_FIELDS = ("subject", "body", "status", "reason", "send_after", "decided_at", "decided_by")

    def add_draft(
        self,
        contact_key: str,
        kind: str,
        step: int | None,
        channel: str,
        subject: str,
        body: str,
        status: str,
        reason: str,
        model: str,
        now: datetime,
        send_after: datetime | None = None,
        decided_by: str = "",
        in_reply_to: int | None = None,
    ) -> int:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO ai_drafts(contact_key, kind, step, channel, subject, body, status, reason, model, "
                "created_at, send_after, decided_at, decided_by, in_reply_to) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    contact_key,
                    kind,
                    step,
                    channel,
                    subject,
                    body,
                    status,
                    reason,
                    model,
                    to_iso(now),
                    to_iso(send_after) if send_after else None,
                    to_iso(now) if decided_by else None,
                    decided_by,
                    in_reply_to,
                ),
            )
        return int(cur.lastrowid)

    def draft(self, draft_id: int) -> DraftRow | None:
        r = self._db.execute("SELECT * FROM ai_drafts WHERE id = ?", (draft_id,)).fetchone()
        return _draft(r) if r else None

    def step_draft(self, contact_key: str, step: int) -> DraftRow | None:
        r = self._db.execute(
            "SELECT * FROM ai_drafts WHERE contact_key = ? AND step = ? AND kind = 'step'", (contact_key, step)
        ).fetchone()
        return _draft(r) if r else None

    def drafts(self, status: str | None = None, kind: str | None = None, contact_key: str | None = None) -> list[DraftRow]:
        sql, args = "SELECT * FROM ai_drafts WHERE 1=1", []
        for col, val in (("status", status), ("kind", kind), ("contact_key", contact_key)):
            if val is not None:
                sql, args = sql + f" AND {col} = ?", [*args, val]
        return [_draft(r) for r in self._db.execute(sql + " ORDER BY id", args)]

    def update_draft(self, draft_id: int, **fields: object) -> None:
        unknown = set(fields) - set(self.DRAFT_FIELDS)
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}")
        values = [to_iso(v) if isinstance(v, datetime) else v for v in fields.values()]
        with self._db:
            self._db.execute(f"UPDATE ai_drafts SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", (*values, draft_id))

    def count_ai_calls(self, start: datetime, end: datetime) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM ai_drafts WHERE model != '' AND created_at >= ? AND created_at < ?",
            (to_iso(start), to_iso(end)),
        ).fetchone()[0]

    def add_inbound(self, contact_key: str, text: str, at: datetime, provider_msg_id: str, chat_id: str = "") -> bool:
        with self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO inbound(contact_key, text, at, provider_msg_id, chat_id) VALUES (?,?,?,?,?)",
                (contact_key, text, to_iso(at), provider_msg_id, chat_id),
            )
        return cur.rowcount == 1

    def inbound(self, contact_key: str | None = None) -> list[InboundRow]:
        sql, args = "SELECT * FROM inbound", []
        if contact_key:
            sql, args = sql + " WHERE contact_key = ?", [contact_key]
        return [
            InboundRow(r["id"], r["contact_key"], r["text"], from_iso(r["at"]), r["provider_msg_id"], r["chat_id"])
            for r in self._db.execute(sql + " ORDER BY at, id", args)
        ]

    # --- resets ---
    def reset_run(self) -> None:
        """Forget everything that happened after launch: touches, events, statuses. The list and the config stay."""
        with self._db:
            self._db.execute("DELETE FROM events")
            self._db.execute("DELETE FROM ai_drafts")
            self._db.execute("DELETE FROM inbound")
            self._db.execute("DELETE FROM touches")
            self._db.execute("UPDATE contacts SET status = ?, stop_reason = '', next_step = 1, next_due = NULL", (C.NOT_STARTED,))
            self._db.execute("UPDATE sequences SET launched_at = NULL")
            self._db.execute("DELETE FROM settings WHERE key IN ('mode', 'clock_start', 'clock_now', 'live', 'live_status')")
            self._db.execute("DELETE FROM suppression WHERE reason IN ('bounced', 'unsubscribed')")

    def reset_list(self) -> None:
        """Forget the imported list and everything after it. Templates, sequences, rules and sender stay."""
        self.reset_run()
        with self._db:
            self._db.execute("DELETE FROM provider_ids")
            self._db.execute("DELETE FROM contacts")
            self._db.execute("DELETE FROM removed")
            self._db.execute("DELETE FROM suppression")
            self._db.execute("DELETE FROM settings WHERE key IN ('validation_run', 'suppression_text', 'import_source')")

    # --- suppression ---
    def add_suppression(self, entries: Suppression, reason: str) -> None:
        rows = (
            [("email", e) for e in entries.emails]
            + [("domain", d) for d in entries.domains]
            + [("linkedin", s) for s in entries.linkedin]
        )
        with self._db:
            self._db.executemany(
                "INSERT OR IGNORE INTO suppression(kind, value, reason) VALUES (?,?,?)", [(k, v, reason) for k, v in rows]
            )

    def suppression(self) -> Suppression:
        by_kind: dict[str, set[str]] = {"email": set(), "domain": set(), "linkedin": set()}
        for r in self._db.execute("SELECT kind, value FROM suppression"):
            by_kind[r["kind"]].add(r["value"])
        return Suppression(frozenset(by_kind["email"]), frozenset(by_kind["domain"]), frozenset(by_kind["linkedin"]))

    def suppress_contact(self, c: Contact, reason: str) -> None:
        self.add_suppression(
            Suppression(
                frozenset({c.email} if c.email else ()),
                frozenset(),
                frozenset({linkedin_slug(c.linkedin_url)} if c.linkedin_url else ()),
            ),
            reason,
        )

    # --- touches and events ---
    def add_touch(
        self,
        contact_key: str,
        sequence: str,
        step: int,
        channel: str,
        template_id: str,
        status: str,
        at: datetime,
        reason: str = "",
        subject: str = "",
        body: str = "",
        provider_id: str = "",
    ) -> int:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO touches(contact_key, sequence, step, channel, template_id, status, reason, "
                "subject, body, at, provider_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (contact_key, sequence, step, channel, template_id, status, reason, subject, body, to_iso(at), provider_id),
            )
        return int(cur.lastrowid)

    def touches(self, contact_key: str | None = None) -> list[TouchRow]:
        sql, args = "SELECT * FROM touches", []
        if contact_key:
            sql, args = sql + " WHERE contact_key = ?", [contact_key]
        return [_touch(r) for r in self._db.execute(sql + " ORDER BY at, id", args)]

    def failed_attempts(self, contact_key: str, step: int) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM touches WHERE contact_key = ? AND step = ? AND status = ?", (contact_key, step, C.FAILED)
        ).fetchone()[0]

    def count_sent(self, channel: str, start: datetime, end: datetime) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM touches WHERE channel = ? AND status = ? AND at >= ? AND at < ?",
            (channel, C.SENT, to_iso(start), to_iso(end)),
        ).fetchone()[0]

    def latest_sent_touch(self, contact_key: str, channel: str | None = None) -> TouchRow | None:
        sql, args = "SELECT * FROM touches WHERE contact_key = ? AND status = ?", [contact_key, C.SENT]
        if channel:
            sql, args = sql + " AND channel = ?", [*args, channel]
        r = self._db.execute(sql + " ORDER BY at DESC, id DESC LIMIT 1", args).fetchone()
        return _touch(r) if r else None

    def add_event(self, contact_key: str, kind: str, at: datetime, touch_id: int | None, detail: str = "") -> bool:
        """Record an event. Returns False when the same event was already recorded for that touch (idempotent)."""
        with self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO events(contact_key, touch_id, kind, at, detail) VALUES (?,?,?,?,?)",
                (contact_key, touch_id, kind, to_iso(at), detail),
            )
        return cur.rowcount == 1

    def events(self, contact_key: str | None = None) -> list[EventRow]:
        sql, args = "SELECT * FROM events", []
        if contact_key:
            sql, args = sql + " WHERE contact_key = ?", [contact_key]
        return [
            EventRow(r["id"], r["contact_key"], r["touch_id"], r["kind"], from_iso(r["at"]), r["detail"])
            for r in self._db.execute(sql + " ORDER BY at, id", args)
        ]

    def has_event(self, contact_key: str, kind: str) -> bool:
        return (
            self._db.execute("SELECT 1 FROM events WHERE contact_key = ? AND kind = ? LIMIT 1", (contact_key, kind)).fetchone()
            is not None
        )
