from datetime import datetime, timezone

import pytest

from sequencer.rules import RulesError, SendingRules, parse_rules, window_verdict


def rules(**kw):
    return parse_rules(
        {
            "timezone": "UTC",
            "email_per_day": 30,
            "linkedin_invites_per_day": 10,
            "linkedin_messages_per_day": 20,
            "start_hour": 9,
            "end_hour": 17,
            "active_days": [1, 2, 3, 4, 5],
            **kw,
        }
    )


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_parse_applies_defaults_for_stop_rules():
    r = rules()
    assert r.stop_on == ("replied", "bounced", "meeting_booked")
    assert r.limit_for("email") == 30 and r.limit_for("linkedin_invite") == 10 and r.limit_for("linkedin_message") == 20


@pytest.mark.parametrize(
    "override,msg",
    [
        ({"email_per_day": 0}, "email_per_day"),
        ({"email_per_day": 201}, "email_per_day"),
        ({"linkedin_invites_per_day": 26}, "linkedin_invites_per_day"),
        ({"linkedin_messages_per_day": 101}, "linkedin_messages_per_day"),
        ({"email_per_day": "many"}, "email_per_day"),
        ({"start_hour": 17, "end_hour": 9}, "start_hour"),
        ({"end_hour": 25}, "end_hour"),
        ({"start_hour": -1}, "start_hour"),
        ({"active_days": []}, "active_days"),
        ({"active_days": [0, 8]}, "active_days"),
        ({"timezone": "Mars/Base"}, "timezone"),
        ({"stop_on": ["replied", "vibes"]}, "stop_on"),
    ],
)
def test_invalid_rules_are_rejected(override, msg):
    with pytest.raises(RulesError, match=msg):
        rules(**override)


def test_missing_required_setting_is_rejected():
    with pytest.raises(RulesError, match="email_per_day"):
        parse_rules({"timezone": "UTC"})


def test_stop_rules_can_be_narrowed_but_must_be_known():
    assert rules(stop_on=["replied"]).stop_on == ("replied",)


def test_window_open_inside_hours_on_active_days():
    assert window_verdict(rules(), at(2026, 11, 10, 9)).open  # Tuesday 09:00
    assert window_verdict(rules(), at(2026, 11, 10, 16, 59)).open


def test_window_closed_outside_hours_and_on_weekends():
    assert window_verdict(rules(), at(2026, 11, 10, 8, 59)).reason == "outside_hours"
    assert window_verdict(rules(), at(2026, 11, 10, 17)).reason == "outside_hours"
    assert window_verdict(rules(), at(2026, 11, 14, 10)).reason == "outside_active_days"  # Saturday


def test_window_uses_the_configured_timezone():
    r = rules(timezone="Asia/Dubai")  # UTC+4
    assert window_verdict(r, at(2026, 11, 10, 5)).open  # 09:00 in Dubai
    assert not window_verdict(r, at(2026, 11, 10, 14)).open  # 18:00 in Dubai


def test_local_date_follows_timezone():
    r = rules(timezone="Asia/Dubai")
    assert r.local_date(at(2026, 11, 10, 21)).isoformat() == "2026-11-11"


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        window_verdict(rules(), datetime(2026, 11, 10, 10))


def test_rules_are_immutable_and_round_trip_through_dict():
    r = rules()
    assert isinstance(r, SendingRules)
    with pytest.raises(AttributeError):
        r.start_hour = 1
    assert parse_rules(r.to_dict()) == r
