"""The committed workflow files, compose file and Slack manifest."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from hub import workflows

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", sorted(workflows.FILES))
def test_committed_workflow_equals_the_generator(name):
    assert (ROOT / "workflows" / name).read_text(encoding="utf-8") == workflows.render(workflows.FILES[name])


@pytest.mark.parametrize("name", sorted(workflows.FILES))
def test_workflow_is_inactive_connected_and_takes_urls_from_run_time_values(name):
    flow = workflows.FILES[name]()
    names = {n["name"] for n in flow["nodes"]}
    assert flow["active"] is False and len(names) == len(flow["nodes"])
    for source, outputs in flow["connections"].items():
        assert source in names
        assert all(link["node"] in names for links in outputs["main"] for link in links)
    for item in flow["nodes"]:
        assert "credentials" not in item
        if item["type"].endswith("httpRequest"):
            assert item["parameters"]["url"] in (workflows.SLACK_URL, workflows.REPLY_URL)
    assert "hooks.slack.com/services" not in json.dumps(flow)


def test_webhook_workflows_do_not_keep_execution_payloads():
    for build in (workflows.signal_workflow, workflows.pql_workflow):
        settings = build()["settings"]
        assert settings["saveDataSuccessExecution"] == settings["saveDataErrorExecution"] == "none"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_scripts_are_valid_javascript(tmp_path):
    for build in workflows.FILES.values():
        for item in build()["nodes"]:
            if "jsCode" in item["parameters"]:
                target = tmp_path / "node.js"
                target.write_text(f"async function run() {{\n{item['parameters']['jsCode']}\n}}\n", encoding="utf-8")
                done = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
                assert done.returncode == 0, f"{item['name']}: {done.stderr}"


def test_manifest_asks_for_one_scope_and_has_no_urls():
    manifest = json.loads((ROOT / "slack" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["oauth_config"] == {"scopes": {"bot": ["incoming-webhook"]}}
    assert manifest["display_information"]["name"] == "GTM Signal Hub (demo)"
    assert "http" not in json.dumps(manifest)
    assert manifest["settings"]["socket_mode_enabled"] is False


def test_compose_is_local_only_serialised_and_pinned_like_the_repo_stack():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:${GTM_HUB_PORT:-5690}:5678"' in compose
    assert "N8N_CONCURRENCY_PRODUCTION_LIMIT: ${GTM_HUB_CONCURRENCY:-1}" in compose
    infra = ROOT.parents[1] / "infra" / "docker-compose.yml"
    if infra.exists():
        image = re.search(r"image: (\S+)", infra.read_text(encoding="utf-8")).group(1)
        assert f"image: {image}" in compose


def test_env_example_holds_no_values():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assert all(line.endswith("=") for line in lines if line and not line.startswith("#"))
