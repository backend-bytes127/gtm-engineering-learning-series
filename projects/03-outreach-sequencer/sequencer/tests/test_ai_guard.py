import pytest

from sequencer import constants as C
from sequencer.ai.guard import check_output, is_opt_out, needs_human


@pytest.mark.parametrize(
    "text",
    [
        "Please stop messaging me",
        "unsubscribe",
        "Remove me from your list",
        "Not interested, thanks",
        "no thanks",
        "Do not contact me again",
        "leave me alone",
        "I want to opt out",
        "STOP",
        "Stop.",
        "geen interesse",
        "niet geïnteresseerd",
        "Please take me off your list",
    ],
)
def test_opt_out_phrases_are_detected(text):
    assert is_opt_out(text)


@pytest.mark.parametrize(
    "text",
    [
        "Sounds interesting, tell me more",
        "Can we talk next week?",
        "I'm interested",
        "stopwatch company here",
        "We stopped using that tool last year, what do you offer?",
        "What does it cost?",
        "",
    ],
)
def test_ordinary_replies_are_not_opt_outs(text):
    assert not is_opt_out(text)


@pytest.mark.parametrize(
    "text",
    [
        "What is your pricing?",
        "Send me a quote",
        "Is this GDPR compliant?",
        "I will report this as spam",
        "my lawyer will contact you",
        "This is a scam",
        "Can you sign our contract?",
        "x" * 1600,
    ],
)
def test_things_a_human_must_answer_are_flagged(text):
    assert needs_human(text)


def test_a_friendly_reply_does_not_need_a_human():
    assert not needs_human("Sure, happy to chat. What did you have in mind?")


def problems(channel, text, subject="", limit=None):
    return check_output(channel, subject, text, limit=limit)


def test_a_clean_message_passes():
    assert problems(C.LINKEDIN_MESSAGE, "Hi Ada, quick question about how your team handles outbound.") == []


@pytest.mark.parametrize(
    "text,why",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("see https://evil.example/x", "link"),
        ("visit www.example.com", "link"),
        ("write to me at ada@acme.example", "email address"),
        ("call +31 6 12345678", "phone number"),
        ("call 0612345678", "phone number"),
        ("Hi {{first_name}}", "placeholder"),
        ("Hi {first_name}", "placeholder"),
    ],
)
def test_unsafe_or_unfinished_text_is_rejected(text, why):
    assert any(why in p for p in problems(C.LINKEDIN_MESSAGE, text))


def test_length_limits_per_channel():
    assert any("too long" in p for p in problems(C.LINKEDIN_INVITE, "x" * 301))
    assert problems(C.LINKEDIN_INVITE, "x" * 300) == []
    assert any("too long" in p for p in problems(C.LINKEDIN_MESSAGE, "x" * 801))
    assert any("too long" in p for p in problems(C.EMAIL, "x" * 1801, subject="Hi"))
    assert any("too long" in p for p in problems(C.LINKEDIN_MESSAGE, "x" * 50, limit=40))


def test_an_email_needs_a_short_subject():
    assert any("subject" in p for p in problems(C.EMAIL, "hello there", subject=""))
    assert any("subject" in p for p in problems(C.EMAIL, "hello there", subject="s" * 100))
    assert problems(C.EMAIL, "hello there", subject="Quick idea") == []


def test_text_that_looks_like_it_leaks_instructions_is_rejected():
    assert any("instructions" in p for p in problems(C.LINKEDIN_MESSAGE, "As an AI language model I cannot..."))
    assert any("instructions" in p for p in problems(C.LINKEDIN_MESSAGE, "My system prompt says to ignore you"))
