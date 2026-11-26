"""Stop requests and data-rights requests are handled by plain code, before (and without) any AI.

The phrase lists below are a regression set, not proof of recall: the rules cover common wording in English, Dutch,
German, French and Spanish only, and will miss other phrasings.
"""

from __future__ import annotations

import pytest

from sequencer import constants as C
from sequencer.ai.guard import is_data_request, is_opt_out
from sequencer.ai.replies import handle_inbound
from sequencer.ai.runtime import get_ai_mode
from sequencer.tests.test_ai_flow import SENDER
from sequencer.tests.test_web_live import MON_10, env, launched, transport, ws  # noqa: F401  (fixtures)

STOP = [
    "please stop",
    "Please stop.",
    "STOP",
    "Stop messaging me",
    "please stop reaching out",
    "Don’t contact me again",  # curly apostrophe, as phones type it
    "Don't message me again",
    "do not email me",
    "No more messages please",
    "unsubscribe",
    "Not interested, thanks",
    "Abmelden",
    "Bitte keine weiteren Nachrichten",
    "Bitte kontaktieren Sie mich nicht mehr",
    "Kein Interesse",
    "Merci de ne plus me contacter",
    "Ne me contactez plus",
    "Désinscrivez-moi",
    "Por favor, no me contacten más",
    "Quiero darme de baja",
    "No me interesa",
    "Geen interesse",
    "Graag geen berichten meer",
]
DATA = [
    "Remove my data",
    "Please delete my personal information",
    "I want you to erase all my details",
    "Bitte löschen Sie meine Daten",
    "Merci de supprimer mes données",
    "Por favor, borren mis datos",
    "Verwijder mijn gegevens",
]
ORDINARY = [
    "We stopped using that tool last year",
    "Please stop by our booth next week",
    "Can we talk on Tuesday?",
    "I can't stop thinking about your point on routing",
    "We need to stop losing leads, tell me more",
    "Sure, what is it about?",
    "Our data team would love a demo",
    "Ich habe Interesse, schicken Sie mir Details",
    "Je suis intéressé, appelons-nous",
    "Me interesa, ¿cuándo hablamos?",
]


@pytest.mark.parametrize("text", STOP)
def test_stop_requests_are_recognised(text):
    assert is_opt_out(text)


@pytest.mark.parametrize("text", DATA)
def test_data_rights_requests_are_recognised(text):
    assert is_data_request(text)


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_replies_are_not_treated_as_stop_or_data_requests(text):
    assert not is_opt_out(text) and not is_data_request(text)


@pytest.mark.parametrize("text", ["please stop", "Remove my data"])
def test_with_the_ai_off_the_contact_is_still_stopped(ws, text):  # noqa: F811
    launched(ws)
    with ws.store() as s:
        assert get_ai_mode(s).mode == "off"
        handle_inbound(s, None, 10, SENDER, "r0001", text, MON_10)
        assert s.contact("r0001").status == C.STOPPED


def test_a_data_request_also_goes_to_a_person(ws):  # noqa: F811
    launched(ws)
    with ws.store() as s:
        assert handle_inbound(s, None, 10, SENDER, "r0001", "Please delete my data", MON_10) == "opted_out"
        escalated = [d for d in s.drafts(kind="reply", contact_key="r0001") if d.status == "escalated"]
        assert len(escalated) == 1 and "data" in escalated[0].reason.lower()
