from datetime import timedelta

import pytest

from sequencer import constants as C
from sequencer.engine import EngineError, launch, launch_checklist, record_event, tick
from sequencer.models import Sequence, Step, Template
from sequencer.provider import SimulatedProvider
from sequencer.templates import approval_hash
from sequencer.tests.conftest import RULES, TEMPLATES, TUESDAY_10, build_store, days, person


class RecordingProvider:
    name = "recording"

    def __init__(self, fail=()):
        self.sent, self.fail = [], set(fail)

    def send(self, contact, step, subject, body, now):
        from sequencer.models import SendResult

        if contact.key in self.fail:
            return SendResult(False, error="boom")
        self.sent.append((contact.key, step.position, step.channel, subject, body))
        return SendResult(True, provider_id=f"id-{contact.key}-{step.position}")


def status(store, key):
    return store.contact(key).status


def live_store(**kw):
    s = build_store(**kw)
    launch(s, "Main", TUESDAY_10)
    return s


# ---------- launch gate ----------


def checks(store, name="Main"):
    return {label: ok for label, ok, _ in launch_checklist(store, name).items}


def test_checklist_all_green_when_everything_is_ready(store):
    cl = launch_checklist(store, "Main")
    assert cl.ready, cl.items


def test_gate_blocks_when_contacts_were_never_validated(store):
    store._db.execute("DELETE FROM settings WHERE key = 'validation_run'")
    assert checks(store)["Contacts imported and validated"] is False


def test_gate_blocks_with_no_contacts_for_the_sequence():
    s = build_store(contacts=[person(1, sequence="Other")])
    assert checks(s)["Contacts imported and validated"] is False


def test_gate_blocks_unapproved_templates():
    s = build_store(approve=False)
    assert checks(s)["Every template approved"] is False
    with pytest.raises(EngineError, match="Every template approved"):
        launch(s, "Main", TUESDAY_10)


def test_editing_an_approved_template_unapproves_it(store):
    store.save_templates({"e1": Template("e1", "email", "Changed {{first_name}} {{unsubscribe_line}}", "Subject {{company}}")})
    assert checks(store)["Every template approved"] is False


def test_gate_blocks_without_rules_or_sender():
    assert checks(build_store(rules=False))["Sending limits, hours and stop rules set"] is False
    assert checks(build_store(sender=False))["Sender profile set"] is False


def test_gate_blocks_malformed_sequence():
    bad = Sequence("Main", (Step(1, "linkedin_message", 0, "dm"),))
    assert checks(build_store(sequence=bad))["Sequence is well-formed"] is False


def test_gate_lists_contacts_whose_drafts_cannot_be_personalised():
    t = {
        **TEMPLATES,
        "e1": Template("e1", "email", "Hi {{first_name}} at {{company}} {{unsubscribe_line}}", "Hello {{first_name}}"),
    }
    s = build_store(contacts=[person(1), person(2, company="")])
    s.save_templates(t)
    s.approve_template("e1", approval_hash(t["e1"]), TUESDAY_10)
    cl = launch_checklist(s, "Main")
    label, ok, detail = next(i for i in cl.items if i[0].startswith("Every draft"))
    assert not ok and "r0002" in detail and "company" in detail


def test_hold_incomplete_parks_failing_contacts_and_launches_the_rest():
    t = {
        **TEMPLATES,
        "e1": Template("e1", "email", "Hi {{first_name}} at {{company}} {{unsubscribe_line}}", "Hello {{first_name}}"),
    }
    s = build_store(contacts=[person(1), person(2, company="")])
    s.save_templates(t)
    s.approve_template("e1", approval_hash(t["e1"]), TUESDAY_10)
    res = launch(s, "Main", TUESDAY_10, hold_incomplete=True)
    assert res.launched == 1 and res.held == ("r0002",)
    assert (s.contact("r0002").status, s.contact("r0002").stop_reason) == (C.STOPPED, "draft_incomplete")
    assert status(s, "r0001") == C.IN_SEQUENCE


