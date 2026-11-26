"""Run every path in a real, throwaway n8n, with Slack replaced by a local fake.

    python e2e/run_e2e.py            # needs Docker; removes its own container and volume afterwards
    python e2e/run_e2e.py --keep     # leave them running so you can look around

Secrets are random, live only in memory and the throwaway container, and are never written to a file.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: E402
from n8n_box import Box, new_secret  # noqa: E402

from hub.fake_slack import Recorder, make_server  # noqa: E402
from hub.pipeline import Settings  # noqa: E402
from hub.scenarios import APPROVER  # noqa: E402

WEBHOOK_WORKFLOWS = ["gtmHubSignal0001", "gtmHubPql0000001"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    recorder = Recorder()
    server = make_server(recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake = f"http://host.docker.internal:{server.server_address[1]}/"
    settings = Settings(new_secret(), new_secret(), response_url_prefix=fake, approvers=(APPROVER,))
    inbox = Path(tempfile.mkdtemp(prefix="gtm-hub-inbox-"))
    shutil.copytree(ROOT / "samples" / "inbox", inbox, dirs_exist_ok=True)
    inbox.chmod(0o755)
    box = Box(
        {
            "N8N_ENCRYPTION_KEY": new_secret(),
            "GTM_HUB_WEBHOOK_SECRET": settings.webhook_secret,
            "SLACK_SIGNING_SECRET": settings.slack_signing_secret,
            "SLACK_APPROVER_IDS": APPROVER,
            "GTM_HUB_SLACK_WEBHOOK_URL": f"{fake}slack",
            "GTM_HUB_RESPONSE_URL_PREFIX": fake,
            "GTM_HUB_INBOX": str(inbox),
        }
    )
    started = time.time()
    try:
        box.start()
        box.import_and_publish(WEBHOOK_WORKFLOWS)
        recorder.reset()
        results = checks.run_all(box, recorder, settings, inbox, fake)
        print(f"finished in {time.time() - started:.0f} s on port {box.port}")
        return checks.write_report(results, ROOT / "reports" / "e2e.md")
    finally:
        if args.keep:
            print(f"left running: 127.0.0.1:{box.port}")
        else:
            box.remove()
        server.shutdown()
        shutil.rmtree(inbox, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
