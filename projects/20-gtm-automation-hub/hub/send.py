"""Send one signed synthetic request to a hub on this machine.

    python -m hub.send signal
    python -m hub.send pql
    python -m hub.send click --decision dismiss --key syn-visitor-001:demo-v1

Secrets are read from the environment and never printed. Only loopback addresses are accepted.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from hub import signing
from hub.scenarios import APPROVER, sample

ROUTES = {"signal": "gtm-hub-signal", "pql": "gtm-hub-pql", "click": "gtm-hub-slack-actions"}
SAMPLE_FILES = {"signal": "signal.synthetic.json", "pql": "pql_lead.synthetic.json"}
LOOPBACK = ("127.0.0.1", "localhost")


def build(args: argparse.Namespace, environment: Mapping[str, str], now: int) -> urllib.request.Request:
    if urlsplit(args.url).hostname not in LOOPBACK:
        raise SystemExit("only a hub on this machine is allowed (127.0.0.1 or localhost)")
    is_click = args.kind == "click"
    variable = "SLACK_SIGNING_SECRET" if is_click else "GTM_HUB_WEBHOOK_SECRET"
    secret = environment.get(variable, "")
    if len(secret) < signing.MIN_SECRET_LENGTH:
        raise SystemExit(f"set {variable} in your environment first (at least {signing.MIN_SECRET_LENGTH} characters)")
    if is_click:
        payload = {
            **sample("slack_click.synthetic.json"),
            "user": {"id": args.user},
            "actions": [{"action_id": f"pql_{args.decision}", "value": args.key}],
            "response_url": "",  # empty: nothing to update, so nothing is posted back
        }
        body = urlencode({"payload": json.dumps(payload)}).encode()
        scheme, content_type = signing.SLACK, "application/x-www-form-urlencoded"
    else:
        body = args.file.read_bytes() if args.file else json.dumps(sample(SAMPLE_FILES[args.kind])).encode()
        scheme, content_type = signing.GENERIC, "application/json"
    headers = {"content-type": content_type, **signing.signed_headers(scheme, secret, now, body)}
    return urllib.request.Request(f"{args.url.rstrip('/')}/webhook/{ROUTES[args.kind]}", data=body, headers=headers, method="POST")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python -m hub.send", description="Send one signed synthetic request to a local hub")
    result.add_argument("kind", choices=sorted(ROUTES))
    result.add_argument("--url", default="http://127.0.0.1:5690")
    result.add_argument("--file", type=Path, help="your own synthetic JSON payload (signal or pql)")
    result.add_argument("--decision", choices=("approve", "dismiss"), default="approve")
    result.add_argument("--key", default="syn-visitor-001:demo-v1")
    result.add_argument("--user", default=APPROVER)
    return result


def main(argv: list[str] | None = None) -> int:
    request = build(parser().parse_args(argv), os.environ, int(time.time()))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, text = response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        status, text = error.code, error.read().decode()
    except OSError as error:
        print(f"could not reach the hub: {error}")
        return 1
    print(status, text[:300])
    return 0 if status == 200 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