def test_launch_moves_contacts_to_in_sequence_and_schedules_step_one(store):
    res = launch(store, "Main", TUESDAY_10)
    assert res.launched == 2 and store.is_live("Main")
    t = store.contact("r0001")
    assert t.status == C.IN_SEQUENCE and t.next_step == 1 and t.next_due == TUESDAY_10


def test_launch_twice_is_refused(store):
    launch(store, "Main", TUESDAY_10)
    with pytest.raises(EngineError, match="already live"):
        launch(store, "Main", TUESDAY_10)


def test_launch_unknown_sequence(store):
    with pytest.raises(EngineError, match="No sequence"):
        launch(store, "Nope", TUESDAY_10)


# ---------- tick: windows, limits, content ----------


def test_tick_sends_due_first_steps_and_logs_touches():
    s, p = live_store(), RecordingProvider()
    res = tick(s, p, TUESDAY_10)
    assert len(res.sent) == 2 and [x[2] for x in p.sent] == ["email", "email"]
    touch = s.touches("r0001")[0]
    assert (touch.status, touch.channel, touch.step, touch.at) == ("sent", "email", 1, TUESDAY_10)
    assert "Person1" in touch.body and "Seller Co" in touch.body and touch.subject == "Idea for Acme"
    t = s.contact("r0001")
    assert (t.status, t.next_step, t.next_due) == (C.IN_SEQUENCE, 2, TUESDAY_10 + days(1))


def test_tick_does_nothing_outside_hours_or_weekends():
    s, p = live_store(), RecordingProvider()
    assert tick(s, p, TUESDAY_10.replace(hour=20)).window_closed == "outside_hours"
    assert tick(s, p, TUESDAY_10 + days(4)).window_closed == "outside_active_days"  # Saturday
    assert p.sent == [] and s.touches() == []


def test_tick_respects_the_daily_email_limit_and_carries_over_to_tomorrow():
    s = live_store()
    s.set_setting("rules", {**RULES, "email_per_day": 1})
    p = RecordingProvider()
    first = tick(s, p, TUESDAY_10)
    assert len(first.sent) == 1 and first.deferred_limit == 1
    assert len(tick(s, p, TUESDAY_10 + timedelta(hours=1)).sent) == 0  # still capped the same day
    nxt = tick(s, p, TUESDAY_10 + days(1))
    assert len(nxt.sent) == 2  # the deferred first email, plus the first contact's LinkedIn invite (a different channel)
    assert {x[0] for x in p.sent if x[1] == 1} == {"r0001", "r0002"}


def test_limits_are_per_channel():
    s = live_store(contacts=[person(1)])
    p = RecordingProvider()
    tick(s, p, TUESDAY_10)
    tick(s, p, TUESDAY_10 + days(1))  # invite
    assert [x[2] for x in p.sent] == ["email", "linkedin_invite"]


def test_tick_skips_email_step_for_contact_without_email_and_moves_on():
    s = live_store(contacts=[person(1, email="")])
    res = tick(s, RecordingProvider(), TUESDAY_10)
    t = s.touches("r0001")[0]
    assert res.skipped == 1 and (t.status, t.reason) == ("skipped", "no_email")
    assert s.contact("r0001").next_step == 2


def test_tick_skips_linkedin_step_without_url():
    s = live_store(contacts=[person(1, linkedin_url="")])
    p = RecordingProvider()
    tick(s, p, TUESDAY_10)
    tick(s, p, TUESDAY_10 + days(1))
    assert s.touches("r0001")[1].reason == "no_linkedin"


def test_unapproved_template_is_never_sent_even_if_it_changed_after_launch():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    s.save_templates({"e1": Template("e1", "email", "Sneaky {{first_name}} {{unsubscribe_line}}", "S {{company}}")})
    res = tick(s, p, TUESDAY_10)
    assert p.sent == [] and res.blocked == 1 and s.touches() == []


