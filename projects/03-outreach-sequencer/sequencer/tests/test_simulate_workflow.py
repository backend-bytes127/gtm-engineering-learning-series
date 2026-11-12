import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sequencer import constants as C
from sequencer.engine import EngineError, launch, launch_checklist
from sequencer.provider import SimProfile, SimulatedProvider
from sequencer.sequence import SequenceError
from sequencer.simulate import run_simulation
from sequencer.store import Store
from sequencer.tests.conftest import TUESDAY_10, build_store, person
from sequencer.workflow import ApprovalError, approve_templates, import_and_validate, lint_all, load_config

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)


def full_store():
    store = Store()
    summary = import_and_validate(
        store,
        ROOT / "sample-data" / "contacts.csv",
        default_sequence="Outbound Intro",
        suppression_path=ROOT / "config" / "suppression.csv",
        now=NOW,
    )
    load_config(store, ROOT / "config")
    approve_templates(store, None, NOW)
    return store, summary


def test_sample_list_is_validated_with_every_defect_caught():
    store, summary = full_store()
    reasons = {}
    for r in summary.report.removed:
        reasons.setdefault(r.reason, []).append(r.contact.name)
    assert summary.read == 36 and len(summary.report.valid) == 26
    assert {k: len(v) for k, v in reasons.items()} == {
        "invalid_email": 2,
        "duplicate": 2,
        "opted_out": 4,
        "no_reachable_channel": 1,
        "missing_name": 1,
    }
    assert len(store.contacts()) == 26 and len(store.removed()) == 10


def test_sample_flags_record_why_a_channel_was_cleared():
    store, _ = full_store()
    flags = {t.contact.name: t.contact.flags for t in store.contacts()}
    assert any("email_cleared" in f for f in flags["Hester Vale"])
    assert any("linkedin_cleared" in f for f in flags["Orla Finnegan"])
    assert any("email_risky" in f for f in flags["Jada Finch"])


def test_import_twice_into_one_database_is_refused():
    store, _ = full_store()
    with pytest.raises(ValueError, match="already has contacts"):
        import_and_validate(store, ROOT / "sample-data" / "contacts.csv", now=NOW)


def test_gate_blocks_the_sample_because_one_contact_has_no_company():
    store, _ = full_store()
    checklist = launch_checklist(store, "Outbound Intro")
    failing = [(label, detail) for label, ok, detail in checklist.items if not ok]
    assert [label for label, _ in failing] == ["Every draft personalised and within channel limits"]
    assert "r0006" in failing[0][1] and "company" in failing[0][1]
    with pytest.raises(EngineError, match="r0006"):
        launch(store, "Outbound Intro", NOW)


def test_hold_incomplete_launches_everyone_else_and_parks_the_gap():
    store, _ = full_store()
    result = launch(store, "Outbound Intro", NOW, hold_incomplete=True)
    assert result.launched == 25 and result.held == ("r0006",)
    assert store.contact("r0006").stop_reason == "draft_incomplete"


def test_shipped_templates_have_no_lint_errors_or_warnings():
    store, _ = full_store()
    assert all(not issues for issues in lint_all(store).values()), lint_all(store)


def test_approval_is_all_or_nothing():
    store = Store()
    from sequencer.models import Template

    store.save_templates(
        {
            "good": Template("good", "linkedin_message", "Hi {{first_name}}"),
            "bad": Template("bad", "linkedin_message", "Hi there"),
        }
    )
    with pytest.raises(ApprovalError, match="bad"):
        approve_templates(store, None, NOW)
    assert store.approved_hash("good") is None
    with pytest.raises(ApprovalError, match="unknown"):
        approve_templates(store, ["zzz"], NOW)


def test_load_config_rejects_an_invalid_sequence(tmp_path):
    for name in ("templates.json", "rules.json", "sender.json"):
        (tmp_path / name).write_text((ROOT / "config" / name).read_text())
    (tmp_path / "sequences.json").write_text(
        json.dumps({"sequences": [{"name": "X", "steps": [{"channel": "email", "wait_days": 0, "template": "nope"}]}]})
    )
    with pytest.raises(SequenceError, match="does not exist"):
        load_config(Store(), tmp_path)


