"""Run the scripted tour against the Python reference, with an in-memory Slack that can fail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hub import pipeline, state
from hub.fake_slack import Recorder
from hub.scenarios import APPROVER, Step, all_steps
from hub.workflows import MAX_TRIES

HANDLERS = {"signal": pipeline.handle_signal, "pql": pipeline.handle_pql, "click": pipeline.handle_interaction}
OFFLINE_SETTINGS = pipeline.Settings(
    webhook_secret="offline-demo-only-webhook-key",
    slack_signing_secret="offline-demo-only-slack-key",
    response_url_prefix="http://fake.invalid/",
    approvers=(APPROVER,),
)


@dataclass(frozen=True)
class Observation:
    step: Step
    status: int
    outcome: str
    posts: tuple[dict[str, Any], ...]  # every attempt the fake Slack saw during this step

    @property
    def matched(self) -> bool:
        return (self.status, self.outcome) == (self.step.status, self.step.outcome)


def run_tour(now: int, settings: pipeline.Settings = OFFLINE_SETTINGS) -> list[Observation]:
    recorder = Recorder()
    states = {"signal": state.State(), "pql": state.State()}  # one per n8n workflow
    requests: dict[str, pipeline.Request] = {}
    observations: list[Observation] = []

    def send(target: str, message: dict[str, Any]) -> bool:
        return any(recorder.post(target, message) == 200 for _ in range(MAX_TRIES))

    for step in all_steps(settings):
        request = requests[step.resend] if step.resend else step.build(now)  # type: ignore[misc]
        requests = {**requests, step.name: request}
        recorder.reset(step.fail_next)
        owner = "signal" if step.route == "signal" else "pql"
        result = HANDLERS[step.route](request, states[owner], settings, send, now)
        states = {**states, owner: result.state}
        observations.append(Observation(step, result.status, result.outcome, recorder.entries()))
    return observations
