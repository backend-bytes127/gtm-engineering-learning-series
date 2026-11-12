import json
from datetime import timedelta

import pytest

from sequencer import constants as C
from sequencer.engine import launch
from sequencer.live.runner import (
    HARD_MAX_CONTACTS,
    LiveError,
    apply_webhook,
    poll_accepts,
    run_live_tick,
    start_live,
    stop_live,
)
from sequencer.live.unipile import UnipileClient, UnipileProvider
from sequencer.models import Sequence, Step
from sequencer.tests.conftest import TUESDAY_10, build_store, days, person
from sequencer.tests.test_unipile import ACCOUNT, FakeTransport, profile

LI_SEQ = Sequence("Main", (Step(1, "linkedin_invite", 0, "inv"), Step(2, "linkedin_message", 2, "dm")))
CAPS = {"linkedin_invite": 3, "linkedin_message": 5}


def live_store(n=2, sequence=LI_SEQ):
    s = build_store(contacts=[person(i + 1) for i in range(n)], sequence=sequence)
    launch(s, "Main", TUESDAY_10)
    return s


def provider_for(s, routes):
    t = FakeTransport(routes)
    p = UnipileProvider(UnipileClient("KEY", ACCOUNT, transport=t), remember=s.set_provider_id)
    return p, t


OK_ROUTES = {
    ("GET", f"/{ACCOUNT}/users/person-1"): (200, profile("SECOND_DEGREE", "prov_1")),
    ("GET", f"/{ACCOUNT}/users/person-2"): (200, profile("SECOND_DEGREE", "prov_2")),
    ("POST", f"/{ACCOUNT}/users/me/relation-requests"): (200, {}),
    ("POST", f"/{ACCOUNT}/inboxes/CLASSIC_PRIMARY/chats/send"): (200, {}),
}


# ---------------------------------------------------------------- start / stop safety


def test_start_requires_a_launched_sequence_and_real_contacts():
    s = build_store()
    with pytest.raises(LiveError, match="Launch"):
        start_live(s, ["r0001"], TUESDAY_10)
    s = live_store()
    with pytest.raises(LiveError, match="at least one"):
        start_live(s, [], TUESDAY_10)
    with pytest.raises(LiveError, match="r0099"):
        start_live(s, ["r0099"], TUESDAY_10)


def test_start_caps_how_many_people_can_be_contacted():
    s = live_store(HARD_MAX_CONTACTS + 2)
    with pytest.raises(LiveError, match=str(HARD_MAX_CONTACTS)):
        start_live(s, [f"r{i:04d}" for i in range(1, HARD_MAX_CONTACTS + 2)], TUESDAY_10)


def test_start_refuses_after_a_simulation_and_marks_the_run_as_live():
    s = live_store()
    s.set_setting("mode", {"provider": "simulated", "seed": 1})
    with pytest.raises(LiveError, match="simulation"):
        start_live(s, ["r0001"], TUESDAY_10)
    s.reset_run()
    launch(s, "Main", TUESDAY_10)
    start_live(s, ["r0001"], TUESDAY_10)
    assert s.get_setting("mode") == {"provider": "unipile"} and s.get_setting("live")["contacts"] == ["r0001"]


def test_stop_is_a_kill_switch_that_halts_sending():
    s = live_store()
    start_live(s, ["r0001"], TUESDAY_10)
    stop_live(s)
    p, t = provider_for(s, OK_ROUTES)
    assert run_live_tick(s, p, TUESDAY_10, CAPS) is None and t.requests == []


# ---------------------------------------------------------------- sending only to the chosen contacts


def test_only_selected_contacts_are_ever_contacted_and_caps_apply():
    s = live_store(3)
    start_live(s, ["r0002"], TUESDAY_10)
    p, t = provider_for(s, OK_ROUTES)
    res = run_live_tick(s, p, TUESDAY_10, CAPS)
    assert [x.contact.key for x in res.sent] == ["r0002"]
    assert {r["path"] for r in t.requests if r["method"] == "POST"} == {f"/{ACCOUNT}/users/me/relation-requests"}
    assert s.touches("r0001") == [] and s.touches("r0003") == []
    assert s.provider_id_for("r0002") == "prov_2"


def test_the_live_daily_cap_is_enforced_even_with_larger_rules():
    s = live_store(5)
    start_live(s, [f"r000{i}" for i in range(1, 6)], TUESDAY_10)
    p, _ = provider_for(
        s,
        {
            **OK_ROUTES,
            **{("GET", f"/{ACCOUNT}/users/person-{i}"): (200, profile("SECOND_DEGREE", f"prov_{i}")) for i in range(1, 6)},
        },
    )
    res = run_live_tick(s, p, TUESDAY_10, {"linkedin_invite": 2, "linkedin_message": 5})
    assert len(res.sent) == 2 and res.deferred_limit == 3


