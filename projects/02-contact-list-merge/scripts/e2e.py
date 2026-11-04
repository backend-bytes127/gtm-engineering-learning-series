#!/usr/bin/env python3
"""End-to-end test against a real n8n container: import -> publish -> submit the form -> compare to golden.

Needs Docker and the stack from infra/ running (`make up` at the repo root). Uses only the standard library.

    python3 scripts/e2e.py [--container gtm-n8n] [--port 5678]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflow" / "contact-list-merge.workflow.json"
FORM_FIELDS = ("01_GoogleAds_LeadForm_Export.xlsx", "02_Event_Delegates_and_Scans.xlsx",
               "03_LinkedIn_LeadGenForm_Export.xlsx", "04_LinkedIn_Scraped_SalesNav.xlsx",
               "05_ThirdParty_Apollo_Export.xlsx", "06_ThirdParty_ZoomInfo_Export.xlsx")


def sh(*cmd: str) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"command failed ({done.returncode}): {' '.join(cmd)}\n{done.stderr.strip()}")
    return done.stdout


def multipart(fields: dict[str, Path]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = b""
    for name, path in fields.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                 "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode()
        body += path.read_bytes() + b"\r\n"
    return body + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def wait_healthy(port: int, seconds: int = 120) -> None:
    for _ in range(seconds // 3):
        try:
            if urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=3).status == 200:
                time.sleep(5)  # webhooks register just after the health endpoint
                return
        except OSError:
            time.sleep(3)
    raise SystemExit("n8n did not become healthy")


def golden() -> list[dict[str, str]]:
    sheet = openpyxl.load_workbook(ROOT / "expected-output" / "Final_Contact_List.xlsx")["Final Output"]
    rows = list(sheet.iter_rows(values_only=True))
    return [{str(h): ("" if v is None else str(v)) for h, v in zip(rows[0], r, strict=False)} for r in rows[1:]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", default="gtm-n8n")
    ap.add_argument("--port", type=int, default=5678)
    args = ap.parse_args()

    reader = ROOT / "scripts" / "read_run.js"
    sh("docker", "cp", str(reader), f"{args.container}:/tmp/read_run.js")
    sh("docker", "cp", str(WORKFLOW), f"{args.container}:/tmp/wf.json")
    sh("docker", "exec", args.container, "n8n", "import:workflow", "--input=/tmp/wf.json")
    sh("docker", "exec", args.container, "n8n", "publish:workflow", "--id=contactListMerge01")
    sh("docker", "restart", args.container)
    wait_healthy(args.port)

    body, ctype = multipart({f"field-{i}": ROOT / "sample-data" / name for i, name in enumerate(FORM_FIELDS)})
    req = urllib.request.Request(f"http://localhost:{args.port}/form/contact-merge-form-0001", data=body,
                                 headers={"Content-Type": ctype}, method="POST")
    for attempt in range(20):  # the health endpoint answers before form webhooks are registered
        try:
            print("form submit ->", urllib.request.urlopen(req, timeout=120).status)
            break
        except urllib.error.HTTPError as err:
            if err.code != 404 or attempt == 19:
                raise
            time.sleep(3)

    run: dict = {"status": "none"}
    for _ in range(20):
        time.sleep(2)
        run = json.loads(sh("docker", "exec", args.container, "node", "/tmp/read_run.js").strip().splitlines()[-1])
        if run["status"] in ("success", "error"):
            break
    print(f"execution {run.get('id')} status={run['status']} rows={len(run.get('final', []))}")
    gold, got = golden(), run.get("final", [])
    diffs = [g["Contact Person Name"] for g, j in zip(gold, got, strict=False) if any(g[k] != j.get(k) for k in g)]
    print(f"differing rows vs golden: {len(diffs)} {diffs[:5]}")
    return 0 if run["status"] == "success" and len(gold) == len(got) and not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
