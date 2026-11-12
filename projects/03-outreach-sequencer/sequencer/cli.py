"""Command line: `python -m sequencer <command>`. Each command is one step of the brief; `demo` runs them all."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import constants as C
from .engine import EngineError, launch, launch_checklist, record_event
from .importer import MappingError
from .provider import SimulatedProvider
from .report import build_report, metrics_dict, summary_lines, write_markdown, write_xlsx
from .rules import RulesError
from .sequence import SequenceError
from .simulate import run_simulation
from .store import Store
from .workflow import ApprovalError, approve_templates, import_and_validate, lint_all, load_config

ROOT = Path(__file__).resolve().parent.parent
DEMO_START = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)  # a Monday, so the demo is identical on every run
KNOWN_ERRORS = (MappingError, SequenceError, RulesError, EngineError, ApprovalError, ValueError, FileNotFoundError, KeyError)


def parse_time(text: str | None) -> datetime:
    if not text:
        return datetime.now(timezone.utc).replace(microsecond=0)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _parse_map(pairs: list[str]) -> dict[str, str]:
    out = {}
    for pair in pairs:
        field_name, sep, header = pair.partition("=")
        if not sep or not header:
            raise MappingError(f"--map expects field=Header, got '{pair}'")
        out[field_name.strip()] = header.strip()
    return out


def cmd_import(a, store: Store) -> int:
    s = import_and_validate(
        store,
        a.file,
        mapping=_parse_map(a.map),
        default_sequence=a.sequence,
        suppression_path=a.suppression,
        now=parse_time(a.now),
    )
    print(f"Read {s.read} rows; kept {len(s.report.valid)}, removed {len(s.report.removed)}.")
    if s.unmapped:
        print(f"Columns not used: {', '.join(s.unmapped)}")
    reasons: dict[str, int] = {}
    for r in s.report.removed:
        reasons[r.reason] = reasons.get(r.reason, 0) + 1
        print(f"  removed row {r.contact.row:>3} {r.contact.name or '(no name)':<22} {r.reason}: {r.detail}")
    for t in store.contacts():
        for flag in t.contact.flags:
            print(f"  kept    row {t.contact.row:>3} {t.contact.name:<22} {flag}")
    return 0


def cmd_config(a, store: Store) -> int:
    for note in load_config(store, a.dir):
        print(note)
    return 0


def cmd_lint(a, store: Store) -> int:
    worst = 0
    for tid, issues in lint_all(store).items():
        print(f"{tid}: {'ok' if not issues else ''}")
        for i in issues:
            print(f"  {i.severity.upper():<7} {i.code}: {i.message}")
            worst = max(worst, i.severity == "error")
    return worst


def cmd_approve(a, store: Store) -> int:
    print("Approved: " + ", ".join(approve_templates(store, a.ids or None, parse_time(a.now))))
    return 0


def cmd_check(a, store: Store) -> int:
    checklist = launch_checklist(store, a.sequence)
    for label, ok, detail in checklist.items:
        print(f"[{'x' if ok else ' '}] {label}: {detail}")
    print("Ready to launch." if checklist.ready else "NOT ready to launch.")
    return 0 if checklist.ready else 1


def cmd_launch(a, store: Store) -> int:
    result = launch(store, a.sequence, parse_time(a.now), hold_incomplete=a.hold_incomplete)
    print(f"Launched '{a.sequence}': {result.launched} contacts in sequence.")
    if result.held:
        print(f"Held back (draft would not personalise): {', '.join(result.held)}")
    return 0


def cmd_run(a, store: Store) -> int:
    summary = run_simulation(store, SimulatedProvider(seed=a.seed), parse_time(a.now), a.days)
    print(
        f"Simulated {summary.hours // 24}d {summary.hours % 24}h: {summary.touches_sent} messages sent, {summary.events} events."
    )
    print(
        "Everyone reached an end state."
        if summary.finished_early
        else "Stopped at the day limit; some contacts are still in sequence."
    )
    return 0


def cmd_event(a, store: Store) -> int:
    fresh = record_event(store, a.contact, a.kind, parse_time(a.now), detail=a.detail)
    t = store.contact(a.contact)
    print(
        f"{'Recorded' if fresh else 'Already recorded'}: {a.kind} for {a.contact}. Status: {t.status}"
        + (f" ({t.stop_reason})" if t.stop_reason else "")
    )
    return 0


def cmd_status(a, store: Store) -> int:
    counts: dict[str, int] = {}
    for t in store.contacts():
        counts[t.status] = counts.get(t.status, 0) + 1
    for status in C.STATUSES:
        print(f"{status:<15} {counts.get(status, 0)}")
    return 0


def _simulated(store: Store) -> bool:
    mode = store.get_setting("mode")
    return isinstance(mode, dict) and mode.get("provider") == "simulated"


def write_reports(store: Store, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    report, simulated = build_report(store), _simulated(store)
    write_xlsx(store, report, out / "Sequence_Report.xlsx", simulated)
    write_markdown(report, out / "Summary.md", simulated)
    (out / "metrics.json").write_text(json.dumps(metrics_dict(report), indent=2) + "\n", encoding="utf-8")
    return out


def cmd_report(a, store: Store) -> int:
    out = write_reports(store, Path(a.out))
    print("\n".join(f"- {line}" for line in summary_lines(build_report(store), _simulated(store))))
    print(f"\nWrote {out}/Sequence_Report.xlsx, Summary.md and metrics.json")
    return 0


def run_demo(out: Path, days: int = 60, seed: int = 7) -> Path:
    """Fresh database, the bundled sample list and config, simulated sending, reports. Same result every run."""
    out.mkdir(parents=True, exist_ok=True)
    db = out / "sequencer.sqlite"
    db.unlink(missing_ok=True)
    with Store(db) as store:
        import_and_validate(
            store,
            ROOT / "sample-data" / "contacts.csv",
            default_sequence="Outbound Intro",
            suppression_path=ROOT / "config" / "suppression.csv",
            now=DEMO_START,
        )
        load_config(store, ROOT / "config")
        approve_templates(store, None, DEMO_START)
        launch(store, "Outbound Intro", DEMO_START, hold_incomplete=True)
        run_simulation(store, SimulatedProvider(seed=seed), DEMO_START, days)
        return write_reports(store, out)


def cmd_demo(a, store: Store | None) -> int:
    out = run_demo(Path(a.out), a.days, a.seed)
    print((out / "Summary.md").read_text(encoding="utf-8"))
    print(f"Wrote {out}/Sequence_Report.xlsx, Summary.md, metrics.json and sequencer.sqlite")
    return 0


def cmd_serve(a, store: Store | None) -> int:
    from .web.server import serve

    serve(Path(a.out), a.port, not a.no_open, a.host)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sequencer", description="Email and LinkedIn sequencing tool (sending is simulated).")
    p.add_argument(
        "--db", default=str(ROOT / "output" / "sequencer.sqlite"), help="SQLite file (default: output/sequencer.sqlite)"
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, fn, help_: str):
        s = sub.add_parser(name, help=help_)
        s.set_defaults(fn=fn)
        return s

    s = add("import", cmd_import, "1-2. import a CSV/XLSX, map columns, validate, remove invalid/duplicate/opted-out")
    s.add_argument("file")
    s.add_argument("--sequence", default="", help="sequence for rows that have none")
    s.add_argument("--map", action="append", default=[], metavar="FIELD=HEADER", help="override a guessed column")
    s.add_argument("--suppression", help="CSV of e-mails, @domains and LinkedIn URLs never to contact")
    s.add_argument("--now")
    s = add("config", cmd_config, "3-5. load templates, sequences, sending rules and sender from a folder")
    s.add_argument("--dir", default=str(ROOT / "config"))
    add("lint", cmd_lint, "4. check every template").set_defaults(fn=cmd_lint)
    s = add("approve", cmd_approve, "4. approve templates that pass the checks (all, or the ids given)")
    s.add_argument("ids", nargs="*")
    s.add_argument("--now")
    s = add("check", cmd_check, "show the launch checklist for a sequence")
    s.add_argument("sequence")
    s = add("launch", cmd_launch, "put a sequence live (refused unless the checklist is green)")
    s.add_argument("sequence")
    s.add_argument(
        "--hold-incomplete", action="store_true", help="park contacts whose drafts cannot be personalised and launch the rest"
    )
    s.add_argument("--now")
    s = add("run", cmd_run, "6. run the sequence with the simulated provider")
    s.add_argument("--days", type=int, default=60)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--now", help="start time, ISO format")
    s = add("event", cmd_event, "6. record a reply, bounce, accepted invite, booked meeting... for one contact")
    s.add_argument("contact", help="contact key, e.g. r0004")
    s.add_argument("kind", choices=C.EVENT_KINDS)
    s.add_argument("--detail", default="")
    s.add_argument("--now")
    add("status", cmd_status, "6. contacts per status")
    s = add("report", cmd_report, "7. results by step and channel, plus what worked")
    s.add_argument("--out", default=str(ROOT / "output"))
    s = add("demo", cmd_demo, "run everything on the bundled sample data")
    s.add_argument("--out", default=str(ROOT / "output"))
    s.add_argument("--days", type=int, default=60)
    s.add_argument("--seed", type=int, default=7)
    s = add("serve", cmd_serve, "open the web app (a local interface for every step)")
    s.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="use 0.0.0.0 on a server (requires APP_PASSWORD)")
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    s.add_argument("--out", default=os.environ.get("DATA_DIR", str(ROOT / "output" / "web")), help="folder for the app's data")
    s.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in ("demo", "serve"):
            return args.fn(args, None)
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        with Store(args.db) as store:
            return args.fn(args, store)
    except KNOWN_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
