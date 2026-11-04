"""Dump the 6 source workbooks (sample-data/) as {extract-node-name: [row dicts]} JSON.

Emulates what the n8n Extract From File nodes emit, so the generated Code nodes can be run locally.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

SESSION = Path(__file__).resolve().parents[1] / "sample-data"
SOURCES = (  # (node name, file, sheet, header row index)
    ("Extract Google Ads", "01_GoogleAds_LeadForm_Export.xlsx", "leads", 0),
    ("Extract Event Delegates", "02_Event_Delegates_and_Scans.xlsx", "Delegate List", 4),
    ("Extract Event Scans", "02_Event_Delegates_and_Scans.xlsx", "Booth Scans", 0),
    ("Extract LinkedIn Form", "03_LinkedIn_LeadGenForm_Export.xlsx", "leads", 0),
    ("Extract Scraped LinkedIn", "04_LinkedIn_Scraped_SalesNav.xlsx", "result", 0),
    ("Extract Apollo", "05_ThirdParty_Apollo_Export.xlsx", "apollo-contacts-export", 0),
    ("Extract ZoomInfo", "06_ThirdParty_ZoomInfo_Export.xlsx", "ZoomInfo Contacts", 0),
)


def main(out: Path) -> None:
    data = {}
    for node, file, sheet, hdr in SOURCES:
        rows = list(openpyxl.load_workbook(SESSION / file, data_only=True)[sheet].iter_rows(values_only=True))
        head = rows[hdr]
        data[node] = [
            {h: str(v) for h, v in zip(head, r, strict=False) if h is not None and v is not None and str(v) != ""}
            for r in rows[hdr + 1:] if any(v is not None for v in r)
        ]
    out.write_text(json.dumps(data))
    print({k: len(v) for k, v in data.items()})


if __name__ == "__main__":
    main(Path(sys.argv[1]))
