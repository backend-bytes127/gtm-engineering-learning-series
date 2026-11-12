"""Step 3: sequence definitions (steps, channel, wait days) and the template library they point to."""

from __future__ import annotations

import json
from pathlib import Path

from . import constants as C
from .models import Sequence, Step, Template


class SequenceError(ValueError):
    pass


def _read_json(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SequenceError(f"{Path(path).name}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise SequenceError(f"{Path(path).name}: expected a JSON object at the top level")
    return data


def parse_sequence(raw: dict) -> Sequence:
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SequenceError("a sequence needs a non-empty name")
    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list):
        raise SequenceError(f"sequence '{name}': steps must be a list")
    steps = []
    for i, s in enumerate(raw_steps, start=1):
        if not isinstance(s, dict) or not isinstance(s.get("template"), str):
            raise SequenceError(f"sequence '{name}' step {i}: needs a template id")
        wait = s.get("wait_days")
        if isinstance(wait, bool) or not isinstance(wait, int):
            raise SequenceError(f"sequence '{name}' step {i}: wait_days must be a whole number")
        steps.append(Step(i, str(s.get("channel", "")), wait, s["template"]))
    return Sequence(name.strip(), tuple(steps))


def load_sequences(path: str | Path) -> list[Sequence]:
    items = _read_json(path).get("sequences")
    if not isinstance(items, list):
        raise SequenceError("expected a 'sequences' list")
    return [parse_sequence(s) for s in items]


def load_templates(path: str | Path) -> dict[str, Template]:
    items = _read_json(path).get("templates")
    if not isinstance(items, list):
        raise SequenceError("expected a 'templates' list")
    out: dict[str, Template] = {}
    for t in items:
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not isinstance(t.get("body"), str):
            raise SequenceError("every template needs a string id and body")
        if t["id"] in out:
            raise SequenceError(f"duplicate template id '{t['id']}'")
        out[t["id"]] = Template(t["id"], str(t.get("channel", "")), t["body"], str(t.get("subject", "")))
    return out


def sequence_errors(seq: Sequence, templates: dict[str, Template]) -> list[str]:
    """Everything wrong with the sequence, as plain sentences. Empty list means it is well-formed."""
    errors: list[str] = []
    if not seq.steps:
        return [f"'{seq.name}' has no steps"]
    if len(seq.steps) > C.MAX_STEPS:
        errors.append(f"'{seq.name}' has {len(seq.steps)} steps; at most {C.MAX_STEPS} are allowed")
    invites = 0
    for s in seq.steps:
        where = f"step {s.position}"
        if s.channel not in C.CHANNELS:
            errors.append(f"{where}: unknown channel '{s.channel}' (use {', '.join(C.CHANNELS)})")
        if not 0 <= s.wait_days <= C.MAX_WAIT_DAYS:
            errors.append(f"{where}: wait_days must be between 0 and {C.MAX_WAIT_DAYS}, got {s.wait_days}")
        t = templates.get(s.template)
        if t is None:
            errors.append(f"{where}: template '{s.template}' does not exist")
        elif s.channel in C.CHANNELS and t.channel != s.channel:
            errors.append(f"{where}: template '{s.template}' is for {t.channel}, but the step is {s.channel}")
        if s.channel == C.LINKEDIN_INVITE:
            invites += 1
            if invites > 1:
                errors.append(f"{where}: only one invite per sequence (a second invite to the same person is spam)")
        if s.channel == C.LINKEDIN_MESSAGE and invites == 0:
            errors.append(f"{where}: a LinkedIn message needs a LinkedIn invite in an earlier step (you can only DM connections)")
    return errors
