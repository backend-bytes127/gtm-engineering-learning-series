import json
import threading
import urllib.error
import urllib.request

import pytest

from hub import fake_slack, send, signing
from hub.__main__ import latest_queue, main


@pytest.fixture
def server():
    recorder = fake_slack.Recorder()
    running = fake_slack.make_server(recorder, echo=True)
    thread = threading.Thread(target=running.serve_forever, daemon=True)
    thread.start()
    yield recorder, f"http://127.0.0.1:{running.server_address[1]}"
    running.shutdown()
    running.server_close()


def post(url, body):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_fake_slack_records_and_fails_on_request(server):
    recorder, url = server
    recorder.reset(fail_next=1)
    assert [post(url + "/slack", b'{"text":"a"}') for _ in range(2)] == [500, 200]
    assert post(url + "/slack", b"nope") == 400
    assert [e["status"] for e in recorder.entries()] == [500, 200]


def test_fake_slack_main_stops_cleanly(monkeypatch, capsys):
    def interrupt(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(fake_slack.ThreadingHTTPServer, "serve_forever", interrupt)
    fake_slack.main(["--port", "0"])
    assert "127.0.0.1" in capsys.readouterr().out


def test_module_entry_point_writes_reports(tmp_path, capsys):
    assert main(["--out", str(tmp_path)]) == 0
    assert "32 of 32" in capsys.readouterr().out
    assert {p.name for p in (tmp_path / "reports").iterdir()} == {"report.md", "outcomes.png", "churn_digest_preview.json"}
    assert len(list((tmp_path / "workflows").glob("*.json"))) == 3


def test_empty_inbox_stops(tmp_path):
    with pytest.raises(SystemExit):
        latest_queue(tmp_path)


def arguments(*values):
    return send.parser().parse_args(list(values))


KEYS = {"GTM_HUB_WEBHOOK_SECRET": "w" * 32, "SLACK_SIGNING_SECRET": "s" * 32}


KINDS = [("signal", signing.GENERIC, "w"), ("pql", signing.GENERIC, "w"), ("click", signing.SLACK, "s")]


@pytest.mark.parametrize("kind,scheme,key", KINDS)
def test_sender_signs_each_kind(kind, scheme, key):
    request = send.build(arguments(kind), KEYS, 1_800_000_000)
    headers = {k.lower(): v for k, v in request.header_items()}
    assert signing.verify(scheme, key * 32, headers, request.data, 1_800_000_000).ok


def test_sender_accepts_a_payload_file(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text(json.dumps({"a": 1}))
    assert send.build(arguments("signal", "--file", str(path)), KEYS, 1).data == b'{"a": 1}'


@pytest.mark.parametrize("argv,environment", [(["signal", "--url", "http://example.com"], KEYS), (["signal"], {})])
def test_sender_refuses_remote_hosts_and_missing_keys(argv, environment):
    with pytest.raises(SystemExit):
        send.build(arguments(*argv), environment, 1)


def test_sender_reports_status_without_printing_secrets(server, monkeypatch, capsys):
    _, url = server
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    assert send.main(["signal", "--url", url]) == 0
    assert send.main(["signal", "--url", "http://127.0.0.1:1"]) == 1
    output = capsys.readouterr().out
    assert "w" * 32 not in output and "could not reach" in output


def test_sender_returns_one_on_an_error_status(server, monkeypatch):
    recorder, url = server
    recorder.reset(fail_next=1)
    monkeypatch.setenv("GTM_HUB_WEBHOOK_SECRET", "w" * 32)
    assert send.main(["signal", "--url", url]) == 1
