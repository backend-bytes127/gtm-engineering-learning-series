import json

from hub import pipeline, signing
from hub import state as st
from hub.pipeline import Request
from hub.scenarios import Tour, sample
from hub.simulate import run_tour

NOW = 1_800_000_000


def test_every_scripted_step_gives_its_expected_result():
    observations = run_tour(NOW)
    assert [(o.step.name, o.status, o.outcome) for o in observations if not o.matched] == []


def test_state_functions_do_not_mutate_their_input():
    start = st.State()
    st.remember_signature(start, "a", NOW, NOW)
    st.record_event(start, "k", {"status": "delivered"}, NOW)
    st.add_dead_letter(start, "r", None, {}, NOW)
    assert start == st.State()


def test_signatures_expire_with_the_freshness_window():
    first = st.remember_signature(st.State(), "a", NOW, NOW)
    assert st.is_replay(first, "a", NOW + 300) and not st.is_replay(first, "a", NOW + 301)
    assert "a" not in st.remember_signature(first, "b", NOW + 301, NOW + 301).signatures


def test_events_expire_and_stores_are_bounded(monkeypatch):
    old = st.record_event(st.State(), "old", {}, NOW)
    assert list(st.record_event(old, "new", {}, NOW + st.EVENT_RETENTION_SECONDS + 1).events) == ["new"]
    monkeypatch.setattr(st, "MAX_EVENTS", 3)
    monkeypatch.setattr(st, "MAX_DEAD_LETTERS", 2)
    state = st.State()
    for i in range(5):
        state = st.add_dead_letter(st.record_event(state, str(i), {}, NOW), str(i), None, {}, NOW)
    assert list(state.events) == ["2", "3", "4"]
    assert [d["reason"] for d in state.dead_letters] == ["3", "4"]


def test_unauthenticated_requests_leave_no_trace(settings):
    for handler in (pipeline.handle_signal, pipeline.handle_pql, pipeline.handle_interaction):
        result = handler(Request({}, b"{}"), st.State(), settings, lambda *_: True, NOW)
        assert (result.status, result.state) == (401, st.State())


def test_failed_delivery_keeps_the_event_and_allows_a_retry(settings):
    event = sample("signal.synthetic.json")
    request = Tour(settings).signed(event)(NOW)
    failed = pipeline.handle_signal(request, st.State(), settings, lambda *_: False, NOW)
    assert failed.status == 502 and not failed.state.events
    assert failed.state.dead_letters[0]["detail"] == {"event": event}
    retry = Tour(settings).signed(event, 1)(NOW)
    assert pipeline.handle_signal(retry, failed.state, settings, lambda *_: True, NOW).outcome == "delivered"


def test_schema_dead_letter_stores_a_hash_and_field_names_only(settings):
    request = Tour(settings).signed({"secret_looking": "do-not-store"})(NOW)
    result = pipeline.handle_signal(request, st.State(), settings, lambda *_: True, NOW)
    assert "do-not-store" not in json.dumps(list(result.state.dead_letters))


def test_missing_secret_is_a_503(settings):
    body = b"{}"
    request = Request(signing.signed_headers(signing.GENERIC, "t" * 32, NOW, body), body)
    blank = pipeline.Settings("", "")
    assert pipeline.handle_signal(request, st.State(), blank, lambda *_: True, NOW).status == 503


def test_pql_with_bad_json_is_dead_lettered(settings):
    request = Tour(settings).signed(b"\xff")(NOW)
    result = pipeline.handle_pql(request, st.State(), settings, lambda *_: True, NOW)
    assert result.outcome == "invalid_json" and len(result.state.dead_letters) == 1
