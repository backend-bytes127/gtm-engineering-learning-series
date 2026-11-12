from datetime import timedelta

import openpyxl
import pytest

from sequencer import constants as C
from sequencer.engine import launch, record_event, tick
from sequencer.report import MIN_SAMPLE, Metrics, build_report, summary_lines, write_markdown, write_xlsx
from sequencer.tests.conftest import TUESDAY_10, build_store, days, person
from sequencer.tests.test_engine import RecordingProvider


def scenario():
    """Three contacts on the shared 4-step sequence (email, invite, DM, email).

    r1: email opened, replied, meeting booked. r2: email bounced. r3: email, invite accepted, DM, replied.
    """
    s = build_store(contacts=[person(1), person(2), person(3)])
    launch(s, "Main", TUESDAY_10)
    p = RecordingProvider()
    tick(s, p, TUESDAY_10)  # three emails
    record_event(s, "r0001", C.OPENED, TUESDAY_10 + timedelta(hours=1))
    record_event(s, "r0001", C.REPLY, TUESDAY_10 + timedelta(hours=3))
    record_event(s, "r0001", C.MEETING, TUESDAY_10 + timedelta(hours=9))
    record_event(s, "r0002", C.BOUNCED, TUESDAY_10 + timedelta(hours=1))
    tick(s, p, TUESDAY_10 + days(1))  # Wed: r3's invite (r1 and r2 have stopped)
    record_event(s, "r0003", C.ACCEPTED, TUESDAY_10 + days(1) + timedelta(hours=2))
    tick(s, p, TUESDAY_10 + days(3))  # Fri: r3's DM (two days after the invite)
    record_event(s, "r0003", C.REPLY, TUESDAY_10 + days(3) + timedelta(hours=2))
    return s


def test_metrics_rates_are_zero_safe():
    m = Metrics()
    assert m.reply_rate is None and m.open_rate is None
    assert Metrics(sent=10, replied=2).reply_rate == pytest.approx(0.2)


def test_by_step_counts_distinct_touches_with_each_outcome():
    r = build_report(scenario())
    step = {x.step: x for x in r.by_step}
    assert step[1].metrics == Metrics(sent=3, opened=1, accepted=0, replied=1, meetings=1)
    assert (step[2].channel, step[2].metrics.sent, step[2].metrics.accepted) == ("linkedin_invite", 1, 1)
    assert (step[3].channel, step[3].metrics.sent, step[3].metrics.replied) == ("linkedin_message", 1, 1)
    assert step[1].template == "e1"


def test_by_channel_groups_linkedin_invites_and_messages():
    r = build_report(scenario())
    ch = {x.channel: x.metrics for x in r.by_channel}
    assert ch["email"].sent == 3 and ch["email"].replied == 1 and ch["email"].opened == 1
    assert ch["linkedin"] == Metrics(sent=2, opened=0, accepted=1, replied=1, meetings=0)


def test_status_funnel_and_stop_reasons():
    r = build_report(scenario())
    assert r.statuses[C.MEETING_BOOKED] == 1 and r.statuses[C.REPLIED] == 1 and r.statuses[C.STOPPED] == 1
    assert r.stop_reasons == {"bounced": 1}
    assert (r.contacts_replied, r.contacts_meeting) == (2, 1)


def test_first_reply_is_attributed_to_the_step_that_got_it():
    r = build_report(scenario())
    assert r.first_reply_by_step == {1: 1, 3: 1}


def test_removed_by_reason_comes_from_the_store():
    from sequencer.models import Contact, Removed

    s = scenario()
    s.add_removed([Removed(Contact(row=9, name="X"), "duplicate", "d"), Removed(Contact(row=10, name="Y"), "duplicate", "d")])
    assert build_report(s).removed_by_reason == {"duplicate": 2}


def test_summary_says_small_sample_instead_of_declaring_a_winner():
    text = "\n".join(summary_lines(build_report(scenario()), simulated=False))
    assert f"fewer than {MIN_SAMPLE}" in text
    assert "Simulated" not in text


def test_summary_flags_simulated_data_first():
    lines = summary_lines(build_report(scenario()), simulated=True)
    assert lines[0].startswith("**Simulated")


def test_summary_mentions_bounce_hygiene_and_best_step():
    text = "\n".join(summary_lines(build_report(scenario()), simulated=False))
    assert "1 of 3 launched contacts bounced" in text.replace("e-mail", "email") or "bounce" in text.lower()
    assert "split evenly between steps 1, 3" in text


def with_channels(email, linkedin):
    from sequencer.report import ChannelStat, Report

    base = build_report(scenario())
    return Report(**{**base.__dict__, "by_channel": [ChannelStat("email", email), ChannelStat("linkedin", linkedin)]})