def test_a_rate_limit_pauses_nothing_permanently_and_logs_no_failure():
    s = live_store(1)
    start_live(s, ["r0001"], TUESDAY_10)
    p, _ = provider_for(
        s,
        {**OK_ROUTES, ("POST", f"/{ACCOUNT}/users/me/relation-requests"): (429, {"type": "too_many_requests", "detail": "slow"})},
    )
    run_live_tick(s, p, TUESDAY_10, CAPS)
    assert s.touches("r0001") == [] and s.contact("r0001").status == C.IN_SEQUENCE


def test_status_is_recorded_after_each_tick():
    s = live_store(1)
    start_live(s, ["r0001"], TUESDAY_10)
    p, _ = provider_for(s, OK_ROUTES)
    run_live_tick(s, p, TUESDAY_10, CAPS)
    st = s.get_setting("live_status")
    assert st["sent"] == 1 and st["at"].startswith("2026-11-10")


# ---------------------------------------------------------------- accepted invites and replies


def test_polling_relations_records_an_accept_only_for_selected_people_with_a_sent_invite():
    s = live_store(2)
    start_live(s, ["r0001", "r0002"], TUESDAY_10)
    p, _ = provider_for(s, OK_ROUTES)
    run_live_tick(s, p, TUESDAY_10, CAPS)
    t = FakeTransport(
        {("GET", f"/{ACCOUNT}/users/me/relations"): (200, {"data": [{"user": {"id": "prov_1"}}, {"user": {"id": "stranger"}}]})}
    )
    n = poll_accepts(s, UnipileClient("KEY", ACCOUNT, transport=t), TUESDAY_10 + timedelta(hours=3))
    assert n == 1 and s.has_event("r0001", C.ACCEPTED) and not s.has_event("r0002", C.ACCEPTED)
    assert poll_accepts(s, UnipileClient("KEY", ACCOUNT, transport=t), TUESDAY_10 + timedelta(hours=4)) == 0  # not recorded twice


def test_polling_makes_no_request_when_no_invite_is_waiting():
    s = live_store(1)
    start_live(s, ["r0001"], TUESDAY_10)
    t = FakeTransport({})
    assert poll_accepts(s, UnipileClient("KEY", ACCOUNT, transport=t), TUESDAY_10) == 0 and t.requests == []


def test_an_accept_unlocks_the_dm_which_then_sends():
    s = live_store(1)
    start_live(s, ["r0001"], TUESDAY_10)
    p, t = provider_for(s, OK_ROUTES)
    run_live_tick(s, p, TUESDAY_10, CAPS)
    rel = FakeTransport({("GET", "/"): (200, {"data": [{"user": {"id": "prov_1"}}]})})
    poll_accepts(s, UnipileClient("KEY", ACCOUNT, transport=rel), TUESDAY_10 + timedelta(hours=2))
    run_live_tick(s, p, TUESDAY_10 + days(3), CAPS)  # Friday: two days after the invite
    assert [r["path"] for r in t.requests if r["method"] == "POST"][-1].endswith("/chats/send")


def reply(provider_id, mid="m1"):
    return {
        "type": "message.new",
        "account_id": ACCOUNT,
        "payload": {"id": mid, "chat_id": "c1", "is_sender": False, "sender_id": provider_id, "text": "sure, let's talk"},
    }


def test_a_reply_webhook_stops_the_contact_and_attaches_to_their_last_message():
    s = live_store(1)
    start_live(s, ["r0001"], TUESDAY_10)
    p, _ = provider_for(s, OK_ROUTES)
    run_live_tick(s, p, TUESDAY_10, CAPS)
    assert apply_webhook(s, reply("prov_1"), ACCOUNT, TUESDAY_10 + timedelta(hours=5)) is True
    assert s.contact("r0001").status == C.REPLIED and s.events("r0001")[-1].touch_id == s.touches("r0001")[0].id


def test_webhooks_from_unknown_people_or_repeats_change_nothing():
    s = live_store(1)
    start_live(s, ["r0001"], TUESDAY_10)
    p, _ = provider_for(s, OK_ROUTES)
    run_live_tick(s, p, TUESDAY_10, CAPS)
    assert apply_webhook(s, reply("stranger"), ACCOUNT, TUESDAY_10) is False
    assert apply_webhook(s, reply("prov_1"), ACCOUNT, TUESDAY_10) is True
    assert apply_webhook(s, reply("prov_1", "m2"), ACCOUNT, TUESDAY_10 + timedelta(hours=1)) is False  # already replied
    assert len([e for e in s.events("r0001") if e.kind == C.REPLY]) == 1


def test_webhook_text_is_not_stored_as_trusted_content():
    s = live_store(1)
    start_live(s, ["r0001"], TUESDAY_10)
    p, _ = provider_for(s, OK_ROUTES)
    run_live_tick(s, p, TUESDAY_10, CAPS)
    env = reply("prov_1")
    env["payload"]["text"] = "<script>alert(1)</script>" * 50
    apply_webhook(s, env, ACCOUNT, TUESDAY_10)
    assert len(s.events("r0001")[-1].detail) <= 200
    json.dumps(s.events("r0001")[-1].detail)