def test_failed_sends_are_logged_and_retried_then_stopped():
    s, p = live_store(contacts=[person(1)]), RecordingProvider(fail={"r0001"})
    for h in range(3):
        tick(s, p, TUESDAY_10 + timedelta(hours=h))
    touches = s.touches("r0001")
    assert [t.status for t in touches] == ["failed"] * 3
    t = s.contact("r0001")
    assert (t.status, t.stop_reason) == (C.STOPPED, "send_failed")


def test_a_retry_that_succeeds_logs_one_sent_touch():
    s, p = live_store(contacts=[person(1)]), RecordingProvider(fail={"r0001"})
    tick(s, p, TUESDAY_10)
    p.fail.clear()
    tick(s, p, TUESDAY_10 + timedelta(hours=1))
    assert [t.status for t in s.touches("r0001")] == ["failed", "sent"]


# ---------- invite -> DM dependency, completion ----------


def advance_to_dm(s, p, accept):
    tick(s, p, TUESDAY_10)  # email
    tick(s, p, TUESDAY_10 + days(1))  # invite (Wed)
    if accept:
        record_event(s, "r0001", C.ACCEPTED, TUESDAY_10 + days(1) + timedelta(hours=3))


def test_dm_is_sent_after_the_invite_is_accepted():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    advance_to_dm(s, p, accept=True)
    tick(s, p, TUESDAY_10 + days(3))  # Fri, wait of 2 days after invite
    assert p.sent[-1][2] == "linkedin_message"


def test_dm_waits_while_the_invite_is_pending_and_is_skipped_when_it_expires():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    advance_to_dm(s, p, accept=False)
    waiting = tick(s, p, TUESDAY_10 + days(3))
    assert waiting.deferred_wait == 1 and [x[2] for x in p.sent] == ["email", "linkedin_invite"]
    expired = tick(s, p, TUESDAY_10 + days(1 + C.INVITE_EXPIRY_DAYS))  # Wed, window open
    assert expired.skipped == 1
    assert [t.reason for t in s.touches("r0001") if t.status == "skipped"] == ["invite_not_accepted"]
    assert s.contact("r0001").next_step == 4


def test_contact_completes_after_the_last_step():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    advance_to_dm(s, p, accept=True)
    tick(s, p, TUESDAY_10 + days(3))
    tick(s, p, TUESDAY_10 + days(6))  # Mon, last email
    t = s.contact("r0001")
    assert (t.status, t.next_due) == (C.COMPLETED, None)
    assert len(tick(s, p, TUESDAY_10 + days(20)).sent) == 0


# ---------- stop rules ----------


@pytest.mark.parametrize(
    "kind,expected,reason",
    [
        (C.REPLY, C.REPLIED, ""),
        (C.MEETING, C.MEETING_BOOKED, ""),
        (C.BOUNCED, C.STOPPED, "bounced"),
        (C.UNSUBSCRIBED, C.STOPPED, "opted_out"),
    ],
)
def test_stop_events_stop_the_sequence(kind, expected, reason):
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    tick(s, p, TUESDAY_10)
    record_event(s, "r0001", kind, TUESDAY_10 + timedelta(hours=2))
    t = s.contact("r0001")
    assert (t.status, t.stop_reason, t.next_due) == (expected, reason, None)
    before = len(p.sent)
    tick(s, p, TUESDAY_10 + days(1))
    assert len(p.sent) == before


def test_open_and_accept_do_not_stop_anything():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    tick(s, p, TUESDAY_10)
    record_event(s, "r0001", C.OPENED, TUESDAY_10 + timedelta(hours=1))
    record_event(s, "r0001", C.ACCEPTED, TUESDAY_10 + timedelta(hours=2))
    assert status(s, "r0001") == C.IN_SEQUENCE


def test_bounce_and_unsubscribe_add_the_contact_to_the_suppression_list():
    s, p = live_store(), RecordingProvider()
    tick(s, p, TUESDAY_10)
    record_event(s, "r0001", C.BOUNCED, TUESDAY_10 + timedelta(hours=1))
    record_event(s, "r0002", C.UNSUBSCRIBED, TUESDAY_10 + timedelta(hours=1))
    sup = s.suppression()
    assert {"p1@acme.example", "p2@acme.example"} <= sup.emails


