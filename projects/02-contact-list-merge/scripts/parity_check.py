#!/usr/bin/env python3
"""Prove the n8n Code nodes (JavaScript) produce exactly the committed golden output (the Python reference).

Runs the *generated* node source from workflow/contact-list-merge.workflow.json under Node with a minimal
emulation of n8n's `$input` / `$()` API, so it tests what n8n runs, not a parallel copy.

    python3 scripts/parity_check.py          # exit 0 when every row and column is identical
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent


def golden_rows() -> list[dict[str, str]]:
    sheet = openpyxl.load_workbook(ROOT / "expected-output" / "Final_Contact_List.xlsx")["Final Output"]
    rows = list(sheet.iter_rows(values_only=True))
    head = rows[0]
    return [{str(h): ("" if v is None else str(v)) for h, v in zip(head, r, strict=False)} for r in rows[1:]]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sheets = Path(tmp) / "sheets.json"
        subprocess.run([sys.executable, str(ROOT / "n8n" / "dump_sheets.py"), str(sheets)], check=True, capture_output=True)
        run = subprocess.run(["node", str(ROOT / "n8n" / "harness.mjs"),
                              str(ROOT / "workflow" / "contact-list-merge.workflow.json"), str(sheets), tmp],
                             check=True, capture_output=True, text=True)
        print(run.stdout.strip())
        js = json.loads((Path(tmp) / "js_final.json").read_text())
    gold = golden_rows()
    diffs = [(i, g["Contact Person Name"], {k: (g[k], j.get(k)) for k in g if g[k] != j.get(k)})
             for i, (g, j) in enumerate(zip(gold, js, strict=False)) if any(g[k] != j.get(k) for k in g)]
    print(f"golden rows={len(gold)} js rows={len(js)} differing rows={len(diffs)}")
    for d in diffs[:10]:
        print("  ", d)
    return 0 if not diffs and len(gold) == len(js) else 1


if __name__ == "__main__":
    sys.exit(main())