def test_summary_compares_channels_when_there_are_enough_messages_and_replies():
    text = "\n".join(summary_lines(with_channels(Metrics(sent=100, replied=3), Metrics(sent=100, replied=12)), simulated=False))
    assert "LinkedIn replied more often: 12% of 100 messages against 3% of 100 for email." in text


def test_summary_calls_a_small_gap_noise_even_with_many_messages():
    text = "\n".join(summary_lines(with_channels(Metrics(sent=100, replied=3), Metrics(sent=100, replied=1)), simulated=False))
    assert "is noise" in text and "replied more often" not in text


def test_summary_calls_equal_rates_equal():
    text = "\n".join(summary_lines(with_channels(Metrics(sent=100, replied=10), Metrics(sent=50, replied=5)), simulated=False))
    assert "same rate (10%)" in text


def test_a_step_is_flagged_silent_only_with_a_real_sample():
    from sequencer.report import Report, StepStat

    base = build_report(scenario())

    def quiet(n):
        return Report(**{**base.__dict__, "by_step": [StepStat("Main", 3, "email", "e2", Metrics(sent=n))]})

    assert "got no replies from 25 messages" in "\n".join(summary_lines(quiet(25), simulated=False))
    assert "got no replies" not in "\n".join(summary_lines(quiet(19), simulated=False))


def test_held_contacts_are_counted_apart_from_launched():
    s = scenario()
    s.set_state("r0003", C.STOPPED, C.REASON_DRAFT_INCOMPLETE)
    r = build_report(s)
    assert (r.contacts_launched, r.contacts_held) == (2, 1)
    assert "1 contact(s) were held back" in "\n".join(summary_lines(r, simulated=False))


def test_metrics_that_do_not_apply_to_a_channel_are_blank_not_zero():
    r = build_report(scenario())
    by_step = {x.step: x for x in r.by_step}
    from sequencer.report import _metric_cells

    email = _metric_cells(by_step[1].metrics, by_step[1].channel)
    invite = _metric_cells(by_step[2].metrics, by_step[2].channel)
    assert email[1] == 1 and email[2] is None and email[5] is not None and email[6] is None
    dm = _metric_cells(by_step[3].metrics, by_step[3].channel)
    assert dm[1] is None and dm[2] is None and dm[6] is None  # a DM is neither opened nor accepted
    assert invite[1] is None and invite[2] == 1 and invite[5] is None and invite[6] == 1.0


def test_metrics_dict_is_plain_json_data():
    import json

    from sequencer.report import metrics_dict

    d = json.loads(json.dumps(metrics_dict(build_report(scenario()))))
    assert d["contacts"]["replied"] == 2 and d["by_channel"]["email"]["sent"] == 3 and d["by_step"][0]["template"] == "e1"


def test_xlsx_has_every_sheet_and_the_numbers(tmp_path):
    s = scenario()
    path = tmp_path / "r.xlsx"
    write_xlsx(s, build_report(s), path, simulated=False)
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Summary", "By Step", "By Channel", "Contacts", "Touch Log", "Removed Records"]
    steps = list(wb["By Step"].iter_rows(values_only=True))
    assert steps[0][:5] == ("Sequence", "Step", "Channel", "Template", "Sent") and steps[1][4] == 3
    contacts = {row[0]: row for row in wb["Contacts"].iter_rows(min_row=2, values_only=True)}
    assert contacts["r0001"][6] == C.MEETING_BOOKED
    log = list(wb["Touch Log"].iter_rows(min_row=2, values_only=True))
    assert len(log) == len(s.touches()) and any("replied" in str(row) for row in log)


def test_markdown_contains_summary_and_tables(tmp_path):
    s = scenario()
    path = tmp_path / "s.md"
    write_markdown(build_report(s), path, simulated=False)
    text = path.read_text()
    assert "## By step" in text and "## By channel" in text and "| 1 |" in text


def test_summary_names_a_single_leading_step():
    from sequencer.report import Report

    base = build_report(scenario())
    lead = Report(**{**base.__dict__, "first_reply_by_step": {1: 3, 3: 1}})
    assert "Most first replies came from step 1 (email, template `e1`): 3 of 4." in "\n".join(
        summary_lines(lead, simulated=False)
    )


@pytest.mark.parametrize("evil", ['=HYPERLINK("http://x.example","click")', "+SUM(1,1)", "-2+3", "@cmd"])
def test_untrusted_text_in_the_workbook_is_never_a_formula(tmp_path, evil):
    s = build_store(contacts=[person(1, name=evil, first_name="Ada", company=evil)])
    path = tmp_path / "r.xlsx"
    write_xlsx(s, build_report(s), path, simulated=False)
    ws = openpyxl.load_workbook(path)["Contacts"]
    cells = [c for c in ws[2] if c.value == evil]
    assert cells, "the text must survive unchanged"
    assert all(c.data_type == "s" for c in cells), f"{evil!r} would be read by Excel as a formula"