def test_meeting_after_reply_upgrades_but_reply_after_meeting_does_not_downgrade():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    tick(s, p, TUESDAY_10)
    record_event(s, "r0001", C.REPLY, TUESDAY_10 + timedelta(hours=2))
    record_event(s, "r0001", C.MEETING, TUESDAY_10 + timedelta(hours=5))
    assert status(s, "r0001") == C.MEETING_BOOKED
    record_event(s, "r0001", C.REPLY, TUESDAY_10 + timedelta(hours=6), touch_id=None, detail="again")
    assert status(s, "r0001") == C.MEETING_BOOKED


def test_unsubscribe_overrides_a_reply():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    tick(s, p, TUESDAY_10)
    record_event(s, "r0001", C.REPLY, TUESDAY_10 + timedelta(hours=1))
    record_event(s, "r0001", C.UNSUBSCRIBED, TUESDAY_10 + timedelta(hours=2))
    assert (status(s, "r0001"), s.contact("r0001").stop_reason) == (C.STOPPED, "opted_out")


def test_reply_after_completion_updates_status():
    s, p = live_store(contacts=[person(1, linkedin_url="")]), RecordingProvider()
    for d in range(8):  # weekend days are closed windows, so nothing is sent on them
        tick(s, p, TUESDAY_10 + days(d))
    assert status(s, "r0001") == C.COMPLETED
    record_event(s, "r0001", C.REPLY, TUESDAY_10 + days(9))
    assert status(s, "r0001") == C.REPLIED


def test_stop_rules_can_be_narrowed():
    s = live_store(contacts=[person(1)])
    s.set_setting("rules", {**RULES, "stop_on": ["bounced"]})
    p = RecordingProvider()
    tick(s, p, TUESDAY_10)
    record_event(s, "r0001", C.REPLY, TUESDAY_10 + timedelta(hours=1))
    assert status(s, "r0001") == C.IN_SEQUENCE
    record_event(s, "r0001", C.UNSUBSCRIBED, TUESDAY_10 + timedelta(hours=2))  # never optional
    assert status(s, "r0001") == C.STOPPED


def test_events_are_idempotent_and_attach_to_the_latest_touch_by_default():
    s, p = live_store(contacts=[person(1)]), RecordingProvider()
    tick(s, p, TUESDAY_10)
    assert record_event(s, "r0001", C.OPENED, TUESDAY_10 + timedelta(hours=1)) is True
    assert record_event(s, "r0001", C.OPENED, TUESDAY_10 + timedelta(hours=2)) is False
    ev = s.events("r0001")
    assert len(ev) == 1 and ev[0].touch_id == s.touches("r0001")[0].id


def test_event_validation():
    s = live_store()
    with pytest.raises(EngineError, match="Unknown event"):
        record_event(s, "r0001", "vibes", TUESDAY_10)
    with pytest.raises(EngineError, match="No contact"):
        record_event(s, "r9999", C.REPLY, TUESDAY_10)


def test_tick_needs_rules_and_sender():
    s = build_store(rules=False)
    with pytest.raises(EngineError, match="rules"):
        tick(s, RecordingProvider(), TUESDAY_10)


def test_templates_fixture_sanity():
    assert set(TEMPLATES) == {"e1", "inv", "dm", "e2"}


def test_simulated_provider_plugs_into_tick():
    s = live_store()
    assert len(tick(s, SimulatedProvider(seed=1), TUESDAY_10).sent) == 2


def test_reset_run_returns_everyone_to_not_started_and_keeps_the_list():
    from sequencer.store import Store  # noqa: F401

    s, p = live_store(), RecordingProvider()
    tick(s, p, TUESDAY_10)
    record_event(s, "r0001", C.BOUNCED, TUESDAY_10 + timedelta(hours=1))
    s.reset_run()
    assert [t.status for t in s.contacts()] == [C.NOT_STARTED] * 2
    assert s.touches() == [] and s.events() == [] and not s.is_live("Main")
    assert "p1@acme.example" not in s.suppression().emails
    launch(s, "Main", TUESDAY_10)  # and it can be launched again


