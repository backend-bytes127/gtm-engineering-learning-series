"""The checks run against the live n8n. Expected values come from the Python reference."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from n8n_box import Box

from hub import pipeline, signing, state
from hub.churn import as_of_from_name, parse_queue
from hub.fake_slack import Recorder
from hub.messages import churn_digest
from hub.scenarios import all_steps, sample
from hub.simulate import HANDLERS
from hub.workflows import MAX_TRIES

SAVE_PAUSE = 1.0  # n8n saves static data when an execution ends, which is after it has answered
CHURN = "gtmHubChurn00001"
PARALLEL = 20


@dataclass
class Results:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    steps: list[tuple[str, str, int, str, int, bool]] = field(default_factory=list)
    probes: list[tuple[str, str, str]] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, bool(ok), detail))
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f": {detail}"), flush=True)


def wait_posts(recorder: Recorder, count: int) -> tuple[dict[str, Any], ...]:
    deadline = time.time() + 15
    while len(recorder.entries()) < count and time.time() < deadline:
        time.sleep(0.1)
    time.sleep(SAVE_PAUSE)
    return recorder.entries()


def comparable(entries: tuple[dict[str, Any], ...], fake: str) -> list[tuple[str, int, Any]]:
    """The fake sees a path; the reference sees a target. Turn paths back into targets."""
    return [("slack" if e["path"] == "/slack" else fake + e["path"].lstrip("/"), e["status"], e["message"]) for e in entries]


def run_tour(box: Box, recorder: Recorder, settings: pipeline.Settings, fake: str, results: Results) -> None:
    states = {"signal": state.State(), "pql": state.State()}
    requests: dict[str, pipeline.Request] = {}
    for step in all_steps(settings):
        now = int(time.time())
        request = requests[step.resend] if step.resend else step.build(now)
        requests = {**requests, step.name: request}
        expected = Recorder()
        expected.reset(step.fail_next)

        def send(target: str, message: dict[str, Any]) -> bool:
            return any(expected.post(target, message) == 200 for _ in range(MAX_TRIES))

        owner = "signal" if step.route == "signal" else "pql"
        reference = HANDLERS[step.route](request, states[owner], settings, send, now)
        states = {**states, owner: reference.state}
        recorder.reset(step.fail_next)
        status, outcome = box.post(step.route, dict(request.headers), request.body, step.content_type)
        seen = comparable(wait_posts(recorder, len(expected.entries())), fake)
        wanted = [(e["path"], e["status"], e["message"]) for e in expected.entries()]
        same = (status, outcome) == (step.status, step.outcome) == (reference.status, reference.outcome) and seen == wanted
        results.steps.append((step.route, step.name, status, outcome, len(seen), same))
        results.check(f"{step.route}: {step.name}", same, f"n8n {status} {outcome}, {len(seen)} posts; expected {len(wanted)}")


def check_parser_quirk(box: Box, recorder: Recorder, results: Results) -> None:
    """n8n 2.32.6 parses a body labelled JSON before the workflow starts, even with the raw-body option."""
    before = box.static_data("gtmHubSignal0001")
    recorder.reset()
    status, text = box.post("signal", {}, b"{not json")
    time.sleep(SAVE_PAUSE)
    untouched = box.static_data("gtmHubSignal0001") == before and not recorder.entries()
    results.check(
        "n8n itself rejects malformed JSON labelled as JSON, before the signature gate",
        status == 422 and "Failed to parse" in text and untouched,
        f"{status} {text}",
    )


def signed_signal(settings: pipeline.Settings, event_id: str, offset: int = 0) -> tuple[dict[str, str], bytes]:
    body = json.dumps({**sample("signal.synthetic.json"), "event_id": event_id}).encode()
    return signing.signed_headers(signing.GENERIC, settings.webhook_secret, int(time.time()) + offset, body), body


def check_static_data(box: Box, settings: pipeline.Settings, fake: str, results: Results) -> None:
    saved = box.static_data("gtmHubSignal0001").get("global", {}).get("hub", {})
    reasons = [entry["reason"] for entry in saved.get("deadLetters", [])]
    wanted = ["invalid_json", "invalid_json", "invalid_schema", "delivery_failed"]
    results.check("dead letters are saved with their reasons", reasons == wanted, str(reasons))
    kept = [e["detail"].get("event", {}).get("event_id") for e in saved.get("deadLetters", []) if e["reason"] == "delivery_failed"]
    results.check("a failed delivery keeps the event for repair", kept == ["syn-evt-0002"], str(kept))
    blob = json.dumps(saved)
    clean = all(value not in blob for value in (settings.webhook_secret, settings.slack_signing_secret, fake))
    results.check("saved state holds no secret and no delivery URL", clean)
    pql = box.static_data("gtmHubPql0000001").get("global", {}).get("hub", {})
    statuses = {key: record["status"] for key, record in pql.get("events", {}).items()}
    wanted_status = {"syn-visitor-001:demo-v1": "approved", "syn-visitor-002:demo-v1": "dismissed", "syn-visitor-003:demo-v1": "approved"}
    results.check("decisions are saved", statuses == wanted_status, str(statuses))


def check_restart(box: Box, recorder: Recorder, settings: pipeline.Settings, results: Results) -> None:
    box.compose("restart", "n8n")
    box.wait_healthy()
    box.wait_webhooks()
    recorder.reset()
    answer = box.post("signal", *signed_signal(settings, "syn-evt-0001", -90))
    results.check("dedupe survives an n8n restart", answer == (200, "duplicate") and not recorder.entries(), str(answer))


def probe_concurrency(box: Box, recorder: Recorder, settings: pipeline.Settings, results: Results, label: str) -> None:
    """Measurements, not pass/fail checks: they show what static data can and cannot guarantee."""
    tag = f"syn-probe-{time.time_ns()}"
    time.sleep(SAVE_PAUSE)
    recorder.reset()
    headers, body = signed_signal(settings, f"{tag}-same")
    with ThreadPoolExecutor(PARALLEL) as pool:
        list(pool.map(lambda _: box.post("signal", headers, body), range(PARALLEL)))
    time.sleep(3)
    copies = f"{PARALLEL} copies of one identical request sent at once: Slack posts (1 is correct)"
    results.probes.append((label, copies, str(len(recorder.entries()))))
    recorder.reset()
    names = [f"{tag}-{i:02d}" for i in range(PARALLEL)]
    requests = [signed_signal(settings, name) for name in names]
    with ThreadPoolExecutor(PARALLEL) as pool:
        first = list(pool.map(lambda r: box.post("signal", *r), requests))
    time.sleep(3)
    accepted = sum(answer == (200, "delivered") for answer in first)
    again = []
    for name in names:
        again.append(box.post("signal", *signed_signal(settings, name, -3)))
        time.sleep(SAVE_PAUSE)
    forgotten = sum(answer == (200, "delivered") for answer in again)
    results.probes.append((label, f"{PARALLEL} different events sent at once: delivered", str(accepted)))
    lost = "of those, delivered a second time when re-sent later, because their record was overwritten"
    results.probes.append((label, lost, str(forgotten)))
    leaked = 0
    for i in range(10):
        pair = signed_signal(settings, f"{tag}-b2b-{i}")
        box.post("signal", *pair)
        leaked += box.post("signal", *pair) == (200, "delivered")
        time.sleep(SAVE_PAUSE)
    results.probes.append((label, "replays sent immediately after the first answer, out of 10, that were delivered again", str(leaked)))


def compare_concurrency(box: Box, recorder: Recorder, settings: pipeline.Settings, results: Results) -> None:
    probe_concurrency(box, recorder, settings, results, "limit 1 (this project's default)")
    box.compose("up", "-d", env={**box.environment, "GTM_HUB_CONCURRENCY": "-1"})
    box.wait_healthy()
    box.wait_webhooks()
    probe_concurrency(box, recorder, settings, results, "no limit (n8n's own default)")


def check_churn(box: Box, recorder: Recorder, inbox: Path, results: Results) -> None:
    queue = next(inbox.glob("alert_queue_*.csv"))
    original = queue.read_text(encoding="utf-8")
    today = datetime.now(timezone.utc).date()
    expected = churn_digest(parse_queue(original), as_of_from_name(queue.name), today)
    recorder.reset()
    done = box.execute(CHURN)
    posts = recorder.entries()
    results.check("churn: manual run succeeds", done.returncode == 0, (done.stdout + done.stderr)[-600:])
    results.check("churn: digest equals the Python reference", [p["message"] for p in posts] == [expected], json.dumps(posts)[:600])
    recorder.reset(MAX_TRIES)
    done = box.execute(CHURN)
    tries = len(recorder.entries())
    failed = done.returncode != 0 and tries == MAX_TRIES
    results.check("churn: Slack down fails the run after three tries", failed, f"exit {done.returncode}, {tries} tries")
    header = original.splitlines()[0]
    bad_inputs = {
        "bad amount": original + "9,1,0.5,1,abc,A,b,c,d\n",
        "wrong columns": "a,b\n1,2\n",
        "header only": header + "\n",
    }
    for label, content in bad_inputs.items():
        queue.write_text(content, encoding="utf-8")
        recorder.reset()
        done = box.execute(CHURN)
        results.check(f"churn: {label} posts nothing and fails", done.returncode != 0 and not recorder.entries(), f"exit {done.returncode}")
    queue.rename(inbox / "unrelated.csv")
    recorder.reset()
    done = box.execute(CHURN)
    results.check("churn: empty inbox posts nothing and fails", done.returncode != 0 and not recorder.entries(), f"exit {done.returncode}")
    (inbox / "unrelated.csv").rename(queue)
    queue.write_text(original, encoding="utf-8")


def check_fail_closed(box: Box, recorder: Recorder, settings: pipeline.Settings, results: Results) -> None:
    blank = {**box.environment, "GTM_HUB_WEBHOOK_SECRET": "", "SLACK_SIGNING_SECRET": ""}
    box.compose("up", "-d", env=blank)
    box.wait_healthy()
    recorder.reset()
    headers, body = signed_signal(settings, "syn-after-blank")
    deadline = time.time() + 90
    answer = (0, "")
    while answer[0] != 503 and time.time() < deadline:
        answer = box.post("signal", headers, body)
        time.sleep(1)
    closed = answer == (503, "not_configured") and not recorder.entries()
    results.check("a missing secret rejects requests (fails closed)", closed, str(answer))


def run_all(box: Box, recorder: Recorder, settings: pipeline.Settings, inbox: Path, fake: str) -> Results:
    results = Results()
    run_tour(box, recorder, settings, fake, results)
    check_static_data(box, settings, fake, results)
    check_parser_quirk(box, recorder, results)
    check_restart(box, recorder, settings, results)
    check_churn(box, recorder, inbox, results)
    logs = box.logs()
    clean = settings.webhook_secret not in logs and settings.slack_signing_secret not in logs
    results.check("container logs hold neither signing secret", clean)
    results.check("container logs hold no delivery URL, even after failed sends", fake not in logs)
    compare_concurrency(box, recorder, settings, results)
    check_fail_closed(box, recorder, settings, results)
    return results


def write_report(results: Results, target: Path) -> int:
    passed = sum(ok for _, ok, _ in results.checks)
    lines = [
        "# End-to-end run against n8n 2.32.6",
        "",
        f"Run on {datetime.now(timezone.utc):%Y-%m-%d} (UTC) by `python e2e/run_e2e.py`.",
        "Synthetic payloads; Slack replaced by a local fake.",
        "Nothing here contacted Slack.",
        "",
        f"**{passed} of {len(results.checks)} checks passed.** For each webhook step, the HTTP status, outcome and every message sent",
        "to the fake endpoint had to equal what the Python reference produced for the same signed bytes.",
        "",
        "| Check | Result |",
        "|---|---|",
        *[f"| {name} | {'pass' if ok else 'FAIL'} |" for name, ok, _ in results.checks],
        "",
        "## Concurrency and timing measurements (limits, not passes)",
        "",
        "One machine, one run. The counts vary between runs.",
        "",
        "| n8n concurrency setting | Measurement | Result |",
        "|---|---|---|",
        *[f"| {label} | {name} | {value} |" for label, name, value in results.probes],
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for label, name, value in results.probes:
        print(f"MEASURE [{label}] {name}: {value}")
    print(f"{passed} of {len(results.checks)} checks passed")
    return 0 if passed == len(results.checks) else 1