def run_full(seed=7, days=60, profile=None):
    store, _ = full_store()
    launch(store, "Outbound Intro", NOW, hold_incomplete=True)
    provider = SimulatedProvider(seed=seed, profile=profile)
    summary = run_simulation(store, provider, NOW, days=days)
    return store, summary


def test_full_simulation_is_deterministic():
    a, _ = run_full()
    b, _ = run_full()
    assert [(t.contact_key, t.step, t.status, t.at) for t in a.touches()] == [
        (t.contact_key, t.step, t.status, t.at) for t in b.touches()
    ]
    assert [(e.contact_key, e.kind, e.at) for e in a.events()] == [(e.contact_key, e.kind, e.at) for e in b.events()]


def test_different_seeds_give_different_outcomes():
    a, _ = run_full(seed=1)
    b, _ = run_full(seed=2)
    assert [e.kind for e in a.events()] != [e.kind for e in b.events()]


def test_simulation_respects_every_rule():
    store, summary = run_full()
    rules = store.get_rules()
    per_day = {}
    for t in store.touches():
        if t.status != "sent":
            continue
        local = rules.local(t.at)
        assert local.isoweekday() in rules.active_days and rules.start_hour <= local.hour < rules.end_hour
        per_day[(t.channel, local.date())] = per_day.get((t.channel, local.date()), 0) + 1
    assert all(n <= rules.limit_for(ch) for (ch, _), n in per_day.items())
    assert any(n == rules.limit_for(ch) for (ch, _), n in per_day.items()), "the demo should actually hit a limit"
    assert summary.finished_early


def test_no_touch_after_a_stop_and_every_contact_has_a_final_state():
    store, _ = run_full()
    stop_kinds = {C.REPLY, C.BOUNCED, C.MEETING, C.UNSUBSCRIBED}
    first_stop = {}
    for e in store.events():
        if e.kind in stop_kinds:
            first_stop.setdefault(e.contact_key, e.at)
    for t in store.touches():
        if t.contact_key in first_stop and t.status == "sent":
            assert t.at <= first_stop[t.contact_key], f"{t.contact_key} was contacted after it stopped"
    assert all(c.status != C.IN_SEQUENCE for c in store.contacts())


def test_touch_log_has_one_sent_or_skipped_row_per_contact_and_step():
    store, _ = run_full()
    seen = set()
    for t in store.touches():
        if t.status in ("sent", "skipped"):
            assert (t.contact_key, t.step) not in seen
            seen.add((t.contact_key, t.step))


def test_simulated_failures_are_retried_then_stopped():
    store, _ = full_store()
    launch(store, "Outbound Intro", NOW, hold_incomplete=True)
    provider = SimulatedProvider(seed=1, fail_keys=frozenset({"r0001"}))
    run_simulation(store, provider, NOW, days=3)
    assert store.contact("r0001").stop_reason == "send_failed"


def test_follow_ups_for_a_bounce_are_only_the_bounce():
    from sequencer.models import Step

    provider = SimulatedProvider(seed=3, profile=SimProfile(email_bounce=1.0))
    ups = provider.follow_ups(person(1), Step(1, "email", 0, "x"), TUESDAY_10)
    assert [u.kind for u in ups] == ["bounced"]


def test_meeting_never_precedes_its_reply():
    from sequencer.models import Step

    provider = SimulatedProvider(seed=3, profile=SimProfile(email_reply=1.0, meeting_given_reply=1.0, email_bounce=0.0))
    ups = {u.kind: u.after_hours for u in provider.follow_ups(person(1), Step(1, "email", 0, "x"), TUESDAY_10)}
    assert ups["meeting_booked"] > ups["replied"]


def test_simulation_stops_at_the_day_limit():
    store, _ = full_store()
    launch(store, "Outbound Intro", NOW, hold_incomplete=True)
    summary = run_simulation(store, SimulatedProvider(seed=7), NOW, days=1)
    assert summary.hours == 24 and not summary.finished_early


def test_small_store_helper_still_works_for_other_tests():
    s = build_store()
    assert len(s.contacts()) == 2 and (TUESDAY_10 - timedelta(hours=1)) < TUESDAY_10
