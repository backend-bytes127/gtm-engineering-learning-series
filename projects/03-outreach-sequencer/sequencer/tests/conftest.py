from datetime import datetime, timedelta, timezone

import pytest

from sequencer.models import Contact, Sender, Sequence, Step, Template
from sequencer.rules import parse_rules
from sequencer.store import Store
from sequencer.templates import approval_hash

SENDER = Sender("Sam Seller", "Seller Co", "1 Example Street, Dubai")
RULES = {
    "timezone": "UTC",
    "email_per_day": 30,
    "linkedin_invites_per_day": 10,
    "linkedin_messages_per_day": 20,
    "start_hour": 9,
    "end_hour": 17,
    "active_days": [1, 2, 3, 4, 5],
}
TEMPLATES = {
    "e1": Template(
        "e1", "email", "Hi {{first_name}}, {{unsubscribe_line}}\n{{company|your team}}", "Idea for {{company|your team}}"
    ),
    "inv": Template("inv", "linkedin_invite", "Hi {{first_name}}, would like to connect."),
    "dm": Template("dm", "linkedin_message", "Thanks for connecting, {{first_name}}."),
    "e2": Template("e2", "email", "Following up, {{first_name}}. {{unsubscribe_line}}", "Re: idea for {{company|your team}}"),
}
SEQ = Sequence(
    "Main",
    (
        Step(1, "email", 0, "e1"),
        Step(2, "linkedin_invite", 1, "inv"),
        Step(3, "linkedin_message", 2, "dm"),
        Step(4, "email", 3, "e2"),
    ),
)
TUESDAY_10 = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)


def person(row, **kw):
    base = dict(
        name=f"Person{row} Test",
        first_name=f"Person{row}",
        last_name="Test",
        company="Acme",
        title="CTO",
        email=f"p{row}@acme.example",
        linkedin_url=f"https://www.linkedin.com/in/person-{row}",
        sequence="Main",
    )
    return Contact(row=row, **{**base, **kw})


def build_store(contacts=None, approve=True, rules=True, sender=True, sequence=SEQ):
    s = Store()
    s.add_contacts(contacts if contacts is not None else [person(1), person(2)])
    s.set_setting("validation_run", {"at": "2026-11-09T00:00:00Z"})
    s.save_templates(TEMPLATES)
    s.save_sequence(sequence)
    if approve:
        for t in TEMPLATES.values():
            s.approve_template(t.id, approval_hash(t), TUESDAY_10)
    if rules:
        s.set_setting("rules", RULES)
    if sender:
        s.set_setting("sender", {"name": SENDER.name, "company": SENDER.company, "postal_address": SENDER.postal_address})
    return s


@pytest.fixture
def store():
    s = build_store()
    yield s
    s.close()


def days(n):
    return timedelta(days=n)


def rules_obj(**kw):
    return parse_rules({**RULES, **kw})
