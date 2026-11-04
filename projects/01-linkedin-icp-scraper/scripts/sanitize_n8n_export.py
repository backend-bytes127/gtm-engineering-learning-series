"""Turn a raw `n8n export:workflow` file into a shareable one.

A raw export carries instance metadata (owner project name and e-mail, internal ids, version counters) and
service identifiers (Google spreadsheet id, credential ids). None of that belongs in version control.
This keeps only what is needed to re-import the flow: id, name, nodes, connections, settings (the CLI import needs an id).

    python3 scripts/sanitize_n8n_export.py raw-export.json workflow/linkedin-icp-scraper.workflow.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SHEET_ID = re.compile(r"\b[0-9A-Za-z_-]{40,}\b")  # Google spreadsheet / drive ids are 44 chars
COURSE_FILE = re.compile(r"'?Task \d+ - [\w ]+\.xlsx'?")  # local spreadsheet file name used in a code comment
PLACEHOLDER_SHEET = "YOUR_GOOGLE_SHEET_ID"
PLACEHOLDER_CRED = "REPLACE_AFTER_IMPORT"


def scrub(value: object) -> object:
    """Recursively replace service identifiers; returns a new structure."""
    if isinstance(value, dict):
        out = {k: scrub(v) for k, v in value.items() if k not in {"cachedResultUrl", "cachedResultName"}}
        if "credentials" in out and isinstance(out["credentials"], dict):
            out["credentials"] = {ctype: {"id": PLACEHOLDER_CRED, "name": c.get("name", ctype)}
                                  for ctype, c in out["credentials"].items()}
        return out
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str) and SHEET_ID.fullmatch(value):
        return PLACEHOLDER_SHEET
    if isinstance(value, str):
        return COURSE_FILE.sub("the keyword-matrix spreadsheet", value)
    return value


def sanitize(raw: dict) -> dict:
    wf = raw[0] if isinstance(raw, list) else raw
    return {"id": wf["id"], "name": wf["name"], "nodes": scrub(wf["nodes"]), "connections": wf["connections"],
            "settings": wf.get("settings", {"executionOrder": "v1"})}


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(sanitize(json.loads(src.read_text())), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {dst}")
