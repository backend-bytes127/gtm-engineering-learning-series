"""Generate the importable n8n workflow files from the readable scripts in ``hub/js``."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

JS_DIR = Path(__file__).with_name("js")
SLACK_URL = "={{ $env.GTM_HUB_SLACK_WEBHOOK_URL }}"
REPLY_URL = "={{ $json.target }}"
INBOX_GLOB = "/home/node/.n8n-files/inbox/alert_queue_*.csv"
MAX_TRIES = 3
Node = dict[str, Any]


def script(name: str, with_common: bool = False) -> str:
    parts = ["common.js", name] if with_common else [name]
    return "\n".join((JS_DIR / part).read_text(encoding="utf-8") for part in parts)


def _id(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "gtm-hub/" + "/".join(parts)))


def node(name: str, kind: str, version: float, x: int, y: int, parameters: dict[str, Any], **extra: Any) -> Node:
    return {
        "id": _id(name),
        "name": name,
        "type": f"n8n-nodes-base.{kind}",
        "typeVersion": version,
        "position": [x, y],
        "parameters": parameters,
        **extra,
    }


def code(name: str, source: str, x: int, y: int) -> Node:
    return node(name, "code", 2, x, y, {"jsCode": source})


def webhook(name: str, path: str, x: int, y: int) -> Node:
    parameters = {"httpMethod": "POST", "path": path, "responseMode": "responseNode", "options": {"rawBody": True}}
    return node(name, "webhook", 2, x, y, parameters, webhookId=_id("webhook", path))


def respond(name: str, x: int, y: int) -> Node:
    parameters = {
        "respondWith": "json",
        "responseBody": "={{ JSON.stringify($json.reply) }}",
        "options": {"responseCode": "={{ $json.status }}"},
    }
    return node(name, "respondToWebhook", 1.1, x, y, parameters)


def if_deliver(name: str, expression: str, x: int, y: int) -> Node:
    condition = {
        "id": _id(name, "condition"),
        "leftValue": expression,
        "rightValue": "",
        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
    }
    options = {"caseSensitive": True, "typeValidation": "strict", "version": 2}
    return node(name, "if", 2.2, x, y, {"conditions": {"options": options, "combinator": "and", "conditions": [condition]}})


def http_post(name: str, url: str, x: int, y: int, on_error: str) -> Node:
    """Three tries, five-second timeout, no redirects. The URL is read from the environment at run time."""
    parameters = {
        "method": "POST",
        "url": url,
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.message) }}",
        "options": {
            "timeout": 5000,
            "redirect": {"redirect": {"followRedirects": False}},
            "response": {"response": {"responseFormat": "text"}},
        },
    }
    extra = {"retryOnFail": True, "maxTries": MAX_TRIES, "waitBetweenTries": 1000, "onError": on_error}
    return node(name, "httpRequest", 4.2, x, y, parameters, **extra)


def _links(*edges: tuple[str, int, str]) -> dict[str, Any]:
    connections: dict[str, Any] = {}
    for source, output, target in edges:
        outputs = connections.get(source, {}).get("main", [])
        padded = [*outputs, *[[] for _ in range(output + 1 - len(outputs))]]
        merged = [[*links, {"node": target, "type": "main", "index": 0}] if i == output else links for i, links in enumerate(padded)]
        connections = {**connections, source: {"main": merged}}
    return connections


def _workflow(identifier: str, name: str, nodes: list[Node], connections: dict[str, Any], save: str) -> dict[str, Any]:
    settings = {"executionOrder": "v1", "saveDataSuccessExecution": save, "saveDataErrorExecution": save}
    return {
        "id": identifier,
        "name": name,
        "active": False,
        "nodes": nodes,
        "connections": connections,
        "settings": settings,
        "pinData": {},
    }


def _delivery_branch(prefix: str, gate: str, y: int) -> tuple[list[Node], list[tuple[str, int, str]]]:
    check, send, done, failed, reply = (f"{prefix}{n}" for n in ("Deliver?", "Send to Slack", "Mark delivered", "Dead-letter", "Respond"))
    settle_ok = script("settle_delivered.js", True).replace("$('Gate')", f"$('{gate}')")
    settle_bad = script("settle_failed.js", True).replace("$('Gate')", f"$('{gate}')")
    nodes = [
        if_deliver(check, "={{ $json.deliver }}", 480, y),
        http_post(send, SLACK_URL, 720, y - 80, "continueErrorOutput"),
        code(done, settle_ok, 960, y - 160),
        code(failed, settle_bad, 960, y),
        respond(reply, 1200, y),
    ]
    edges = [
        (gate, 0, check),
        (check, 0, send),
        (check, 1, reply),
        (send, 0, done),
        (send, 1, failed),
        (done, 0, reply),
        (failed, 0, reply),
    ]
    return nodes, edges


def signal_workflow() -> dict[str, Any]:
    start = [webhook("Signal webhook", "gtm-hub-signal", 0, 300), code("Gate", script("signal_gate.js", True), 240, 300)]
    nodes, edges = _delivery_branch("", "Gate", 300)
    links = _links(("Signal webhook", 0, "Gate"), *edges)
    return _workflow("gtmHubSignal0001", "GTM Hub C: signed inbound signal", [*start, *nodes], links, "none")


def pql_workflow() -> dict[str, Any]:
    """Alerts and button clicks share one workflow because n8n static data is private to a workflow."""
    start = [webhook("PQL webhook", "gtm-hub-pql", 0, 240), code("PQL gate", script("pql_gate.js", True), 240, 240)]
    nodes, edges = _delivery_branch("", "PQL gate", 240)
    clicks = [
        webhook("Slack actions webhook", "gtm-hub-slack-actions", 0, 620),
        code("Click gate", script("click_gate.js", True), 240, 620),
        respond("Acknowledge Slack", 480, 620),
        if_deliver("Update message?", "={{ $('Click gate').first().json.deliver }}", 720, 620),
        http_post("Replace Slack message", REPLY_URL, 960, 620, "continueRegularOutput"),
    ]
    # The respond node passes its input on, so the reply to Slack happens before the slower message update.
    click_edges = [
        ("PQL webhook", 0, "PQL gate"),
        ("Slack actions webhook", 0, "Click gate"),
        ("Click gate", 0, "Acknowledge Slack"),
        ("Acknowledge Slack", 0, "Update message?"),
        ("Update message?", 0, "Replace Slack message"),
    ]
    links = _links(*click_edges, *edges)
    return _workflow("gtmHubPql0000001", "GTM Hub B: PQL review with buttons", [*start, *nodes, *clicks], links, "none")


def churn_workflow() -> dict[str, Any]:
    """No error output on the send: a failed execution is the weekly digest's visible dead letter."""
    weekly = {"rule": {"interval": [{"field": "weeks", "triggerAtDay": [1], "triggerAtHour": 8}]}}
    keep = {"alwaysOutputData": True}
    nodes = [
        node("Every Monday 08:00", "scheduleTrigger", 1.2, 0, 200, weekly),
        node("Run by hand", "manualTrigger", 1, 0, 400, {}),
        node("Read queue files", "readWriteFile", 1, 240, 300, {"fileSelector": INBOX_GLOB, "options": {}}, **keep),
        code("Pick latest queue", script("pick_latest.js"), 480, 300),
        node("Parse CSV", "extractFromFile", 1, 720, 300, {"operation": "csv", "options": {}}, **keep),
        code("Build digest", script("churn_digest.js"), 960, 300),
        http_post("Send to Slack", SLACK_URL, 1200, 300, "stopWorkflow"),
    ]
    chain = [n["name"] for n in nodes[2:]]
    edges = [("Every Monday 08:00", 0, chain[0]), ("Run by hand", 0, chain[0]), *((a, 0, b) for a, b in zip(chain, chain[1:]))]
    return _workflow("gtmHubChurn00001", "GTM Hub A: weekly churn-risk digest", nodes, _links(*edges), "all")


FILES = {
    "a-churn-digest.json": churn_workflow,
    "b-pql-review.json": pql_workflow,
    "c-signed-signal.json": signal_workflow,
}


def render(build: Any) -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def write_all(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    targets = [directory / name for name in FILES]
    for target in targets:
        target.write_text(render(FILES[target.name]), encoding="utf-8")
    return targets
