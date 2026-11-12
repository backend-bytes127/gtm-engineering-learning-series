import json
from pathlib import Path

import openpyxl
import pytest

from sequencer.cli import main, parse_time, run_demo

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = str(ROOT / "sample-data" / "contacts.csv")
CONFIG = str(ROOT / "config")
SUPPRESSION = str(ROOT / "config" / "suppression.csv")
GOLDEN = ROOT / "expected-output" / "metrics.json"


def cli(db, *args):
    return main(["--db", str(db), *args])


def test_parse_time_accepts_z_suffix_and_offsets():
    assert parse_time("2026-11-09T09:00:00Z").hour == 9
    assert parse_time("2026-11-09T13:00:00+04:00").hour == 9
    assert parse_time(None).tzinfo is not None


def test_step_by_step_through_the_cli(tmp_path, capsys):
    db = tmp_path / "s.sqlite"
    assert (
        cli(db, "import", SAMPLE, "--sequence", "Outbound Intro", "--suppression", SUPPRESSION, "--now", "2026-11-09T09:00:00Z")
        == 0
    )
    out = capsys.readouterr().out
    assert "Read 36 rows; kept 26, removed 10." in out and "removed row" in out and "Columns not used" not in out
    assert cli(db, "config", "--dir", CONFIG) == 0
    assert cli(db, "lint") == 0
    assert cli(db, "check", "Outbound Intro") == 1  # templates not approved yet, and one draft cannot be personalised
    out = capsys.readouterr().out
    assert "[ ] Every template approved" in out and "NOT ready" in out
    assert cli(db, "launch", "Outbound Intro", "--now", "2026-11-09T09:00:00Z") == 1  # refused
    assert "Not ready to launch" in capsys.readouterr().err
    assert cli(db, "approve", "--now", "2026-11-09T09:00:00Z") == 0
    assert cli(db, "launch", "Outbound Intro", "--hold-incomplete", "--now", "2026-11-09T09:00:00Z") == 0
    assert "25 contacts" in capsys.readouterr().out
    assert cli(db, "run", "--days", "60", "--now", "2026-11-09T09:00:00Z") == 0
    assert cli(db, "status") == 0
    status = capsys.readouterr().out
    assert "In Sequence     0" in status
    assert cli(db, "report", "--out", str(tmp_path / "out")) == 0
    assert (tmp_path / "out" / "Sequence_Report.xlsx").exists()


def test_manual_event_stops_a_contact(tmp_path, capsys):
    db = tmp_path / "s.sqlite"
    for args in (
        ["import", SAMPLE, "--sequence", "Outbound Intro", "--suppression", SUPPRESSION],
        ["config", "--dir", CONFIG],
        ["approve"],
    ):
        assert cli(db, *args) == 0
    assert cli(db, "launch", "Outbound Intro", "--hold-incomplete", "--now", "2026-11-09T09:00:00Z") == 0
    capsys.readouterr()
    assert cli(db, "event", "r0001", "replied", "--now", "2026-11-09T12:00:00Z") == 0
    assert "Status: Replied" in capsys.readouterr().out
    assert cli(db, "event", "r0001", "replied", "--now", "2026-11-09T12:00:00Z") == 0
    assert cli(db, "event", "r0002", "unsubscribed") == 0
    assert "Stopped (opted_out)" in capsys.readouterr().out


def test_lint_returns_nonzero_on_errors(tmp_path, capsys):
    db = tmp_path / "s.sqlite"
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    for name in ("sequences.json", "rules.json", "sender.json"):
        (cfg / name).write_text((ROOT / "config" / name).read_text())
    bad = json.loads((ROOT / "config" / "templates.json").read_text())
    bad["templates"][1]["body"] = "Hello there, we would like to connect."
    (cfg / "templates.json").write_text(json.dumps(bad))
    assert cli(db, "config", "--dir", str(cfg)) == 0
    assert cli(db, "lint") == 1
    assert "no_personalisation" in capsys.readouterr().out
    assert cli(db, "approve") == 1
    assert "not approved, fix first" in capsys.readouterr().err