def test_reset_list_clears_contacts_but_keeps_config():
    s = live_store()
    s.reset_list()
    assert s.contacts() == [] and s.get_setting("validation_run") is None
    assert s.sequence("Main") is not None and s.get_rules() is not None and len(s.templates()) == 4


def test_delete_template():
    s = build_store()
    s.delete_template("e2")
    assert "e2" not in s.templates()


def test_refused_launch_does_not_park_anyone_even_with_hold_incomplete():
    t = {
        **TEMPLATES,
        "e1": Template("e1", "email", "Hi {{first_name}} at {{company}} {{unsubscribe_line}}", "Hello {{first_name}}"),
    }
    s = build_store(contacts=[person(1), person(2, company="")], approve=False)  # templates unapproved: a different failure
    s.save_templates(t)
    with pytest.raises(EngineError, match="Every template approved"):
        launch(s, "Main", TUESDAY_10, hold_incomplete=True)
    assert [x.status for x in s.contacts()] == [C.NOT_STARTED, C.NOT_STARTED]


# ---------- provider verdicts: skip and retry-later, only/caps filters ----------


class ScriptedProvider:
    name = "scripted"

    def __init__(self, result):
        self.result, self.calls = result, 0

    def send(self, contact, step, subject, body, now):
        self.calls += 1
        return self.result


def test_a_provider_skip_is_logged_as_skipped_not_failed_and_the_sequence_moves_on():
    from sequencer.models import SendResult

    s = live_store(contacts=[person(1)])
    p = ScriptedProvider(SendResult(False, skip_reason="channel_not_enabled"))
    res = tick(s, p, TUESDAY_10)
    t = s.touches("r0001")[0]
    assert res.skipped == 1 and (t.status, t.reason) == ("skipped", "channel_not_enabled")
    assert s.contact("r0001").next_step == 2 and s.contact("r0001").status == C.IN_SEQUENCE


def test_already_connected_skips_the_invite_and_unlocks_the_dm():
    from sequencer.models import SendResult

    s = live_store(contacts=[person(1)])
    tick(s, RecordingProvider(), TUESDAY_10)  # step 1 email
    tick(s, ScriptedProvider(SendResult(False, skip_reason="already_connected")), TUESDAY_10 + days(1))  # step 2 invite
    assert [t.reason for t in s.touches("r0001") if t.status == "skipped"] == ["already_connected"]
    assert s.has_event("r0001", C.ACCEPTED)
    rec = RecordingProvider()
    tick(s, rec, TUESDAY_10 + days(3))  # step 3 DM: goes out because the person is already a connection
    assert rec.sent[-1][2] == "linkedin_message"
    report_events = [e for e in s.events("r0001") if e.kind == C.ACCEPTED]
    assert report_events[0].touch_id == next(t.id for t in s.touches("r0001") if t.reason == "already_connected")


def test_retry_later_neither_logs_a_failure_nor_burns_attempts():
    from sequencer.models import SendResult

    s = live_store(contacts=[person(1)])
    p = ScriptedProvider(SendResult(False, error="rate limited", retry_later=True))
    for h in range(6):
        res = tick(s, p, TUESDAY_10 + timedelta(hours=h))
    assert s.touches("r0001") == [] and s.contact("r0001").status == C.IN_SEQUENCE and res.deferred_limit == 1 and p.calls == 6


def test_only_restricts_who_is_contacted():
    s, p = live_store(), RecordingProvider()
    res = tick(s, p, TUESDAY_10, only=frozenset({"r0002"}))
    assert [x[0] for x in p.sent] == ["r0002"] and len(res.sent) == 1


def test_caps_can_only_lower_the_rules_limits():
    s, p = live_store(), RecordingProvider()
    tick(s, p, TUESDAY_10, caps={"email": 1})
    assert len(p.sent) == 1
    s2, p2 = live_store(), RecordingProvider()
    tick(s2, p2, TUESDAY_10, caps={"email": 500})  # a larger cap must not raise the configured 30
    assert len(p2.sent) == 2
