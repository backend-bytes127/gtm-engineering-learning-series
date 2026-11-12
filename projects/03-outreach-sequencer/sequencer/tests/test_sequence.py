import json

import pytest

from sequencer.models import Sequence, Step, Template
from sequencer.sequence import SequenceError, load_sequences, load_templates, parse_sequence, sequence_errors

T = {
    t.id: t
    for t in [
        Template("e1", "email", "hi", "s"),
        Template("inv", "linkedin_invite", "hi"),
        Template("dm", "linkedin_message", "hi"),
    ]
}


def steps(*specs):
    return [{"channel": ch, "wait_days": w, "template": t} for ch, w, t in specs]


def test_parse_assigns_positions_in_order():
    seq = parse_sequence({"name": "A", "steps": steps(("email", 0, "e1"), ("linkedin_invite", 2, "inv"))})
    assert [s.position for s in seq.steps] == [1, 2] and seq.steps[1].wait_days == 2


def test_valid_sequence_has_no_errors():
    seq = parse_sequence(
        {"name": "A", "steps": steps(("email", 0, "e1"), ("linkedin_invite", 1, "inv"), ("linkedin_message", 3, "dm"))}
    )
    assert sequence_errors(seq, T) == []


@pytest.mark.parametrize(
    "raw,msg",
    [
        ({"steps": []}, "name"),
        ({"name": "A", "steps": "x"}, "steps"),
        ({"name": "A", "steps": [{"channel": "email", "wait_days": "two", "template": "e1"}]}, "wait_days"),
        ({"name": "A", "steps": [{"channel": "email"}]}, "template"),
    ],
)
def test_parse_rejects_malformed_input(raw, msg):
    with pytest.raises(SequenceError, match=msg):
        parse_sequence(raw)


def errs(*specs, templates=T):
    return sequence_errors(Sequence("A", tuple(Step(i, ch, w, t) for i, (ch, w, t) in enumerate(specs, 1))), templates)


def test_empty_sequence_is_an_error():
    assert any("no steps" in e for e in errs())


def test_unknown_channel_and_template_are_errors():
    assert any("channel" in e for e in errs(("fax", 0, "e1")))
    assert any("template 'zzz'" in e for e in errs(("email", 0, "zzz")))


def test_template_channel_must_match_step_channel():
    assert any("is for email" in e for e in errs(("linkedin_invite", 0, "e1")))


def test_wait_days_bounds():
    assert any("wait_days" in e for e in errs(("email", -1, "e1")))
    assert any("wait_days" in e for e in errs(("email", 61, "e1")))


def test_linkedin_message_needs_an_earlier_invite():
    assert any("invite" in e for e in errs(("email", 0, "e1"), ("linkedin_message", 2, "dm")))
    assert errs(("linkedin_invite", 0, "inv"), ("linkedin_message", 2, "dm")) == []


def test_only_one_invite_and_a_step_cap():
    assert any("one invite" in e for e in errs(("linkedin_invite", 0, "inv"), ("linkedin_invite", 3, "inv")))
    assert any("at most" in e for e in errs(*[("email", 1, "e1")] * 11))


def test_load_sequences_and_templates_from_json(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"sequences": [{"name": "A", "steps": steps(("email", 0, "e1"))}]}))
    (tmp_path / "t.json").write_text(json.dumps({"templates": [{"id": "e1", "channel": "email", "subject": "s", "body": "b"}]}))
    assert load_sequences(tmp_path / "s.json")[0].name == "A"
    assert load_templates(tmp_path / "t.json")["e1"].subject == "s"


def test_duplicate_template_ids_and_bad_json_are_rejected(tmp_path):
    (tmp_path / "t.json").write_text(json.dumps({"templates": [{"id": "x", "channel": "email", "body": "b"}] * 2}))
    with pytest.raises(SequenceError, match="duplicate"):
        load_templates(tmp_path / "t.json")
    (tmp_path / "bad.json").write_text("{nope")
    with pytest.raises(SequenceError, match="JSON"):
        load_sequences(tmp_path / "bad.json")
