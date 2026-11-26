"""Create, drive and remove one throwaway n8n container. It refuses to reuse anything that already exists."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "gtm-hub-e2e"
CONTAINER = "gtm-hub-e2e-n8n"
VOLUME = "gtm-hub-e2e-data"
PATHS = {"signal": "gtm-hub-signal", "pql": "gtm-hub-pql", "click": "gtm-hub-slack-actions"}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run(*command: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(command, capture_output=True, text=True, env=env, timeout=240)
    if check and done.returncode != 0:
        raise RuntimeError(f"{' '.join(command[:4])} failed: {done.stderr[-800:]}")
    return done


def new_secret() -> str:
    return secrets.token_hex(24)


class Box:
    def __init__(self, environment: dict[str, str]) -> None:
        self.port = free_port()
        self.environment = {
            **environment,
            "GTM_HUB_PORT": str(self.port),
            "GTM_HUB_CONTAINER": CONTAINER,
            "GTM_HUB_VOLUME": VOLUME,
        }
        self.created = False

    def compose(self, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        # --env-file /dev/null: a real .env in this folder must never reach a test run.
        command = ["docker", "compose", "-p", PROJECT, "--env-file", os.devnull, "-f", str(ROOT / "docker-compose.yml"), *arguments]
        return run(*command, env={**os.environ, **(env or self.environment)})

    def refuse_to_reuse(self) -> None:
        containers = run("docker", "ps", "-a", "--filter", f"name=^{CONTAINER}$", "-q").stdout.strip()
        volumes = run("docker", "volume", "ls", "--filter", f"name=^{VOLUME}$", "-q").stdout.strip()
        if containers or volumes:
            raise SystemExit(f"{CONTAINER} or {VOLUME} already exists. Check it and remove it yourself, then rerun.")

    def start(self) -> None:
        self.refuse_to_reuse()
        self.created = True
        self.compose("up", "-d")
        self.wait_healthy()

    def exec(self, *command: str, check: bool = True, extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
        return run("docker", "exec", *extra, CONTAINER, *command, check=check)

    def wait_healthy(self) -> None:
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=3) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
            time.sleep(1)
        raise RuntimeError("n8n did not become healthy")

    def wait_webhooks(self) -> None:
        """Healthy comes before the webhooks are registered. An unsigned request must reach the gate (401)."""
        deadline = time.time() + 120
        for route in PATHS:
            while self.post(route, {}, b"{}")[0] != 401:
                if time.time() > deadline:
                    raise RuntimeError(f"webhook for {route} never became ready")
                time.sleep(1)

    def post(self, route: str, headers: dict[str, str], body: bytes, content_type: str | None = None) -> tuple[int, str]:
        content_type = content_type or ("application/x-www-form-urlencoded" if route == "click" else "application/json")
        url = f"http://127.0.0.1:{self.port}/webhook/{PATHS[route]}"
        request = urllib.request.Request(url, data=body, headers={"content-type": content_type, **headers}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, text = response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            status, text = error.code, error.read().decode()
        except OSError as error:
            return 0, str(error)
        try:
            return status, json.loads(text).get("outcome", text[:200])
        except (ValueError, AttributeError):
            return status, text[:200]

    def import_and_publish(self, publish: list[str]) -> None:
        self.exec("n8n", "import:workflow", "--separate", "--input=/workflows")
        for identifier in publish:
            self.exec("n8n", "publish:workflow", f"--id={identifier}")
        self.compose("restart", "n8n")
        self.wait_healthy()
        self.wait_webhooks()

    def static_data(self, identifier: str) -> dict:
        self.exec("n8n", "export:workflow", f"--id={identifier}", "--output=/tmp/export.json")
        exported = json.loads(self.exec("cat", "/tmp/export.json").stdout)
        workflow = exported[0] if isinstance(exported, list) else exported
        data = workflow.get("staticData") or {}
        return json.loads(data) if isinstance(data, str) else data

    def execute(self, identifier: str) -> subprocess.CompletedProcess[str]:
        # The running server already holds the default task-runner port, so the one-off command needs its own.
        return self.exec("n8n", "execute", f"--id={identifier}", check=False, extra=("-e", "N8N_RUNNERS_BROKER_PORT=5699"))

    def logs(self) -> str:
        done = run("docker", "logs", CONTAINER)
        return done.stdout + done.stderr

    def remove(self) -> None:
        if self.created:
            self.compose("down", "--volumes")