def test_column_mapping_override_and_bad_map(tmp_path, capsys):
    f = tmp_path / "c.csv"
    f.write_text("who,mail\nAda Lovelace,ada@acme.example\n")
    assert cli(tmp_path / "a.sqlite", "import", str(f), "--map", "name=who", "--map", "email=mail") == 0
    assert "kept 1" in capsys.readouterr().out
    assert cli(tmp_path / "b.sqlite", "import", str(f), "--map", "oops") == 1
    assert "field=Header" in capsys.readouterr().err


def test_errors_are_one_line_not_tracebacks(tmp_path, capsys):
    assert cli(tmp_path / "s.sqlite", "import", str(tmp_path / "missing.csv")) == 1
    assert capsys.readouterr().err.startswith("error:")
    assert cli(tmp_path / "s.sqlite", "check", "Nope") == 1


def test_demo_is_reproducible_and_matches_the_golden_metrics(tmp_path):
    out = run_demo(tmp_path / "demo")
    got = json.loads((out / "metrics.json").read_text())
    assert got == json.loads(GOLDEN.read_text()), "demo output changed: review the diff, then regenerate expected-output/"
    again = json.loads((run_demo(tmp_path / "demo2") / "metrics.json").read_text())
    assert got == again
    assert (out / "Summary.md").read_text() == (tmp_path / "demo2" / "Summary.md").read_text()
    assert (out / "Summary.md").read_text() == (GOLDEN.parent / "Summary.md").read_text()


def test_demo_workbook_and_summary_content(tmp_path):
    out = run_demo(tmp_path / "demo")
    wb = openpyxl.load_workbook(out / "Sequence_Report.xlsx")
    assert wb.sheetnames == ["Summary", "By Step", "By Channel", "Contacts", "Touch Log", "Removed Records"]
    assert wb["Removed Records"].max_row == 11  # header + 10 removed
    text = (out / "Summary.md").read_text()
    assert "Simulated results" in text and "25 contacts entered the sequence" in text


def test_demo_command(tmp_path, capsys):
    assert main(["demo", "--out", str(tmp_path / "d")]) == 0
    assert "Sequence results" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["nonsense"]])
def test_bad_usage_exits_with_argparse_error(argv):
    with pytest.raises(SystemExit):
        main(argv)


def test_report_numbers_match_an_independent_recount_from_raw_sql(tmp_path):
    """The report builder and this query share no code, so agreement means the counts are right, not just stable."""
    import sqlite3

    out = run_demo(tmp_path / "demo")
    got = json.loads((out / "metrics.json").read_text())
    db = sqlite3.connect(out / "sequencer.sqlite")

    def one(sql):
        return db.execute(sql).fetchone()[0]

    for row in got["by_step"]:
        step = row["step"]
        assert row["sent"] == one(f"SELECT COUNT(*) FROM touches WHERE status='sent' AND step={step}")
        for kind, field in (
            ("opened", "opened"),
            ("accepted", "accepted"),
            ("replied", "replied"),
            ("meeting_booked", "meetings"),
        ):
            expect = one(
                f"SELECT COUNT(DISTINCT t.id) FROM touches t JOIN events e ON e.touch_id=t.id "
                f"WHERE t.status='sent' AND t.step={step} AND e.kind='{kind}'"
            )
            assert row[field] == expect, f"step {step} {field}"
    assert got["contacts"]["replied"] == one("SELECT COUNT(DISTINCT contact_key) FROM events WHERE kind='replied'")
    assert sum(got["statuses"].values()) == one("SELECT COUNT(*) FROM contacts") == got["contacts"]["total"]
    assert got["by_channel"]["email"]["sent"] + got["by_channel"]["linkedin"]["sent"] == one(
        "SELECT COUNT(*) FROM touches WHERE status='sent'"
    )
