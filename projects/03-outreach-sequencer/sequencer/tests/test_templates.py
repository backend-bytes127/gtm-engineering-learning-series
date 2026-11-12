import pytest

from sequencer.models import Contact, Sender, Template
from sequencer.templates import approval_hash, check_draft, lint_template, render, variables_in

SENDER = Sender("Sam Seller", "Seller Co", "1 Example Street, Dubai")
ADA = Contact(
    row=1, name="Ada Lovelace", first_name="Ada", last_name="Lovelace", company="Acme", title="CTO", email="a@acme.example"
)
FOOTER = "\n\n{{unsubscribe_line}}"


def email(body, subject="Quick question for {{company}}"):
    return Template("e", "email", body + FOOTER, subject)


def codes(issues, severity=None):
    return {i.code for i in issues if severity in (None, i.severity)}


def test_variables_in_finds_names_with_and_without_fallbacks():
    assert variables_in("Hi {{ first_name }}, {{title|your role}} at {{company}} {{first_name}}") == [
        "first_name",
        "title",
        "company",
    ]


def test_render_replaces_variables_and_reports_nothing_missing():
    out = render("Hi {{first_name}} at {{company}}", ADA, SENDER)
    assert out.text == "Hi Ada at Acme" and out.missing == () and out.fallbacks == ()


def test_render_uses_fallbacks_and_reports_them():
    c = Contact(row=2, name="Bo", first_name="Bo", email="b@x.example")
    out = render("Hi {{first_name}} at {{company|your company}}", c, SENDER)
    assert out.text == "Hi Bo at your company" and out.fallbacks == ("company",)


def test_render_reports_missing_without_fallback_and_leaves_no_placeholder():
    c = Contact(row=2, name="Bo", first_name="Bo", email="b@x.example")
    out = render("Hi {{first_name}} at {{company}}", c, SENDER)
    assert out.missing == ("company",) and "{{" not in out.text


def test_render_unsubscribe_line_uses_sender_details():
    out = render("{{unsubscribe_line}}", ADA, SENDER)
    assert "unsubscribe" in out.text.lower() and "1 Example Street, Dubai" in out.text and "Seller Co" in out.text


def test_render_does_not_evaluate_placeholders_inside_values():
    c = Contact(row=3, name="X", first_name="{{company}}", company="Acme", email="x@x.example")
    assert render("Hi {{first_name}}", c, SENDER).text == "Hi {{company}}"


def test_lint_passes_a_good_email():
    t = email("Hi {{first_name}},\n\nSaw {{company}} is growing. Worth a chat?\n\n{{sender_name}}")
    assert codes(lint_template(t), "error") == set()


def test_lint_requires_personalisation():
    t = email("Hello,\n\nWe sell things. Worth a chat?", subject="Quick question")
    assert "no_personalisation" in codes(lint_template(t), "error")


def test_lint_flags_unknown_variables():
    assert "unknown_variable" in codes(lint_template(email("Hi {{firstname}} {{company}}")), "error")


def test_lint_requires_unsubscribe_line_in_email_only():
    no_footer = Template("e", "email", "Hi {{first_name}}", "Hey {{company}}")
    assert "missing_unsubscribe" in codes(lint_template(no_footer), "error")
    assert "missing_unsubscribe" not in codes(lint_template(Template("i", "linkedin_invite", "Hi {{first_name}}")))


def test_lint_requires_email_subject():
    assert "missing_subject" in codes(lint_template(Template("e", "email", "Hi {{first_name}}" + FOOTER)), "error")


def test_lint_flags_empty_body_and_bad_channel():
    assert "empty_body" in codes(lint_template(Template("e", "linkedin_message", "  ")), "error")
    assert "bad_channel" in codes(lint_template(Template("e", "fax", "Hi {{first_name}}")), "error")


def test_invite_over_300_chars_is_an_error_even_after_longest_substitution():
    ok = Template("i", "linkedin_invite", "Hi {{first_name}}, " + "x" * 270)
    assert "invite_too_long" not in codes(lint_template(ok))
    bad = Template("i", "linkedin_invite", "Hi {{first_name}}, " + "x" * 300)
    assert "invite_too_long" in codes(lint_template(bad), "error")


def test_spam_words_and_shouting_are_warnings_not_errors():
    t = email("Hi {{first_name}}!! ACT NOW for a FREE guaranteed result!!! 100% risk free")
    issues = lint_template(t)
    assert {"spam_words", "shouting"} <= codes(issues, "warning") and codes(issues, "error") == set()


def test_many_links_is_a_warning():
    t = email("Hi {{first_name}} see https://a.example and https://b.example")
    assert "many_links" in codes(lint_template(t), "warning")


def test_long_email_is_a_warning():
    t = email("Hi {{first_name}} " + "word " * 200)
    assert "long_email" in codes(lint_template(t), "warning")


def test_approval_hash_changes_with_content_only():
    a = email("Hi {{first_name}} {{company}}")
    assert approval_hash(a) == approval_hash(email("Hi {{first_name}} {{company}}"))
    assert approval_hash(a) != approval_hash(email("Hi {{first_name}} {{company}}!"))


def test_check_draft_blocks_on_missing_data_and_long_invite():
    bad = Contact(row=2, name="Bo", first_name="Bo", email="b@x.example")
    t = email("Hi {{first_name}}, how is {{company}}?")
    issues = check_draft(t, bad, SENDER)
    assert codes(issues, "error") == {"missing_data"} and "company" in issues[0].message
    assert check_draft(t, ADA, SENDER) == []
    long_invite = Template("i", "linkedin_invite", "Hi {{first_name}} " + "x" * 290)
    long_contact = Contact(row=3, name="Z", first_name="Z" * 30, email="z@x.example")
    assert "invite_too_long" in codes(check_draft(long_invite, long_contact, SENDER), "error")


@pytest.mark.parametrize("fallback_value", ["", "   "])
def test_blank_values_count_as_missing(fallback_value):
    c = Contact(row=5, name="Bo", first_name="Bo", company=fallback_value, email="b@x.example")
    assert render("{{company}}", c, SENDER).missing == ("company",)
